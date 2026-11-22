"""Attention centre: API, service and the housekeeper thread (AP-36)."""

import threading
import time
from datetime import UTC, datetime, timedelta
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
    start = datetime.now(UTC) - timedelta(minutes=minutes_ago + 30)
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
    now = datetime.now(UTC)
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
    service = AttentionService(env.storage, clock=lambda: datetime.now(UTC) + timedelta(days=31))
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


# --------------------------------------------------------- workday questions via API


def test_idle_and_auto_stop_questions_are_answered_through_the_same_endpoint(env: Env) -> None:
    from octaledger.domain.attention import AttentionItem, AttentionKind

    activity = make_activity(env)
    now = datetime.now(UTC)
    with env.storage.transaction() as repos:
        from octaledger.domain.models import Session, SessionSource

        session = repos.sessions.add(
            Session(activity, now - timedelta(hours=2), source=SessionSource.MANUAL)
        )
        idle = repos.attention.add(
            AttentionItem(
                kind=AttentionKind.IDLE,
                created_at=now,
                session_id=session.id,
                payload={"idle_since": (now - timedelta(minutes=30)).isoformat()},
            )
        )
        reminder = repos.attention.add(
            AttentionItem(
                kind=AttentionKind.REMINDER, created_at=now, payload={"reason": "no_timer"}
            )
        )
    assert env.post(f"/attention/{idle.id}/resolve", {"action": "fly"}).status_code == 422
    done = env.post(f"/attention/{idle.id}/resolve", {"action": "discard"})
    assert done.status_code == 200 and done.json()["resolution"] == "discard"
    # a reminder is closed with "dismiss", not answered
    assert env.post(f"/attention/{reminder.id}/resolve", {"action": "keep"}).status_code == 409
    assert env.post(f"/attention/{reminder.id}/dismiss").json()["status"] == "dismissed"


# ------------------------------------------------------- schedule, absences, balance


def test_schedule_absence_and_balance_endpoints(env: Env) -> None:
    assert env.get("/schedule").json() == []
    put = env.call(
        "PUT", "/schedule", json={"valid_from": "2026-01-01", "minutes": [480] * 5 + [0, 0]}
    )
    assert put.status_code == 200 and put.json()[0]["minutes"][0] == 480
    assert (
        env.call("PUT", "/schedule", json={"valid_from": "2026-01-01", "minutes": [1]}).status_code
        == 422
    )
    assert (
        env.call(
            "PUT", "/schedule", json={"valid_from": "2026-01-01", "minutes": [9999] * 7}
        ).status_code
        == 422
    )
    created = env.post(
        "/absences", {"start": "2026-01-06", "end": "2026-01-06", "kind": "vacation"}
    )
    assert created.status_code == 201
    assert (
        env.post(
            "/absences", {"start": "2026-01-06", "end": "2026-01-05", "kind": "sick"}
        ).status_code
        == 422
    )
    assert (
        env.post(
            "/absences", {"start": "2026-01-06", "end": "2026-01-06", "kind": "party"}
        ).status_code
        == 422
    )
    assert len(env.get("/absences").json()) == 1
    result = env.get(
        "/reports/balance", params={"first": "2026-01-05", "last": "2026-01-07", "tz": "UTC"}
    ).json()
    assert result["has_schedule"] is True
    assert [d["target_seconds"] for d in result["days"]] == [28800, 0, 28800]
    assert result["days"][1]["reason"] == "Ferien"
    assert (
        env.get(
            "/reports/balance", params={"first": "2026-01-07", "last": "2026-01-05"}
        ).status_code
        == 422
    )
    assert env.call("DELETE", f"/absences/{created.json()['id']}").status_code == 204
    assert env.call("DELETE", f"/absences/{created.json()['id']}").status_code == 404
    assert env.call("DELETE", "/schedule/2026-01-01").json() == []


# ------------------------------------------------------------- tags and billing (API)


