"""Attention centre: API, service and the housekeeper thread (AP-36)."""

import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from octaledger.agent.housekeeper import Housekeeper
from octaledger.application.attention_service import AttentionService
from octaledger.core.errors import NotFoundError
from octaledger.domain.attention import AttentionStatus
from octaledger.domain.models import Device, EventKind, RawEvent
from tests.unit.test_api import Env, FakeAgent, make_activity


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path, FakeAgent())


def lose_link(env: Env, minutes_ago: int = 60) -> tuple[str, str]:
    """Run an entry on a device, lose the link ``minutes_ago`` ago, run the watchdog."""
    activity = make_activity(env)
    with env.storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Büro"))
        repos.mappings.assign(device.id, 1, activity)
    tracking = env.context.tracking
    tracking.set_active_device(device.id)
    start = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago + 30)
    for kind, value, at in (
        (EventKind.FACE_CHANGE, 1, start),
        (EventKind.DISCONNECT, None, start + timedelta(minutes=30)),
    ):
        tracking.record_event(
            RawEvent(
                device_id=device.id,
                kind=kind,
                sequence=0,
                connection_id="c",
                raw_value=value,
                received_at=at,
            )
        )
    assert len(tracking.watchdog()) == 1
    return device.id, activity


def test_attention_lists_open_questions_and_waiting_connections(env: Env) -> None:
    assert env.get("/attention").json()["items"] == []
    device_id, _ = lose_link(env)
    body = env.get("/attention").json()
    (item,) = body["items"]
    assert item["kind"] == "gap" and item["status"] == "open"
    assert item["payload"]["device_id"] == device_id and item["payload"]["returned_at"] is None
    assert body["link_lost"] == []  # already ended, so nothing is "waiting" any more


def test_waiting_connection_shows_when_it_will_stop(env: Env) -> None:
    activity = make_activity(env)
    with env.storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Büro"))
        repos.mappings.assign(device.id, 1, activity)
    tracking = env.context.tracking
    tracking.set_active_device(device.id)
    now = datetime.now(timezone.utc)
    for kind, value, at in (
        (EventKind.FACE_CHANGE, 1, now - timedelta(minutes=20)),
        (EventKind.DISCONNECT, None, now - timedelta(minutes=1)),
    ):
        tracking.record_event(
            RawEvent(
                device_id=device.id,
                kind=kind,
                sequence=0,
                connection_id="c",
                raw_value=value,
                received_at=at,
            )
        )
    (waiting,) = env.get("/attention").json()["link_lost"]
    assert waiting["alias"] == "Büro" and waiting["grace_seconds"] == 300
    assert waiting["since"] < waiting["stops_at"]


def test_resolve_through_the_api(env: Env) -> None:
    _, activity = lose_link(env)
    (item,) = env.get("/attention").json()["items"]
    done = env.post(
        f"/attention/{item['id']}/resolve", {"action": "assign", "activity_id": activity}
    )
    assert done.status_code == 200 and done.json()["resolution"] == "assign"
    assert env.get("/attention").json()["items"] == []
    again = env.post(f"/attention/{item['id']}/resolve", {"action": "keep"})
    assert again.status_code == 409  # already answered


def test_resolve_errors_are_clear(env: Env) -> None:
    _, _ = lose_link(env)
    (item,) = env.get("/attention").json()["items"]
    assert env.post(f"/attention/{item['id']}/resolve", {"action": "fly"}).status_code == 422
    assert env.post(f"/attention/{item['id']}/resolve", {"action": "assign"}).status_code == 422
    assert env.post(f"/attention/{'0' * 32}/resolve", {"action": "keep"}).status_code == 404
    assert env.post(f"/attention/{item['id']}/resolve", {"nope": 1}).status_code == 422


def test_dismiss_closes_without_touching_time(env: Env) -> None:
    lose_link(env)
    (item,) = env.get("/attention").json()["items"]
    sessions_before = env.get("/sessions/uncertain").json()
    done = env.post(f"/attention/{item['id']}/dismiss")
    assert done.status_code == 200 and done.json()["status"] == "dismissed"
    assert env.get("/attention").json()["items"] == []
    assert env.get("/sessions/uncertain").json() == sessions_before
    assert env.post(f"/attention/{'0' * 32}/dismiss").status_code == 404


def test_attention_needs_the_token(env: Env) -> None:
    assert env.client.get("/api/v1/attention").status_code == 401


def test_old_open_questions_expire(env: Env) -> None:
    lose_link(env)
    service = AttentionService(
        env.storage, clock=lambda: datetime.now(timezone.utc) + timedelta(days=31)
    )
    assert service.expire_old() == 1 and service.list_open() == []
    assert service.list_recent()[0].status is AttentionStatus.EXPIRED
    with pytest.raises(NotFoundError):
        service.dismiss("0" * 32)


# ---------------------------------------------------------------------- housekeeper


def wait_for(predicate: object, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():  # type: ignore[operator]
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.01)


def test_housekeeper_ticks_at_start_and_periodically() -> None:
    count = 0

    def task() -> None:
        nonlocal count
        count += 1

    keeper = Housekeeper([task], interval=0.01)
    keeper.start()
    keeper.start()  # idempotent
    wait_for(lambda: count >= 3)
    assert keeper.running
    keeper.stop()
    assert not keeper.running


def test_housekeeper_survives_a_failing_task() -> None:
    ran = threading.Event()

    def broken() -> None:
        raise RuntimeError("boom")

    keeper = Housekeeper([broken, ran.set], interval=0.01)
    keeper.start()
    assert ran.wait(5)  # the second task still runs although the first one fails
    keeper.stop()


def test_housekeeper_stops_promptly_despite_a_long_interval() -> None:
    keeper = Housekeeper([lambda: None], interval=60)
    keeper.start()
    started = time.monotonic()
    keeper.stop()
    assert time.monotonic() - started < 2


# ------------------------------------------------------------------ buttons via API


def test_button_assignment_through_the_api(env: Env) -> None:
    with env.storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Büro"))
    path = f"/devices/{device.id}/buttons"
    assert env.get(path).json() == {"buttons": {"short": None, "long": None}}
    done = env.call("PUT", f"{path}/long", json={"action": "stop"})
    assert done.status_code == 200 and done.json()["buttons"]["long"] == "stop"
    assert (
        env.call("PUT", f"{path}/long", json={"action": "none"}).json()["buttons"]["long"] is None
    )
    assert env.call("PUT", f"{path}/double", json={"action": "stop"}).status_code == 422
    assert env.call("PUT", f"{path}/short", json={"action": "boom"}).status_code == 422
    assert env.get(f"/devices/{'0' * 32}/buttons").status_code == 404
