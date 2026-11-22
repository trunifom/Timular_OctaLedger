"""Timezone-aware time helpers shared by the whole application.

Rules (see ``CLAUDE.md``): inside OctaLedger every point in time is a timezone-aware
``datetime`` normalised to **UTC**. Naive datetimes are rejected on purpose because they
silently depend on the local machine timezone and daylight-saving rules. Conversion to
the user's display timezone happens only at the presentation edge.
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from octaledger.core.errors import ValidationError


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(value: datetime, *, name: str = "datetime") -> datetime:
    """Normalise ``value`` to UTC, rejecting naive datetimes.

    Args:
        value: A timezone-aware datetime in any timezone.
        name: Field name used in the error message.

    Returns:
        The same instant expressed in UTC.

    Raises:
        ValidationError: If ``value`` is not a datetime or has no timezone.
    """
    if not isinstance(value, datetime):
        raise ValidationError(f"{name} must be a datetime", details={"field": name})
    if value.utcoffset() is None:
        raise ValidationError(
            f"{name} must be timezone-aware",
            user_message="Zeitangaben benötigen eine Zeitzone.",
            details={"field": name},
        )
    return value.astimezone(UTC)


def interval_duration(start: datetime, end: datetime) -> timedelta:
    """Calculate elapsed time in UTC, rejecting naive or inverted intervals.

    Args:
        start: Interval start (timezone-aware).
        end: Interval end (timezone-aware, not before ``start``).

    Returns:
        The non-negative elapsed time.

    Raises:
        ValidationError: If a datetime is naive or ``end`` precedes ``start``.
            ``ValidationError`` is also a ``ValueError``.
    """
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValidationError("Timezone-aware datetimes are required")
    duration = end.astimezone(UTC) - start.astimezone(UTC)
    if duration < timedelta(0):
        raise ValidationError("End must not precede start")
    return duration


# --------------------------------------------------------------------------------------
# Interval algebra used by reports: day splitting, overlap detection, union, windows.
# --------------------------------------------------------------------------------------

Interval = tuple[datetime, datetime]
"""A half-open time span ``[start, end)``; both ends timezone-aware UTC."""


def parse_timezone(name: str) -> ZoneInfo:
    """Return the IANA timezone ``name`` (e.g. ``Europe/Zurich``).

    Raises:
        ValidationError: If the name is empty or unknown.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("Timezone name must not be empty")
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValidationError(
            f"Unknown timezone: {name!r}",
            user_message=f"Die Zeitzone „{name}“ ist unbekannt (Beispiel: Europe/Zurich).",
            details={"timezone": name},
        ) from exc


def _local_midnight_utc(day: date, tz: ZoneInfo) -> datetime:
    """Return the first instant of local calendar ``day`` as UTC.

    If midnight does not exist (a DST gap at midnight), the instant maps to the first
    valid moment after the gap, which is the correct start of that day.
    """
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)


def local_day_bounds(day: date, tz: ZoneInfo) -> Interval:
    """Return ``[start, end)`` of the local calendar ``day`` in UTC.

    The span is 23, 24 or 25 hours long around daylight-saving changes.
    """
    return _local_midnight_utc(day, tz), _local_midnight_utc(day + timedelta(days=1), tz)


def local_week_bounds(day: date, tz: ZoneInfo, *, week_starts_on: int = 0) -> Interval:
    """Return ``[start, end)`` of the local week containing ``day`` in UTC.

    Args:
        day: Any day of the week.
        tz: Display timezone.
        week_starts_on: ``0`` = Monday (default, ISO), ``6`` = Sunday.

    Raises:
        ValidationError: If ``week_starts_on`` is not ``0..6``.
    """
    if not 0 <= week_starts_on <= 6:
        raise ValidationError("week_starts_on must be 0..6")
    offset = (day.weekday() - week_starts_on) % 7
    first = day - timedelta(days=offset)
    return _local_midnight_utc(first, tz), _local_midnight_utc(first + timedelta(days=7), tz)


def validate_interval(start: datetime, end: datetime) -> Interval:
    """Normalise an interval to UTC and reject naive or inverted spans."""
    interval_duration(start, end)  # raises ValidationError for naive / inverted
    return ensure_utc(start), ensure_utc(end)


def clip_interval(interval: Interval, window: Interval) -> Interval | None:
    """Return the part of ``interval`` inside ``window`` or ``None`` if disjoint."""
    start = max(interval[0], window[0])
    end = min(interval[1], window[1])
    return (start, end) if start < end else None


def split_at_day_boundaries(
    start: datetime, end: datetime, tz: ZoneInfo
) -> list[tuple[date, Interval]]:
    """Split ``[start, end)`` at local midnights of ``tz``.

    Reports must assign multi-day sessions to the days they actually touched
    (Datenmodell: "zeitraumübergreifende Sitzungen an Grenzen aufteilen"). Daylight-saving
    changes are handled because boundaries are computed from the local calendar.

    Args:
        start: Interval start (aware).
        end: Interval end (aware, not before ``start``).
        tz: Display timezone.

    Returns:
        ``(local_date, (part_start_utc, part_end_utc))`` pairs in chronological order.
        The parts are contiguous and their durations add up to the original duration.
        A zero-length interval yields a single zero-length part.

    Raises:
        ValidationError: For naive or inverted intervals.
    """
    start_utc, end_utc = validate_interval(start, end)
    day = start_utc.astimezone(tz).date()
    if start_utc == end_utc:
        return [(day, (start_utc, end_utc))]
    parts: list[tuple[date, Interval]] = []
    cursor = start_utc
    while cursor < end_utc:
        _, day_end = local_day_bounds(day, tz)
        part_end = min(day_end, end_utc)
        if part_end > cursor:
            parts.append((day, (cursor, part_end)))
            cursor = part_end
        day += timedelta(days=1)
    return parts


def merge_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    """Return the union of ``intervals`` as sorted, non-overlapping spans.

    Touching spans (end == next start) are merged. Empty spans are dropped.
    """
    ordered = sorted((i for i in intervals if i[0] < i[1]), key=lambda i: i[0])
    merged: list[Interval] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            last_start, last_end = merged[-1]
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def union_duration(intervals: Iterable[Interval]) -> timedelta:
    """Total time covered by ``intervals`` **without counting overlaps twice**.

    This is the correct "personal working time" when several devices overlap, as opposed
    to :func:`sum_durations`, the sum of device times (Pflichtenheft section 6).
    """
    return sum((end - start for start, end in merge_intervals(intervals)), timedelta(0))


def sum_durations(intervals: Iterable[Interval]) -> timedelta:
    """Plain sum of the lengths of ``intervals`` (overlaps counted per interval)."""
    return sum((end - start for start, end in intervals), timedelta(0))


def find_overlaps(items: Iterable[tuple[str, Interval]]) -> list[tuple[str, str]]:
    """Return id pairs whose intervals overlap (touching spans do not overlap).

    Args:
        items: ``(identifier, interval)`` pairs.

    Returns:
        Pairs ``(earlier_id, later_id)`` ordered by start time of the first element.
    """
    ordered = sorted(items, key=lambda item: item[1][0])
    overlaps: list[tuple[str, str]] = []
    for index, (first_id, (_, first_end)) in enumerate(ordered):
        for second_id, (second_start, _) in ordered[index + 1 :]:
            if second_start >= first_end:
                break  # sorted by start: no later item can overlap this one
            overlaps.append((first_id, second_id))
    return overlaps
