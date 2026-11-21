"""Tags, note templates and project billing (budget, hourly rate, billable).

Everything here is optional: an entry without tags and a project without budget behave exactly
as before. Money is stored as **integer cents** and only *computed* from minutes and rate in
reports (rounded there, never in the raw data), so a changed rate never alters stored entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from octaledger.core.errors import ValidationError
from octaledger.domain.models import _check_id, new_id

MAX_TAG_NAME = 50
MAX_TEMPLATE = 500


@dataclass(frozen=True, slots=True)
class Tag:
    """A free label on time entries.

    Attributes:
        name: Unique (case-insensitive) name, 1 to 50 characters.
        color: ``#RRGGBB``.
    """

    name: str
    color: str
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Validate id, name and colour."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        name = self.name.strip() if isinstance(self.name, str) else ""
        if not 1 <= len(name) <= MAX_TAG_NAME or not name.isprintable():
            raise ValidationError(
                f"Invalid tag name {self.name!r}",
                user_message=f"Ein Tag braucht einen Namen mit 1 bis {MAX_TAG_NAME} Zeichen.",
            )
        object.__setattr__(self, "name", name)
        if (
            not isinstance(self.color, str)
            or len(self.color) != 7
            or self.color[0] != "#"
            or any(c not in "0123456789abcdefABCDEF" for c in self.color[1:])
        ):
            raise ValidationError(
                f"Invalid colour {self.color!r}", user_message="Die Farbe muss wie #0072B2 lauten."
            )


@dataclass(frozen=True, slots=True)
class ProjectBilling:
    """Budget and rate of one project.

    Attributes:
        project_id: The project.
        budget_minutes: Planned time, or ``None`` for no budget.
        hourly_rate_cents: Rate per hour in cents, or ``None`` for none.
        billable: Whether the time is billable.
    """

    project_id: str
    budget_minutes: int | None = None
    hourly_rate_cents: int | None = None
    billable: bool = False

    def __post_init__(self) -> None:
        """Validate ranges."""
        object.__setattr__(self, "project_id", _check_id(self.project_id, "project_id"))
        if self.budget_minutes is not None and not 1 <= self.budget_minutes <= 6_000_000:
            raise ValidationError(
                f"Invalid budget {self.budget_minutes!r}",
                user_message="Das Budget muss mindestens 1 Minute betragen.",
            )
        if self.hourly_rate_cents is not None and not 0 <= self.hourly_rate_cents <= 100_000_000:
            raise ValidationError(
                f"Invalid rate {self.hourly_rate_cents!r}",
                user_message="Der Stundensatz ist ungültig.",
            )

    @property
    def is_empty(self) -> bool:
        """Whether nothing is set (the row can be dropped)."""
        return self.budget_minutes is None and self.hourly_rate_cents is None and not self.billable


def amount_cents(duration: timedelta, hourly_rate_cents: int | None) -> int | None:
    """Money for a duration at an hourly rate, rounded **to whole cents here** (reports only).

    Returns ``None`` when there is no rate.
    """
    if hourly_rate_cents is None:
        return None
    return round(duration.total_seconds() / 3600 * hourly_rate_cents)


def budget_fraction(used: timedelta, budget_minutes: int | None) -> float | None:
    """Used share of the budget (``1.0`` = 100 %), or ``None`` without a budget."""
    if budget_minutes is None:
        return None
    return used.total_seconds() / (budget_minutes * 60)
