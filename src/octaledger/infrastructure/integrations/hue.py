"""Philips Hue adapter: switch lights, rooms and scenes through the Hue Bridge in your home network.

Talks to the bridge's local interface (CLIP API v2, ``https://<bridge>/clip/v2``): no cloud, no
account, nothing leaves the home network. A *connection* is the bridge address; the
**application key** is created once by pairing (press the round button on the bridge, then
"Koppeln") and kept as a secret. An *action* switches one lamp, one room (or zone) or recalls
one scene.

Certificate pinning (trust on first use)
----------------------------------------
The bridge uses a certificate signed by its own authority, which a normal check cannot verify.
Instead of switching verification off, pairing **remembers the SHA-256 fingerprint** of the
bridge's certificate (stored in the settings; it is not a secret) and every later request only
talks to a server presenting exactly that certificate. Trust is therefore established once, at
pairing time, on the home network - the same trust as pressing the physical button. Without a
stored fingerprint the adapter refuses to send anything over ``https``.

Retry rule: as in the other web adapters (see :mod:`httpio`) only a request that certainly did
not arrive is retried. Toggling reads the lamp's state first and then sets the opposite; if the
write fails the outcome is unknown and is not repeated.

Limits: no groups other than rooms/zones, no colour (only brightness and warmth), no entertainment
or sensors, no event stream, no automatic bridge discovery (the address is entered by hand; the
Hue cloud discovery service would send data out of the home). Verified against a local fake of
the interface over plain HTTP; the certificate pinning itself was **not** exercised against a real
bridge or a real TLS handshake.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl
from collections.abc import Callable, Mapping
from typing import Any, Final

from requests import Response, Session
from requests.adapters import HTTPAdapter

from octaledger.core.errors import IntegrationConnectionError, IntegrationError, ValidationError
from octaledger.infrastructure.integrations.base import (
    ActionSpec,
    Adapter,
    AdapterSpec,
    FieldSpec,
    PairResult,
)
from octaledger.infrastructure.integrations.httpio import new_session, read_limited, send

_HOST: Final = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?(:\d{1,5})?$")
_UUID: Final = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_FINGERPRINT: Final = re.compile(r"^[0-9A-Fa-f]{64}$")
DEVICE_TYPE: Final = "octaledger#pc"
MAX_LISTED: Final = 200
#: Mirek (the unit Hue uses for colour temperature) allowed range: 6500 K down to 2000 K.
MIREK_MIN: Final = 153
MIREK_MAX: Final = 500

SessionFor = Callable[[str | None], Session]
CertificateFetcher = Callable[[str, int, float], str]


# ------------------------------------------------------------------ certificate pinning


def fingerprint_of(der_certificate: bytes) -> str:
    """The SHA-256 fingerprint of a DER certificate as 64 upper-case hex characters."""
    return hashlib.sha256(der_certificate).hexdigest().upper()


def fetch_fingerprint(host: str, port: int, timeout: float) -> str:
    """Connect once and return the fingerprint of the certificate the server presents.

    The certificate is only *read* here (no verification can be done yet); the caller decides to
    trust it, which is exactly the "first use" of trust on first use.
    """
    pem = ssl.get_server_certificate((host, port), timeout=timeout)
    return fingerprint_of(ssl.PEM_cert_to_DER_cert(pem))


class PinnedAdapter(HTTPAdapter):
    """A transport adapter that only talks to a server with exactly the pinned certificate."""

    def __init__(self, fingerprint: str) -> None:
        """Remember the fingerprint (hex, 64 characters)."""
        self._fingerprint = fingerprint
        super().__init__()

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool = False, **kwargs: Any
    ) -> None:
        """Create the pool manager with the fingerprint assertion switched on."""
        kwargs["assert_fingerprint"] = self._fingerprint
        kwargs["assert_hostname"] = False  # the bridge is addressed by IP; identity is the pin
        super().init_poolmanager(connections, maxsize, block, **kwargs)


def pinned_session(fingerprint: str | None) -> Session:
    """A session whose ``https`` requests are pinned to ``fingerprint`` (if given)."""
    session = new_session()
    if fingerprint:
        session.mount("https://", PinnedAdapter(fingerprint))
    return session


def explain_connect_error(host: str, exc: OSError) -> str:
    """Turn a low-level network error into a German explanation with the next step.

    The raw exception class tells what really happened; "not reachable" alone does not help a
    user who does not know where to look.
    """
    if isinstance(exc, socket.gaierror):
        return (
            f"Der Name „{host}“ lässt sich nicht auflösen. Tragen Sie die **IP-Adresse** "
            "der Bridge ein (z. B. 192.168.1.5), nicht einen Namen."
        )
    if isinstance(exc, ConnectionRefusedError):
        return (
            f"Unter „{host}“ nimmt kein Gerät die Verbindung an. Das ist vermutlich **nicht** die "
            "Hue Bridge – prüfen Sie die IP-Adresse (Hue-App › Einstellungen › Bridges › Info)."
        )
    if isinstance(exc, TimeoutError):
        return (
            f"Unter „{host}“ antwortet nichts (Zeitüberschreitung). Meist ist **die Adresse "
            "falsch** "
            "oder der PC ist **nicht im selben Netz** wie die Bridge (Gastnetz, VPN, anderes "
            "Subnetz, Firewall). Öffnen Sie zur Probe im Browser `http://" + host + "/api/config`: "
            "Antwortet eine Seite mit „bridgeid“, stimmt die Adresse."
        )
    if isinstance(exc, ssl.SSLError):
        return (
            f"Unter „{host}“ antwortet ein Gerät, aber nicht wie eine Hue Bridge (TLS-Fehler). "
            "Bitte die Adresse prüfen."
        )
    return (
        f"Die Hue Bridge unter „{host}“ ist nicht erreichbar ({type(exc).__name__}). "
        "Bitte die Adresse prüfen."
    )


def _split_host(host: str) -> tuple[str, int]:
    name, _, port = host.partition(":")
    return name, int(port) if port else 443


_LIGHT_FIELDS: Final = (
    FieldSpec(
        "state",
        "Zustand",
        kind="choice",
        default="on",
        choices=(("on", "Einschalten"), ("off", "Ausschalten"), ("toggle", "Umschalten")),
        help="Umschalten wechselt bei jedem Senden zwischen an und aus.",
    ),
    FieldSpec(
        "brightness",
        "Helligkeit in % (optional)",
        kind="int",
        minimum=1,
        maximum=100,
        help="Nur beim Einschalten. Leer lassen für die letzte Helligkeit.",
    ),
    FieldSpec(
        "warmth_k",
        "Farbtemperatur in Kelvin (optional)",
        kind="int",
        minimum=2000,
        maximum=6500,
        help="2000 = sehr warm, 6500 = kaltweiß. Leer lassen für die letzte Einstellung.",
    ),
)


SETUP_GUIDE: Final = """\
**Wofür:** Philips-Hue-Lampen, -Räume und -Szenen direkt über die **Bridge** im Heimnetz, ohne Cloud.

