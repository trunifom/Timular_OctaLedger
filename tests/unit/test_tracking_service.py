"""Tests for the tracking service: event rules, manual control, corrections, recovery."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octaledger.application.tracking_service import Outcome, TrackingService
from octaledger.core.errors import (
    ConflictError,
    InvalidStateError,
    NotFoundError,
    ValidationError,
)
from octaledger.core.settings import (
    BaselinePolicy,
    DisconnectPolicy,
    NeutralPolicy,
    TrackingSettings,
)
from octaledger.domain.models import (
    Activity,
    Device,
    EventKind,
    Project,
    Quality,
    RawEvent,
    SessionSource,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
M = timedelta(minutes=1)


class Clock:
    """Controllable clock; ``now`` is read on every call."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: float) -> datetime:
        self.now += timedelta(minutes=minutes)
        return self.now


@dataclass
class Env:
    storage: Storage
    clock: Clock
    device: str
    other_device: str
    meeting: str
    code: str
    project: str
    service: TrackingService

    def make_service(self, **settings: object) -> TrackingService:
        return TrackingService(self.storage, TrackingSettings(**settings), clock=self.clock)  # type: ignore[arg-type]

    def event(
        self, kind: EventKind, value: int | None, minutes: float = 0, device: str | None = None
    ) -> RawEvent:
        return RawEvent(
            device_id=device or self.device,
            kind=kind,
            sequence=0,
            connection_id="c1",
            raw_value=value,
            received_at=T0 + timedelta(minutes=minutes),
        )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    clock = Clock()
    with storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Büro"))
        other = repos.devices.add(Device(alias="Zuhause"))
        meeting = repos.activities.add(Activity(name="Meeting"))
        code = repos.activities.add(Activity(name="Code"))
        project = repos.projects.add(Project(name="Alpha"))
        repos.mappings.assign(device.id, 1, meeting.id)
        repos.mappings.assign(device.id, 2, code.id, project.id)
        repos.mappings.assign(device.id, 3, None)  # face configured but empty
        repos.mappings.assign(other.id, 1, code.id)
    service = TrackingService(storage, clock=clock)
    service.set_active_device(device.id)
    return Env(storage, clock, device.id, other.id, meeting.id, code.id, project.id, service)


def add_done(env: Env, activity_id: str, start: datetime, end: datetime, **kw: object):  # type: ignore[no-untyped-def]
    """Add a finished session; first move the clock past ``end`` (future ends are rejected)."""
    env.clock.now = max(env.clock.now, end + 10 * M)
    return env.service.add_manual_session(activity_id, start, end, **kw)  # type: ignore[arg-type]


def sessions(env: Env) -> list:  # type: ignore[type-arg]
    with env.storage.read() as repos:
        return repos.sessions.list_all()


# ------------------------------------------------------------------- face changes


def test_face_change_starts_and_switches_sessions(env: Env) -> None:
    first = env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    assert first.outcome is Outcome.STARTED and first.session is not None
    assert first.session.source is SessionSource.DEVICE and first.session.device_id == env.device
    second = env.service.record_event(env.event(EventKind.FACE_CHANGE, 2, 30))
    assert second.outcome is Outcome.SWITCHED
    done, running = sessions(env)
    assert done.ended_at == T0 + 30 * M and done.activity_id == env.meeting
    assert running.started_at == T0 + 30 * M and running.is_running
    assert (running.activity_id, running.project_id) == (env.code, env.project)


def test_same_activity_continues(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    again = env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 5))
    assert again.outcome is Outcome.CONTINUED
    assert len(sessions(env)) == 1


