"""Integration: the real dashboard client talking to the real API over real HTTP.

A uvicorn server runs in a background thread on a free loopback port. This proves what the
mocked unit tests cannot: that ``requests`` (with its real ``Host`` header), the middleware, the
authentication and the services work together end to end.
"""

import socket
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import uvicorn

from octaledger.api.app import create_app
from octaledger.api.context import AppContext
from octaledger.application.catalog_service import CatalogService
from octaledger.application.device_service import DeviceService
from octaledger.application.export_service import ExportService
from octaledger.application.reporting_service import ReportService
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import (
    ApiUnavailableError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
)
from octaledger.core.settings import Settings, SettingsStore
from octaledger.dashboard_client.client import ApiClient
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

TOKEN = "i" * 43
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[ApiClient, int]]:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    port = free_port()
    context = AppContext(
        storage=storage,
        tracking=TrackingService(storage),
        devices=DeviceService(storage),
        catalog=CatalogService(storage),
        reports=ReportService(storage),
        exports=ExportService(storage, exports_dir=tmp_path / "ex", backup_dir=tmp_path / "bk2"),
        settings=SettingsStore(tmp_path / "settings.toml", Settings()),
        token=TOKEN,
        port=port,
    )
    config = uvicorn.Config(create_app(context), host="127.0.0.1", port=port, log_level="warning")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.02)
    try:
        yield ApiClient(f"http://127.0.0.1:{port}", TOKEN), port
    finally:
        uv.should_exit = True
        thread.join(timeout=10)


def test_full_workflow_over_real_http(server: tuple[ApiClient, int]) -> None:
    client, _ = server
    assert client.is_agent_running() and client.health()["api_version"] == 1

    device = client.register_device("Büro")
    meeting = client.create_item("activities", "Meeting")
    code = client.create_item("activities", "Code")
    project = client.create_item("projects", "Alpha")
    client.assign_face(device["id"], 1, meeting["id"])
    client.assign_face(device["id"], 2, code["id"], project["id"])
    assert client.devices()[0]["configured_faces"] == 2 and client.devices()[0]["is_active"]

    started = client.start_tracking(meeting["id"], note="Planung")
    assert started["running"] and client.status()["tracking"]["activity"]["name"] == "Meeting"
    client.pause_tracking()
    client.resume_tracking()
    assert client.stop_tracking()["running"] is False

    added = client.add_session(
        code["id"], NOW - timedelta(hours=5), NOW - timedelta(hours=3), project["id"]
    )
    with pytest.raises(ConflictError):  # overlap: the rule travels through the whole stack
        client.add_session(code["id"], NOW - timedelta(hours=4), NOW - timedelta(hours=2))
    corrected = client.correct_session(
        added["id"], {"ended_at": NOW - timedelta(hours=2, minutes=30)}, "Nachgetragen"
    )
    assert corrected["revision"] == 2
    parts = client.split_session(added["id"], NOW - timedelta(hours=4), "Pause")
    assert len(parts) == 2

    window = (NOW - timedelta(days=1), NOW + timedelta(hours=1))
    assert len(client.journal(*window)) >= 3
    report = client.report(*window, tz="Europe/Zurich")
    assert report["device_seconds"] > 0 and report["by_project"][0]["name"] in {
        "Alpha",
        "Ohne Projekt",
    }
    week = client.week_report(NOW.date(), tz="UTC")
    assert len(week["daily"]) == 7

    csv = client.export_csv("Europe/Zurich", ",")
    assert csv["rows"] >= 3 and csv["content"].startswith("session_id,")
    backup = client.create_backup()
    assert client.inspect_restore(backup["content"])["counts"]["sessions"] >= 3
    restored = client.restore(backup["content"], confirm=True)
    assert restored["restored"]["devices"] == 1

    settings = client.update_settings({"display": {"theme": "dark"}})
    assert (
        settings["display"]["theme"] == "dark"
        and client.get_settings()["display"]["theme"] == "dark"
    )
    assert client.integrity() == {"ok": True, "problems": []}
    assert client.logs(5) == []  # no agent log provider configured in this test


def test_errors_arrive_as_the_right_exception_types(server: tuple[ApiClient, int]) -> None:
    client, port = server
    with pytest.raises(NotFoundError):
        client.observed_face("ghost")
    with pytest.raises(ConflictError):
        client.create_item("activities", "X")
        client.create_item("activities", "x")
    with pytest.raises(AuthenticationError):
        ApiClient(f"http://127.0.0.1:{port}", "w" * 43).status()


def test_stopped_server_is_reported_as_agent_unavailable(server: tuple[ApiClient, int]) -> None:
    _, port = server
    dead = ApiClient(f"http://127.0.0.1:{free_port()}", TOKEN, timeout=(0.5, 1.0))
    with pytest.raises(ApiUnavailableError):
        dead.status()
    assert not dead.is_agent_running()
    assert port != 0
