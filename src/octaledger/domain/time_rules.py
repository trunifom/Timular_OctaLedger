"""Minimal timezone-aware interval validation.

All durations are computed in UTC. Naive datetimes are rejected on purpose because they
silently depend on the local machine timezone and daylight-saving rules.
"""

from datetime import datetime, timedelta, timezone

from octaledger.core.errors import ValidationError


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
    duration = end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
    if duration < timedelta(0):
        raise ValidationError("End must not precede start")
    return duration
