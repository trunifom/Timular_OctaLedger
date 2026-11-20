"""Timezone-aware time helpers shared by the whole application.

Rules (see ``CLAUDE.md``): inside OctaLedger every point in time is a timezone-aware
``datetime`` normalised to **UTC**. Naive datetimes are rejected on purpose because they
silently depend on the local machine timezone and daylight-saving rules. Conversion to
the user's display timezone happens only at the presentation edge.
"""

from datetime import datetime, timedelta, timezone

from octaledger.core.errors import ValidationError


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


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
    return value.astimezone(timezone.utc)


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
