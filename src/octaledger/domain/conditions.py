"""Simple conditions for an action step: a time window and weekdays (pure rules).

A step with a condition is only sent when the condition holds **at the moment the cube is
turned**. Times are the user's local clock. A window may span midnight (22:00 to 06:00); for
such a window the weekday refers to the day on which the window *started*, so "Monday 22:00 to
06:00" still holds on Tuesday at 02:00.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from octaledger.core.errors import ValidationError

_VALID_DAYS = frozenset({"1", "2", "3", "4", "5", "6", "7"})


@dataclass(frozen=True, slots=True)
class Condition:
    """When a step is allowed to run.

    Attributes:
        start: ``HH:MM`` window start, empty for "no time window".
        end: ``HH:MM`` window end (exclusive), empty for "no time window".
        weekdays: Comma-separated ISO weekday numbers (1 = Monday), empty for "every day".
    """

    start: str = ""
    end: str = ""
    weekdays: str = ""

    def __post_init__(self) -> None:
        """Validate and normalise the three parts."""
        start, end = _clock(self.start), _clock(self.end)
        if bool(start) != bool(end):
            raise ValidationError(
                "A time window needs a start and an end",
                user_message="Ein Zeitfenster braucht Beginn und Ende (oder beides leer).",
            )
        days = sorted({d.strip() for d in self.weekdays.split(",") if d.strip()})
        if not set(days) <= _VALID_DAYS:
            raise ValidationError(
                f"Invalid weekdays {self.weekdays!r}",
                user_message="Wochentage sind Zahlen von 1 (Montag) bis 7 (Sonntag).",
            )
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "weekdays", ",".join(days))

    @property
    def is_empty(self) -> bool:
        """Whether the condition restricts nothing."""
        return not (self.start or self.weekdays)

    def to_json(self) -> dict[str, str]:
        """The stored form."""
        return {"start": self.start, "end": self.end, "weekdays": self.weekdays}


def _clock(text: str) -> str:
    if not isinstance(text, str):
        raise ValidationError("Time must be text", user_message="Die Uhrzeit ist ungültig.")
    text = text.strip()
    if not text:
        return ""
    parts = text.split(":")
    if (
        len(parts) != 2
        or not all(p.isdigit() and len(p) in (1, 2) for p in parts)
        or not (0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59)
    ):
        raise ValidationError(
            f"Invalid time {text!r}", user_message="Uhrzeiten haben das Format HH:MM (z. B. 08:30)."
        )
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"


def parse_condition(data: Mapping[str, Any] | None) -> Condition | None:
    """Build a condition from stored/API data (``None`` or an empty one means "always")."""
    if not data:
        return None
    unknown = set(data) - {"start", "end", "weekdays"}
    if unknown:
        raise ValidationError(
            f"Unknown condition keys: {sorted(unknown)}",
            user_message="Die Bedingung enthält unbekannte Angaben.",
        )
    condition = Condition(
        str(data.get("start") or ""), str(data.get("end") or ""), str(data.get("weekdays") or "")
    )
    return None if condition.is_empty else condition


def holds(condition: Condition | None, local: datetime) -> bool:
    """Whether the step may run at ``local`` (an aware datetime in the user's zone)."""
    if condition is None:
        return True
    now = local.time().replace(second=0, microsecond=0)
    weekday = local.isoweekday()
    if condition.start:
        begin = time.fromisoformat(condition.start)
        finish = time.fromisoformat(condition.end)
        if begin < finish:
            inside = begin <= now < finish
        elif begin > finish:
            inside = now >= begin or now < finish
            if inside and now < finish:  # after midnight: the window started yesterday
                weekday = (local - timedelta(days=1)).isoweekday()
        else:
            inside = True  # start == end: the whole day
        if not inside:
            return False
    return not condition.weekdays or str(weekday) in condition.weekdays.split(",")
