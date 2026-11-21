"""Target working time: weekly schedule, absences and holidays (pure rules).

The balance of a day is *actual minus target*. The target comes from the weekday schedule that
was valid on that day, **minus** public holidays and absences: a whole absence or holiday day
has target 0 unless the absence says otherwise (for example a half holiday: 240 minutes).

Schedules are versioned by their start date, so changing them (part-time from a date) never
alters earlier balances. All dates are local calendar dates; nothing here knows about UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from octaledger.core.errors import ValidationError
from octaledger.domain.models import new_id

#: Minutes in a day: the upper bound of any target.
MINUTES_PER_DAY = 1440
WEEKDAY_NAMES = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


class AbsenceKind(StrEnum):
    """Why a day has a different target."""

    VACATION = "vacation"
    SICK = "sick"
    #: A holiday that is not in the public list (company day off, half holiday ...).
    HOLIDAY_CUSTOM = "holiday_custom"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class WorkSchedule:
    """Target minutes per weekday, valid from ``valid_from`` until a later schedule starts.

    Attributes:
        valid_from: First local date the schedule applies to.
        minutes: Seven values, Monday first, each ``0..1440``.
    """

    valid_from: date
    minutes: tuple[int, int, int, int, int, int, int]

    def __post_init__(self) -> None:
        """Validate the seven values."""
        if len(self.minutes) != 7 or not all(
            isinstance(m, int) and not isinstance(m, bool) and 0 <= m <= MINUTES_PER_DAY
            for m in self.minutes
        ):
            raise ValidationError(
                f"Invalid schedule minutes: {self.minutes!r}",
                user_message="Das Soll je Wochentag muss zwischen 0 und 24 Stunden liegen.",
            )


@dataclass(frozen=True, slots=True)
class Absence:
    """A period (inclusive) with a different target.

    Attributes:
        start: First local date.
        end: Last local date (not before ``start``).
        kind: The reason.
        target_minutes: Target of each day in the period; ``None`` means 0 (whole day off).
        note: Optional short text.
    """

    start: date
    end: date
    kind: AbsenceKind
    target_minutes: int | None = None
    note: str | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Validate order, kind, target and note length."""
        object.__setattr__(self, "kind", AbsenceKind(self.kind))
        if self.end < self.start:
            raise ValidationError(
                "Absence ends before it starts",
                user_message="Das Ende der Abwesenheit liegt vor dem Beginn.",
            )
        if self.target_minutes is not None and not 0 <= self.target_minutes <= MINUTES_PER_DAY:
            raise ValidationError(
                f"Invalid target minutes {self.target_minutes!r}",
                user_message="Das Soll muss zwischen 0 und 24 Stunden liegen.",
            )
        if self.note is not None and len(self.note) > 500:
            raise ValidationError(
                "Absence note too long",
                user_message="Die Notiz ist zu lang (höchstens 500 Zeichen).",
            )

    def covers(self, day: date) -> bool:
        """Whether ``day`` lies inside the period."""
        return self.start <= day <= self.end


def schedule_for(day: date, schedules: list[WorkSchedule]) -> WorkSchedule | None:
    """Return the schedule valid on ``day`` (the latest one that started on or before it)."""
    valid = [s for s in schedules if s.valid_from <= day]
    return max(valid, key=lambda s: s.valid_from) if valid else None


def target_minutes(
    day: date,
    schedules: list[WorkSchedule],
    absences: list[Absence],
    holidays: frozenset[date] = frozenset(),
) -> int:
    """Target minutes of one local day.

    The order of precedence: an absence covering the day (its target, or 0), else a public
    holiday (0), else the weekday value of the valid schedule, else 0 (nothing configured).
    If several absences cover the day, the smallest target wins.
    """
    covering = [a for a in absences if a.covers(day)]
    if covering:
        return min(a.target_minutes if a.target_minutes is not None else 0 for a in covering)
    if day in holidays:
        return 0
    schedule = schedule_for(day, schedules)
    return schedule.minutes[day.weekday()] if schedule is not None else 0
