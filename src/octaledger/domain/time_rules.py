"""Minimal timezone-aware interval validation."""

from datetime import datetime, timedelta, timezone


def interval_duration(start: datetime, end: datetime) -> timedelta:
    """Calculate elapsed time in UTC, rejecting naive or inverted intervals."""
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Timezone-aware datetimes are required")
    duration = end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
    if duration < timedelta(0):
        raise ValueError("End must not precede start")
    return duration