def test_unmapped_face_changes_nothing(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    for face in (3, 8):  # configured-empty and never configured
        assert env.service.record_event(env.event(EventKind.FACE_CHANGE, face, 5)).outcome is (
            Outcome.UNMAPPED
        )
    (only,) = sessions(env)
    assert only.is_running and only.activity_id == env.meeting


def test_every_event_is_stored_even_without_effect(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 8, 0))  # unmapped
    env.service.record_event(env.event(EventKind.INVALID, None, 1))
    env.service.record_event(env.event(EventKind.RECONNECT, None, 2))
    with env.storage.read() as repos:
        assert repos.events.count(env.device) == 3
    assert sessions(env) == []


# --------------------------------------------------------- inactive device (A-07)


def test_inactive_device_events_are_stored_but_create_no_session(env: Env) -> None:
    result = env.service.record_event(
        env.event(EventKind.FACE_CHANGE, 1, 0, device=env.other_device)
    )
    assert result.outcome is Outcome.STORED
    assert sessions(env) == []
    with env.storage.read() as repos:
        assert repos.events.count(env.other_device) == 1


def test_handover_ends_device_session_without_double_time(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    env.clock.advance(60)
    ended = env.service.handover(env.other_device)
    assert ended is not None and ended.ended_at == T0 + 60 * M
    assert env.service.get_active_device_id() == env.other_device
    # Old tracker is now inactive; new one drives the next session.
    assert (
        env.service.record_event(env.event(EventKind.FACE_CHANGE, 2, 61)).outcome is Outcome.STORED
    )
    started = env.service.record_event(
        env.event(EventKind.FACE_CHANGE, 1, 62, device=env.other_device)
    )
    assert started.outcome is Outcome.STARTED
    first, second = sessions(env)
    assert first.ended_at is not None and first.ended_at <= second.started_at  # no overlap


def test_handover_keeps_manual_session_and_ignores_same_device(env: Env) -> None:
    env.service.start_manual(env.code)
    assert env.service.handover(env.other_device) is None
    assert env.service.status().running is not None
    assert env.service.handover(env.other_device) is None  # already active: no-op


def test_handover_unknown_device(env: Env) -> None:
    with pytest.raises(NotFoundError):
        env.service.handover("missing")


# --------------------------------------------------------------- baseline policy


def test_baseline_never_starts_session_by_default(env: Env) -> None:
    result = env.service.record_event(env.event(EventKind.BASELINE, 1, 0))
    assert result.outcome is Outcome.STORED and sessions(env) == []


def test_baseline_adopt_current_starts_session(env: Env) -> None:
    service = env.make_service(baseline_policy=BaselinePolicy.ADOPT_CURRENT)
    result = service.record_event(env.event(EventKind.BASELINE, 2, 0))
    assert result.outcome is Outcome.STARTED
    assert result.session is not None and result.session.activity_id == env.code


def test_adopt_current_ignores_unmapped_and_neutral_baseline(env: Env) -> None:
    service = env.make_service(baseline_policy=BaselinePolicy.ADOPT_CURRENT)
    assert service.record_event(env.event(EventKind.BASELINE, 0, 0)).outcome is Outcome.STORED
    assert service.record_event(env.event(EventKind.BASELINE, 8, 1)).outcome is Outcome.STORED
    assert sessions(env) == []


@pytest.mark.parametrize("policy", list(BaselinePolicy))
def test_reconnect_with_same_face_continues_without_new_session(
    env: Env, policy: BaselinePolicy
) -> None:
    """Acceptance A-04: a reconnect must not create an unintended new session."""
    service = env.make_service(baseline_policy=policy)
    service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    service.record_event(env.event(EventKind.DISCONNECT, None, 10))
    service.record_event(env.event(EventKind.RECONNECT, None, 12))
    result = service.record_event(env.event(EventKind.BASELINE, 1, 12))
    assert result.outcome is Outcome.CONTINUED
    (only,) = sessions(env)
    assert only.is_running and only.quality is Quality.UNCERTAIN  # user must still confirm


def test_reconnect_with_other_face_observe_only_keeps_uncertain_session(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    env.service.record_event(env.event(EventKind.DISCONNECT, None, 10))
    result = env.service.record_event(env.event(EventKind.BASELINE, 2, 12))
    assert result.outcome is Outcome.STORED  # observe-only: no silent switch
    (only,) = sessions(env)
    assert only.activity_id == env.meeting and only.quality is Quality.UNCERTAIN


def test_reconnect_with_other_face_adopt_current_switches(env: Env) -> None:
    service = env.make_service(baseline_policy=BaselinePolicy.ADOPT_CURRENT)
    service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    service.record_event(env.event(EventKind.DISCONNECT, None, 10))
    result = service.record_event(env.event(EventKind.BASELINE, 2, 12))
    assert result.outcome is Outcome.SWITCHED
    old, new = sessions(env)
    assert old.quality is Quality.UNCERTAIN and old.ended_at == T0 + 12 * M
    assert new.quality is Quality.CONFIRMED


# ----------------------------------------------------------------- neutral/disconnect


def test_neutral_only_observed_by_default(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    assert env.service.record_event(env.event(EventKind.NEUTRAL, 0, 5)).outcome is Outcome.STORED
    assert sessions(env)[0].is_running


def test_neutral_pause_policy_ends_and_allows_resume(env: Env) -> None:
    service = env.make_service(neutral_policy=NeutralPolicy.PAUSE)
    service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    result = service.record_event(env.event(EventKind.NEUTRAL, 0, 20))
    assert result.outcome is Outcome.ENDED
    assert service.status().paused and service.status().running is None
    env.clock.advance(30)
    resumed = service.resume()
    assert resumed.activity_id == env.meeting and not service.status().paused


def test_neutral_pause_without_running_session_is_only_stored(env: Env) -> None:
    service = env.make_service(neutral_policy=NeutralPolicy.PAUSE)
    assert service.record_event(env.event(EventKind.NEUTRAL, 0, 1)).outcome is Outcome.STORED


def test_disconnect_marks_uncertain_by_default(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    result = env.service.record_event(env.event(EventKind.DISCONNECT, None, 10))
    assert result.outcome is Outcome.MARKED_UNCERTAIN
    assert env.service.status().uncertain_count == 1
    assert env.service.list_uncertain()[0].is_running


def test_disconnect_stop_policy_ends_uncertain(env: Env) -> None:
    service = env.make_service(disconnect_policy=DisconnectPolicy.STOP_SESSION)
    service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    result = service.record_event(env.event(EventKind.DISCONNECT, None, 10))
    assert result.outcome is Outcome.ENDED
    ended = sessions(env)[0]
    assert ended.ended_at == T0 + 10 * M and ended.quality is Quality.UNCERTAIN


def test_disconnect_ignored_for_manual_session_or_nothing_running(env: Env) -> None:
    assert (
        env.service.record_event(env.event(EventKind.DISCONNECT, None, 1)).outcome is Outcome.STORED
    )
    env.service.start_manual(env.code)
    assert (
        env.service.record_event(env.event(EventKind.DISCONNECT, None, 2)).outcome is Outcome.STORED
    )
    assert env.service.status().uncertain_count == 0


def test_confirming_clears_uncertainty(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    env.service.record_event(env.event(EventKind.DISCONNECT, None, 10))
    (uncertain,) = env.service.list_uncertain()
    confirmed = env.service.confirm_session(uncertain.id)
    assert confirmed.quality is Quality.CONFIRMED and confirmed.revision == 2
    assert env.service.confirm_session(uncertain.id).revision == 2  # idempotent
    assert env.service.list_uncertain() == []


# ----------------------------------------------------------------- clock protection


def test_event_before_last_session_end_is_clamped_not_overlapping(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 30))
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 2, 60))
    # A late/jumped event claims a time before the running session's start.
    result = env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 10))
    assert result.outcome is Outcome.SWITCHED
    all_sessions = sessions(env)  # same start time -> order by id is arbitrary, select by trait
    running = [x for x in all_sessions if x.is_running]
    zero_length = [x for x in all_sessions if x.ended_at == x.started_at]
    assert len(all_sessions) == 3 and len(running) == 1 and len(zero_length) == 1
    assert zero_length[0].ended_at == running[0].started_at == T0 + 60 * M  # clamped, no overlap