1. **Adresse der Bridge** eintragen (IP-Adresse): in der Hue-App unter *Einstellungen → Bridges → Info* oder
   in der Geräteliste Ihres Routers.
2. **Verbindung anlegen.**
3. **Koppeln:** Drücken Sie die **große Taste in der Mitte der Bridge** und klicken Sie **innerhalb von
   30 Sekunden** hier auf **Koppeln**. Erscheint „Taste noch nicht gedrückt“, einfach nochmal versuchen.
4. Mit **Geräte der Verbindung auflisten** wählen Sie Lampen, Räume und Szenen nach Namen.

**Sicherheit:** Beim Koppeln merkt sich OctaLedger den **Fingerabdruck des Zertifikats** der Bridge
(„Vertrauen beim ersten Mal“) und spricht danach nur noch mit genau dieser Bridge.

**Wenn das Koppeln fehlschlägt**
- *„Zeitüberschreitung“ / „antwortet nichts“:* Die **Adresse stimmt meist nicht** oder PC und Bridge sind nicht im
  gleichen Netz. **Probe:** Öffnen Sie im Browser `http://<Adresse>/api/config`. Erscheint Text mit `"bridgeid"`, ist
  die Adresse richtig. Die Adresse finden Sie auch, wenn Sie im Browser `https://discovery.meethue.com` öffnen
  (das fragt Philips, nicht OctaLedger) oder in der Geräteliste Ihres Routers (Name „Philips-hue“).
