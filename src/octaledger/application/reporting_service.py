"""Timezone-aware reports without accidental overlap sums.

Responsibility
--------------
Aggregate sessions for the dashboard's statistics and journal pages:

* **Day / week windows** in the user's display timezone (daylight-saving aware).
* Sessions that cross a window edge or midnight are **clipped and split** so every day gets
  exactly the time that really lies inside it.
* **Device time vs. personal time** (Pflichtenheft section 6): *device time* sums every
  session; *personal time* is the **union** of all intervals, so overlaps are counted once.
  The two are reported separately and never added together.
* **Uncertainty is shown, not hidden**: time of sessions flagged ``uncertain`` is reported
  separately so the user can see how much of a total still needs confirmation.
* A running session is measured up to "now" (injectable clock).

:func:`build_report` is a pure function (easy to test with synthetic, even overlapping
sessions); :class:`ReportService` loads the data and calls it.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from octaledger.core.errors import ValidationError
from octaledger.domain.models import Activity, Project, Quality, Session
from octaledger.domain.time_rules import (
    Interval,
    clip_interval,
    ensure_utc,
    local_day_bounds,
    local_week_bounds,
    parse_timezone,
    split_at_day_boundaries,
    sum_durations,
    union_duration,
    utc_now,
)
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

#: Longest report window in days (protects the GUI and the daily bar chart).
MAX_REPORT_DAYS = 400
#: Bucket label for time without a project.
NO_PROJECT_NAME = "Ohne Projekt"
#: Neutral colour for the "no project" bucket.
NO_PROJECT_COLOR = "#9E9E9E"


@dataclass(frozen=True, slots=True)
class ReportFilter:
    """Which sessions and which time window a report covers.

    Attributes:
        start: Window start (UTC, inclusive).
        end: Window end (UTC, exclusive); must be after ``start``.
        device_id / activity_id / project_id: Optional exact-match filters.
    """

    start: datetime
    end: datetime
    device_id: str | None = None
    activity_id: str | None = None
    project_id: str | None = None

    def __post_init__(self) -> None:
        """Normalise to UTC and validate the window."""
        object.__setattr__(self, "start", ensure_utc(self.start, name="start"))
        object.__setattr__(self, "end", ensure_utc(self.end, name="end"))
        if self.end <= self.start:
            raise ValidationError(
                "Report window must have positive length",
                user_message="Das Ende des Zeitraums muss nach dem Beginn liegen.",
            )


@dataclass(frozen=True, slots=True)
class DayTotal:
    """Time of one local calendar day."""

    day: date
    device_time: timedelta
    personal_time: timedelta
    uncertain_time: timedelta


@dataclass(frozen=True, slots=True)
class Share:
    """Time attributed to one activity or project."""

    id: str | None
    name: str
    color: str
    duration: timedelta
    uncertain: timedelta
    fraction: float  # share of the total device time (0..1)


@dataclass(frozen=True, slots=True)
class Report:
    """Aggregated result for a window and filter."""

    window: Interval
    timezone: str
    daily: tuple[DayTotal, ...]
    by_activity: tuple[Share, ...]
    by_project: tuple[Share, ...]
    device_time: timedelta
    personal_time: timedelta
    uncertain_time: timedelta
    session_count: int
    includes_running: bool

    @property
    def overlap_time(self) -> timedelta:
        """Time counted by several devices at once (``device_time - personal_time``)."""
        return self.device_time - self.personal_time


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """One whole session with resolved names for the journal table."""

    session: Session
    activity_name: str
    project_name: str | None
    device_alias: str | None
    duration: timedelta


def _local_dates(window: Interval, tz: ZoneInfo) -> list[date]:
    """Return every local calendar day touched by ``window`` (capped)."""
    first = window[0].astimezone(tz).date()
    last = (window[1] - timedelta(microseconds=1)).astimezone(tz).date()
    days = (last - first).days + 1
    if days > MAX_REPORT_DAYS:
        raise ValidationError(
            f"Report window too long: {days} days",
            user_message=f"Der Zeitraum ist zu lang (höchstens {MAX_REPORT_DAYS} Tage).",
            details={"days": days},
        )
    return [first + timedelta(days=i) for i in range(days)]


def _shares(
    buckets: Mapping[str | None, tuple[timedelta, timedelta]],
    names: Callable[[str | None], tuple[str, str]],
    total: timedelta,
) -> tuple[Share, ...]:
    """Build sorted :class:`Share` rows from ``{id: (duration, uncertain)}``."""
    rows = [
        Share(
            id=key,
            name=names(key)[0],
            color=names(key)[1],
            duration=duration,
            uncertain=uncertain,
            fraction=(duration / total) if total > timedelta(0) else 0.0,
        )
        for key, (duration, uncertain) in buckets.items()
    ]
    return tuple(sorted(rows, key=lambda r: (-r.duration, r.name.lower())))


def build_report(
    sessions: Iterable[Session],
    activities: Mapping[str, Activity],
    projects: Mapping[str, Project],
    flt: ReportFilter,
    tz: ZoneInfo,
    *,
    now: datetime,
) -> Report:
    """Aggregate ``sessions`` for ``flt`` in timezone ``tz`` (pure function).

    Sessions are first filtered (device/activity/project), then clipped to the window and
    split at local midnights. Running sessions end at ``now``.

    Args:
        sessions: Candidate sessions (may extend beyond the window).
        activities: Activities by id (names and colours).
        projects: Projects by id.
        flt: Window and filters.
        tz: Display timezone.
        now: Current time, the end of running sessions.

    Raises:
        ValidationError: If the window covers more than :data:`MAX_REPORT_DAYS` days.
    """
    window: Interval = (flt.start, flt.end)
    now = ensure_utc(now, name="now")
    dates = _local_dates(window, tz)

    per_day_all: dict[date, list[Interval]] = defaultdict(list)
    per_day_uncertain: dict[date, list[Interval]] = defaultdict(list)
    activity_buckets: dict[str | None, list[timedelta]] = defaultdict(lambda: [timedelta(0)] * 2)
    project_buckets: dict[str | None, list[timedelta]] = defaultdict(lambda: [timedelta(0)] * 2)
    all_parts: list[Interval] = []
    uncertain_parts: list[Interval] = []
    count = 0
    running = False

    for session in sessions:
        if flt.device_id is not None and session.device_id != flt.device_id:
            continue
        if flt.activity_id is not None and session.activity_id != flt.activity_id:
            continue
        if flt.project_id is not None and session.project_id != flt.project_id:
            continue
        end = session.ended_at if session.ended_at is not None else max(now, session.started_at)
        clipped = clip_interval((session.started_at, end), window)
        if clipped is None:
            continue
        count += 1
        running = running or session.is_running
        is_uncertain = session.quality is Quality.UNCERTAIN
        for day, part in split_at_day_boundaries(clipped[0], clipped[1], tz):
            length = part[1] - part[0]
            per_day_all[day].append(part)
            all_parts.append(part)
            for buckets, key in (
                (activity_buckets, session.activity_id),
                (project_buckets, session.project_id),
            ):
                buckets[key][0] += length
            if is_uncertain:
                per_day_uncertain[day].append(part)
                uncertain_parts.append(part)
                activity_buckets[session.activity_id][1] += length
                project_buckets[session.project_id][1] += length

    daily = tuple(
        DayTotal(
            day=day,
            device_time=sum_durations(per_day_all.get(day, [])),
            personal_time=union_duration(per_day_all.get(day, [])),
            uncertain_time=union_duration(per_day_uncertain.get(day, [])),
        )
        for day in dates
    )
    device_total = sum_durations(all_parts)

    def activity_name(key: str | None) -> tuple[str, str]:
        """Display name and colour of an activity id ("Unbekannt" if it is gone)."""
        activity = activities.get(key) if key else None
        return (activity.name, activity.color) if activity else ("Unbekannt", NO_PROJECT_COLOR)

    def project_name(key: str | None) -> tuple[str, str]:
        """Display name and colour of a project id ("ohne Projekt" if none)."""
        project = projects.get(key) if key else None
        return (project.name, project.color) if project else (NO_PROJECT_NAME, NO_PROJECT_COLOR)

    return Report(
        window=window,
        timezone=tz.key,
        daily=daily,
        by_activity=_shares(
            {k: (v[0], v[1]) for k, v in activity_buckets.items()}, activity_name, device_total
        ),
        by_project=_shares(
            {k: (v[0], v[1]) for k, v in project_buckets.items()}, project_name, device_total
        ),
        device_time=device_total,
        personal_time=union_duration(all_parts),
        uncertain_time=union_duration(uncertain_parts),
        session_count=count,
        includes_running=running,
    )


class ReportService:
    """Loads data and builds reports and journal listings."""

    def __init__(self, storage: Storage, *, clock: Callable[[], datetime] = utc_now) -> None:
        """Create the service (``clock`` is injectable for tests)."""
        self._storage = storage
        self._clock = clock

    def report(self, flt: ReportFilter, timezone_name: str = "UTC") -> Report:
        """Build a report for ``flt`` displayed in ``timezone_name``.

        Raises:
            ValidationError: For an unknown timezone or a too long window.
        """
        tz = parse_timezone(timezone_name)
        with self._storage.read() as repos:
            sessions = repos.sessions.list_between(
                flt.start,
                flt.end,
                device_id=flt.device_id,
                activity_id=flt.activity_id,
                project_id=flt.project_id,
            )
            activities = {a.id: a for a in repos.activities.list_all(include_archived=True)}
            projects = {p.id: p for p in repos.projects.list_all(include_archived=True)}
        return build_report(sessions, activities, projects, flt, tz, now=self._clock())

    def day_report(self, day: date, timezone_name: str = "UTC", **filters: str | None) -> Report:
        """Report for one local calendar day (23-25 h on daylight-saving days)."""
        start, end = local_day_bounds(day, parse_timezone(timezone_name))
        return self.report(ReportFilter(start, end, **filters), timezone_name)

    def week_report(
        self,
        day: date,
        timezone_name: str = "UTC",
        *,
        week_starts_on: int = 0,
        **filters: str | None,
    ) -> Report:
        """Report for the local week containing ``day`` (Monday start by default)."""
        start, end = local_week_bounds(
            day, parse_timezone(timezone_name), week_starts_on=week_starts_on
        )
        return self.report(ReportFilter(start, end, **filters), timezone_name)

    def journal(self, flt: ReportFilter) -> list[JournalEntry]:
        """Return whole sessions overlapping the window with resolved names (newest first)."""
        now = ensure_utc(self._clock(), name="now")
        with self._storage.read() as repos:
            sessions = repos.sessions.list_between(
                flt.start,
                flt.end,
                device_id=flt.device_id,
                activity_id=flt.activity_id,
                project_id=flt.project_id,
            )
            activities = {a.id: a.name for a in repos.activities.list_all(include_archived=True)}
            projects = {p.id: p.name for p in repos.projects.list_all(include_archived=True)}
            devices = {d.id: d.alias for d in repos.devices.list_all()}
        entries = [
            JournalEntry(
                session=s,
                activity_name=activities.get(s.activity_id, "Unbekannt"),
                project_name=projects.get(s.project_id) if s.project_id else None,
                device_alias=devices.get(s.device_id) if s.device_id else None,
                duration=s.duration(now),
            )
            for s in sessions
        ]
        return sorted(entries, key=lambda e: e.session.started_at, reverse=True)
