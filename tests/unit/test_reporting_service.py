"""Tests for reports: clipping, midnight/DST splitting, overlap handling, uncertainty, filters."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from octaledger.application.reporting_service import (
    MAX_REPORT_DAYS,
    NO_PROJECT_NAME,
    ReportFilter,
    ReportService,
    build_report,
)
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import ValidationError
from octaledger.domain.models import Activity, Device, Project, Quality, Session, SessionSource
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

UTC = timezone.utc
ZURICH = ZoneInfo("Europe/Zurich")
H = timedelta(hours=1)
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

MEETING = Activity(name="Meeting", color="#112233")
CODE = Activity(name="Code", color="#445566")
ALPHA = Project(name="Alpha", color="#778899")
ACTIVITIES = {MEETING.id: MEETING, CODE.id: CODE}
PROJECTS = {ALPHA.id: ALPHA}


def at(day: int, hour: int, minute: int = 0, month: int = 1) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


def session(
    start: datetime, end: datetime | None, activity: Activity = MEETING, **kw: object
) -> Session:
    return Session(activity_id=activity.id, started_at=start, ended_at=end, **kw)  # type: ignore[arg-type]


def report(
    sessions: list[Session],
    start: datetime,
    end: datetime,
    tz: ZoneInfo = ZoneInfo("UTC"),
    **filters: str | None,
):  # type: ignore[no-untyped-def]
    return build_report(
        sessions, ACTIVITIES, PROJECTS, ReportFilter(start, end, **filters), tz, now=NOW
    )


# -------------------------------------------------------------------------------- basics


def test_simple_day_totals_and_shares() -> None:
    result = report(
        [session(at(5, 8), at(5, 10)), session(at(5, 10), at(5, 11), CODE, project_id=ALPHA.id)],
        at(5, 0),
        at(6, 0),
    )
    assert result.device_time == result.personal_time == 3 * H
    assert result.session_count == 2 and not result.includes_running
    assert [s.name for s in result.by_activity] == ["Meeting", "Code"]  # biggest first
    assert result.by_activity[0].fraction == pytest.approx(2 / 3)
    assert result.by_activity[0].color == "#112233"
    assert {s.name: s.duration for s in result.by_project} == {NO_PROJECT_NAME: 2 * H, "Alpha": H}
    assert sum(s.fraction for s in result.by_activity) == pytest.approx(1.0)
    (day,) = result.daily
    assert day.day == date(2026, 1, 5) and day.device_time == 3 * H


def test_empty_report() -> None:
    result = report([], at(5, 0), at(8, 0))
    assert result.device_time == timedelta(0) and result.session_count == 0
    assert [d.day for d in result.daily] == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    assert all(d.device_time == timedelta(0) for d in result.daily)
    assert result.by_activity == () and result.by_project == ()


def test_sessions_are_clipped_to_the_window() -> None:
    result = report([session(at(5, 6), at(5, 12))], at(5, 8), at(5, 10))
    assert result.device_time == 2 * H


def test_sessions_outside_window_are_ignored() -> None:
    result = report([session(at(4, 6), at(4, 12)), session(at(6, 0), at(6, 2))], at(5, 0), at(6, 0))
    assert result.session_count == 0 and result.device_time == timedelta(0)


def test_running_session_measured_until_now() -> None:
    running = session(datetime(2026, 6, 1, 9, tzinfo=UTC), None)
    result = report(
        [running], datetime(2026, 6, 1, 0, tzinfo=UTC), datetime(2026, 6, 2, 0, tzinfo=UTC)
    )
    assert result.device_time == 3 * H and result.includes_running


def test_running_session_not_extended_beyond_window_end() -> None:
    running = session(datetime(2026, 6, 1, 9, tzinfo=UTC), None)
    result = report(
        [running], datetime(2026, 6, 1, 0, tzinfo=UTC), datetime(2026, 6, 1, 10, tzinfo=UTC)
    )
    assert result.device_time == H


# ------------------------------------------------------------- midnight and DST (local)


def test_session_across_local_midnight_is_split_between_days() -> None:
    start = datetime(2026, 1, 15, 22, tzinfo=ZURICH)
    result = report([session(start, start + 5 * H)], start - H, start + 10 * H, ZURICH)
    assert [(d.day, d.device_time) for d in result.daily] == [
        (date(2026, 1, 15), 2 * H),
        (date(2026, 1, 16), 3 * H),
    ]
    assert result.device_time == 5 * H


def test_utc_midnight_is_not_local_midnight() -> None:
    # 23:30-00:30 UTC is 00:30-01:30 local (CET): the whole hour belongs to the 15th locally.
    result = report([session(at(14, 23, 30), at(15, 0, 30))], at(14, 0), at(16, 0), ZURICH)
    assert {d.day: d.device_time for d in result.daily if d.device_time} == {date(2026, 1, 15): H}


def test_dst_day_has_23_hours_of_possible_time() -> None:
    day_start = datetime(2026, 3, 29, 0, tzinfo=ZURICH)
    day_end = datetime(2026, 3, 30, 0, tzinfo=ZURICH)
    result = report([session(day_start, day_end)], day_start, day_end, ZURICH)
    assert result.device_time == 23 * H  # the real elapsed time of that local day


# ------------------------------------------------------------ overlap: device vs personal


def test_overlapping_sessions_are_not_double_counted_as_personal_time() -> None:
    a = session(at(5, 8), at(5, 10))
    b = session(at(5, 9), at(5, 11), CODE)  # synthetic overlap (two devices)
    result = report([a, b], at(5, 0), at(6, 0))
    assert result.device_time == 4 * H  # sum of device times
    assert result.personal_time == 3 * H  # union: 08:00-11:00
    assert result.overlap_time == H
    (day,) = result.daily
    assert (day.device_time, day.personal_time) == (4 * H, 3 * H)


def test_touching_sessions_have_no_overlap() -> None:
    result = report(
        [session(at(5, 8), at(5, 9)), session(at(5, 9), at(5, 10), CODE)], at(5, 0), at(6, 0)
    )
    assert result.overlap_time == timedelta(0)


# ----------------------------------------------------------------------------- uncertainty


def test_uncertain_time_is_reported_separately() -> None:
    result = report(
        [
            session(at(5, 8), at(5, 9), quality=Quality.UNCERTAIN),
            session(at(5, 9), at(5, 11), CODE),
        ],
        at(5, 0),
        at(6, 0),
    )
    assert result.uncertain_time == H and result.device_time == 3 * H
    assert result.daily[0].uncertain_time == H
    meeting = next(s for s in result.by_activity if s.name == "Meeting")
    code = next(s for s in result.by_activity if s.name == "Code")
    assert meeting.uncertain == H and code.uncertain == timedelta(0)


# ---------------------------------------------------------------------------------- filters


def test_filters_by_activity_project_and_device() -> None:
    d1, d2 = "dev-1", "dev-2"
    sessions = [
        session(at(5, 8), at(5, 9), MEETING, device_id=d1, source=SessionSource.DEVICE),
        session(
            at(5, 9),
            at(5, 11),
            CODE,
            project_id=ALPHA.id,
            device_id=d2,
            source=SessionSource.DEVICE,
        ),
        session(at(5, 11), at(5, 12), CODE),
    ]
    window = (at(5, 0), at(6, 0))
    assert report(sessions, *window, activity_id=CODE.id).device_time == 3 * H
    assert report(sessions, *window, project_id=ALPHA.id).device_time == 2 * H
    assert report(sessions, *window, device_id=d1).device_time == H
    assert report(sessions, *window, activity_id=CODE.id, device_id=d2).device_time == 2 * H
    assert report(sessions, *window, device_id="nobody").session_count == 0


def test_unknown_activity_gets_placeholder_name() -> None:
    ghost = Session(activity_id="gone", started_at=at(5, 8), ended_at=at(5, 9))
    result = report([ghost], at(5, 0), at(6, 0))
    assert result.by_activity[0].name == "Unbekannt"


# ------------------------------------------------------------------------------ validation


def test_filter_validation() -> None:
    with pytest.raises(ValidationError):
        ReportFilter(at(5, 8), at(5, 8))
    with pytest.raises(ValidationError):
        ReportFilter(at(5, 9), at(5, 8))
    with pytest.raises(ValidationError):
        ReportFilter(datetime(2026, 1, 5), at(6, 0))


def test_window_too_long_rejected() -> None:
    start = at(1, 0)
    with pytest.raises(ValidationError, match="too long"):
        report([], start, start + timedelta(days=MAX_REPORT_DAYS + 1))
    assert len(report([], start, start + timedelta(days=MAX_REPORT_DAYS)).daily) == MAX_REPORT_DAYS


# --------------------------------------------------------------------------- the service


@pytest.fixture
def service_env(tmp_path: Path):  # type: ignore[no-untyped-def]
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    with storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Büro"))
        meeting = repos.activities.add(Activity(name="Meeting"))
        code = repos.activities.add(Activity(name="Code"))
        project = repos.projects.add(Project(name="Alpha"))
    clock = [NOW]
    tracking = TrackingService(storage, clock=lambda: clock[0])
    reports = ReportService(storage, clock=lambda: clock[0])
    return storage, tracking, reports, device, meeting, code, project, clock


def test_service_week_and_day_reports(service_env) -> None:  # type: ignore[no-untyped-def]
    _, tracking, reports, _, meeting, code, project, clock = service_env
    clock[0] = datetime(2026, 6, 10, 12, tzinfo=UTC)
    tracking.add_manual_session(
        meeting.id, datetime(2026, 6, 8, 8, tzinfo=UTC), datetime(2026, 6, 8, 10, tzinfo=UTC)
    )
    tracking.add_manual_session(
        code.id,
        datetime(2026, 6, 9, 9, tzinfo=UTC),
        datetime(2026, 6, 9, 10, 30, tzinfo=UTC),
        project_id=project.id,
    )
    week = reports.week_report(date(2026, 6, 10), "UTC")  # Wednesday -> week of Monday 8 June
    assert week.device_time == timedelta(hours=3, minutes=30)
    assert [d.day for d in week.daily][0] == date(2026, 6, 8) and len(week.daily) == 7
    assert reports.day_report(date(2026, 6, 9)).device_time == timedelta(hours=1, minutes=30)
    assert reports.day_report(date(2026, 6, 9), activity_id=meeting.id).device_time == timedelta(0)
    sunday_week = reports.week_report(date(2026, 6, 10), "UTC", week_starts_on=6)
    assert sunday_week.daily[0].day == date(2026, 6, 7)


def test_service_invalid_timezone(service_env) -> None:  # type: ignore[no-untyped-def]
    _, _, reports, *_ = service_env
    with pytest.raises(ValidationError):
        reports.day_report(date(2026, 6, 1), "Mars/Olympus")


def test_service_includes_running_and_uses_timezone(service_env) -> None:  # type: ignore[no-untyped-def]
    _, tracking, reports, _, meeting, _, _, clock = service_env
    clock[0] = datetime(2026, 6, 1, 9, tzinfo=UTC)
    tracking.start_manual(meeting.id)
    clock[0] = datetime(2026, 6, 1, 11, tzinfo=UTC)
    result = reports.day_report(date(2026, 6, 1), "Europe/Zurich")
    assert result.includes_running and result.device_time == 2 * H
    assert result.timezone == "Europe/Zurich"


def test_journal_lists_whole_sessions_newest_first_with_names(service_env) -> None:  # type: ignore[no-untyped-def]
    storage, tracking, reports, device, meeting, code, project, clock = service_env
    clock[0] = datetime(2026, 6, 10, 18, tzinfo=UTC)
    tracking.add_manual_session(
        meeting.id, datetime(2026, 6, 8, 8, tzinfo=UTC), datetime(2026, 6, 8, 9, tzinfo=UTC)
    )
    with storage.transaction() as repos:
        repos.sessions.add(
            Session(
                activity_id=code.id,
                project_id=project.id,
                device_id=device.id,
                started_at=datetime(2026, 6, 9, 8, tzinfo=UTC),
                ended_at=datetime(2026, 6, 9, 10, tzinfo=UTC),
                source=SessionSource.DEVICE,
            )
        )
    entries = reports.journal(
        ReportFilter(datetime(2026, 6, 8, tzinfo=UTC), datetime(2026, 6, 10, tzinfo=UTC))
    )
    assert [e.activity_name for e in entries] == ["Code", "Meeting"]  # newest first
    assert entries[0].project_name == "Alpha" and entries[0].device_alias == "Büro"
    assert entries[1].project_name is None and entries[1].device_alias is None
    assert entries[0].duration == 2 * H
    # A session crossing the window edge is listed whole, not clipped.
    edge = reports.journal(
        ReportFilter(datetime(2026, 6, 9, 9, tzinfo=UTC), datetime(2026, 6, 9, 9, 30, tzinfo=UTC))
    )
    assert len(edge) == 1 and edge[0].duration == 2 * H