- PC am **WLAN-Gastnetz** oder per **VPN**? Dann erreicht er die Bridge nicht. Bridge am Router per **Kabel**, PC im selben Heimnetz.
- *„Knopf noch nicht gedrückt“:* Erst die Taste an der Bridge drücken, dann **sofort** (30 Sekunden) auf Koppeln.
- Es sind **keine weiteren Einstellungen in der Hue-App nötig**: Die lokale Schnittstelle der Bridge ist immer aktiv. Eine
  Bridge **v1 (rund)** wird nicht unterstützt, nur die **v2 (eckig)**.
- Zum Üben ohne echte Geräte gibt es die Verbindungsart **Testverbindung (Probelauf)**.
"""  # noqa: E501


class HueAdapter(Adapter):
    """Controls a Hue Bridge (see the module docstring)."""

    spec = AdapterSpec(
        kind="hue",
        title="Philips Hue (Bridge)",
        description=(
            "Schaltet Hue-Lampen, Räume und Szenen direkt über die Bridge in Ihrem Heimnetz, ohne "
            "Cloud. Einmaliges Koppeln per Knopf an der Bridge."
        ),
        setup_guide=SETUP_GUIDE,
        config_fields=(
            FieldSpec(
                "host",
                "Adresse der Bridge",
                required=True,
                placeholder="192.168.1.5",
                help="Die IP-Adresse der Hue Bridge im Heimnetz (zu finden in der Hue-App unter "
                "Einstellungen › Bridges › Info, oder im Router).",
            ),
            FieldSpec(
                "fingerprint",
                "Zertifikat-Fingerabdruck",
                advanced=True,
                help="Wird beim Koppeln automatisch gesetzt (SHA-256 des Bridge-Zertifikats) und "
                "schützt vor einer untergeschobenen Bridge. Nicht von Hand ändern.",
            ),
            FieldSpec(
                "app_key",
                "Anwendungsschlüssel",
                advanced=True,
                kind="password",
                help="Entsteht beim Koppeln automatisch; muss nicht eingegeben werden.",
            ),
        ),
        actions=(
            ActionSpec(
                "light",
                "Lampe schalten",
                "Schaltet eine einzelne Lampe.",
                (
                    FieldSpec(
                        "light_id",
                        "Lampe",
                        required=True,
                        choices_from=("lights",),
                        placeholder="wählen über „Entdecken“",
                        help="Die Kennung der Lampe. „Entdecken“ listet Ihre Lampen mit Namen auf.",
                    ),
                    *_LIGHT_FIELDS,
                ),
                idempotent=False,
            ),
            ActionSpec(
                "room",
                "Raum oder Zone schalten",
                "Schaltet alle Lampen eines Raums oder einer Zone gemeinsam.",
                (
                    FieldSpec(
                        "group_id",
                        "Raum",
                        required=True,
                        choices_from=("rooms",),
                        placeholder="wählen über „Entdecken“",
                        help="Die Kennung der Lampengruppe. „Entdecken“ listet Ihre Räume auf.",
                    ),
                    *_LIGHT_FIELDS,
                ),
                idempotent=False,
            ),
            ActionSpec(
                "scene",
                "Szene aktivieren",
                "Aktiviert eine in der Hue-App angelegte Szene.",
                (
                    FieldSpec(
                        "scene_id",
                        "Szene",
                        required=True,
                        choices_from=("scenes",),
                        placeholder="wählen über „Entdecken“",
                        help="Die Kennung der Szene. „Entdecken“ listet Ihre Szenen auf.",
                    ),
                ),
            ),
        ),
        can_pair=True,
        pair_help=(
            "Drücken Sie den runden Knopf oben auf der Hue Bridge und klicken Sie dann innerhalb "
            "von 30 Sekunden auf „Koppeln“."
        ),
        can_discover=True,
    )

    def __init__(
        self,
        *,
        scheme: str = "https",
        pin: bool | None = None,
        session_for: SessionFor = pinned_session,
        fetch_certificate: CertificateFetcher = fetch_fingerprint,
    ) -> None:
        """Create the adapter.

        Args:
            scheme: ``https`` for a real bridge; tests use ``http`` against a local fake.
            pin: Whether the certificate is pinned (default: exactly when ``scheme`` is ``https``).
            session_for: Builds the session for a fingerprint (replaceable for tests).
            fetch_certificate: Reads the bridge's certificate fingerprint (replaceable for tests).
        """
        self._scheme = scheme
        self._pin = (scheme == "https") if pin is None else pin
        self._session_for = session_for
        self._fetch = fetch_certificate

    # ------------------------------------------------------------------ validation

    def validate_config(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Check the bridge address and a stored fingerprint."""
        config = super().validate_config(values)
        if not _HOST.match(config["host"]):
            raise ValidationError(
                f"Invalid bridge address {config['host']!r}",
                user_message="Die Adresse der Bridge muss ein Name oder eine IP-Adresse sein, "
                "ohne „https://“ und ohne Pfad.",
                details={"field": "host"},
            )
        fingerprint = config.get("fingerprint")
        if fingerprint:
            cleaned = fingerprint.replace(":", "").strip()
            if not _FINGERPRINT.match(cleaned):
                raise ValidationError(
                    "Invalid fingerprint",
                    user_message="Der Zertifikat-Fingerabdruck muss aus 64 Hexadezimal-Zeichen "
                    "bestehen. Am besten per „Koppeln“ neu setzen.",
                    details={"field": "fingerprint"},
                )
            config["fingerprint"] = cleaned.upper()
        return config

    def validate_action(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Check identifiers (they become part of the request path) and the combination."""
        cleaned = super().validate_action(params)
        for name in ("light_id", "group_id", "scene_id"):
            if name in cleaned and not _UUID.match(str(cleaned[name])):
                raise ValidationError(
                    f"Invalid identifier for {name}",
                    user_message="Die Kennung muss aus dem „Entdecken“ der Bridge stammen (Format "
                    "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).",
                    details={"field": name},
                )
        if cleaned["action"] in ("light", "room"):
            cleaned.setdefault("state", "on")
            if cleaned["state"] != "on" and (cleaned.get("brightness") or cleaned.get("warmth_k")):
                raise ValidationError(
                    "Brightness or warmth without switching on",
                    user_message="Helligkeit und Farbtemperatur gibt es nur beim Einschalten.",
                    details={"field": "state"},
                )
        return cleaned

    # ----------------------------------------------------------------- operations

    def pair(self, config: Mapping[str, Any], *, timeout: float) -> PairResult:
        """Create the application key (the bridge's button must have been pressed just before)."""
        host = str(config["host"])
        fingerprint: str | None = None
        if self._pin:
            name, port = _split_host(host)
            try:
                fingerprint = self._fetch(name, port, timeout)
            except OSError as exc:
                raise IntegrationConnectionError(
                    f"Cannot read the bridge certificate: {type(exc).__name__}",
                    user_message=explain_connect_error(name, exc),
                ) from exc
        body = {"devicetype": DEVICE_TYPE, "generateclientkey": True}
        response = self._request(host, fingerprint, "POST", "/api", None, body, timeout)
        status = response.status_code
        answer = _json(response) if status == 200 else None
        response.close()
        first = (
            answer[0] if isinstance(answer, list) and answer and isinstance(answer[0], dict) else {}
        )
        success = first.get("success")
        if isinstance(success, dict) and isinstance(success.get("username"), str):
            config_update = {"fingerprint": fingerprint} if fingerprint else {}
            return PairResult(
                secrets={"app_key": success["username"]},
                config=config_update,
                message="Mit der Hue Bridge gekoppelt.",
            )
        error = first.get("error")
        if isinstance(error, dict) and error.get("type") == 101:
            raise IntegrationError(
                "Link button not pressed",
                user_message="Der Knopf auf der Hue Bridge wurde noch nicht gedrückt. Drücken Sie "
                "ihn und klicken Sie innerhalb von 30 Sekunden erneut auf „Koppeln“.",
            )
        raise IntegrationError(
            f"Pairing failed (HTTP {status})",
            user_message="Das Koppeln mit der Hue Bridge ist fehlgeschlagen. Bitte Adresse prüfen "
            "und es erneut versuchen.",
        )

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """Ask the bridge for its own description (read only)."""
        answer = self._get(config, secrets, "/clip/v2/resource/bridge", timeout)
        data = answer.get("data") if isinstance(answer, dict) else None
        bridge = data[0].get("bridge_id") if isinstance(data, list) and data else None
        return "Die Hue Bridge ist erreichbar" + (f" (Kennung {bridge})." if bridge else ".")

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Switch a lamp or room, or recall a scene."""
        action = str(params["action"])
        if action == "scene":
            path = f"/clip/v2/resource/scene/{params['scene_id']}"
            self._put(config, secrets, path, {"recall": {"action": "active"}}, timeout)
            return "Szene aktiviert."
        resource = "light" if action == "light" else "grouped_light"
        identifier = params["light_id"] if action == "light" else params["group_id"]
        path = f"/clip/v2/resource/{resource}/{identifier}"
        state = str(params.get("state", "on"))
        if state == "toggle":
            current = self._get(config, secrets, path, timeout)
            data = current.get("data") if isinstance(current, dict) else None
            is_on = bool(data[0]["on"]["on"]) if isinstance(data, list) and data else False
            state = "off" if is_on else "on"
        body: dict[str, Any] = {"on": {"on": state == "on"}}
        if state == "on" and params.get("brightness"):
            body["dimming"] = {"brightness": float(params["brightness"])}
        if state == "on" and params.get("warmth_k"):
            mirek = round(1_000_000 / int(params["warmth_k"]))
            body["color_temperature"] = {"mirek": max(MIREK_MIN, min(MIREK_MAX, mirek))}
        self._put(config, secrets, path, body, timeout)
        return "Eingeschaltet." if state == "on" else "Ausgeschaltet."

    def discover(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> dict[str, list[dict[str, str]]]:
        """List lamps, rooms (with the id of their lamp group) and scenes by name."""
        lights = self._items(config, secrets, "light", timeout)
        scenes = self._items(config, secrets, "scene", timeout)
        rooms: list[dict[str, str]] = []
        for room in self._resources(config, secrets, "room", timeout):
            group = next(
                (
                    service.get("rid")
                    for service in room.get("services", [])
                    if isinstance(service, dict) and service.get("rtype") == "grouped_light"
                ),
                None,
            )
            name = _name(room)
            if isinstance(group, str) and name:
                rooms.append({"id": group, "name": name})
        found = {"lights": lights, "rooms": _sorted(rooms), "scenes": scenes}
        return {kind: items for kind, items in found.items() if items}

    # -------------------------------------------------------------------- internals

    def _resources(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], kind: str, timeout: float
    ) -> list[dict[str, Any]]:
        answer = self._get(config, secrets, f"/clip/v2/resource/{kind}", timeout)
        data = answer.get("data") if isinstance(answer, dict) else None
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def _items(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], kind: str, timeout: float
    ) -> list[dict[str, str]]:
        items = [
            {"id": str(item["id"]), "name": _name(item)}
            for item in self._resources(config, secrets, kind, timeout)
            if isinstance(item.get("id"), str) and _name(item)
        ]
        return _sorted(items)

    def _get(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], path: str, timeout: float
    ) -> Any:
        key, fingerprint = self._credentials(config, secrets)
        response = self._request(str(config["host"]), fingerprint, "GET", path, key, None, timeout)
        status = response.status_code
        answer = _json(response) if status == 200 else None
        response.close()
        self._raise_for_status(status)
        return answer

    def _put(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        path: str,
        body: dict[str, Any],
        timeout: float,
    ) -> None:
        key, fingerprint = self._credentials(config, secrets)
        response = self._request(str(config["host"]), fingerprint, "PUT", path, key, body, timeout)
        status = response.status_code
        answer = _json(response) if status in (200, 207) else None
        response.close()
        self._raise_for_status(status)
        errors = answer.get("errors") if isinstance(answer, dict) else None
        if errors:
            description = errors[0].get("description") if isinstance(errors[0], dict) else None
            raise IntegrationError(
                f"The bridge reported an error: {description}",
                user_message="Die Hue Bridge meldet einen Fehler: "
                f"{str(description or 'unbekannt')[:120]}",
            )

    def _credentials(
        self, config: Mapping[str, Any], secrets: Mapping[str, str]
    ) -> tuple[str, str | None]:
        key = secrets.get("app_key")
        if not key:
            raise IntegrationError(
                "Not paired with the bridge",
                user_message="Noch nicht mit der Hue Bridge gekoppelt. Drücken Sie den Knopf "
                "an der Bridge und klicken Sie auf „Koppeln“.",
            )
        fingerprint = config.get("fingerprint")
        if self._pin and not fingerprint:
            raise IntegrationError(
                "No certificate fingerprint stored",
                user_message="Das Zertifikat der Bridge ist noch nicht gespeichert. Bitte erneut "
                "koppeln.",
            )
        return key, fingerprint or None

    def _request(
        self,
        host: str,
        fingerprint: str | None,
        method: str,
        path: str,
        key: str | None,
        body: dict[str, Any] | None,
        timeout: float,
    ) -> Response:
        headers = {"User-Agent": "OctaLedger"}
        if key:
            headers["hue-application-key"] = key
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        return send(
            lambda: self._session_for(fingerprint),
            method,
            f"{self._scheme}://{host}{path}",
            headers=headers,
            data=data,
            timeout=timeout,
            verify=False,  # identity is guaranteed by the pinned fingerprint, not by a CA
        )

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if status in (200, 207):
            return
        if status in (401, 403):
            raise IntegrationError(
                f"HTTP {status}",
                user_message="Die Hue Bridge lehnt den Anwendungsschlüssel ab. Bitte erneut "
                "koppeln.",
            )
        if status == 404:
            raise IntegrationError(
                "HTTP 404",
                user_message="Die Bridge kennt diese Lampe, diesen Raum oder diese Szene nicht. "
                "Bitte über „Entdecken“ neu auswählen.",
            )
        raise IntegrationError(
            f"HTTP {status}",
            user_message=f"Die Hue Bridge hat die Anfrage abgelehnt (HTTP {status}).",
        )


def _json(response: Response) -> Any:
    try:
        return json.loads(read_limited(response))
    except ValueError as exc:
        raise IntegrationError(
            "The bridge sent no valid JSON",
            user_message="Die Hue Bridge hat eine unlesbare Antwort geliefert.",
        ) from exc


def _name(item: Mapping[str, Any]) -> str:
    metadata = item.get("metadata")
    name = metadata.get("name") if isinstance(metadata, dict) else None
    return str(name)[:100] if name else ""


def _sorted(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(items, key=lambda item: item["name"].casefold())[:MAX_LISTED]
