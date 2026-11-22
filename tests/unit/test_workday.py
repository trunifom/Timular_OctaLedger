"""The working day: auto-stop, idle questions, reminders (AP-38) with an injected clock."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from octaledger.application.workday_service import (
    IDLE_DISCARD,
    IDLE_KEEP,
    IDLE_PAUSE,
    STOP_EXTEND,
    STOP_KEEP,
    WorkdayService,
)
from octaledger.core.errors import ConfigurationError, InvalidStateError, ValidationError
from octaledger.core.settings import Settings, WorkSettings
from octaledger.domain.attention import AttentionKind
from octaledger.domain.models import Activity, Quality, Session, SessionSource
from octaledger.domain.workday import (
    DayState,
    RunningEntry,
    WorkAction,
    evaluate,
    is_workday,
    parse_clock,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from octaledger.infrastructure.system.idle import FixedInputProbe, WindowsInputProbe

TZ = ZoneInfo("Europe/Zurich")
UTC = UTC
# Monday 2026-01-05, Zurich is UTC+1 in January: 16:00 UTC = 17:00 local.
MON = datetime(2026, 1, 5, 7, 0, tzinfo=UTC)  # 08:00 local
H = timedelta(hours=1)


def local(hour: int, minute: int = 0, day: int = 5) -> datetime:
    return datetime(2026, 1, day, hour, minute, tzinfo=TZ).astimezone(UTC)


# --------------------------------------------------------------------- settings


def test_everything_is_off_by_default() -> None:
    work = WorkSettings()
    assert (work.workday_end, work.idle_minutes, work.reminder_no_timer_after) == ("", 0, "")
    assert work.reminder_running_hours == 0 and work.workday_numbers() == {1, 2, 3, 4, 5}


@pytest.mark.parametrize(
    "bad",
    [
        {"workday_end": "25:00"},
        {"workday_end": "17-30"},
        {"workday_end": "7"},
        {"reminder_no_timer_after": "09:75"},
        {"idle_minutes": -1},
        {"idle_minutes": 9999},
        {"reminder_running_hours": 25},
        {"workdays": ""},
        {"workdays": "0,8"},
        {"workdays": "mo"},
    ],
)
def test_invalid_values_are_rejected_with_the_setting_name(bad: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        WorkSettings(**bad)  # type: ignore[arg-type]


def test_clock_times_are_normalised_and_days_sorted() -> None:
    work = WorkSettings(workday_end="7:5", workdays="5, 1,1")
    assert work.workday_end == "07:05" and work.workdays == "1,5"
    assert parse_clock("") is None and parse_clock("07:05").hour == 7  # type: ignore[union-attr]


# ------------------------------------------------------------------- pure rules


def entry(started: datetime) -> RunningEntry:
    return RunningEntry("a" * 32, started)


def rules(
    work: WorkSettings,
    now: datetime,
    running: RunningEntry | None,
    idle: float | None = None,
    state: DayState | None = None,
) -> list[WorkAction]:
    return [d.action for d in evaluate(now, TZ, work, running, idle, state or DayState())]


def test_auto_stop_at_the_end_only_on_workdays_and_only_when_running() -> None:
    work = WorkSettings(workday_end="17:30")
    running = entry(local(9))
    assert rules(work, local(17, 29), running) == []
    (decision,) = evaluate(local(17, 31), TZ, work, running, None, DayState())
    assert decision.action is WorkAction.AUTO_STOP and decision.at == local(17, 30)
    assert rules(work, local(17, 31), None) == []  # nothing runs
    assert rules(work, local(17, 31, day=10), entry(local(9, day=10))) == []  # Saturday? no: Sat=10
    assert rules(work, local(17, 31, day=6), entry(local(9, day=6))) == [WorkAction.AUTO_STOP]


def test_an_entry_started_after_the_end_is_not_stopped_at_once() -> None:
    work = WorkSettings(workday_end="17:30")
    assert rules(work, local(19), entry(local(18))) == []


def test_auto_stop_happens_once_per_day() -> None:
    work = WorkSettings(workday_end="17:30")
    state = DayState(auto_stopped_on="2026-01-05")
    assert rules(work, local(18), entry(local(9)), state=state) == []


def test_idle_needs_the_threshold_a_running_entry_and_asks_once() -> None:
    work = WorkSettings(idle_minutes=10)
    running = entry(local(9))
    assert rules(work, local(10), running, idle=599) == []
    (decision,) = evaluate(local(10), TZ, work, running, 600, DayState())
    assert decision.action is WorkAction.IDLE and decision.at == local(10) - timedelta(seconds=600)
    assert rules(work, local(10), running, idle=None) == []  # unknown idle time
    assert rules(work, local(10), None, idle=9999) == []
    assert rules(work, local(10), running, idle=700, state=DayState(idle_asked_for="a" * 32)) == []


def test_no_timer_reminder_once_a_day_on_workdays_before_the_end() -> None:
    work = WorkSettings(reminder_no_timer_after="09:00", workday_end="17:30")
    assert rules(work, local(8, 59), None) == []
    assert rules(work, local(9, 1), None) == [WorkAction.REMIND_NO_TIMER]
    assert rules(work, local(9, 1), entry(local(8))) == []
    assert rules(work, local(9, 1), None, state=DayState(reminded_no_timer_on="2026-01-05")) == []
    assert rules(work, local(18), None) == []  # the day is over
    assert rules(work, local(9, 1, day=10), None) == []  # weekend


def test_running_too_long_reminder_once_per_entry() -> None:
    work = WorkSettings(reminder_running_hours=4)
    running = entry(local(8))
    assert rules(work, local(11, 59), running) == []
    assert rules(work, local(12), running) == [WorkAction.REMIND_RUNNING]
    assert rules(work, local(13), running, state=DayState(reminded_running="a" * 32)) == []


def test_is_workday_uses_the_local_weekday() -> None:
    work = WorkSettings(workdays="1")
    assert is_workday(work, local(12), TZ) and not is_workday(work, local(12, day=6), TZ)
    # 23:30 UTC on Monday is already Tuesday in Zurich
    assert not is_workday(work, datetime(2026, 1, 5, 23, 30, tzinfo=UTC), TZ)


# ---------------------------------------------------------------------- service


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        with self.storage.transaction() as repos:
            self.activity = repos.activities.add(Activity(name="Code")).id
        self.work = WorkSettings()
        self.probe = FixedInputProbe(None)
        self.now = local(9)
        self.service = WorkdayService(
            self.storage,
            lambda: replace(Settings(), work=self.work, display=_zurich()),
            self.probe,
            clock=lambda: self.now,
        )

    def start(self, at: datetime) -> str:
        with self.storage.transaction() as repos:
            return repos.sessions.add(Session(self.activity, at, source=SessionSource.MANUAL)).id

    def sessions(self) -> list[Session]:
        with self.storage.read() as repos:
            return repos.sessions.list_all()

    def open_items(self) -> list:  # type: ignore[type-arg]
        with self.storage.read() as repos:
            return repos.attention.list_open()


def _zurich():  # type: ignore[no-untyped-def]
    from octaledger.core.settings import DisplaySettings

    return DisplaySettings(timezone="Europe/Zurich")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_nothing_configured_does_nothing_and_never_reads_the_idle_time(env: Env) -> None:
    class Spy(FixedInputProbe):
        called = False

        def idle_seconds(self) -> float | None:
            Spy.called = True
            return 99999

    env.service = WorkdayService(env.storage, lambda: Settings(), Spy(), clock=lambda: env.now)
    env.start(local(8))
    assert env.service.tick(local(23)) == [] and not Spy.called


def test_the_probe_is_only_read_when_idle_detection_is_on(env: Env) -> None:
    env.work = WorkSettings(workday_end="17:30")
    env.start(local(8))

    class Spy(FixedInputProbe):
        called = False

        def idle_seconds(self) -> float | None:
            Spy.called = True
            return None

    env.service = WorkdayService(
        env.storage, lambda: replace(Settings(), work=env.work), Spy(), clock=lambda: env.now
    )
    env.service.tick(local(10))
    assert not Spy.called


def test_auto_stop_ends_at_the_set_time_flags_uncertain_and_asks(env: Env) -> None:
    env.work = WorkSettings(workday_end="17:30")
    env.start(local(9))
    (item,) = env.service.tick(local(17, 45))
    assert item.kind is AttentionKind.AUTO_STOP
    (session,) = env.sessions()
    assert session.ended_at == local(17, 30) and session.quality is Quality.UNCERTAIN
    assert env.service.tick(local(18)) == []  # once


def test_extend_after_an_auto_stop_is_audited_and_bounded(env: Env) -> None:
    env.work = WorkSettings(workday_end="17:30")
    env.start(local(9))
    (item,) = env.service.tick(local(17, 45))
    env.now = local(19)
    for bad in (local(17, 30), local(20), None):
        with pytest.raises(ValidationError):
            env.service.resolve_auto_stop(item.id, STOP_EXTEND, bad)
    closed = env.service.resolve_auto_stop(item.id, STOP_EXTEND, local(18, 30))
    assert closed.resolution == STOP_EXTEND and env.sessions()[0].ended_at == local(18, 30)
    with pytest.raises(InvalidStateError):
        env.service.resolve_auto_stop(item.id, STOP_KEEP)  # already answered
    with env.storage.read() as repos:
        assert "resolve_auto_stop" in [a.action for a in repos.audit.list_all()]


def test_extend_is_refused_when_another_entry_took_the_time(env: Env) -> None:
    env.work = WorkSettings(workday_end="17:30")
    env.start(local(9))
    (item,) = env.service.tick(local(17, 45))
    with env.storage.transaction() as repos:
        repos.sessions.add(
            Session(env.activity, local(17, 40), local(17, 50), source=SessionSource.MANUAL)
        )
    env.now = local(19)
    with pytest.raises(InvalidStateError):
        env.service.resolve_auto_stop(item.id, STOP_EXTEND, local(18, 30))


def test_keep_leaves_the_stop_as_it_is(env: Env) -> None:
    env.work = WorkSettings(workday_end="17:30")
    env.start(local(9))
    (item,) = env.service.tick(local(17, 45))
    env.service.resolve_auto_stop(item.id, STOP_KEEP)
    assert env.sessions()[0].ended_at == local(17, 30) and env.open_items() == []


def idle_item(env: Env):  # type: ignore[no-untyped-def]
    env.work = WorkSettings(idle_minutes=10)
    env.start(local(9))
    env.probe.seconds = 1800
    (item,) = env.service.tick(local(10))
    return item


def test_idle_raises_one_question_with_the_start_of_the_idle_time(env: Env) -> None:
    item = idle_item(env)
    assert item.kind is AttentionKind.IDLE
    assert item.payload["idle_since"] == (local(10) - timedelta(minutes=30)).isoformat()
    assert env.service.tick(local(10, 5)) == []  # not asked again for the same entry


def test_idle_keep_changes_nothing(env: Env) -> None:
    item = idle_item(env)
    env.service.resolve_idle(item.id, IDLE_KEEP)
    assert env.sessions()[0].is_running and env.open_items() == []


def test_idle_discard_ends_the_entry_where_the_idle_time_began(env: Env) -> None:
    item = idle_item(env)
    env.service.resolve_idle(item.id, IDLE_DISCARD)
    (session,) = env.sessions()
    assert session.ended_at == local(9, 30) and session.quality is Quality.UNCERTAIN


def test_idle_pause_ends_it_and_remembers_the_activity(env: Env) -> None:
    item = idle_item(env)
    env.service.resolve_idle(item.id, IDLE_PAUSE)
    with env.storage.read() as repos:
        assert repos.state.get("paused") is not None
    assert env.sessions()[0].ended_at == local(9, 30)


def test_idle_before_the_start_of_the_entry_is_clamped(env: Env) -> None:
    env.work = WorkSettings(idle_minutes=10)
    env.start(local(9, 50))
    env.probe.seconds = 3600  # the idle time began before the entry (started by the cube)
    (item,) = env.service.tick(local(10))
    env.service.resolve_idle(item.id, IDLE_DISCARD)
    assert env.sessions()[0].ended_at == local(9, 50)


def test_idle_answers_validate(env: Env) -> None:
    item = idle_item(env)
    with pytest.raises(ValidationError):
        env.service.resolve_idle(item.id, "fly")
    with env.storage.transaction() as repos:
        repos.sessions.end(repos.sessions.get_running().id, local(9, 40))  # type: ignore[union-attr]
    with pytest.raises(InvalidStateError):
        env.service.resolve_idle(item.id, IDLE_DISCARD)  # the entry no longer runs
    env.service.resolve_idle(item.id, IDLE_KEEP)  # keeping is always possible


def test_reminders_are_raised_once(env: Env) -> None:
    env.work = WorkSettings(reminder_no_timer_after="09:00", reminder_running_hours=2)
    (first,) = env.service.tick(local(9, 5))
    assert first.payload == {"reason": "no_timer"} and env.service.tick(local(9, 10)) == []
    env.start(local(9, 15))
    (second,) = env.service.tick(local(11, 20))
    assert second.payload["reason"] == "running_long" and second.payload["hours"] == 2.1
    assert env.service.tick(local(12)) == []


def test_unknown_questions_cannot_be_answered_with_the_wrong_kind(env: Env) -> None:
    env.work = WorkSettings(reminder_no_timer_after="09:00")
    (item,) = env.service.tick(local(9, 5))
    with pytest.raises(InvalidStateError):
        env.service.resolve_idle(item.id, IDLE_KEEP)


# ------------------------------------------------------------------------ probe


def test_the_fixed_probe_returns_what_was_set() -> None:
    probe = FixedInputProbe(12.5)
    assert probe.idle_seconds() == 12.5
    probe.seconds = None
    assert probe.idle_seconds() is None


def test_the_windows_probe_never_raises_and_returns_a_sane_value() -> None:
    value = WindowsInputProbe().idle_seconds()
    assert value is None or 0 <= value < 10 * 365 * 24 * 3600
