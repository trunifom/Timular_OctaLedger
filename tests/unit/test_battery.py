"""Battery stages, history, estimate, service and API (AP-52)."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from octaledger.application.battery_service import BatteryService
from octaledger.domain.battery import (
    RECORD_EVERY,
    bar,
    describe_days,
    estimate_days_left,
    is_worse,
    should_record,
    stage_by_key,
    stage_for,
)
from octaledger.domain.models import Device
from tests.unit.test_api import Env, FakeAgent

UTC = timezone.utc
T0 = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)


# ----------------------------------------------------------------------- pure rules


@pytest.mark.parametrize(
    ("percent", "key"),
    [
        (100, "good"),
        (40, "good"),
        (39, "soon"),
        (20, "soon"),
        (19, "weak"),
        (10, "weak"),
        (9, "empty"),
        (0, "empty"),
    ],
)
def test_stage_boundaries(percent: int, key: str) -> None:
    assert stage_for(percent).key == key


def test_stages_have_text_and_icons_not_only_colour() -> None:
    for key in ("good", "soon", "weak", "empty"):
        stage = stage_by_key(key)
        assert stage.text and stage.icon and stage.level in ("ok", "warn", "bad")


def test_bar_has_five_segments_one_per_started_twenty_percent() -> None:
    assert bar(100) == "▮▮▮▮▮" and bar(62) == "▮▮▮▮▯" and bar(60) == "▮▮▮▯▯" and bar(21) == "▮▮▯▯▯"
    assert bar(1) == "▮▯▯▯▯" and bar(0) == "▯▯▯▯▯" and len(bar(55)) == 5


def test_is_worse_only_for_a_lower_stage() -> None:
    assert is_worse(None, stage_for(30))
    assert not is_worse(None, stage_for(80))
    assert is_worse(stage_for(80), stage_for(15))
    assert not is_worse(stage_for(15), stage_for(15))
    assert not is_worse(stage_for(15), stage_for(80))  # recovering is no warning


def test_should_record_first_changed_or_after_six_hours() -> None:
    assert should_record(None, None, 80, T0)
    assert not should_record(80, T0, 80, T0 + timedelta(hours=1))
    assert should_record(80, T0, 79, T0 + timedelta(minutes=1))
    assert should_record(80, T0, 80, T0 + RECORD_EVERY)


def series(
    start: int, per_day: float, days: int, step_hours: int = 12
) -> list[tuple[datetime, int]]:
    points = []
    for i in range(0, days * 24 // step_hours + 1):
        at = T0 + timedelta(hours=i * step_hours)
        points.append((at, round(start - per_day * (i * step_hours / 24))))
    return points


def test_estimate_from_a_falling_history() -> None:
    points = series(80, 2.0, 10)  # 2 % per day, now at 60 %
    days = estimate_days_left(points, points[-1][0])
    assert days is not None and 28 <= days <= 32  # about 60 / 2


def test_no_estimate_without_enough_history_or_trend() -> None:
    short = series(80, 2.0, 2)
    assert estimate_days_left(short, short[-1][0]) is None  # under three days
    few = series(80, 2.0, 10)[::10]
    assert estimate_days_left(few, few[-1][0]) is None  # too few points
    flat = series(80, 0.0, 10)
    assert estimate_days_left(flat, flat[-1][0]) is None  # not falling


def test_a_battery_replacement_restarts_the_estimate() -> None:
    old = series(30, 3.0, 5)
    just_replaced = old + [(old[-1][0] + timedelta(hours=12), 100)]
    assert estimate_days_left(just_replaced, just_replaced[-1][0]) is None  # nothing since yet
    start = old[-1][0] + timedelta(hours=12)
    new = [(start + timedelta(hours=12 * i), round(100 - 1.0 * i / 2)) for i in range(0, 21)]
    days = estimate_days_left(old + new, new[-1][0])
    assert days is not None and 80 <= days <= 100  # judged by the new battery only


def test_estimate_text_is_always_marked_as_an_estimate() -> None:
    assert "keine Schätzung" in describe_days(None)
    for days in (0.5, 5, 30, 200, 4000):
        assert describe_days(days).startswith("Schätzung")


# ---------------------------------------------------------------------- the service


def warnings_of(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Only the battery service's own warnings (other loggers may be at INFO in a full run)."""
    return [
        r
        for r in caplog.records
        if r.name == "octaledger.application.battery_service" and r.levelno >= logging.WARNING
    ]


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path, FakeAgent())


