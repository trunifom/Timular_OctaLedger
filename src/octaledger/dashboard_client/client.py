"""Authenticated local API client, no direct BLE or SQL.

Responsibility
--------------
The only way the dashboard talks to the agent. It

* sends the bearer token **only to loopback addresses** (a misconfigured base URL can never
  leak the token to another host) and never puts it into a URL or a log line,
* translates connection problems into :class:`ApiUnavailableError` ("agent not reachable")
  and API error bodies back into the matching :class:`OctaLedgerError` subclass (by its stable
  code), so GUI code handles failures exactly like the rest of the application,
* uses strict timeouts (a hanging agent must never freeze the GUI) and does **not** retry
  automatically: many calls change data, and a silent second attempt could do it twice.

All methods return plain JSON-like values (dictionaries/lists) exactly as documented in
``docs/SOFTWAREDOKUMENTATION.md`` section 19.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

import requests

from octaledger.api.security import LOOPBACK_NAMES, TOKEN_FILE_NAME, validate_token_format
from octaledger.core.errors import (
    ERROR_CODE_PATTERN,
    ERROR_REGISTRY,
    ApiUnavailableError,
    ConfigurationError,
    OctaLedgerError,
    ValidationError,
)
from octaledger.core.fileio import read_text_limited
from octaledger.core.settings import AgentSettings

logger = logging.getLogger(__name__)

#: Pairing waits for the user (a browser login can take two minutes).
PAIR_TIMEOUT: tuple[float, float] = (3.0, 150.0)

#: (connect, read) timeouts in seconds.
DEFAULT_TIMEOUT: Final = (3.0, 30.0)
_CATALOG_KINDS: Final = ("activities", "projects")
_PREFIX: Final = "/api/v1"


def read_token(token_file: Path) -> str:
    """Read the token the agent created (the dashboard never creates one).

    Raises:
        ConfigurationError: If the file is missing (agent never started) or malformed.
    """
    if not token_file.exists():
        raise ConfigurationError(
            f"Token file {token_file} does not exist",
            user_message=(
                "Es gibt noch kein API-Token. Bitte starten Sie zuerst den OctaLedger-Agenten; "
                "er legt das Token an."
            ),
        )
    return validate_token_format(
        read_text_limited(token_file, max_bytes=1024, error_cls=ConfigurationError).strip()
    )


def _time(value: datetime | None) -> str | None:
    """Serialise an aware datetime (naive ones are a programming error)."""
    if value is None:
        return None
    if value.utcoffset() is None:
        raise ValidationError("Timezone-aware datetime required", details={"value": str(value)})
    return value.isoformat()


def error_from_response(status: int, payload: Any) -> OctaLedgerError:
    """Rebuild the matching :class:`OctaLedgerError` from an API error body.

    Unknown or malformed bodies become a generic error that still names the HTTP status.
    """
    body = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(body, dict):
        return OctaLedgerError(
            f"Unexpected response (HTTP {status})",
            user_message=f"Der Agent hat unerwartet geantwortet (HTTP {status}).",
        )
    code = str(body.get("code", ""))
    message = str(body.get("technical_message") or body.get("message") or f"HTTP {status}")
    kwargs: dict[str, Any] = {
        "user_message": str(body["message"]) if body.get("message") else None,
        "details": body.get("details") if isinstance(body.get("details"), dict) else None,
    }
    error_class = ERROR_REGISTRY.get(code)
    if error_class is not None:
        return error_class(message, **kwargs)
    safe_code = code if ERROR_CODE_PATTERN.match(code) else None
    return OctaLedgerError(message, code=safe_code, **kwargs)


class ApiClient:
    """Client for the OctaLedger local API."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        """Create the client.

        Args:
            base_url: ``http://127.0.0.1:<port>`` (loopback only).
            token: The API token.
            timeout: ``(connect, read)`` timeouts in seconds.
            session: Injectable ``requests.Session`` (tests).

        Raises:
            ConfigurationError: If ``base_url`` is not a plain-http loopback URL or the token
                is malformed.
        """
        parts = urlsplit(base_url)
        host = f"[{parts.hostname}]" if parts.hostname and ":" in parts.hostname else parts.hostname
        if (
            parts.scheme != "http"
            or (host or "").lower() not in LOOPBACK_NAMES
            or parts.port is None
        ):
            raise ConfigurationError(
                "The API client only talks to a loopback http URL with a port",
                user_message=(
                    "Die Adresse der lokalen Schnittstelle ist ungültig. Erlaubt ist nur "
                    "http://127.0.0.1:<Port> (das Token wird nie an fremde Rechner gesendet)."
                ),
                details={"scheme": parts.scheme},
            )
        self._base = f"http://{parts.netloc}"
        self._token = validate_token_format(token)
        self._timeout = timeout
        self._session = session or requests.Session()

    @classmethod
    def from_settings(cls, agent: AgentSettings, data_dir: Path, **kwargs: Any) -> ApiClient:
        """Create a client from the agent settings and the token file in ``data_dir``."""
        host = f"[{agent.host}]" if ":" in agent.host else agent.host
        return cls(f"http://{host}:{agent.port}", read_token(data_dir / TOKEN_FILE_NAME), **kwargs)

    # ------------------------------------------------------------------ transport

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
        timeout: tuple[float, float] | None = None,
    ) -> Any:
        """Send one request and return the decoded JSON body (``None`` for 204).

        Raises:
            ApiUnavailableError: If the agent cannot be reached or does not answer in time.
            OctaLedgerError: The error reported by the API (class chosen by its code).
        """
        headers = {"Authorization": f"Bearer {self._token}"} if authenticated else {}
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            response = self._session.request(
                method,
                f"{self._base}{_PREFIX}{path}",
                json=json,
                params=clean or None,
                headers=headers,
                timeout=timeout or self._timeout,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            # Do not log the exception text verbatim: it may contain the request URL.
            logger.warning("Agent not reachable (%s)", type(exc).__name__)
            raise ApiUnavailableError(
                f"Agent not reachable: {type(exc).__name__}",
                details={"path": path},
            ) from exc
        except requests.RequestException as exc:
            raise ApiUnavailableError(
                f"Request failed: {type(exc).__name__}", details={"path": path}
            ) from exc
        if response.status_code == 204:
            return None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code >= 400:
            raise error_from_response(response.status_code, payload)
        return payload

    def _get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json=body if body is not None else {})

    # --------------------------------------------------------------------- overview

    def health(self) -> dict[str, Any]:
        """Public liveness check (does not need the token)."""
        result: dict[str, Any] = self._request("GET", "/health", authenticated=False)
        return result

    def is_agent_running(self) -> bool:
        """``True`` if the agent answers; never raises for connection problems."""
        try:
            return self.health().get("status") == "ok"
        except OctaLedgerError:
            return False

    def status(self) -> dict[str, Any]:
        """Running session, active tracker and live device states."""
        result: dict[str, Any] = self._get("/status")
        return result

    # ---------------------------------------------------------------------- devices

    def devices(self) -> list[dict[str, Any]]:
        """All devices with calibration and live status."""
        result: list[dict[str, Any]] = self._get("/devices")
        return result

    def register_device(self, alias: str) -> dict[str, Any]:
        """Register a tracker."""
        result: dict[str, Any] = self._post("/devices", {"alias": alias})
        return result

    def rename_device(
        self, device_id: str, alias: str | None = None, color: str | None = None
    ) -> dict[str, Any]:
        """Change a tracker's alias and/or identity colour."""
        body = {k: v for k, v in {"alias": alias, "color": color}.items() if v is not None}
        result: dict[str, Any] = self._request("PATCH", f"/devices/{device_id}", json=body)
        return result

    def remove_device(self, device_id: str) -> None:
        """Remove a device without recorded data."""
        self._request("DELETE", f"/devices/{device_id}")

    def assign_face(
        self, device_id: str, face: int, activity_id: str | None, project_id: str | None = None
    ) -> dict[str, Any]:
        """Assign an activity (and project) to a face."""
        result: dict[str, Any] = self._request(
            "PUT",
            f"/devices/{device_id}/faces/{face}",
            json={"activity_id": activity_id, "project_id": project_id},
        )
        return result

    def clear_face(self, device_id: str, face: int) -> dict[str, Any]:
        """Remove the assignment of a face."""
        result: dict[str, Any] = self._request("DELETE", f"/devices/{device_id}/faces/{face}")
        return result

    def observed_face(self, device_id: str) -> dict[str, Any]:
        """The face most recently seen from the device (``{"face": None}`` if none yet)."""
        result: dict[str, Any] = self._get(f"/devices/{device_id}/observed-face")
        return result

    def set_device_mode(self, device_id: str, mode: str) -> dict[str, Any]:
        """Switch a tracker between ``"time"``, ``"control"`` and ``"music"``."""
        result: dict[str, Any] = self._request(
            "PUT", f"/devices/{device_id}/mode", json={"mode": mode}
        )
        return result

    def assign_action(
        self,
        device_id: str,
        face: int,
        integration_id: str,
        label: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Give a face an action of a connection."""
        result: dict[str, Any] = self._request(
            "PUT",
            f"/devices/{device_id}/actions/{face}",
            json={"integration_id": integration_id, "label": label, "params": params},
        )
        return result

    def clear_action(self, device_id: str, face: int) -> dict[str, Any]:
        """Remove the action of a face."""
        result: dict[str, Any] = self._request("DELETE", f"/devices/{device_id}/actions/{face}")
        return result

    def adapters(self) -> list[dict[str, Any]]:
        """The kinds of connection with their form descriptions."""
        result: list[dict[str, Any]] = self._get("/adapters")
        return result

    def integrations(self) -> list[dict[str, Any]]:
        """All connections (settings and the names of stored secrets)."""
        result: list[dict[str, Any]] = self._get("/integrations")
        return result

    def create_integration(self, kind: str, name: str, values: dict[str, Any]) -> dict[str, Any]:
        """Create a connection (secrets inside ``values`` are stored separately)."""
        result: dict[str, Any] = self._post(
            "/integrations", {"kind": kind, "name": name, "values": values}
        )
        return result

    def update_integration(
        self,
        integration_id: str,
        *,
        name: str | None = None,
        values: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """Change a connection; only the given fields are sent."""
        body = {
            key: value
            for key, value in (("name", name), ("values", values), ("enabled", enabled))
            if value is not None
        }
        result: dict[str, Any] = self._request(
            "PATCH", f"/integrations/{integration_id}", json=body
        )
        return result

    def delete_integration(self, integration_id: str) -> None:
        """Delete a connection."""
        self._request("DELETE", f"/integrations/{integration_id}")

    def check_integration(self, integration_id: str) -> str:
        """Test a connection; returns the message."""
        return str(self._post(f"/integrations/{integration_id}/check")["message"])

    def probe_integration(self, integration_id: str, params: dict[str, Any]) -> str:
        """Run one action right now; returns the message."""
        return str(
            self._post(f"/integrations/{integration_id}/probe", {"params": params})["message"]
        )

    def pair_integration(self, integration_id: str) -> str:
        """Run the one-time pairing; returns the message."""
        # Pairing may wait for the user (for example a browser login), so it gets a long read time.
        result = self._request(
            "POST", f"/integrations/{integration_id}/pair", json={}, timeout=PAIR_TIMEOUT
        )
        return str(result["message"])

    def discover_integration(self, integration_id: str) -> dict[str, list[dict[str, str]]]:
        """List what the target offers to choose from (lights, scenes ...)."""
        items: dict[str, list[dict[str, str]]] = self._post(
            f"/integrations/{integration_id}/discover"
        )["items"]
        return items

    def jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        """History of sent actions, newest first."""
        result: list[dict[str, Any]] = self._get("/jobs", limit=limit)
        return result

    def live_view(self, device_id: str) -> dict[str, Any]:
        """Live position, debounce state, recent movements and effect of one cube."""
        result: dict[str, Any] = self._get(f"/devices/{device_id}/live")
        return result

    def activate_device(self, device_id: str) -> dict[str, Any]:
        """Hand over to this tracker."""
        result: dict[str, Any] = self._post(f"/devices/{device_id}/activate")
        return result

    def connect_device(self, device_id: str) -> None:
        """Start the Bluetooth connection."""
        self._post(f"/devices/{device_id}/connect")

    def disconnect_device(self, device_id: str) -> None:
        """Stop a device on purpose."""
        self._post(f"/devices/{device_id}/disconnect")

    def set_device_address(self, device_id: str, address: str) -> dict[str, Any]:
        """Store the address found by a scan."""
        result: dict[str, Any] = self._post(
            f"/devices/{device_id}/address", {"platform_address": address}
        )
        return result

    def scan(self, seconds: float = 5.0) -> list[dict[str, Any]]:
        """Scan for BLE devices."""
        result: list[dict[str, Any]] = self._post("/scan", {"seconds": seconds})
        return result

    # ---------------------------------------------------------- activities / projects

    @staticmethod
    def _kind(kind: str) -> str:
        if kind not in _CATALOG_KINDS:
            raise ValidationError(f"kind must be one of {_CATALOG_KINDS}, got {kind!r}")
        return kind

    def list_items(self, kind: str, include_archived: bool = False) -> list[dict[str, Any]]:
        """List ``"activities"`` or ``"projects"``."""
        result: list[dict[str, Any]] = self._get(
            f"/{self._kind(kind)}", include_archived=include_archived or None
        )
        return result

    def create_item(self, kind: str, name: str, color: str | None = None) -> dict[str, Any]:
        """Create an activity or project."""
        result: dict[str, Any] = self._post(f"/{self._kind(kind)}", {"name": name, "color": color})
        return result

    def update_item(
        self, kind: str, item_id: str, name: str | None = None, color: str | None = None
    ) -> dict[str, Any]:
        """Rename and/or recolour an activity or project."""
        result: dict[str, Any] = self._request(
            "PATCH", f"/{self._kind(kind)}/{item_id}", json={"name": name, "color": color}
        )
        return result

    def archive_item(self, kind: str, item_id: str, archived: bool = True) -> dict[str, Any]:
        """Archive or restore an activity or project."""
        result: dict[str, Any] = self._post(
            f"/{self._kind(kind)}/{item_id}/archive", {"archived": archived}
        )
        return result

    def delete_item(self, kind: str, item_id: str) -> None:
        """Delete an unused activity or project."""
        self._request("DELETE", f"/{self._kind(kind)}/{item_id}")

    # --------------------------------------------------------------------- tracking

    def start_tracking(
        self, activity_id: str, project_id: str | None = None, note: str | None = None
    ) -> dict[str, Any]:
        """Start a manual session."""
        result: dict[str, Any] = self._post(
            "/tracking/start", {"activity_id": activity_id, "project_id": project_id, "note": note}
        )
        return result

    def stop_tracking(self) -> dict[str, Any]:
        """End the running session."""
        result: dict[str, Any] = self._post("/tracking/stop")
        return result

    def pause_tracking(self) -> dict[str, Any]:
        """Pause."""
        result: dict[str, Any] = self._post("/tracking/pause")
        return result

    def resume_tracking(self) -> dict[str, Any]:
        """Resume."""
        result: dict[str, Any] = self._post("/tracking/resume")
        return result

    # --------------------------------------------------------------------- sessions

    def journal(
        self,
        start: datetime,
        end: datetime,
        *,
        device_id: str | None = None,
        activity_id: str | None = None,
        project_id: str | None = None,
        tag_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Whole sessions overlapping the window, newest first."""
        result: list[dict[str, Any]] = self._get(
            "/sessions",
            start=_time(start),
            end=_time(end),
            device_id=device_id,
            activity_id=activity_id,
            project_id=project_id,
            tag_id=tag_id,
        )
        return result

    def uncertain_sessions(self) -> list[dict[str, Any]]:
        """Sessions awaiting confirmation."""
        result: list[dict[str, Any]] = self._get("/sessions/uncertain")
        return result

    def add_session(
        self,
        activity_id: str,
        start: datetime,
        end: datetime,
        project_id: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Add a back-dated session."""
        result: dict[str, Any] = self._post(
            "/sessions",
            {
                "activity_id": activity_id,
                "start": _time(start),
                "end": _time(end),
                "project_id": project_id,
                "note": note,
            },
        )
        return result

    def correct_session(
        self, session_id: str, changes: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        """Correct a session (datetimes in ``changes`` are serialised)."""
        prepared = {k: _time(v) if isinstance(v, datetime) else v for k, v in changes.items()}
        result: dict[str, Any] = self._post(
            f"/sessions/{session_id}/correct", {"changes": prepared, "reason": reason}
        )
        return result

    def split_session(self, session_id: str, at: datetime, reason: str) -> list[dict[str, Any]]:
        """Split a session in two."""
        result: list[dict[str, Any]] = self._post(
            f"/sessions/{session_id}/split", {"at": _time(at), "reason": reason}
        )
        return result

    def confirm_session(self, session_id: str) -> dict[str, Any]:
        """Confirm an uncertain session."""
        result: dict[str, Any] = self._post(f"/sessions/{session_id}/confirm")
        return result

    def delete_session(self, session_id: str, reason: str) -> None:
        """Delete a session."""
        self._post(f"/sessions/{session_id}/delete", {"reason": reason})

    # ---------------------------------------------------------------------- reports

    def report(
        self,
        start: datetime,
        end: datetime,
        *,
        tz: str | None = None,
        device_id: str | None = None,
        activity_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Report for a window."""
        result: dict[str, Any] = self._get(
            "/reports",
            start=_time(start),
            end=_time(end),
            tz=tz,
            device_id=device_id,
            activity_id=activity_id,
            project_id=project_id,
        )
        return result

    def day_report(self, day: date, **filters: Any) -> dict[str, Any]:
        """Report for one local day (``tz``, ``device_id``, ``activity_id``, ``project_id``)."""
        result: dict[str, Any] = self._get("/reports/day", day=day.isoformat(), **filters)
        return result

    def week_report(self, day: date, **filters: Any) -> dict[str, Any]:
        """Report for the local week containing ``day``."""
        result: dict[str, Any] = self._get("/reports/week", day=day.isoformat(), **filters)
        return result

    # ------------------------------------------------------------------ data / backup

    def export_csv(
        self,
        tz: str = "UTC",
        delimiter: str = ";",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        """Create a CSV export; returns ``filename``, ``rows``, ``size`` and ``content``."""
        result: dict[str, Any] = self._post(
            "/export/csv",
            {"tz": tz, "delimiter": delimiter, "start": _time(start), "end": _time(end)},
        )
        return result

    def create_backup(self) -> dict[str, Any]:
        """Create a JSON backup; returns ``filename``, ``records``, ``size`` and ``content``."""
        result: dict[str, Any] = self._post("/backup")
        return result

    # ------------------------------------------------------------ data management

    def data_overview(self) -> dict[str, Any]:
        """How much is stored (entries, events, cubes, activities ...)."""
        result: dict[str, Any] = self._get("/data/overview")
        return result

    def preview_entries(self, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """What deleting the entries of a period would touch (changes nothing)."""
        result: dict[str, Any] = self._post("/data/entries/preview", _period(start, end))
        return result

    def delete_entries(
        self,
        expected_count: int,
        start: str | None = None,
        end: str | None = None,
        include_events: bool = False,
    ) -> dict[str, Any]:
        """Delete the entries of a period (after an automatic safety backup)."""
        body = _period(start, end)
        body.update(expected_count=expected_count, include_events=include_events)
        result: dict[str, Any] = self._post("/data/entries/delete", body)
        return result

    def factory_reset(self, confirm_text: str, reset_settings: bool = True) -> dict[str, Any]:
        """Delete everything (needs the typed confirmation text)."""
        result: dict[str, Any] = self._post(
            "/data/reset", {"confirm_text": confirm_text, "reset_settings": reset_settings}
        )
        return result

    def remove_device_with_options(self, device_id: str, delete_data: bool) -> dict[str, Any]:
        """Remove a cube; ``delete_data`` also removes everything recorded with it."""
        result: dict[str, Any] = self._post(
            f"/devices/{device_id}/remove", {"delete_data": delete_data}
        )
        return result

    def music_state(self) -> list[dict[str, Any]]:
        """For every music cube: what plays at the moment."""
        result: dict[str, Any] = self._get("/music/state")
        devices: list[dict[str, Any]] = result["devices"]
        return devices

    def read_out(
        self, device_id: str, kind: str = "datasheet", seconds: int = 10, interval_ms: int = 500
    ) -> dict[str, Any]:
        """Read out a connected cube (read only); waits for the result."""
        result: dict[str, Any] = self._request(
            "POST",
            f"/devices/{device_id}/readout",
            json={"kind": kind, "seconds": seconds, "interval_ms": interval_ms},
            timeout=(3.0, float(seconds) + 60.0),
        )
        return result

    def snapshots(self, device_id: str) -> list[dict[str, Any]]:
        """The stored read-outs of a cube, newest first."""
        result: dict[str, Any] = self._get(f"/devices/{device_id}/snapshots")
        items: list[dict[str, Any]] = result["snapshots"]
        return items

    def snapshot(self, snapshot_id: str) -> dict[str, Any]:
        """One stored read-out with its readings."""
        result: dict[str, Any] = self._get(f"/snapshots/{snapshot_id}")
        return result

    def delete_snapshot(self, snapshot_id: str) -> None:
        """Delete a stored read-out."""
        self._request("DELETE", f"/snapshots/{snapshot_id}")

    def music_owners(self) -> list[dict[str, Any]]:
        """Who controls what: per music target the cube that started what plays."""
        result: dict[str, Any] = self._get("/music/owners")
        owners: list[dict[str, Any]] = result["owners"]
        return owners

    def battery(self, device_id: str, days: int = 60) -> dict[str, Any]:
        """Battery summary and stored history of one cube."""
        result: dict[str, Any] = self._get(f"/devices/{device_id}/battery", days=days)
        return result

    def browser_player_state(self) -> dict[str, Any]:
        """The wanted state of the player on the page "Musik-Player"."""
        result: dict[str, Any] = self._get("/music/browser-state")
        return result

    def parse_music(self, text: str) -> dict[str, Any]:
        """Recognise a pasted music link (changes nothing)."""
        result: dict[str, Any] = self._post("/music/parse", {"text": text})
        return result

    def music_settings(self, device_id: str) -> dict[str, Any]:
        """Holder action, stop delay and default volume of a music cube."""
        result: dict[str, Any] = self._get(f"/devices/{device_id}/music")
        return result

    def set_music_settings(
        self, device_id: str, base_action: str, stop_delay_ms: int, default_volume: int
    ) -> dict[str, Any]:
        """Save the behaviour of a music cube."""
        result: dict[str, Any] = self._request(
            "PUT",
            f"/devices/{device_id}/music",
            json={
                "base_action": base_action,
                "stop_delay_ms": stop_delay_ms,
                "default_volume": default_volume,
            },
        )
        return result

    def set_music_title(
        self,
        device_id: str,
        face: int,
        integration_id: str,
        link: str,
        label: str,
        volume: int | None = None,
        options: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Give a face a title from a pasted link."""
        body: dict[str, Any] = {
            "integration_id": integration_id,
            "link": link,
            "label": label,
            "options": options or {},
        }
        if volume is not None:
            body["volume"] = volume
        result: dict[str, Any] = self._request(
            "PUT", f"/devices/{device_id}/music/faces/{face}", json=body
        )
        return result

    def find_targets(self, kind: str, online: bool = False) -> list[dict[str, str]]:
        """Look for the target on the network (``online`` also asks an internet service)."""
        result: dict[str, Any] = self._post(f"/adapters/{kind}/find", {"online": online})
        items: list[dict[str, str]] = result["items"]
        return items

    def render_report(
        self, first: date, last: date, fmt: str = "html", tz: str | None = None
    ) -> dict[str, Any]:
        """A printable report (``html`` text or ``pdf`` as base64)."""
        body: dict[str, Any] = {"first": first.isoformat(), "last": last.isoformat(), "format": fmt}
        if tz:
            body["tz"] = tz
        result: dict[str, Any] = self._post("/reports/render", body)
        return result

    def ics_preview(
        self, content: str, first: date, last: date, tz: str | None = None
    ) -> dict[str, Any]:
        """Read appointments from calendar text as proposals (nothing is booked)."""
        body: dict[str, Any] = {
            "content": content,
            "first": first.isoformat(),
            "last": last.isoformat(),
        }
        if tz:
            body["tz"] = tz
        result: dict[str, Any] = self._post("/import/ics/preview", body)
        return result

    def ics_apply(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Book the confirmed appointments (all or nothing)."""
        result: dict[str, Any] = self._post("/import/ics/apply", {"entries": entries})
        return result

    def tags(self) -> list[dict[str, Any]]:
        """All tags."""
        result: list[dict[str, Any]] = self._get("/tags")
        return result

    def create_tag(self, name: str, color: str | None = None) -> dict[str, Any]:
        """Create a tag."""
        body: dict[str, Any] = {"name": name}
        if color:
            body["color"] = color
        result: dict[str, Any] = self._post("/tags", body)
        return result

    def update_tag(
        self, tag_id: str, name: str | None = None, color: str | None = None
    ) -> dict[str, Any]:
        """Rename or recolour a tag."""
        body = {k: v for k, v in (("name", name), ("color", color)) if v is not None}
        result: dict[str, Any] = self._request("PUT", f"/tags/{tag_id}", json=body)
        return result

    def delete_tag(self, tag_id: str) -> None:
        """Delete a tag."""
        self._request("DELETE", f"/tags/{tag_id}")

    def set_session_tags(self, session_id: str, tag_ids: list[str]) -> list[dict[str, Any]]:
        """Replace the tags of an entry."""
        result: list[dict[str, Any]] = self._request(
            "PUT", f"/sessions/{session_id}/tags", json={"tag_ids": tag_ids}
        )
        return result

    def activity_defaults(self, activity_id: str) -> dict[str, Any]:
        """Default tags and note template of an activity."""
        result: dict[str, Any] = self._get(f"/activities/{activity_id}/defaults")
        return result

    def set_activity_defaults(
        self, activity_id: str, tag_ids: list[str], note_template: str | None
    ) -> dict[str, Any]:
        """Set default tags and note template of an activity."""
        result: dict[str, Any] = self._request(
            "PUT",
            f"/activities/{activity_id}/defaults",
            json={"tag_ids": tag_ids, "note_template": note_template},
        )
        return result

    def project_billing(self, project_id: str) -> dict[str, Any]:
        """Budget, hourly rate and billable flag of a project."""
        result: dict[str, Any] = self._get(f"/projects/{project_id}/billing")
        return result

    def set_project_billing(
        self,
        project_id: str,
        budget_minutes: int | None,
        hourly_rate_cents: int | None,
        billable: bool,
    ) -> dict[str, Any]:
        """Set budget, hourly rate and billable flag of a project."""
        result: dict[str, Any] = self._request(
            "PUT",
            f"/projects/{project_id}/billing",
            json={
                "budget_minutes": budget_minutes,
                "hourly_rate_cents": hourly_rate_cents,
                "billable": billable,
            },
        )
        return result

    def budgets(self) -> list[dict[str, Any]]:
        """Used time, budget share and amount per project with billing information."""
        result: list[dict[str, Any]] = self._get("/reports/budgets")
        return result

    def balance(self, first: date, last: date, tz: str | None = None) -> dict[str, Any]:
        """Target, actual and running balance per local day."""
        result: dict[str, Any] = self._get(
            "/reports/balance", first=first.isoformat(), last=last.isoformat(), tz=tz
        )
        return result

    def schedule(self) -> list[dict[str, Any]]:
        """The target working time per weekday (one entry per valid-from date)."""
        result: list[dict[str, Any]] = self._get("/schedule")
        return result

    def set_schedule(self, valid_from: date, minutes: list[int]) -> list[dict[str, Any]]:
        """Create or replace the schedule that starts on ``valid_from``."""
        result: list[dict[str, Any]] = self._request(
            "PUT", "/schedule", json={"valid_from": valid_from.isoformat(), "minutes": minutes}
        )
        return result

    def delete_schedule(self, valid_from: date) -> list[dict[str, Any]]:
        """Remove one schedule version."""
        result: list[dict[str, Any]] = self._request(
            "DELETE", f"/schedule/{valid_from.isoformat()}"
        )
        return result

    def absences(self) -> list[dict[str, Any]]:
        """All absences."""
        result: list[dict[str, Any]] = self._get("/absences")
        return result

    def add_absence(
        self,
        start: date,
        end: date,
        kind: str,
        target_minutes: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Record an absence."""
        body: dict[str, Any] = {"start": start.isoformat(), "end": end.isoformat(), "kind": kind}
        if target_minutes is not None:
            body["target_minutes"] = target_minutes
        if note:
            body["note"] = note
        result: dict[str, Any] = self._post("/absences", body)
        return result

    def delete_absence(self, absence_id: str) -> None:
        """Remove an absence."""
        self._request("DELETE", f"/absences/{absence_id}")

    def autostart(self) -> dict[str, Any]:
        """Whether OctaLedger starts with Windows (read from the registry)."""
        result: dict[str, Any] = self._get("/system/autostart")
        return result

    def set_autostart(self, enabled: bool) -> dict[str, Any]:
        """Switch "start with Windows" on or off."""
        result: dict[str, Any] = self._request(
            "PUT", "/system/autostart", json={"enabled": enabled}
        )
        return result

    def capabilities(self) -> dict[str, Any]:
        """Which optional extras (tray icon, toast messages) are installed."""
        result: dict[str, Any] = self._get("/system/capabilities")
        return result

    def assign_steps(
        self, device_id: str, face: int, steps: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Give a face a chain of steps."""
        result: dict[str, Any] = self._request(
            "PUT", f"/devices/{device_id}/actions/{face}", json={"steps": steps}
        )
        return result

    def action_chains(self, device_id: str) -> dict[str, list[dict[str, Any]]]:
        """The steps of every face of a device that has an action."""
        result: dict[str, list[dict[str, Any]]] = self._get(f"/devices/{device_id}/chains")
        return result

    def device_buttons(self, device_id: str) -> dict[str, str | None]:
        """The actions of the short and long button press (``None`` = nothing)."""
        result: dict[str, Any] = self._get(f"/devices/{device_id}/buttons")
        buttons: dict[str, str | None] = result["buttons"]
        return buttons

    def set_device_button(self, device_id: str, press: str, action: str) -> dict[str, str | None]:
        """Assign an action to a button press (``none`` clears it)."""
        result: dict[str, Any] = self._request(
            "PUT", f"/devices/{device_id}/buttons/{press}", json={"action": action}
        )
        buttons: dict[str, str | None] = result["buttons"]
        return buttons

    def attention(self) -> dict[str, Any]:
        """Open questions and connections that are lost but still inside the grace period."""
        result: dict[str, Any] = self._get("/attention")
        return result

    def resolve_attention(
        self,
        item_id: str,
        action: str,
        activity_id: str | None = None,
        project_id: str | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        """Answer a question; the allowed actions depend on its kind."""
        body: dict[str, Any] = {"action": action}
        if until is not None:
            body["until"] = _time(until)
        if activity_id is not None:
            body["activity_id"] = activity_id
        if project_id is not None:
            body["project_id"] = project_id
        result: dict[str, Any] = self._post(f"/attention/{item_id}/resolve", body)
        return result

    def dismiss_attention(self, item_id: str) -> dict[str, Any]:
        """Close a question without acting on it."""
        result: dict[str, Any] = self._post(f"/attention/{item_id}/dismiss")
        return result

    def unpair_device(self, device_id: str) -> dict[str, Any]:
        """Stop the connection and forget the Bluetooth address (cube and data stay)."""
        result: dict[str, Any] = self._post(f"/devices/{device_id}/unpair")
        return result

    def reset_settings(self, section: str | None = None) -> dict[str, Any]:
        """Restore default settings of one section (or all)."""
        result: dict[str, Any] = self._post("/settings/reset", {"section": section})
        return result

    def inspect_restore(self, content: str) -> dict[str, Any]:
        """Validate a backup without changing anything."""
        result: dict[str, Any] = self._post("/restore/inspect", {"content": content})
        return result

    def restore(self, content: str, confirm: bool) -> dict[str, Any]:
        """Restore a backup (``confirm`` must be true)."""
        result: dict[str, Any] = self._post("/restore", {"content": content, "confirm": confirm})
        return result

    # --------------------------------------------------------------------- settings

    def get_settings(self) -> dict[str, dict[str, Any]]:
        """Current settings."""
        result: dict[str, dict[str, Any]] = self._get("/settings")
        return result

    def update_settings(self, sections: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Validate and save (partial) settings."""
        result: dict[str, dict[str, Any]] = self._request(
            "PUT", "/settings", json={"settings": sections}
        )
        return result

    # ------------------------------------------------------------------ diagnostics

    def logs(self, limit: int = 200) -> list[str]:
        """The most recent redacted log lines."""
        lines: list[str] = self._get("/diagnostics/logs", limit=limit)["lines"]
        return lines

    def integrity(self) -> dict[str, Any]:
        """Database integrity check result."""
        result: dict[str, Any] = self._get("/diagnostics/integrity")
        return result


def _period(start: str | None, end: str | None) -> dict[str, Any]:
    """Request body for a period (``None`` leaves a side open)."""
    return {"start": start, "end": end}