def test_tag_billing_and_budget_endpoints(env: Env) -> None:
    activity = make_activity(env)
    project = env.post("/projects", {"name": "Alpha"}).json()["id"]
    tag = env.post("/tags", {"name": "Kunde", "color": "#112233"})
    assert tag.status_code == 201
    assert env.post("/tags", {"name": "kunde"}).status_code == 409
    assert env.post("/tags", {"name": "x", "color": "rot"}).status_code == 422
    tag_id = tag.json()["id"]
    assert env.call("PUT", f"/tags/{tag_id}", json={"name": "Kunde A"}).json()["name"] == "Kunde A"
    default = env.call(
        "PUT",
        f"/activities/{activity}/defaults",
        json={"tag_ids": [tag_id], "note_template": "Ziel:"},
    ).json()
    assert default["note_template"] == "Ziel:" and default["tags"][0]["id"] == tag_id
    assert (
        env.call(
            "PUT", f"/activities/{activity}/defaults", json={"tag_ids": ["0" * 32]}
        ).status_code
        == 404
    )
    billing = env.call(
        "PUT",
        f"/projects/{project}/billing",
        json={"budget_minutes": 600, "hourly_rate_cents": 9000, "billable": True},
    )
    assert billing.status_code == 200 and billing.json()["billable"] is True
    assert (
        env.call("PUT", f"/projects/{project}/billing", json={"budget_minutes": 0}).status_code
        == 422
    )
    assert env.get(f"/projects/{project}/billing").json()["hourly_rate_cents"] == 9000
    started = env.post("/tracking/start", {"activity_id": activity, "project_id": project}).json()
    assert env.get("/reports/budgets").json()[0]["name"] == "Alpha"
    tags = env.call("PUT", f"/sessions/{started['id']}/tags", json={"tag_ids": [tag_id]}).json()
    assert [t["name"] for t in tags] == ["Kunde A"]
    now = datetime.now(UTC)
    journal = env.get(
        "/sessions",
        params={
            "start": (now - timedelta(days=1)).isoformat(),
            "end": (now + timedelta(days=1)).isoformat(),
            "tag_id": tag_id,
        },
    ).json()
    assert journal[0]["tags"] == ["Kunde A"] and journal[0]["billable"] is True
    assert env.call("DELETE", f"/tags/{tag_id}").status_code == 204
    assert env.call("DELETE", f"/tags/{tag_id}").status_code == 404


# ------------------------------------------------------------------ bridge search (API)


def test_find_endpoint_searches_only_for_adapters_that_can(env: Env, tmp_path: Path) -> None:
    from octaledger.application.integration_service import IntegrationService
    from octaledger.core.secrets import SecretStore
    from octaledger.infrastructure.integrations.hue import HueAdapter

    online_asked: list[bool] = []

    def cloud(_t: float) -> list[dict[str, str]]:
        online_asked.append(True)
        return [{"id": "c", "address": "192.168.1.9", "name": "Cloud"}]

    env.context.integrations = IntegrationService(
        env.storage,
        SecretStore(tmp_path / "s3.json"),
        {
            "hue": HueAdapter(
                mdns_finder=lambda _t: [{"id": "m", "address": "192.168.1.5", "name": "Lokal"}],
                cloud_finder=cloud,
            )
        },
    )
    local = env.post("/adapters/hue/find", {})
    assert local.status_code == 200 and [i["address"] for i in local.json()["items"]] == [
        "192.168.1.5"
    ]
    assert online_asked == []
    both = env.post("/adapters/hue/find", {"online": True}).json()["items"]
    assert [i["address"] for i in both] == ["192.168.1.5", "192.168.1.9"]
    assert env.post("/adapters/nope/find", {}).status_code == 422
    assert env.post("/adapters/hue/find", {"online": "vielleicht"}).status_code == 422


# ----------------------------------------------------------------- action chains (API)


