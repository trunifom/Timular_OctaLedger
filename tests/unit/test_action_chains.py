"""Action chains: steps, delays, conditions, cancelling, failure follow-up, migration (AP-44)."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from octaledger.application.device_service import DeviceService
from octaledger.application.export_service import ExportService
from octaledger.application.integration_service import IntegrationService
from octaledger.application.outbox import (
    OUTSIDE_WINDOW_MESSAGE,
    PREVIOUS_FAILED_MESSAGE,
    REPLACED_MESSAGE,
    chain_for,
    step_key,
)
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import (
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from octaledger.core.secrets import SecretStore
from octaledger.domain.conditions import Condition, holds, parse_condition
from octaledger.domain.models import DeviceMode, EventKind, JobStatus, RawEvent
from octaledger.domain.steps import ActionStep, check_chain
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from tests.fake_adapter import FakeAdapter

UTC = UTC
ZRH = ZoneInfo("Europe/Zurich")
T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)  # Monday 09:00 in Zurich


# ----------------------------------------------------------------- conditions (pure)


def local(hour: int, minute: int = 0, day: int = 5) -> datetime:
    return datetime(2026, 1, day, hour, minute, tzinfo=ZRH)  # day 5 = Monday


def test_no_condition_always_holds() -> None:
    assert holds(None, local(3)) and holds(Condition(), local(3))
    assert parse_condition(None) is None and parse_condition({}) is None
    assert parse_condition({"start": "", "end": "", "weekdays": ""}) is None


def test_a_time_window_is_start_inclusive_end_exclusive() -> None:
    window = Condition("08:00", "18:00")
    assert holds(window, local(8, 0)) and holds(window, local(17, 59))
    assert not holds(window, local(18, 0)) and not holds(window, local(7, 59))


def test_a_window_may_span_midnight() -> None:
    night = Condition("22:00", "06:00")
    assert holds(night, local(23)) and holds(night, local(2)) and holds(night, local(5, 59))
    assert not holds(night, local(6)) and not holds(night, local(12))


def test_weekdays_refer_to_the_day_the_window_started() -> None:
    monday_night = Condition("22:00", "06:00", "1")
    assert holds(monday_night, local(23, day=5))  # Monday evening
    assert holds(monday_night, local(2, day=6))  # Tuesday 02:00: the window began on Monday
    assert not holds(monday_night, local(23, day=6))  # Tuesday evening
    assert not holds(monday_night, local(2, day=5))  # Monday 02:00: began on Sunday


def test_weekdays_alone_and_whole_day_window() -> None:
    assert holds(Condition(weekdays="1,2"), local(12, day=5))
    assert not holds(Condition(weekdays="1,2"), local(12, day=7))  # Wednesday
    assert holds(Condition("08:00", "08:00"), local(3))  # start == end: the whole day


@pytest.mark.parametrize(
    "bad",
    [
        {"start": "25:00", "end": "26:00"},
        {"start": "08:00"},  # a window needs both ends
        {"weekdays": "0"},
        {"weekdays": "mo"},
        {"start": "8-00", "end": "9:00"},
        {"unknown": "x"},
    ],
)
def test_invalid_conditions_are_rejected(bad: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        parse_condition(bad)


def test_conditions_are_normalised() -> None:
    cond = parse_condition({"start": "8:5", "end": "18:00", "weekdays": "5, 1,1"})
    assert cond == Condition("08:05", "18:00", "1,5")


# ------------------------------------------------------------------------ chains


def test_chain_validation() -> None:
    def step(position: int, delay: int = 0) -> ActionStep:
        return ActionStep("d" * 32, 1, position, "i" * 32, "x", {"action": "ping"}, delay_ms=delay)

    check_chain([step(0), step(1, 1000)])
    with pytest.raises(ValidationError):
        check_chain([])
    with pytest.raises(ValidationError):
        check_chain([step(0)] * 11)
    with pytest.raises(ValidationError):
        check_chain([step(1)])  # positions must start at 0
    with pytest.raises(ValidationError):
        check_chain([step(0, 200_000), step(1, 200_000)])  # more than five minutes in total
    with pytest.raises(ValidationError):
        step(0, delay=300_001)


def test_step_keys_are_stable_and_distinct() -> None:
    assert step_key("abc", 0) == "abc"
    assert step_key("abc", 1) == step_key("abc", 1) != step_key("abc", 2)
    assert len(step_key("abc", 3)) <= 64


# ------------------------------------------------------------------------ service


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.now = T0
        self.adapter = FakeAdapter()
        self.service = IntegrationService(
            self.storage,
            SecretStore(tmp_path / "secrets.json"),
            {"fake": self.adapter},
            clock=lambda: self.now,
        )
        self.tracking = TrackingService(
            self.storage, clock=lambda: self.now, timezone=lambda: "Europe/Zurich"
        )
        devices = DeviceService(self.storage)
        devices.register("Zeit")
        control = devices.register("Steuerung")
        devices.set_mode(control.id, DeviceMode.CONTROL)
        self.device = control.id
        self.lamp = self.service.create(
            "fake", "Lampe", {"host": "h", "password": "richtig"}
        ).integration.id
        self.radio = self.service.create(
            "fake", "Radio", {"host": "r", "password": "richtig"}
        ).integration.id
        self.sequence = 0

    def steps(self, *specs: dict[str, Any]) -> list[ActionStep]:
        built = [
            {
                "integration_id": spec.pop("integration", self.lamp),
                "label": spec.pop("label", "Schritt"),
                "params": spec.pop("params", {"action": "ping", "target": "x"}),
                **spec,
            }
            for spec in specs
        ]
        return self.service.assign_steps(self.device, 1, built)

    def turn(self, face: int = 1) -> RawEvent:
        self.sequence += 1
        event = RawEvent(
            device_id=self.device,
            kind=EventKind.FACE_CHANGE,
            sequence=self.sequence,
            connection_id="c1",
            raw_value=face,
            received_at=self.now,
        )
        self.tracking.record_event(event)
        return event

    def jobs(self) -> list[Any]:
        with self.storage.read() as repos:
            return sorted(repos.jobs.list_recent(100), key=lambda j: (j.created_at, j.step))


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_one_turn_queues_every_step_with_its_own_delay_and_lifetime(env: Env) -> None:
    env.steps({"label": "Licht"}, {"label": "Musik", "delay_ms": 2000, "integration": env.radio})
    event = env.turn()
    first, second = env.jobs()
    assert (first.label, first.step, first.next_attempt_at) == ("Licht", 0, T0)
    assert (second.label, second.step) == ("Musik", 1)
    assert second.next_attempt_at == T0 + timedelta(seconds=2)
    assert second.expires_at == T0 + timedelta(seconds=32)  # the lifetime starts after the delay
    assert first.chain_id == second.chain_id == event.id
    assert first.idempotency_key == event.id and second.idempotency_key == step_key(event.id, 1)


def test_the_steps_are_sent_in_order_at_the_right_times(env: Env) -> None:
    env.steps(
        {"label": "A", "params": {"action": "ping", "target": "a"}},
        {"label": "B", "delay_ms": 2000, "params": {"action": "ping", "target": "b"}},
        {"label": "C", "delay_ms": 3000, "params": {"action": "ping", "target": "c"}},
    )
    env.turn()
    sent = lambda: [c[2].get("target") for c in env.adapter.calls]  # noqa: E731
    env.service.process_due()
    assert sent() == ["a"]
    env.now = T0 + timedelta(seconds=1)
    env.service.process_due()
    assert sent() == ["a"]  # B is not due yet
    env.now = T0 + timedelta(seconds=2)
    env.service.process_due()
    assert sent() == ["a", "b"]
    env.now = T0 + timedelta(seconds=10)
    env.service.process_due()
    assert sent() == ["a", "b", "c"]


def test_a_new_turn_cancels_the_unsent_steps_of_the_previous_chain(env: Env) -> None:
    env.steps({"label": "A"}, {"label": "Später", "delay_ms": 10_000})
    env.turn()
    env.service.process_due()  # A is sent
    env.now = T0 + timedelta(seconds=3)
    env.steps({"label": "Neu"})
    env.turn()
    later = [j for j in env.jobs() if j.label == "Später"][0]
    assert later.status is JobStatus.EXPIRED and later.last_error == REPLACED_MESSAGE
    env.now = T0 + timedelta(seconds=20)
    env.service.process_due()
    assert [c[2]["target"] for c in env.adapter.calls] == ["x", "x"]  # A and Neu, never "Später"


def test_two_quick_turns_still_send_both_first_steps_in_order(env: Env) -> None:
    env.steps({"label": "An"})
    env.turn()
    env.turn()
    assert [j.status for j in env.jobs()] == [JobStatus.PENDING, JobStatus.PENDING]


def test_a_failed_step_cancels_the_following_ones_unless_it_continues(env: Env) -> None:
    env.steps({"label": "1"}, {"label": "2"}, {"label": "3", "delay_ms": 1000})
    env.turn()
    env.adapter.script = [IntegrationError("kaputt", user_message="Nein")]
    env.now = T0
    env.service.process_due()
    statuses = {j.label: (j.status, j.last_error) for j in env.jobs()}
    assert statuses["1"][0] is JobStatus.FAILED
    assert statuses["2"] == (JobStatus.EXPIRED, PREVIOUS_FAILED_MESSAGE)
    assert statuses["3"] == (JobStatus.EXPIRED, PREVIOUS_FAILED_MESSAGE)


def test_a_step_marked_continue_does_not_stop_the_chain(env: Env) -> None:
    env.steps({"label": "1", "continue_on_error": True}, {"label": "2"})
    env.turn()
    env.adapter.script = [IntegrationError("kaputt", user_message="Nein")]
    env.service.process_due()
    by_label = {j.label: j.status for j in env.jobs()}
    assert by_label == {"1": JobStatus.FAILED, "2": JobStatus.DONE}


def test_a_step_outside_its_time_window_is_not_queued(env: Env) -> None:
    env.steps(
        {"label": "Immer"},
        {"label": "Nachts", "condition": {"start": "22:00", "end": "06:00"}},
        {"label": "Tags", "condition": {"start": "08:00", "end": "18:00", "weekdays": "1"}},
    )
    env.turn()  # Monday 09:00 Zurich
    assert [j.label for j in env.jobs()] == ["Immer", "Tags"]
    env.now = datetime(2026, 1, 6, 8, 0, tzinfo=UTC)  # Tuesday 09:00
    env.turn()
    assert [j.label for j in env.jobs()][2:] == ["Immer"]  # the Monday-only step is skipped


def test_disabled_steps_are_skipped_but_kept(env: Env) -> None:
    env.steps({"label": "A"}, {"label": "B", "enabled": False})
    env.turn()
    assert [j.label for j in env.jobs()] == ["A"]
    assert [s.enabled for s in env.service.get_steps(env.device, 1)] == [True, False]


def test_a_single_action_is_a_chain_of_one(env: Env) -> None:
    env.service.assign_action(env.device, 2, env.lamp, "Alt", {"action": "ping", "target": "x"})
    steps = env.service.get_steps(env.device, 2)
    assert len(steps) == 1 and steps[0].label == "Alt" and steps[0].delay_ms == 0
    env.turn(2)
    (job,) = env.jobs()
    assert job.label == "Alt" and job.chain_id is not None and job.step == 0


def test_a_face_with_only_the_old_action_row_still_works(env: Env) -> None:
    with env.storage.transaction() as repos:  # as left by a restored older backup
        repos.actions.assign(env.device, 3, env.lamp, "Nur alt", {"action": "ping", "target": "x"})
        assert repos.steps.list_for(env.device, 3) == []
        assert [s.label for s in chain_for(repos, env.device, 3)] == ["Nur alt"]
    env.turn(3)
    assert [j.label for j in env.jobs()] == ["Nur alt"]


def test_assigning_steps_mirrors_step_one_and_validates_everything(env: Env) -> None:
    env.steps({"label": "Erster"}, {"label": "Zweiter", "delay_ms": 500})
    with env.storage.read() as repos:
        action = repos.actions.get(env.device, 1)
        assert action is not None and action.label == "Erster"
    for bad in (
        [],
        [{"integration_id": env.lamp, "label": "x", "params": {"action": "nope"}}],
        [{"integration_id": env.lamp, "label": "", "params": {"action": "toggle"}}],
        [
            {"integration_id": env.lamp, "label": "x", "params": {"action": "toggle"}},
            {
                "integration_id": env.lamp,
                "label": "y",
                "params": {"action": "toggle"},
                "delay_ms": 400_000,
            },
        ],
    ):
        with pytest.raises(ValidationError):
            env.service.assign_steps(env.device, 4, bad)
    with pytest.raises(NotFoundError):
        env.service.assign_steps(
            env.device, 4, [{"integration_id": "0" * 32, "label": "x", "params": {}}]
        )
    assert env.service.get_steps(env.device, 4) == []  # nothing half-saved


def test_clearing_a_face_removes_all_its_steps(env: Env) -> None:
    env.steps({"label": "A"}, {"label": "B"})
    env.service.clear_action(env.device, 1)
    assert env.service.get_steps(env.device, 1) == []
    with env.storage.read() as repos:
        assert repos.actions.get(env.device, 1) is None


def test_a_connection_used_by_a_step_cannot_be_deleted(env: Env) -> None:
    env.steps({"label": "A"}, {"label": "B", "integration": env.radio})
    from octaledger.core.errors import ConflictError

    with pytest.raises(ConflictError):
        env.service.delete(env.radio)


def test_the_outside_window_message_exists_for_the_history() -> None:
    assert "Zeitfenster" in OUTSIDE_WINDOW_MESSAGE


# ---------------------------------------------------------------------- backup


def test_steps_survive_a_backup_and_restore(env: Env, tmp_path: Path) -> None:
    env.steps({"label": "A"}, {"label": "B", "delay_ms": 1500, "condition": {"weekdays": "1,2"}})
    exports = ExportService(
        env.storage, exports_dir=tmp_path / "ex", backup_dir=tmp_path / "bk2", clock=lambda: T0
    )
    text = exports.create_backup_text()
    env.service.clear_action(env.device, 1)
    exports.restore_backup_text(text)
    steps = env.service.get_steps(env.device, 1)
    assert [(s.label, s.delay_ms) for s in steps] == [("A", 0), ("B", 1500)]
    assert steps[1].condition == Condition(weekdays="1,2")


# -------------------------------------------------------------------- migration


def test_the_migration_turns_existing_actions_into_step_one(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    database = Database(path, backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    devices = DeviceService(storage)
    control = devices.register("Steuerung")
    devices.set_mode(control.id, DeviceMode.CONTROL)
    with storage.transaction() as repos:
        from octaledger.domain.models import Integration

        lamp = repos.integrations.add(Integration("webhook", "Lampe"))
        repos.actions.assign(control.id, 2, lamp.id, "Alt", {"action": "toggle"})
    # simulate a database from before AP-44: empty the new table, as if the migration had not run
    with sqlite3.connect(path) as raw:
        raw.execute("DELETE FROM face_action_steps")
        raw.execute(
            "INSERT INTO face_action_steps (device_id, face, position, integration_id, label, "
            "params) SELECT device_id, face, 0, integration_id, label, params FROM face_actions"
        )  # the statement the migration runs
        rows = raw.execute(
            "SELECT position, label, delay_ms, enabled FROM face_action_steps"
        ).fetchall()
    assert rows == [(0, "Alt", 0, 1)]
