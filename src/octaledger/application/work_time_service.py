"""Target working time: the weekly schedule and absences (use cases).

Thin transactional wrapper around the schedule and absence repositories. Changes are audited
(who changed which target and when is part of understanding an overtime balance later).
"""

from __future__ import annotations

import logging
from datetime import date

from octaledger.core.errors import ConflictError, ValidationError
from octaledger.domain.schedule import Absence, AbsenceKind, WorkSchedule
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

#: Upper bound for the number of stored schedule versions and absences (keeps lists usable).
MAX_ABSENCES = 5000
MAX_SCHEDULES = 200


class WorkTimeService:
    """Schedule and absence management."""

    def __init__(self, storage: Storage) -> None:
        """Create the service on top of ``storage``."""
        self._storage = storage

    # --------------------------------------------------------------------- schedule

    def list_schedules(self) -> list[WorkSchedule]:
        """Return all schedule versions, oldest first."""
        with self._storage.read() as repos:
            return repos.schedule.list_all()

    def set_schedule(self, valid_from: date, minutes: list[int]) -> list[WorkSchedule]:
        """Create or replace the schedule that starts on ``valid_from``.

        Args:
            valid_from: First local date it applies to.
            minutes: Seven target values (Monday first) in minutes.

        Raises:
            ValidationError: For anything but seven values in ``0..1440``.
            ConflictError: If the maximum number of versions would be exceeded.
        """
        if len(minutes) != 7:
            raise ValidationError(
                f"Expected 7 values, got {len(minutes)}",
                user_message="Das Soll braucht sieben Werte, einen je Wochentag.",
            )
        schedule = WorkSchedule(valid_from, tuple(minutes))  # type: ignore[arg-type]
        with self._storage.transaction() as repos:
            known = repos.schedule.list_all()
            if len(known) >= MAX_SCHEDULES and all(s.valid_from != valid_from for s in known):
                raise ConflictError(
                    "Too many schedule versions",
                    user_message="Es gibt schon sehr viele Soll-Versionen; löschen Sie alte.",
                )
            repos.schedule.set(schedule)
            repos.audit.add("set_schedule", "work_schedule", valid_from.isoformat(), str(minutes))
            return repos.schedule.list_all()

    def delete_schedule(self, valid_from: date) -> list[WorkSchedule]:
        """Remove one schedule version (earlier days then use the version before it)."""
        with self._storage.transaction() as repos:
            repos.schedule.delete(valid_from)
            repos.audit.add("delete_schedule", "work_schedule", valid_from.isoformat())
            return repos.schedule.list_all()

    # --------------------------------------------------------------------- absences

    def list_absences(self) -> list[Absence]:
        """Return all absences, oldest first."""
        with self._storage.read() as repos:
            return repos.absences.list_all()

    def add_absence(
        self,
        start: date,
        end: date,
        kind: str,
        target_minutes: int | None = None,
        note: str | None = None,
    ) -> Absence:
        """Record an absence (vacation, sick days, own holiday ...).

        Raises:
            ValidationError: For an unknown kind, a reversed period or a bad target.
            ConflictError: If the maximum number of absences would be exceeded.
        """
        try:
            parsed = AbsenceKind(kind)
        except ValueError:
            raise ValidationError(
                f"Unknown absence kind {kind!r}", user_message="Unbekannte Art der Abwesenheit."
            ) from None
        absence = Absence(start, end, parsed, target_minutes, (note or "").strip() or None)
        with self._storage.transaction() as repos:
            if len(repos.absences.list_all()) >= MAX_ABSENCES:
                raise ConflictError(
                    "Too many absences",
                    user_message="Es gibt schon sehr viele Abwesenheiten; löschen Sie alte.",
                )
            repos.absences.add(absence)
            repos.audit.add("add_absence", "absence", absence.id, f"{start} {end} {kind}")
        logger.info("Absence added: %s", kind)
        return absence

    def delete_absence(self, absence_id: str) -> None:
        """Remove an absence.

        Raises:
            NotFoundError: If it does not exist.
        """
        with self._storage.transaction() as repos:
            repos.absences.delete(absence_id)
            repos.audit.add("delete_absence", "absence", absence_id)
