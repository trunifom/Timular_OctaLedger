"""Tests for the HTTP API: auth, host/origin guard, error mapping and every endpoint group."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from octaledger.api.app import create_app
from octaledger.api.context import AppContext
from octaledger.application.catalog_service import CatalogService
from octaledger.application.device_service import DeviceService
from octaledger.application.export_service import ExportService
from octaledger.application.reporting_service import ReportService
from octaledger.application.tracking_service import TrackingService
from octaledger.core.settings import Settings, SettingsStore
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from tests.conftest import FakeAgent

PORT = 8765
TOKEN = "t" * 43
BASE = f"http://127.0.0.1:{PORT}"
V1 = "/api/v1"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime.now(timezone.utc).replace(microsecond=0)


class Env:
    def __init__(self, tmp_path: Path, agent: FakeAgent | None) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.settings_file = tmp_path / "settings.toml"
        tracking = TrackingService(self.storage)
        self.context = AppContext(
            storage=self.storage,
            tracking=tracking,
            devices=DeviceService(self.storage),
            catalog=CatalogService(self.storage),
            reports=ReportService(self.storage),
            exports=ExportService(
                self.storage, exports_dir=tmp_path / "exports", backup_dir=tmp_path / "backups"
            ),
            settings=SettingsStore(self.settings_file, Settings()),
            token=TOKEN,
            port=PORT,
            log_lines=lambda: ["line one", "line two", "line three"],
            agent=agent,
        )
        self.client = TestClient(
            create_app(self.context), base_url=BASE, raise_server_exceptions=False
        )

    def call(self, method: str, path: str, **kwargs: Any) -> Any:
        return self.client.request(method, V1 + path, headers=AUTH, **kwargs)

    def get(self, path: str, **kw: Any) -> Any:
        return self.call("GET", path, **kw)

    def post(self, path: str, body: Any = None, **kw: Any) -> Any:
        return self.call("POST", path, json={} if body is None else body, **kw)


@pytest.fixture
def agent() -> FakeAgent:
    return FakeAgent()


@pytest.fixture
def env(tmp_path: Path, agent: FakeAgent) -> Env:
    return Env(tmp_path, agent)


def make_activity(env: Env, name: str = "Meeting") -> str:
    response = env.post("/activities", {"name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


def iso(delta_hours: float) -> str:
    return (NOW + timedelta(hours=delta_hours)).isoformat()


# ----------------------------------------------------------------- auth and the guard


def test_health_is_public_everything_else_needs_the_token(env: Env) -> None:
    health = env.client.get(f"{V1}/health")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert health.json()["api_version"] == 1
    for path in ("/status", "/devices", "/activities", "/settings", "/diagnostics/logs"):
        response = env.client.get(V1 + path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "OL-API-001"


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer wrong"},
        {"Authorization": "Basic " + TOKEN},
        {"Authorization": TOKEN},
        {"Authorization": "Bearer"},
        {"X-Token": TOKEN},
    ],
)
def test_wrong_or_misplaced_credentials_are_rejected(env: Env, headers: dict[str, str]) -> None:
    assert env.client.get(f"{V1}/status", headers=headers).status_code == 401


def test_token_in_the_url_is_never_accepted(env: Env) -> None:
    assert env.client.get(f"{V1}/status?token={TOKEN}").status_code == 401


def test_correct_token_is_accepted_and_responses_are_not_cached(env: Env) -> None:
    response = env.get("/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    "host", ["evil.example:8765", "127.0.0.1", "127.0.0.1:9999", "localhost.evil.com:8765"]
)
def test_foreign_host_header_is_rejected_even_for_health(env: Env, host: str) -> None:
    response = env.client.get(f"{V1}/health", headers={"Host": host})
    assert response.status_code == 403 and response.json()["error"]["code"] == "OL-API-003"


def test_foreign_origin_is_rejected_loopback_origin_allowed(env: Env) -> None:
    bad = env.client.get(f"{V1}/status", headers={**AUTH, "Origin": "http://evil.example"})
    assert bad.status_code == 403
    assert env.client.get(f"{V1}/status", headers={**AUTH, "Origin": "null"}).status_code == 403
    good = env.client.get(f"{V1}/status", headers={**AUTH, "Origin": "http://localhost:8501"})
    assert good.status_code == 200


def test_interactive_docs_are_disabled(env: Env) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert env.client.get(path, headers=AUTH).status_code == 404


def test_oversized_body_is_rejected(env: Env) -> None:
    response = env.client.post(
        f"{V1}/tracking/stop",
        headers={**AUTH, "Content-Length": str(200 * 1024 * 1024)},
        content=b"x",
    )
    assert response.status_code == 413
    bad = env.client.post(
        f"{V1}/tracking/stop", headers={**AUTH, "Content-Length": "abc"}, content=b""
    )
    assert bad.status_code in (400, 413)


def test_no_get_route_changes_state(env: Env) -> None:
    """Pflichtenheft section 8: state changes never happen through GET."""
    verbs = (
        "start",
        "stop",
        "pause",
        "resume",
        "delete",
        "restore",
        "backup",
        "scan",
        "export",
        "activate",
        "connect",
        "disconnect",
        "confirm",
        "correct",
        "split",
        "archive",
        "address",
    )
    for route in env.context and create_app(env.context).routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if "GET" in methods and not path.endswith(("/health",)):
            assert not any(f"/{verb}" in path for verb in verbs), path


# ------------------------------------------------------------------------ error mapping


def test_not_found_conflict_and_invalid_state_map_to_status_codes(env: Env) -> None:
    assert env.get("/devices/ghost/observed-face").status_code == 404
    assert env.call("PATCH", "/activities/ghost", json={"name": "x"}).status_code == 404
    make_activity(env, "Dup")
    duplicate = env.post("/activities", {"name": "dup"})
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "OL-STATE-002"
    stop = env.post("/tracking/stop")
    assert stop.status_code == 409 and stop.json()["error"]["code"] == "OL-STATE-003"
    assert "keine Zeiterfassung" in stop.json()["error"]["message"]


def test_request_validation_errors_are_uniform_and_name_the_fields(env: Env) -> None:
    response = env.post("/activities", {"nome": "typo"})  # unknown + missing field
    body = response.json()["error"]
    assert response.status_code == 422 and body["code"] == "OL-VALID-001"
    assert "name" in body["details"]["fields"] and "nome" in body["details"]["fields"]
    assert env.post("/activities", {"name": "x" * 500}).status_code == 422
    assert env.call("PUT", "/devices/x/faces/1", json={"activity_id": 5}).status_code == 422


def test_invalid_query_values_are_422(env: Env) -> None:
    assert env.get("/reports/day", params={"day": "not-a-date"}).status_code == 422
    assert (
        env.get("/reports/week", params={"day": "2026-01-05", "week_starts_on": 9}).status_code
        == 422
    )
    assert env.get("/sessions", params={"start": "x", "end": "y"}).status_code == 422


def test_unexpected_errors_become_generic_500_without_internals(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("secret internal detail /home/x")

    monkeypatch.setattr(env.context.tracking, "status", boom)
    response = env.get("/status")
    assert response.status_code == 500
    text = response.text
    assert "secret internal detail" not in text and "Traceback" not in text
    assert response.json()["error"]["code"] == "OL-GENERIC-000"


# --------------------------------------------------------------------------- devices


def test_device_lifecycle_calibration_and_hand_over(env: Env) -> None:
    activity = make_activity(env)
    created = env.post("/devices", {"alias": "Büro"})
    assert created.status_code == 201
    device = created.json()
    assert device["is_active"] and device["configured_faces"] == 0 and not device["has_address"]
    second = env.post("/devices", {"alias": "Zuhause"}).json()
    assert not second["is_active"]
    assert env.post("/devices", {"alias": "büro"}).status_code == 409

    assigned = env.call("PUT", f"/devices/{device['id']}/faces/3", json={"activity_id": activity})
    assert assigned.json()["faces"]["3"]["activity_id"] == activity
    assert (
        env.call(
            "PUT", f"/devices/{device['id']}/faces/9", json={"activity_id": activity}
        ).status_code
        == 422
    )
    assert (
        env.call(
            "PUT", f"/devices/{device['id']}/faces/1", json={"activity_id": "ghost"}
        ).status_code
        == 404
    )
    assert env.call("DELETE", f"/devices/{device['id']}/faces/3").json()["faces"] == {}

    assert env.get(f"/devices/{device['id']}/observed-face").json() == {"face": None}
    assert (
        env.call("PATCH", f"/devices/{device['id']}", json={"alias": "Büro 2"}).json()["alias"]
        == "Büro 2"
    )
    handover = env.post(f"/devices/{second['id']}/activate")
    assert handover.status_code == 200 and handover.json() == {"ended_session": None}
    assert {d["alias"]: d["is_active"] for d in env.get("/devices").json()} == {
        "Büro 2": False,
        "Zuhause": True,
    }
    assert env.call("DELETE", f"/devices/{device['id']}").status_code == 204
    assert [d["alias"] for d in env.get("/devices").json()] == ["Zuhause"]


def test_device_connection_control_scan_and_address(env: Env, agent: FakeAgent) -> None:
    device = env.post("/devices", {"alias": "A"}).json()
    no_address = env.post(f"/devices/{device['id']}/connect")
    assert no_address.status_code == 422 and "Adresse" in no_address.json()["error"]["message"]
    scanned = env.post("/scan", {"seconds": 3})
    assert scanned.json() == [
        {
            "address": "AA:BB",
            "name": "ZEI",
            "rssi": -60,
            "is_candidate": True,
            "looks_like_tracker": True,
            "label": "ZEI (-60 dBm)",
        }
    ]
    stored = env.post(f"/devices/{device['id']}/address", {"platform_address": "AA:BB"})
    assert stored.json()["has_address"] is True
    assert "AA:BB" not in stored.text  # the address itself is never sent back to clients
    assert env.post(f"/devices/{device['id']}/connect").json() == {"started": True}
    assert agent.started == [device["id"]]
    live = env.get("/devices").json()[0]["status"]
    assert live["state"] == "ready" and live["battery_percent"] == 87
    assert env.post(f"/devices/{device['id']}/disconnect").json() == {"stopped": True}
    assert agent.stopped == [device["id"]]
    assert env.post("/devices/ghost/disconnect").status_code == 404
    assert env.post(f"/devices/{device['id']}/address", {"platform_address": ""}).status_code == 422


def test_scan_failure_is_a_clear_502_and_missing_agent_is_503(
    env: Env, agent: FakeAgent, tmp_path: Path
) -> None:
    agent.fail_scan = True
    failed = env.post("/scan", {})
    assert failed.status_code == 502 and failed.json()["error"]["message"] == "Bluetooth ist aus."
    headless = Env(tmp_path / "headless", None)
    unavailable = headless.post("/scan", {})
    assert unavailable.status_code == 503 and unavailable.json()["error"]["code"] == "OL-API-002"
    assert headless.get("/status").json()["agent_running"] is False


# ---------------------------------------------------------------------------- catalog


@pytest.mark.parametrize("kind", ["activities", "projects"])
def test_catalog_lifecycle(env: Env, kind: str) -> None:
    created = env.post(f"/{kind}", {"name": "Eins", "color": "#112233"})
    assert created.status_code == 201 and created.json()["color"] == "#112233"
    item_id = created.json()["id"]
    assert env.post(f"/{kind}", {"name": "Zwei"}).json()["color"].startswith("#")  # auto colour
    assert env.call("PATCH", f"/{kind}/{item_id}", json={"name": "Uno"}).json()["name"] == "Uno"
    assert env.post(f"/{kind}", {"name": "Bad", "color": "red"}).status_code == 422
    archived = env.post(f"/{kind}/{item_id}/archive", {})
    assert archived.json()["archived"] is True
    assert [i["name"] for i in env.get(f"/{kind}").json()] == ["Zwei"]
    assert len(env.get(f"/{kind}", params={"include_archived": True}).json()) == 2
    assert env.post(f"/{kind}/{item_id}/archive", {"archived": False}).json()["archived"] is False
    assert env.call("DELETE", f"/{kind}/{item_id}").status_code == 204
    assert env.call("DELETE", f"/{kind}/{item_id}").status_code == 404


def test_used_activity_cannot_be_deleted_but_can_be_archived(env: Env) -> None:
    activity = make_activity(env)
    env.post("/tracking/start", {"activity_id": activity})
    response = env.call("DELETE", f"/activities/{activity}")
    assert response.status_code == 409 and "archivieren" in response.json()["error"]["message"]
    assert env.post(f"/activities/{activity}/archive", {}).status_code == 200


# --------------------------------------------------------------------------- tracking


def test_manual_tracking_flow_and_status(env: Env) -> None:
    activity = make_activity(env)
    started = env.post("/tracking/start", {"activity_id": activity, "note": "Plan"})
    assert started.status_code == 200 and started.json()["running"] is True
    status = env.get("/status").json()
    assert status["tracking"]["running"]["activity_id"] == activity
    assert status["tracking"]["activity"]["name"] == "Meeting" and status["agent_running"] is True
    paused = env.post("/tracking/pause")
    assert (
        paused.json()["running"] is False
        and env.get("/status").json()["tracking"]["paused"] is True
    )
    assert env.post("/tracking/resume").json()["running"] is True
    assert env.post("/tracking/stop").json()["running"] is False
    assert env.post("/tracking/resume").status_code == 409
    assert env.post("/tracking/start", {"activity_id": "ghost"}).status_code == 404


# --------------------------------------------------------------------------- sessions


def test_session_journal_correct_split_confirm_delete(env: Env) -> None:
    activity = make_activity(env)
    other = make_activity(env, "Code")
    added = env.post(
        "/sessions", {"activity_id": activity, "start": iso(-5), "end": iso(-3), "note": "alt"}
    )
    assert added.status_code == 201
    session_id = added.json()["id"]
    assert (
        env.post(
            "/sessions", {"activity_id": activity, "start": iso(-4), "end": iso(-2)}
        ).status_code
        == 409
    )
    assert (
        env.post(
            "/sessions", {"activity_id": activity, "start": iso(-2), "end": iso(+9)}
        ).status_code
        == 422
    )

    window = {"start": iso(-24), "end": iso(1)}
    journal = env.get("/sessions", params=window).json()
    assert [(e["activity_name"], e["duration_seconds"]) for e in journal] == [("Meeting", 7200)]
    assert env.get("/sessions", params={**window, "activity_id": other}).json() == []

    corrected = env.post(
        f"/sessions/{session_id}/correct",
        {
            "changes": {"ended_at": iso(-2.5), "note": "neu", "activity_id": other},
            "reason": "Falsch",
        },
    )
    assert corrected.status_code == 200 and corrected.json()["revision"] == 2
    assert corrected.json()["activity_id"] == other
    assert (
        env.post(
            f"/sessions/{session_id}/correct", {"changes": {"id": "x"}, "reason": "r"}
        ).status_code
        == 422
    )
    assert (
        env.post(
            f"/sessions/{session_id}/correct", {"changes": {"ended_at": "bogus"}, "reason": "r"}
        ).status_code
        == 422
    )
    assert (
        env.post(
            f"/sessions/{session_id}/correct", {"changes": {"note": "x"}, "reason": " "}
        ).status_code
        == 422
    )

    parts = env.post(f"/sessions/{session_id}/split", {"at": iso(-4), "reason": "Pause"})
    assert parts.status_code == 200 and len(parts.json()) == 2
    assert (
        env.post(f"/sessions/{session_id}/split", {"at": iso(-9), "reason": "x"}).status_code == 422
    )

    second_id = parts.json()[1]["id"]
    assert env.get("/sessions/uncertain").json() == []
    assert env.post(f"/sessions/{second_id}/confirm").json()["quality"] == "confirmed"
    assert env.post(f"/sessions/{second_id}/delete", {"reason": ""}).status_code == 422
    assert env.post(f"/sessions/{second_id}/delete", {"reason": "Testdaten"}).status_code == 204
    assert env.post("/sessions/ghost/confirm").status_code == 404


# ---------------------------------------------------------------------------- reports


def test_reports_day_week_and_window(env: Env) -> None:
    activity = make_activity(env)
    start = (NOW - timedelta(hours=3)).replace(minute=0, second=0)
    env.post(
        "/sessions",
        {
            "activity_id": activity,
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
        },
    )
    window = env.get(
        "/reports",
        params={
            "start": (start - timedelta(hours=1)).isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
            "tz": "UTC",
        },
    )
    body = window.json()
    assert (
        body["device_seconds"] == body["personal_seconds"] == 3600 and body["overlap_seconds"] == 0
    )
    assert body["by_activity"][0]["name"] == "Meeting" and body["by_activity"][0]["fraction"] == 1.0
    today = start.date().isoformat()
    day = env.get("/reports/day", params={"day": today, "tz": "UTC"}).json()
    assert day["device_seconds"] == 3600 and day["daily"][0]["day"] == today
    week = env.get(
        "/reports/week", params={"day": today, "tz": "UTC", "activity_id": activity}
    ).json()
    assert week["device_seconds"] == 3600 and len(week["daily"]) == 7
    assert env.get("/reports/day", params={"day": today, "tz": "Mars/Olympus"}).status_code == 422
    assert env.get("/reports", params={"start": iso(1), "end": iso(0)}).status_code == 422


def test_reports_use_the_display_timezone_from_the_settings(env: Env) -> None:
    env.call("PUT", "/settings", json={"settings": {"display": {"timezone": "Europe/Zurich"}}})
    day = env.get("/reports/day", params={"day": NOW.date().isoformat()}).json()
    assert day["timezone"] == "Europe/Zurich"


# ------------------------------------------------------------------------ data / backup


def test_csv_export_backup_inspect_and_confirmed_restore(env: Env, tmp_path: Path) -> None:
    activity = make_activity(env)
    env.post("/sessions", {"activity_id": activity, "start": iso(-3), "end": iso(-2)})
    csv_response = env.post("/export/csv", {"tz": "Europe/Zurich", "delimiter": ","})
    assert csv_response.status_code == 200
    assert csv_response.json()["rows"] == 1 and csv_response.json()["content"].startswith(
        "session_id,"
    )
    assert (tmp_path / "exports" / csv_response.json()["filename"]).exists()
    assert env.post("/export/csv", {"delimiter": "|"}).status_code == 422

    backup = env.post("/backup").json()
    assert backup["records"] > 0 and (tmp_path / "backups" / backup["filename"]).exists()
    preview = env.post("/restore/inspect", {"content": backup["content"]})
    assert preview.json()["counts"]["sessions"] == 1 and preview.json()["schema_version"] == 1

    env.post("/tracking/start", {"activity_id": activity})  # change data after the backup
    unconfirmed = env.post("/restore", {"content": backup["content"]})
    assert unconfirmed.status_code == 409 and "bestätigen" in unconfirmed.json()["error"]["message"]
    assert env.get("/status").json()["tracking"]["running"] is not None  # still unchanged

    restored = env.post("/restore", {"content": backup["content"], "confirm": True})
    assert restored.status_code == 200 and restored.json()["restored"]["sessions"] == 1
    assert restored.json()["pre_restore_backup"].startswith("octaledger-pre-restore-")
    assert env.get("/status").json()["tracking"]["running"] is None  # the running session is gone


def test_invalid_backups_are_rejected_with_a_clear_message(env: Env) -> None:
    for content in ("", "{not json", '{"format": "other"}'):
        inspect = env.post("/restore/inspect", {"content": content})
        assert inspect.status_code == 422 and inspect.json()["error"]["code"] == "OL-DATA-002"
        assert "keine Daten verändert" in inspect.json()["error"]["message"]
        assert env.post("/restore", {"content": content, "confirm": True}).status_code == 422


# ------------------------------------------------------------------------------ settings


def test_settings_read_partial_update_and_persistence(env: Env) -> None:
    initial = env.get("/settings").json()
    assert initial["display"]["theme"] == "light" and initial["agent"]["port"] == 8765
    updated = env.call(
        "PUT",
        "/settings",
        json={
            "settings": {
                "display": {"theme": "dark", "font_size": "large"},
                "tracking": {"debounce_ms": 450},
            }
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["display"]["theme"] == "dark" and body["display"]["timezone"] == "UTC"  # untouched
    assert body["tracking"]["debounce_ms"] == 450
    assert 'theme = "dark"' in env.settings_file.read_text(encoding="utf-8")  # saved to disk


@pytest.mark.parametrize(
    "payload",
    [
        {"display": {"theme": "neon"}},
        {"display": {"unknown_key": 1}},
        {"nonsense": {}},
        {"agent": {"host": "0.0.0.0"}},
        {"tracking": {"debounce_ms": -5}},
    ],
)
def test_invalid_settings_are_rejected_and_not_applied(env: Env, payload: dict[str, Any]) -> None:
    response = env.call("PUT", "/settings", json={"settings": payload})
    assert response.status_code == 422 and response.json()["error"]["code"] in (
        "OL-CONFIG-001",
        "OL-VALID-001",
    )
    assert env.get("/settings").json()["display"]["theme"] == "light"
    assert not env.settings_file.exists()


# ---------------------------------------------------------------------------- diagnostics


def test_diagnostics_endpoints(env: Env) -> None:
    logs = env.get("/diagnostics/logs", params={"limit": 2}).json()
    assert logs["lines"] == ["line two", "line three"]
    assert env.get("/diagnostics/logs", params={"limit": 0}).status_code == 422
    assert env.get("/diagnostics/integrity").json() == {"ok": True, "problems": []}


def test_live_view_shows_position_calibration_and_effect(env: Env, agent: FakeAgent) -> None:
    activity = make_activity(env, "Meeting")
    device = env.post("/devices", {"alias": "A"}).json()
    env.post(f"/devices/{device['id']}/address", {"platform_address": "AA:BB"})
    env.call("PUT", f"/devices/{device['id']}/faces/3", json={"activity_id": activity})

    idle = env.get(f"/devices/{device['id']}/live").json()  # never started: nothing is invented
    assert idle["state"] is None and idle["raw_value"] is None and idle["recent"] == []
    assert idle["faces"]["3"]["activity"]["name"] == "Meeting"
    assert idle["faces"]["4"] == {"activity": None, "project": None}
    assert sorted(idle["faces"]) == [str(n) for n in range(1, 9)]

    env.post(f"/devices/{device['id']}/connect")
    env.post("/tracking/start", {"activity_id": activity})
    live = env.get(f"/devices/{device['id']}/live").json()
    assert live["state"] == "ready" and live["raw_value"] == 3 and live["pending_value"] is None
    assert live["committed_value"] == 3 and live["debounce_ms"] == 300
    assert [e["kind"] for e in live["recent"]] == ["face_change", "raw"]  # newest first
    assert live["tracking"]["running"]["activity_id"] == activity
    assert env.get("/devices/ghost/live").status_code == 404
