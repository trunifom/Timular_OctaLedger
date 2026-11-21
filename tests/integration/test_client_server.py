"""Integration: the real dashboard client talking to the real API over real HTTP.

A uvicorn server runs in a background thread on a free loopback port. This proves what the
mocked unit tests cannot: that ``requests`` (with its real ``Host`` header), the middleware, the
authentication and the services work together end to end.
"""

from datetime import datetime, timedelta, timezone

import pytest

from octaledger.core.errors import (
    ApiUnavailableError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
)
from octaledger.dashboard_client.client import ApiClient
from tests.conftest import RunningApi, free_port

TOKEN = "i" * 43  # same value as tests.conftest.API_TOKEN
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def test_full_workflow_over_real_http(api_server: RunningApi) -> None:
    client = api_server.client
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


def test_errors_arrive_as_the_right_exception_types(api_server: RunningApi) -> None:
    client, port = api_server.client, api_server.port
    with pytest.raises(NotFoundError):
        client.observed_face("ghost")
    with pytest.raises(NotFoundError):
        client.live_view("ghost")
    with pytest.raises(ConflictError):
        client.create_item("activities", "X")
        client.create_item("activities", "x")
    with pytest.raises(AuthenticationError):
        ApiClient(f"http://127.0.0.1:{port}", "w" * 43).status()


def test_stopped_server_is_reported_as_agent_unavailable(api_server: RunningApi) -> None:
    port = api_server.port
    dead = ApiClient(f"http://127.0.0.1:{free_port()}", TOKEN, timeout=(0.5, 1.0))
    with pytest.raises(ApiUnavailableError):
        dead.status()
    assert not dead.is_agent_running()
    assert port != 0


def test_live_view_over_real_http(api_server: RunningApi) -> None:
    client = api_server.client
    activity = client.create_item("activities", "Meeting")
    device = client.register_device("Würfel")
    client.assign_face(device["id"], 2, activity["id"], None)
    live = client.live_view(device["id"])
    assert live["alias"] == "Würfel" and live["raw_value"] is None and live["recent"] == []
    assert live["faces"]["2"]["activity"]["name"] == "Meeting"
