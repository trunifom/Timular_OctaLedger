"""Managing many entries at once: bulk edit, bulk delete and the change history (AP-57).

Responsibility
--------------
The tracking service changes **one** entry with an audit trail. This service applies the same
rules to **many** entries in a single step - the engine behind the page *Einträge*:

* :meth:`apply` changes activity, project, note, time (shift), quality and tags of the selected
  entries. It is **all or nothing**: one transaction, so a conflict on entry 40 of 50 leaves all
  50 untouched. Every changed field of every entry lands in the ``corrections`` table (the
  same audit trail as a single correction) with the given reason.
* :meth:`delete` removes the finished entries among the selection after an automatic safety
  backup; one summary entry (count and reason) goes into the audit log.
* :meth:`history` merges corrections and audit-log entries into one readable change protocol.

Rules: a running entry is never deleted or shifted (it is still being recorded; it is counted
as *skipped*, never silently changed); every operation needs a reason; at most
:data:`MAX_BULK` entries per call.

Limits: there is no undo button. The undo is the safety backup before a delete (restore on the
page *Daten*) and, for edits, the old values in the change history.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

from octaledger.application.export_service import ExportService
from octaledger.application.tracking_service import FUTURE_TOLERANCE
from octaledger.core.errors import ValidationError
from octaledger.domain.models import Quality
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.repositories import Repositories, Storage

logger = logging.getLogger(__name__)

#: Upper bound of entries per call (keeps one transaction and one request reasonable).
MAX_BULK: Final = 10_000
#: How the note is changed.
NOTE_MODES: Final = frozenset({"keep", "set", "append", "clear"})
#: Largest time shift in one step (one year).
MAX_SHIFT: Final = timedelta(days=366)


@dataclass(frozen=True, slots=True)
class BulkChange:
    """What to change on every selected entry (``None``/empty = leave as it is).

    Attributes:
        activity_id: New activity.
        project_id: New project.
        clear_project: Remove the project (wins over ``project_id``).
        note_mode: ``keep``, ``set`` (replace), ``append`` (add behind) or ``clear``.
        note: Text for ``set`` and ``append``.
        shift_seconds: Move start and end by this many seconds (negative = earlier).
        quality: ``confirmed`` or ``uncertain``.
        tags_add: Tags to add.
        tags_remove: Tags to remove.
        tags_replace: Replace all tags by exactly these (``None`` = do not replace).
    """

    activity_id: str | None = None
    project_id: str | None = None
    clear_project: bool = False
    note_mode: str = "keep"
    note: str | None = None
    shift_seconds: int = 0
    quality: str | None = None
    tags_add: tuple[str, ...] = ()
    tags_remove: tuple[str, ...] = ()
    tags_replace: tuple[str, ...] | None = None

    def is_empty(self) -> bool:
        """True if the change would do nothing at all."""
        return (
            self.activity_id is None
            and self.project_id is None
            and not self.clear_project
            and self.note_mode == "keep"
            and self.shift_seconds == 0
            and self.quality is None
            and not self.tags_add
            and not self.tags_remove
            and self.tags_replace is None
        )


@dataclass(frozen=True, slots=True)
class BulkResult:
    """The outcome of a bulk operation.

    Attributes:
        changed: Entries that really changed.
        unchanged: Entries that already had the wanted values.
        skipped_running: Running entries that were left out (shift/delete never touch them).
        safety_backup: File name of the backup written first (delete only).
    """

    changed: int
    unchanged: int
    skipped_running: int
    safety_backup: str | None = None


@dataclass(frozen=True, slots=True)
class HistoryRow:
    """One line of the change protocol."""

    at: datetime
    kind: str
    session_id: str | None
    field_name: str
    old_value: str | None
    new_value: str | None
    reason: str
    revision: int | None = None
    extra: dict[str, str] = field(default_factory=dict)


class EntryService:
    """Bulk operations on entries and their change history."""

    def __init__(
        self,
        storage: Storage,
        exports: ExportService | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create the service.

        Args:
            storage: The database.
            exports: Used for the safety backup before a delete (``None`` = no backup, tests).
            clock: Source of "now" (injectable for tests).
        """
        self._storage = storage
        self._exports = exports
        self._clock = clock

    # ------------------------------------------------------------------ validation
    @staticmethod
    def _check_ids(ids: Sequence[str]) -> list[str]:
        unique = list(dict.fromkeys(ids))
        if not unique:
            raise ValidationError("No entries selected", user_message="Es ist nichts ausgewählt.")
        if len(unique) > MAX_BULK:
            raise ValidationError(
                "Too many entries",
                user_message=f"Höchstens {MAX_BULK} Einträge auf einmal.",
            )
        return unique

    @staticmethod
    def _check_reason(reason: str) -> str:
        text = reason.strip()
        if not text:
            raise ValidationError(
                "A reason is required", user_message="Bitte einen Grund angeben (Pflicht)."
            )
        return text

    # ----------------------------------------------------------------------- edit
    def apply(self, ids: Sequence[str], change: BulkChange, reason: str) -> BulkResult:
        """Apply ``change`` to every selected entry in one transaction (all or nothing).

        Raises:
            ValidationError: Nothing selected/changed, no reason, bad values, a shift that moves
                an entry into the future.
            NotFoundError: An entry, activity, project or tag does not exist.
            ConflictError: A changed entry would overlap another one.
        """
        selected = self._check_ids(ids)
        why = self._check_reason(reason)
        if change.is_empty():
            raise ValidationError("Nothing to change", user_message="Es wurde nichts geändert.")
        if change.note_mode not in NOTE_MODES:
            raise ValidationError("Unknown note mode", user_message="Unbekannte Notiz-Aktion.")
        shift = timedelta(seconds=change.shift_seconds)
        if abs(shift) > MAX_SHIFT:
            raise ValidationError(
                "Shift too large", user_message="Die Verschiebung darf höchstens ein Jahr betragen."
            )
        now = ensure_utc(self._clock(), name="now")
        changed = unchanged = skipped = 0
        with self._storage.transaction() as repos:
            if change.activity_id is not None:
                repos.activities.require(change.activity_id)
            if change.project_id is not None and not change.clear_project:
                repos.projects.require(change.project_id)
            for tag_id in (*change.tags_add, *change.tags_remove, *(change.tags_replace or ())):
                repos.tags.require(tag_id)
            sessions = [repos.sessions.require(i) for i in selected]
            # Moving entries one by one must not create a temporary overlap between two
            # selected neighbours: later first when moving later, earlier first otherwise.
            sessions.sort(key=lambda s: s.started_at, reverse=shift > timedelta(0))
            for session in sessions:
                if shift and session.is_running:
                    skipped += 1
                    continue
                fields: dict[str, object] = {}
                if change.activity_id is not None:
                    fields["activity_id"] = change.activity_id
                if change.clear_project:
                    fields["project_id"] = None
                elif change.project_id is not None:
                    fields["project_id"] = change.project_id
                if change.quality is not None:
                    fields["quality"] = Quality(change.quality)
                note = self._new_note(session.note, change)
                if change.note_mode != "keep":
                    fields["note"] = note
                if shift:
                    fields["started_at"] = session.started_at + shift
                    if session.ended_at is not None:
                        end = session.ended_at + shift
                        if end > now + FUTURE_TOLERANCE:
                            raise ValidationError(
                                "Shift moves an entry into the future",
                                user_message="Die Verschiebung würde einen Eintrag in die "
                                "Zukunft legen.",
                            )
                        fields["ended_at"] = end
                real = {k: v for k, v in fields.items() if getattr(session, k) != v}
                touched = bool(real)
                if real:
                    repos.sessions.correct(session.id, real, f"Sammelbearbeitung: {why}")
                if self._change_tags(repos, session.id, change):
                    touched = True
                if touched:
                    changed += 1
                else:
                    unchanged += 1
            if changed:
                repos.audit.add("bulk_edit", "sessions", None, f"{changed} entries, reason={why}")
        logger.info("Bulk edit: %d changed, %d unchanged, %d skipped", changed, unchanged, skipped)
        return BulkResult(changed, unchanged, skipped)

    @staticmethod
    def _new_note(old: str | None, change: BulkChange) -> str | None:
        """The note after the change (``None`` = empty)."""
        text = (change.note or "").strip()
        if change.note_mode == "clear":
            return None
        if change.note_mode == "set":
            return text or None
        if change.note_mode == "append" and text:
            return f"{old} {text}" if old else text
        return old

    @staticmethod
    def _change_tags(repos: Repositories, session_id: str, change: BulkChange) -> bool:
        """Apply the tag part of the change; True if the tags of the entry changed."""
        if change.tags_replace is None and not change.tags_add and not change.tags_remove:
            return False
        before = [t.id for t in repos.tags.of_session(session_id)]
        if change.tags_replace is not None:
            after = list(dict.fromkeys(change.tags_replace))
        else:
            after = [t for t in before if t not in set(change.tags_remove)]
            after += [t for t in change.tags_add if t not in after]
        if set(after) == set(before):
            return False
        repos.tags.set_session_tags(session_id, after)
        return True

    # --------------------------------------------------------------------- delete
    def delete(self, ids: Sequence[str], reason: str) -> BulkResult:
        """Delete the finished entries among ``ids`` after an automatic safety backup.

        Raises:
            ValidationError: Nothing selected or no reason.
            NotFoundError: An entry does not exist.
        """
        selected = self._check_ids(ids)
        why = self._check_reason(reason)
        with self._storage.read() as repos:
            sessions = [repos.sessions.require(i) for i in selected]
        running = sum(1 for s in sessions if s.is_running)
        if running == len(sessions):
            raise ValidationError(
                "Only running entries selected",
                user_message="Laufende Einträge werden nicht gelöscht. Beenden Sie sie zuerst.",
            )
        backup = None
        if self._exports is not None:
            stamp = ensure_utc(self._clock()).strftime("%Y%m%d-%H%M%S")
            backup = self._exports.export_backup(
                filename=f"octaledger-pre-delete-{stamp}.json"
            ).path.name
        with self._storage.transaction() as repos:
            deleted = repos.sessions.delete_many(selected, why, repos.audit)
        logger.info(
            "Bulk delete: %d deleted, %d running left out, backup %s", deleted, running, backup
        )
        return BulkResult(deleted, 0, running, backup)

    # -------------------------------------------------------------------- history
    def history(self, *, session_id: str | None = None, limit: int = 300) -> list[HistoryRow]:
        """The change protocol, newest first: corrections and audit-log entries together.

        Raises:
            ValidationError: If ``limit`` is not between 1 and 5000.
        """
        if not 1 <= limit <= 5000:
            raise ValidationError("limit must be 1..5000")
        with self._storage.read() as repos:
            names = {a.id: a.name for a in repos.activities.list_all(include_archived=True)}
            names |= {p.id: p.name for p in repos.projects.list_all(include_archived=True)}
            rows = [
                HistoryRow(
                    c.corrected_at,
                    "Korrektur",
                    c.session_id,
                    c.field_name,
                    names.get(c.old_value or "", c.old_value),
                    names.get(c.new_value or "", c.new_value),
                    c.reason,
                    c.revision,
                )
                for c in repos.sessions.list_corrections(session_id)
            ]
            if session_id is None:
                rows += [
                    HistoryRow(a.at, "Aktion", a.entity_id, a.action, None, None, a.detail or "")
                    for a in repos.audit.recent(limit)
                    if a.entity in ("session", "sessions")
                ]
        rows.sort(key=lambda r: r.at, reverse=True)
        return rows[:limit]
