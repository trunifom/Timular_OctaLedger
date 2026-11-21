"""Data management: look at what is stored, delete it deliberately, remove a cube, start over.

Responsibility
--------------
The export/backup service saves data; this service **removes** it. Removal is irreversible, so
every operation follows the same safety pattern (research-based, see ``docs/FORTSCHRITT.md``
AP-33):

1. **Preview first.** :meth:`preview_entries` names exactly what a deletion would touch (count,
   period, how many carry a note, whether a running entry is left out).
2. **Confirmation by number.** The caller passes the count it was shown (``expected_count``). If
   the data changed in the meantime the operation is refused instead of deleting something else.
3. **Automatic safety backup.** Before anything is deleted a complete JSON backup is written to
   the backup folder, and its name is returned. Undoing a deletion therefore means restoring
   that backup (page *Daten*), which is the one undo that always works.
4. **One transaction.** A failure leaves everything as it was.
5. **Audit trail.** One summary entry per operation goes into the audit log.

Running entries are never deleted by a bulk operation (they are still being recorded).

Limits: the safety backup contains the data *before* the deletion, so it is as private as the
data itself; and ``secrets.json`` (credentials of connections) is not part of any backup.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from octaledger.application.device_service import DeviceService
from octaledger.application.export_service import ExportService
from octaledger.application.integration_service import IntegrationService
from octaledger.application.tracking_service import STATE_ACTIVE_DEVICE
from octaledger.core.errors import InvalidStateError, ValidationError
from octaledger.core.settings import Settings, SettingsStore
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.repositories import BackupContent, RangeStats, Storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DataOverview:
    """How much of everything is stored (the numbers on the data page)."""

    sessions: int
    running_sessions: int
    raw_events: int
    devices: int
    activities: int
    projects: int
    integrations: int
    first_session: datetime | None
    last_session: datetime | None


@dataclass(frozen=True, slots=True)
class DeleteResult:
    """What a deletion removed and where the safety backup is."""

    sessions: int
    raw_events: int
    safety_backup: str


@dataclass(frozen=True, slots=True)
class DeviceRemoval:
    """What removing a cube removed."""

    sessions: int
    raw_events: int
    safety_backup: str | None


@dataclass(frozen=True, slots=True)
class ResetResult:
    """What a factory reset removed."""

    counts: dict[str, int]
    safety_backup: str
    settings_reset: bool


class DataService:
    """Deliberate deletion of recorded data (see the module docstring for the safety rules)."""

    def __init__(
        self,
        storage: Storage,
        exports: ExportService,
        integrations: IntegrationService | None = None,
        settings: SettingsStore | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create the service.

        Args:
            storage: The database.
            exports: Writes the safety backups.
            integrations: Needed to forget stored credentials on a factory reset.
            settings: Needed to restore default settings on a factory reset.
            clock: Time source (injectable for tests).
        """
        self._storage = storage
        self._exports = exports
        self._integrations = integrations
        self._settings = settings
        self._clock = clock

    # ------------------------------------------------------------------ look

    def overview(self) -> DataOverview:
        """Count what is stored."""
        with self._storage.read() as repos:
            stats = repos.sessions.range_stats()
            running = len([s for s in [repos.sessions.get_running()] if s is not None])
            return DataOverview(
                sessions=repos.sessions.count_all(),
                running_sessions=running,
                raw_events=repos.events.count(),
                devices=len(repos.devices.list_all()),
                activities=len(repos.activities.list_all(include_archived=True)),
                projects=len(repos.projects.list_all(include_archived=True)),
                integrations=len(repos.integrations.list_all()),
                first_session=stats.first,
                last_session=stats.last,
            )

    def preview_entries(self, start: datetime | None, end: datetime | None) -> RangeStats:
        """What deleting the finished entries that started in ``[start, end)`` would touch."""
        start, end = self._window(start, end)
        with self._storage.read() as repos:
            return repos.sessions.range_stats(start, end)

    # ---------------------------------------------------------------- delete

    def delete_entries(
        self,
        start: datetime | None,
        end: datetime | None,
        *,
        expected_count: int,
        include_events: bool = False,
    ) -> DeleteResult:
        """Delete finished entries that started in ``[start, end)``, after a safety backup.

        Args:
            start: Inclusive lower bound; ``None`` = from the beginning.
            end: Exclusive upper bound; ``None`` = until now and later.
            expected_count: The count the user was shown; a different current count aborts.
            include_events: Also delete the raw tracker observations of the same period.

        Raises:
            InvalidStateError: If the data changed since the preview, or nothing matches.
            ValidationError: If ``end`` is not after ``start``.
        """
        start, end = self._window(start, end)
        stats = self.preview_entries(start, end)
        if stats.count == 0:
            raise InvalidStateError(
                "Nothing to delete in this range",
                user_message="In diesem Zeitraum gibt es keine Einträge zum Löschen.",
            )
        if stats.count != expected_count:
            raise InvalidStateError(
                f"Expected {expected_count} entries, found {stats.count}",
                user_message=(
                    f"Die Anzahl hat sich geändert (jetzt {stats.count} statt "
                    f"{expected_count}). Bitte die Vorschau erneut ansehen."
                ),
            )
        backup = self._safety_backup("pre-delete")
        with self._storage.transaction() as repos:
            deleted = repos.sessions.delete_range(start, end, repos.audit)
            events = repos.events.delete_range(start, end, repos.audit) if include_events else 0
        logger.info("Deleted %d entries and %d events (backup %s)", deleted, events, backup)
        return DeleteResult(sessions=deleted, raw_events=events, safety_backup=backup)

    def remove_device(self, device_id: str, *, delete_data: bool) -> DeviceRemoval:
        """Remove a cube; with ``delete_data`` also everything recorded with it.

        Without ``delete_data`` a cube that has recorded data is refused (the data would lose
        its cube). The face assignments and actions of the cube always go with it.

        Raises:
            NotFoundError: If the cube does not exist.
            ConflictError: If it has data and ``delete_data`` is false.
        """
        with self._storage.read() as repos:
            device = repos.devices.require(device_id)
        if not delete_data:
            self._remove_plain(device_id)
            return DeviceRemoval(sessions=0, raw_events=0, safety_backup=None)
        backup = self._safety_backup("pre-remove-device")
        with self._storage.transaction() as repos:
            sessions = repos.sessions.delete_all_of_device(device_id, repos.audit)
            events = repos.events.delete_all_of_device(device_id)
            repos.devices.delete(device_id, repos.audit)
            if repos.state.get(STATE_ACTIVE_DEVICE) == device_id:
                repos.state.delete(STATE_ACTIVE_DEVICE)
        logger.info("Removed cube %s with %d entries (backup %s)", device.alias, sessions, backup)
        return DeviceRemoval(sessions=sessions, raw_events=events, safety_backup=backup)

    def _remove_plain(self, device_id: str) -> None:
        """Remove a cube that has no data (delegates to the device service rules)."""
        DeviceService(self._storage).remove(device_id)

    def factory_reset(self, *, reset_settings: bool = True) -> ResetResult:
        """Delete **everything**: entries, cubes, activities, projects, connections, credentials.

        A complete backup is written first. Settings return to their defaults when
        ``reset_settings`` is true. The audit log and the app state are emptied as well.
        """
        backup = self._safety_backup("pre-reset")
        with self._storage.transaction() as repos:
            counts = repos.backup.snapshot().counts()
            integration_ids = [i.id for i in repos.integrations.list_all()]
            repos.backup.replace_all(BackupContent())
        if self._integrations is not None:
            self._integrations.forget_secrets(integration_ids)
        if reset_settings and self._settings is not None:
            self._settings.update(Settings())
        logger.warning("Factory reset done (backup %s)", backup)
        return ResetResult(counts=counts, safety_backup=backup, settings_reset=reset_settings)

    # --------------------------------------------------------------- helpers

    def _safety_backup(self, label: str) -> str:
        stamp = ensure_utc(self._clock()).strftime("%Y%m%d-%H%M%S")
        return self._exports.export_backup(filename=f"octaledger-{label}-{stamp}.json").path.name

    @staticmethod
    def _window(
        start: datetime | None, end: datetime | None
    ) -> tuple[datetime | None, datetime | None]:
        start = None if start is None else ensure_utc(start, name="start")
        end = None if end is None else ensure_utc(end, name="end")
        if start is not None and end is not None and end <= start:
            raise ValidationError(
                "End must be after start",
                user_message="Das Ende muss nach dem Anfang liegen.",
            )
        return start, end