def test_unknown_device_event_conflicts_and_stores_nothing(env: Env) -> None:
    with pytest.raises(ConflictError):
        env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0, device="ghost"))


# --------------------------------------------------------------- manual operations


def test_manual_start_stop(env: Env) -> None:
    started = env.service.start_manual(env.meeting, env.project, "Planung")
    assert started.source is SessionSource.MANUAL and started.note == "Planung"
    env.clock.advance(45)
    stopped = env.service.stop()
    assert stopped.ended_at == T0 + 45 * M
    with pytest.raises(InvalidStateError):
        env.service.stop()


def test_manual_start_ends_running_session_first(env: Env) -> None:
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    env.clock.advance(10)
    env.service.start_manual(env.code)
    first, second = sessions(env)
    assert first.ended_at == second.started_at == T0 + 10 * M


def test_manual_start_unknown_references(env: Env) -> None:
    with pytest.raises(NotFoundError):
        env.service.start_manual("missing")
    with pytest.raises(NotFoundError):
        env.service.start_manual(env.meeting, "missing-project")
    assert sessions(env) == []


def test_pause_and_resume(env: Env) -> None:
    env.service.start_manual(env.code, env.project)
    env.clock.advance(20)
    paused = env.service.pause()
    assert paused.ended_at == T0 + 20 * M and env.service.status().paused
    env.clock.advance(15)
    resumed = env.service.resume()
    assert (resumed.activity_id, resumed.project_id) == (env.code, env.project)
    assert resumed.started_at == T0 + 35 * M
    assert not env.service.status().paused