@pytest.fixture
def clock() -> Clock:
    return Clock()


def service(env: Env, clock: Clock) -> tuple[BatteryService, str]:
    with env.storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Büro"))
    return BatteryService(env.storage, clock=clock), device.id


def test_record_stores_changes_and_every_six_hours_only(env: Env, clock: Clock) -> None:
    battery, did = service(env, clock)
    assert battery.record({did: 80}) == 1
    clock.now += timedelta(hours=1)
    assert battery.record({did: 80}) == 0  # unchanged, not due
    assert battery.record({did: None}) == 0  # no reading
    clock.now += timedelta(minutes=5)
    assert battery.record({did: 79}) == 1  # changed
    clock.now += timedelta(hours=7)
    assert battery.record({did: 79}) == 1  # due after six hours
    assert [p for _, p in battery.history(did)] == [80, 79, 79]


def test_a_lower_stage_is_logged_once_and_not_again(
    env: Env, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    battery, did = service(env, clock)
    with caplog.at_level(logging.WARNING, logger="octaledger.application.battery_service"):
        battery.record({did: 80})
        assert not warnings_of(caplog)  # good: nothing to say
        clock.now += timedelta(minutes=10)
        battery.record({did: 35})
        battery.record({did: 34})
        assert [r.levelno for r in warnings_of(caplog)] == [logging.WARNING]
        assert "bald tauschen" in caplog.text and "35" in caplog.text
        clock.now += timedelta(minutes=10)
        battery.record({did: 8})
        assert warnings_of(caplog)[-1].levelno == logging.ERROR and "fast leer" in caplog.text


def test_stage_memory_survives_a_restart(
    env: Env, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    battery, did = service(env, clock)
    battery.record({did: 35})
    caplog.clear()
    fresh = BatteryService(env.storage, clock=clock)  # a new process
    with caplog.at_level(logging.WARNING, logger="octaledger.application.battery_service"):
        clock.now += timedelta(minutes=10)
        fresh.record({did: 34})
    assert not warnings_of(caplog)  # already warned before the restart


def test_summary_uses_the_live_value_else_the_last_stored_one(env: Env, clock: Clock) -> None:
    battery, did = service(env, clock)
    assert battery.summary({})[did] is None  # nothing known yet
    battery.record({did: 50})
    clock.now += timedelta(hours=2)
    stored = battery.summary({})[did]
    assert stored is not None and stored.percent == 50 and not stored.live
    assert stored.measured_at == T0
    live = battery.summary({did: 47})[did]
    assert live is not None and live.percent == 47 and live.live and live.stage.key == "good"


def test_old_history_is_pruned(env: Env, clock: Clock) -> None:
    battery, did = service(env, clock)
    with env.storage.transaction() as repos:
        repos.battery.add(did, T0 - timedelta(days=500), 90)
    battery.record({did: 80})
    with env.storage.read() as repos:
        assert [p for _, p in repos.battery.since(did, T0 - timedelta(days=900))] == [80]


def test_api_status_and_battery_route(env: Env) -> None:
    cube = env.post("/devices", {"alias": "Büro"}).json()
    assert env.get("/status").json()["devices"][0]["battery"] is None
    now = datetime.now(UTC)
    with env.storage.transaction() as repos:
        repos.battery.add(cube["id"], now - timedelta(hours=1), 33)
    status = env.get("/status").json()["devices"][0]["battery"]
    assert status["percent"] == 33 and status["stage"] == "soon" and status["live"] is False
    assert status["stage_text"] == "bald tauschen" and status["estimate_text"]
    detail = env.get(f"/devices/{cube['id']}/battery", params={"days": 7}).json()
    assert detail["summary"]["percent"] == 33 and [h["percent"] for h in detail["history"]] == [33]
    assert env.get("/devices/unknown/battery").status_code == 404


def test_the_history_belongs_to_the_backup(env: Env) -> None:
    cube = env.post("/devices", {"alias": "Büro"}).json()
    with env.storage.transaction() as repos:
        repos.battery.add(cube["id"], T0, 77)
    text = env.context.exports.create_backup_text()
    env.context.exports.restore_backup_text(text)
    with env.storage.read() as repos:
        assert repos.battery.latest(cube["id"]) == (T0, 77)