def test_chain_endpoints(env: Env) -> None:
    integrations = env.context.integrations
    assert integrations is not None
    lamp = integrations.create("fake", "Lampe", {"host": "h", "password": "richtig"}).integration.id
    device = env.post("/devices", {"alias": "Steuerung"}).json()["id"]
    assert env.call("PUT", f"/devices/{device}/mode", json={"mode": "control"}).status_code == 200
    step = {"integration_id": lamp, "label": "Licht", "params": {"action": "ping", "target": "x"}}
    done = env.call(
        "PUT",
        f"/devices/{device}/actions/1",
        json={
            "steps": [
                step,
                {
                    **step,
                    "label": "Musik",
                    "delay_ms": 2500,
                    "condition": {"start": "08:00", "end": "18:00"},
                },
            ]
        },
    )
    assert done.status_code == 200
    chains = env.get(f"/devices/{device}/chains").json()
    assert [s["label"] for s in chains["1"]] == ["Licht", "Musik"]
    assert chains["1"][1]["delay_ms"] == 2500 and chains["1"][1]["condition"]["start"] == "08:00"
    assert env.get("/devices").json()[0]["actions"]["1"]["label"] == "Licht"  # step 1 mirrored
    # the old single form still works and resets the chain to one step
    single = env.call("PUT", f"/devices/{device}/actions/1", json=step)
    assert single.status_code == 200
    assert len(env.get(f"/devices/{device}/chains").json()["1"]) == 1
    for body in (
        {},
        {"steps": []},
        {"steps": [{**step, "delay_ms": 400_000}]},
        {"steps": [{**step, "condition": {"start": "25:00", "end": "26:00"}}]},
        {"steps": [{**step, "params": {"action": "nope"}}]},
    ):
        assert env.call("PUT", f"/devices/{device}/actions/2", json=body).status_code in (
            400,
            422,
        ), body
    assert env.get(f"/devices/{device}/chains").json().get("2") is None


# ------------------------------------------------------------------- music mode (API)


def test_music_endpoints(env: Env, tmp_path: Path) -> None:
    from octaledger.application.integration_service import IntegrationService
    from octaledger.application.music_service import MusicService
    from octaledger.core.secrets import SecretStore
    from octaledger.infrastructure.integrations.player import PlayerAdapter

    service = IntegrationService(
        env.storage, SecretStore(tmp_path / "sm.json"), {"player": PlayerAdapter()}
    )
    env.context.integrations = service
    env.context.music = MusicService(env.storage, service, lambda: env.context.settings.settings)
    radio = service.create("player", "Radio", {}).integration.id
    device = env.post("/devices", {"alias": "Musik"}).json()["id"]
    assert (
        env.call("PUT", f"/devices/{device}/mode", json={"mode": "music"}).json()["mode"] == "music"
    )
    assert env.call("PUT", f"/devices/{device}/mode", json={"mode": "disco"}).status_code == 422

    parsed = env.post(
        "/music/parse", {"text": "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"}
    )
    assert parsed.json()["uri"] == "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
    assert env.post("/music/parse", {"text": "nope"}).status_code == 422

    assert env.get(f"/devices/{device}/music").json() == {
        "base_action": "stop",
        "stop_delay_ms": 0,
        "default_volume": 50,
    }
    saved = env.call(
        "PUT",
        f"/devices/{device}/music",
        json={"base_action": "pause", "stop_delay_ms": 2000, "default_volume": 30},
    )
    assert saved.json()["base_action"] == "pause"
    assert (
        env.call("PUT", f"/devices/{device}/music", json={"base_action": "dance"}).status_code
        == 422
    )

    title = {"integration_id": radio, "link": "https://93.184.216.34/lofi.mp3", "label": "Lofi"}
    done = env.call("PUT", f"/devices/{device}/music/faces/1", json=title)
    assert done.status_code == 200 and done.json()["steps"][0]["action"] == "play_url"
    assert done.json()["device"]["actions"]["1"]["label"] == "Lofi"
    bad = {**title, "link": "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"}
    assert env.call("PUT", f"/devices/{device}/music/faces/2", json=bad).status_code == 422
    assert (
        env.call(
            "PUT", f"/devices/{device}/music/faces/2", json={**title, "volume": 500}
        ).status_code
        == 422
    )
    state = env.get("/music/state").json()["devices"]
    assert state == [{"device_id": device, "alias": "Musik", "playing": None, "lost_since": None}]
    normal = env.post("/devices", {"alias": "Zeit"}).json()["id"]
    assert env.call("PUT", f"/devices/{normal}/music/faces/1", json=title).status_code == 409


def test_music_without_the_service_answers_503(env: Env) -> None:
    env.context.music = None
    assert env.get("/music/state").status_code == 503