def test_pause_and_resume_errors(env: Env) -> None:
    with pytest.raises(InvalidStateError):
        env.service.pause()
    with pytest.raises(InvalidStateError):
        env.service.resume()
    env.service.start_manual(env.code)
    env.service.pause()
    env.service.start_manual(env.meeting)  # starting anything clears the pause
    assert not env.service.status().paused
    with pytest.raises(InvalidStateError):
        env.service.resume()


def test_stop_clears_pause_state(env: Env) -> None:
    env.service.start_manual(env.code)
    env.service.pause()
    env.service.start_manual(env.code)
    env.service.stop()
    assert not env.service.status().paused


def test_add_manual_session_and_validation(env: Env) -> None:
    env.clock.advance(600)
    added = add_done(env, env.meeting, T0, T0 + 60 * M, note="Nachtrag")
    assert not added.is_running and added.source is SessionSource.MANUAL
    with pytest.raises(ConflictError):
        env.service.add_manual_session(env.code, T0 + 30 * M, T0 + 90 * M)
    with pytest.raises(ValidationError):
        env.service.add_manual_session(env.code, T0 + 5 * M, T0 + 2 * M)
    with pytest.raises(ValidationError, match="future"):
        env.service.add_manual_session(
            env.code, env.clock.now, env.clock.now + 3 * timedelta(hours=1)
        )
    with pytest.raises(NotFoundError):
        env.service.add_manual_session("missing", T0 + 200 * M, T0 + 201 * M)


# ------------------------------------------------------------ correcting/splitting


def test_split_finished_session(env: Env) -> None:
    session = add_done(env, env.meeting, T0, T0 + 60 * M, note="x")
    env.clock.advance(120)
    first, second = env.service.split_session(session.id, T0 + 20 * M, "Pause vergessen")
    assert (first.started_at, first.ended_at) == (T0, T0 + 20 * M) and first.revision == 2
    assert (second.started_at, second.ended_at) == (T0 + 20 * M, T0 + 60 * M)
    assert second.activity_id == session.activity_id and second.note == "x"
    with env.storage.read() as repos:
        assert [c.field_name for c in repos.sessions.list_corrections(session.id)] == ["ended_at"]


