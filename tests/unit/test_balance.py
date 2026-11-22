"""Target working time, balance, absences and break hints (AP-40)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from octaledger.application.reporting_service import ReportService
from octaledger.application.work_time_service import WorkTimeService
from octaledger.application.workday_service import WorkdayService
from octaledger.core.errors import ConfigurationError, NotFoundError, ValidationError
from octaledger.core.settings import DisplaySettings, Settings, WorkSettings
from octaledger.domain.attention import AttentionKind
from octaledger.domain.break_rules import (
    SOURCES,
    BreakRegion,
    required_break_minutes,
    summarize_day,
)
from octaledger.domain.models import Activity, Session, SessionSource
from octaledger.domain.schedule import (
    Absence,
    AbsenceKind,
    WorkSchedule,
    schedule_for,
    target_minutes,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from octaledger.infrastructure.system.holidays_provider import holiday_dates, holidays_available

UTC = UTC
TZ = ZoneInfo("Europe/Zurich")
FULL = WorkSchedule(date(2026, 1, 1), (480, 480, 480, 480, 480, 0, 0))  # Mon-Fri 8 h
MON = date(2026, 1, 5)


# ------------------------------------------------------------------- pure rules


def test_target_follows_the_weekday_of_the_valid_schedule() -> None:
    assert target_minutes(MON, [FULL], []) == 480
    assert target_minutes(date(2026, 1, 10), [FULL], []) == 0  # Saturday
    assert target_minutes(date(2025, 12, 31), [FULL], []) == 0  # before any schedule
    assert target_minutes(MON, [], []) == 0


def test_a_later_schedule_does_not_change_earlier_days() -> None:
    part_time = WorkSchedule(date(2026, 2, 1), (240, 240, 240, 240, 240, 0, 0))
    assert schedule_for(date(2026, 1, 31), [FULL, part_time]) == FULL
    assert target_minutes(date(2026, 1, 30), [FULL, part_time], []) == 480
    assert target_minutes(date(2026, 2, 2), [FULL, part_time], []) == 240
    assert schedule_for(date(2026, 2, 1), [part_time, FULL]) == part_time  # order does not matter


def test_absence_holiday_and_half_holiday_override_the_schedule() -> None:
    vacation = Absence(MON, MON + timedelta(days=1), AbsenceKind.VACATION)
    half = Absence(date(2026, 1, 7), date(2026, 1, 7), AbsenceKind.HOLIDAY_CUSTOM, 240)
    assert target_minutes(MON, [FULL], [vacation]) == 0
    assert target_minutes(date(2026, 1, 7), [FULL], [half]) == 240
    assert target_minutes(date(2026, 1, 8), [FULL], [vacation, half]) == 480
    assert target_minutes(MON, [FULL], [], frozenset({MON})) == 0  # public holiday
    # an absence wins over the public holiday list (half holiday on a listed holiday)
    assert (
        target_minutes(MON, [FULL], [Absence(MON, MON, AbsenceKind.OTHER, 120)], frozenset({MON}))
        == 120
    )


def test_overlapping_absences_use_the_smallest_target() -> None:
    a = Absence(MON, MON, AbsenceKind.OTHER, 300)
    b = Absence(MON, MON, AbsenceKind.SICK)
    assert target_minutes(MON, [FULL], [a, b]) == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"minutes": (480,) * 6},
        {"minutes": (480, 480, 480, 480, 480, 0, 1441)},
        {"minutes": (480, 480, 480, 480, 480, 0, -1)},
    ],
)
def test_invalid_schedules_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        WorkSchedule(MON, **bad)  # type: ignore[arg-type]


def test_invalid_absences_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Absence(MON, MON - timedelta(days=1), AbsenceKind.OTHER)
    with pytest.raises(ValidationError):
        Absence(MON, MON, AbsenceKind.OTHER, 2000)
    with pytest.raises(ValidationError):
        Absence(MON, MON, AbsenceKind.OTHER, note="x" * 501)
    with pytest.raises(ValueError):
        Absence(MON, MON, "party")  # type: ignore[arg-type]


# ------------------------------------------------------------------ break rules


@pytest.mark.parametrize(
    ("region", "minutes", "required"),
    [
        (BreakRegion.CH, 330, 0),  # exactly 5.5 h: not "more than"
        (BreakRegion.CH, 331, 15),
        (BreakRegion.CH, 420, 15),
        (BreakRegion.CH, 421, 30),
        (BreakRegion.CH, 541, 60),
        (BreakRegion.EU, 360, 0),
        (BreakRegion.EU, 361, 20),
        (BreakRegion.OFF, 999, 0),
    ],
)
def test_break_thresholds(region: BreakRegion, minutes: float, required: int) -> None:
    assert required_break_minutes(region, minutes) == required


def test_every_table_names_its_source_and_status() -> None:
    assert SOURCES[BreakRegion.CH] and "Stand" in SOURCES[BreakRegion.CH]
    assert "2003/88" in SOURCES[BreakRegion.EU]


def test_summarize_day_counts_only_gaps_between_entries() -> None:
    t = datetime(2026, 1, 5, 7, tzinfo=UTC)
    h = timedelta(hours=1)
    worked, rest = summarize_day([(t, t + 3 * h), (t + 3.5 * h, t + 6 * h), (t + 5 * h, t + 7 * h)])
    assert (worked, rest) == (6.5 * 60, 30)  # the overlap is merged, the gap is a break
    assert summarize_day([]) == (0.0, 0.0)
    assert summarize_day([(t, t + h)]) == (60.0, 0.0)  # nothing before/after counts as a break


# ---------------------------------------------------------------------- balance


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.now = datetime(2026, 1, 9, 20, tzinfo=UTC)
        self.reports = ReportService(self.storage, clock=lambda: self.now)
        self.work = WorkTimeService(self.storage)
        with self.storage.transaction() as repos:
            self.activity = repos.activities.add(Activity(name="Code")).id

    def add(self, start: datetime, end: datetime | None) -> None:
        with self.storage.transaction() as repos:
            repos.sessions.add(Session(self.activity, start, end, source=SessionSource.MANUAL))


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, minute, tzinfo=TZ).astimezone(UTC)


def test_balance_target_actual_and_running_total(env: Env) -> None:
    env.work.set_schedule(date(2026, 1, 1), [480, 480, 480, 480, 480, 0, 0])
    env.add(at(5, 8), at(5, 17))  # Monday 9 h
    env.add(at(6, 8), at(6, 14))  # Tuesday 6 h
    result = env.reports.balance(date(2026, 1, 5), date(2026, 1, 6), "Europe/Zurich")
    monday, tuesday = result.days
    assert (monday.actual, monday.target, monday.difference) == (
        timedelta(hours=9),
        timedelta(hours=8),
        timedelta(hours=1),
    )
    assert tuesday.difference == timedelta(hours=-2) and tuesday.balance == timedelta(hours=-1)
    assert result.difference == timedelta(hours=-1) and result.has_schedule


def test_holiday_and_absence_reduce_the_target_and_show_a_reason(env: Env) -> None:
    env.work.set_schedule(date(2026, 1, 1), [480] * 5 + [0, 0])
    env.work.add_absence(date(2026, 1, 6), date(2026, 1, 6), "vacation")
    env.work.add_absence(date(2026, 1, 7), date(2026, 1, 7), "holiday_custom", 240, "halber Tag")
    result = env.reports.balance(date(2026, 1, 5), date(2026, 1, 7), "Europe/Zurich")
    assert [d.target for d in result.days] == [
        timedelta(hours=8),
        timedelta(0),
        timedelta(hours=4),
    ]
    assert [d.reason for d in result.days] == ["", "Ferien", "Feiertag (eigener)"]


def test_without_a_schedule_the_target_is_zero(env: Env) -> None:
    env.add(at(5, 8), at(5, 9))
    result = env.reports.balance(date(2026, 1, 5), date(2026, 1, 5), "Europe/Zurich")
    assert not result.has_schedule and result.target == timedelta(0)
    assert result.actual == timedelta(hours=1)


def test_a_running_entry_counts_until_now_and_overlaps_are_not_double_counted(env: Env) -> None:
    env.work.set_schedule(date(2026, 1, 1), [480] * 5 + [0, 0])
    env.now = at(5, 12)
    env.add(at(5, 8), None)  # running: 4 h so far
    result = env.reports.balance(date(2026, 1, 5), date(2026, 1, 5), "Europe/Zurich")
    assert result.includes_running and result.days[0].actual == timedelta(hours=4)


def test_midnight_is_cut_at_the_local_boundary(env: Env) -> None:
    env.work.set_schedule(date(2026, 1, 1), [0] * 7)
    env.add(at(5, 22), at(6, 2))  # crosses local midnight: 2 h each day
    result = env.reports.balance(date(2026, 1, 5), date(2026, 1, 6), "Europe/Zurich")
    assert [d.actual for d in result.days] == [timedelta(hours=2), timedelta(hours=2)]


def test_a_daylight_saving_day_has_23_hours(env: Env) -> None:
    zurich = ZoneInfo("Europe/Zurich")
    start = datetime(2026, 3, 29, 0, 0, tzinfo=zurich).astimezone(UTC)
    env.now = datetime(2026, 4, 2, tzinfo=UTC)
    env.add(start, datetime(2026, 3, 30, 0, 0, tzinfo=zurich).astimezone(UTC))  # the whole day
    result = env.reports.balance(date(2026, 3, 29), date(2026, 3, 29), "Europe/Zurich")
    assert result.days[0].actual == timedelta(hours=23)


def test_balance_validates_its_input(env: Env) -> None:
    with pytest.raises(ValidationError):
        env.reports.balance(date(2026, 1, 6), date(2026, 1, 5), "UTC")
    with pytest.raises(ValidationError):
        env.reports.balance(date(2026, 1, 5), date(2026, 1, 5), "Mars/Base")


# ---------------------------------------------------------------- the service


def test_schedule_versions_and_audit(env: Env) -> None:
    env.work.set_schedule(date(2026, 1, 1), [480] * 5 + [0, 0])
    versions = env.work.set_schedule(date(2026, 2, 1), [240] * 5 + [0, 0])
    assert [s.valid_from for s in versions] == [date(2026, 1, 1), date(2026, 2, 1)]
    env.work.set_schedule(date(2026, 2, 1), [300] * 5 + [0, 0])  # replace, not add
    assert len(env.work.list_schedules()) == 2
    assert len(env.work.delete_schedule(date(2026, 2, 1))) == 1
    with env.storage.read() as repos:
        assert {"set_schedule", "delete_schedule"} <= {a.action for a in repos.audit.list_all()}
    with pytest.raises(ValidationError):
        env.work.set_schedule(date(2026, 3, 1), [480] * 6)


def test_absence_crud_and_errors(env: Env) -> None:
    absence = env.work.add_absence(date(2026, 1, 5), date(2026, 1, 9), "sick", note=" Grippe ")
    assert absence.note == "Grippe" and env.work.list_absences() == [absence]
    with pytest.raises(ValidationError):
        env.work.add_absence(date(2026, 1, 5), date(2026, 1, 9), "party")
    with pytest.raises(ValidationError):
        env.work.add_absence(date(2026, 1, 9), date(2026, 1, 5), "sick")
    env.work.delete_absence(absence.id)
    assert env.work.list_absences() == []
    with pytest.raises(NotFoundError):
        env.work.delete_absence(absence.id)


# -------------------------------------------------------------------- holidays


def test_no_region_or_package_means_no_holidays() -> None:
    assert holiday_dates("", date(2026, 1, 1), date(2026, 12, 31)) == frozenset()
    assert holiday_dates("ZZ-NOPE", date(2026, 1, 1), date(2026, 12, 31)) == frozenset()


@pytest.mark.skipif(not holidays_available(), reason="optional package not installed")
def test_holidays_of_a_swiss_canton() -> None:
    found = holiday_dates("CH-ZH", date(2026, 1, 1), date(2026, 12, 31))
    assert date(2026, 1, 1) in found and date(2026, 8, 1) in found


def test_work_settings_validate_the_new_fields() -> None:
    assert WorkSettings().holiday_region == "" and WorkSettings().break_region == "off"
    assert WorkSettings(holiday_region="ch-zh").holiday_region == "CH-ZH"
    for bad in ({"holiday_region": "Schweiz"}, {"break_region": "mars"}):
        with pytest.raises(ConfigurationError):
            WorkSettings(**bad)  # type: ignore[arg-type]


# ------------------------------------------------------------------ break hint


class Hint:
    def __init__(self, env: Env, region: str = "ch") -> None:
        self.env = env
        self.work = WorkSettings(break_region=region)
        self.service = WorkdayService(
            env.storage,
            lambda: replace(
                Settings(), work=self.work, display=DisplaySettings(timezone="Europe/Zurich")
            ),
            probe=_NoProbe(),
        )


class _NoProbe:
    def idle_seconds(self) -> float | None:
        return None


def test_a_long_day_without_a_break_raises_one_hint(env: Env) -> None:
    hint = Hint(env)
    env.add(at(5, 8), at(5, 14, 30))  # 6.5 h in one block
    (item,) = hint.service.tick(at(5, 15))
    assert item.kind is AttentionKind.BREAK_HINT
    assert item.payload["required_minutes"] == 15 and item.payload["recorded_minutes"] == 0
    assert hint.service.tick(at(5, 16)) == []  # once per day
    assert [i.kind for i in hint.service.tick(at(6, 15))] == []  # next day: nothing worked yet


def test_a_recorded_break_or_a_short_day_raises_nothing(env: Env) -> None:
    hint = Hint(env)
    env.add(at(5, 8), at(5, 11))
    env.add(at(5, 11, 30), at(5, 15))  # 30 min break, 6.5 h work
    assert hint.service.tick(at(5, 16)) == []
    env.add(at(6, 8), at(6, 12))  # 4 h only
    assert hint.service.tick(at(6, 13)) == []


def test_break_hints_are_off_by_default(env: Env) -> None:
    hint = Hint(env, region="off")
    env.add(at(5, 8), at(5, 18))
    assert hint.service.tick(at(5, 19)) == []