def test_split_running_session_keeps_second_part_running(env: Env) -> None:
    session = env.service.start_manual(env.code)
    env.clock.advance(60)
    first, second = env.service.split_session(session.id, T0 + 30 * M, "geteilt")
    assert first.ended_at == T0 + 30 * M and second.is_running
    assert env.service.status().running is not None


@pytest.mark.parametrize("minute", [0, -5, 60, 90])
def test_split_outside_session_rejected(env: Env, minute: int) -> None:
    session = add_done(env, env.meeting, T0, T0 + 60 * M)
    env.clock.advance(300)
    with pytest.raises(ValidationError):
        env.service.split_session(session.id, T0 + minute * M, "x")
    assert len(sessions(env)) == 1


def test_split_requires_reason_and_rolls_back(env: Env) -> None:
    session = add_done(env, env.meeting, T0, T0 + 60 * M)
    env.clock.advance(300)
    with pytest.raises(ValidationError):
        env.service.split_session(session.id, T0 + 20 * M, "  ")
    (unchanged,) = sessions(env)
    assert unchanged.ended_at == T0 + 60 * M and unchanged.revision == 1


def test_correct_session_validates_references(env: Env) -> None:
    session = add_done(env, env.meeting, T0, T0 + 60 * M)
    updated = env.service.correct_session(
        session.id, {"activity_id": env.code, "project_id": env.project}, "falsch gebucht"
    )
    assert (updated.activity_id, updated.project_id) == (env.code, env.project)
    with pytest.raises(NotFoundError):
        env.service.correct_session(session.id, {"activity_id": "missing"}, "r")
    with pytest.raises(NotFoundError):
        env.service.correct_session(session.id, {"project_id": "missing"}, "r")
    cleared = env.service.correct_session(session.id, {"project_id": None}, "ohne Projekt")
    assert cleared.project_id is None


def test_delete_session_needs_reason(env: Env) -> None:
    session = add_done(env, env.meeting, T0, T0 + 60 * M)
    with pytest.raises(ValidationError):
        env.service.delete_session(session.id, "")
    env.service.delete_session(session.id, "Testdaten")
    assert sessions(env) == []
    with env.storage.read() as repos:
        assert repos.audit.recent()[0].entity == "session"


# ------------------------------------------------------------ status and recovery


def test_status_snapshot(env: Env) -> None:
    empty = env.service.status()
    assert empty.running is None and empty.elapsed == timedelta(0)
    assert empty.active_device_id == env.device and not empty.paused
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 2, 0))
    env.clock.advance(42)
    status = env.service.status()
    assert status.activity is not None and status.activity.name == "Code"
    assert status.project is not None and status.project.name == "Alpha"
    assert status.elapsed == 42 * M


def test_active_device_selection(env: Env) -> None:
    env.service.set_active_device(None)
    assert env.service.get_active_device_id() is None
    assert (
        env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0)).outcome is Outcome.STORED
    )
    with pytest.raises(NotFoundError):
        env.service.set_active_device("missing")


def test_deleted_active_device_is_reported_as_none(env: Env) -> None:
    with env.storage.transaction() as repos:
        repos.mappings.clear(env.other_device, 1)
        repos.devices.delete(env.other_device)
        repos.state.set("active_device", env.other_device)  # stale pointer to a deleted device
    assert env.service.get_active_device_id() is None
    assert env.service.status().active_device_id is None


def test_restart_keeps_confirmed_data_and_unclear_section(env: Env) -> None:
    """Acceptance A-06: after a process restart data persists and the gap stays flagged."""
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    env.service.record_event(env.event(EventKind.DISCONNECT, None, 10))
    restarted = TrackingService(env.storage, clock=env.clock)  # fresh process, same database
    status = restarted.status()
    assert status.running is not None and status.uncertain_count == 1
    assert status.active_device_id == env.device
