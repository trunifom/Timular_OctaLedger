"""Transactional storage and audit persistence.

Responsibility
--------------
Translate between domain models and SQL rows. **All SQL of the application lives here and
in** ``database.py`` (never in services or the GUI) and is always parametrised.

Structure
---------
* Each repository wraps one ``sqlite3.Connection``; it does not open or commit anything
  itself. Transaction boundaries belong to the caller (the services), so several
  repository calls can succeed or fail **together**.
* :class:`Storage` is the entry point: ``with storage.transaction() as repos`` gives a
  :class:`Repositories` bundle bound to one atomic write transaction, ``with
  storage.read() as repos`` one for reading.
* Rows that no longer satisfy the domain rules (e.g. edited by hand) are reported as
  :class:`~octaledger.core.errors.DataIntegrityError` instead of leaking invalid objects.
* Multi-statement operations (correction, deletion with audit entry) use a ``SAVEPOINT``
  so they are atomic on their own and compose inside an outer transaction.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sqlite3
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, TypeVar

from octaledger.core.errors import (
    DataIntegrityError,
    NotFoundError,
    ValidationError,
)
from octaledger.domain.attention import AttentionItem, AttentionKind, AttentionStatus
from octaledger.domain.models import (
    Activity,
    ButtonAction,
    ButtonPress,
    Correction,
    Device,
    EventKind,
    FaceAction,
    FaceMapping,
    Integration,
    IntegrationJob,
    JobStatus,
    Project,
    Quality,
    RawEvent,
    Session,
    SessionSource,
    new_id,
)
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.database import Database, translate_sqlite_error

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Far-future sentinel used for "still running" in range queries (matches the SQL triggers).
_FAR_FUTURE: Final = "9999-12-31T23:59:59.999999Z"
#: Session fields that may be changed through :meth:`SessionRepository.correct`.
CORRECTABLE_FIELDS: Final = frozenset(
    {"activity_id", "project_id", "started_at", "ended_at", "note", "quality"}
)


# ----------------------------------------------------------------------------- helpers


def to_db_time(value: datetime) -> str:
    """Encode an aware datetime as fixed-width UTC text ``YYYY-MM-DDTHH:MM:SS.ffffffZ``.

    The fixed width makes plain string comparison equal to chronological comparison, which
    the database indexes, range queries and triggers rely on.
    """
    return ensure_utc(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def from_db_time(text: str) -> datetime:
    """Decode text produced by :func:`to_db_time`.

    Raises:
        DataIntegrityError: If the text is not in the expected format.
    """
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError) as exc:
        raise DataIntegrityError(
            f"Invalid timestamp in database: {text!r}", details={"value": str(text)}
        ) from exc


@contextmanager
def _db_errors(action: str) -> Iterator[None]:
    """Translate ``sqlite3`` errors raised inside the block."""
    try:
        yield
    except sqlite3.Error as exc:
        raise translate_sqlite_error(exc, action) from exc


@contextmanager
def _savepoint(connection: sqlite3.Connection, name: str) -> Iterator[None]:
    """Run the block atomically; works inside or outside an outer transaction."""
    connection.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        connection.execute(f"ROLLBACK TO {name}")
        connection.execute(f"RELEASE {name}")
        raise
    connection.execute(f"RELEASE {name}")


def _load(factory: Callable[[], T], what: str, row_id: object) -> T:
    """Build a domain object from a row; invalid stored data becomes DataIntegrityError."""
    try:
        return factory()
    except (ValidationError, ValueError, KeyError) as exc:
        raise DataIntegrityError(
            f"Stored {what} {row_id!r} violates domain rules: {exc}",
            details={"entity": what, "id": str(row_id)},
        ) from exc


def _opt_time(text: str | None) -> datetime | None:
    return None if text is None else from_db_time(text)


# ----------------------------------------------------------------------------- devices


class DeviceRepository:
    """Persistence of registered trackers."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection (transaction control stays with the caller)."""
        self._c = connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Device:
        return _load(
            lambda: Device(
                id=row["id"],
                alias=row["alias"],
                platform_address=row["platform_address"],
                model=row["model"],
                firmware=row["firmware"],
                created_at=from_db_time(row["created_at"]),
                mode=row["mode"],
            ),
            "device",
            row["id"],
        )

    def add(self, device: Device) -> Device:
        """Insert a device.

        Raises:
            ConflictError: If the alias is already used.
        """
        with _db_errors("insert device"):
            self._c.execute(
                "INSERT INTO devices (id, alias, platform_address, model, firmware, created_at, "
                "mode) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    device.id,
                    device.alias,
                    device.platform_address,
                    device.model,
                    device.firmware,
                    to_db_time(device.created_at),
                    device.mode.value,
                ),
            )
        logger.info("Device registered: %s (%s)", device.alias, device.id[:8])
        return device

    def get(self, device_id: str) -> Device | None:
        """Return the device or ``None``."""
        with _db_errors("read device"):
            row = self._c.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return None if row is None else self._from_row(row)

    def require(self, device_id: str) -> Device:
        """Return the device or raise :class:`NotFoundError`."""
        device = self.get(device_id)
        if device is None:
            raise NotFoundError(f"Device {device_id} not found", details={"id": device_id})
        return device

    def list_all(self) -> list[Device]:
        """Return all devices ordered by alias."""
        with _db_errors("list devices"):
            rows = self._c.execute("SELECT * FROM devices ORDER BY alias COLLATE NOCASE").fetchall()
        return [self._from_row(r) for r in rows]

    def update(self, device: Device) -> Device:
        """Update alias, address, model, firmware and mode of an existing device.

        Raises:
            NotFoundError: If the device does not exist.
            ConflictError: If the new alias is already used.
        """
        with _db_errors("update device"):
            cursor = self._c.execute(
                "UPDATE devices SET alias = ?, platform_address = ?, model = ?, firmware = ?, "
                "mode = ? WHERE id = ?",
                (
                    device.alias,
                    device.platform_address,
                    device.model,
                    device.firmware,
                    device.mode.value,
                    device.id,
                ),
            )
        if cursor.rowcount == 0:
            raise NotFoundError(f"Device {device.id} not found", details={"id": device.id})
        return device

    def delete(self, device_id: str, audit: AuditLogRepository | None = None) -> None:
        """Delete a device (and its face mappings).

        Raises:
            NotFoundError: If missing.
            ConflictError: If events or sessions still reference it (retention rule).
        """
        device = self.require(device_id)
        with _savepoint(self._c, "delete_device"):
            with _db_errors("delete device"):
                self._c.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            if audit is not None:
                audit.add("delete", "device", device_id, f"alias={device.alias}")
        logger.info("Device deleted: %s", device_id[:8])


# --------------------------------------------------------- activities and projects


class _NamedRepository[M: (Activity, Project)]:
    """Shared implementation for activities and projects (identical table shape)."""

    _table: str
    _entity: str
    _model: type[M]

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    def _from_row(self, row: sqlite3.Row) -> M:
        return _load(
            lambda: self._model(
                id=row["id"],
                name=row["name"],
                color=row["color"],
                archived=bool(row["archived"]),
            ),
            self._entity,
            row["id"],
        )

    def add(self, item: M) -> M:
        """Insert an item.

        Raises:
            ConflictError: If a non-archived item with the same name exists.
        """
        with _db_errors(f"insert {self._entity}"):
            self._c.execute(
                f"INSERT INTO {self._table} (id, name, color, archived) VALUES (?, ?, ?, ?)",  # noqa: S608
                (item.id, item.name, item.color, int(item.archived)),
            )
        logger.info("%s created: %s", self._entity.capitalize(), item.name)
        return item

    def get(self, item_id: str) -> M | None:
        """Return the item or ``None``."""
        with _db_errors(f"read {self._entity}"):
            row = self._c.execute(
                f"SELECT * FROM {self._table} WHERE id = ?",  # noqa: S608
                (item_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def require(self, item_id: str) -> M:
        """Return the item or raise :class:`NotFoundError`."""
        item = self.get(item_id)
        if item is None:
            raise NotFoundError(f"{self._entity} {item_id} not found", details={"id": item_id})
        return item

    def list_all(self, *, include_archived: bool = False) -> list[M]:
        """Return items ordered by name (archived ones only on request)."""
        sql = f"SELECT * FROM {self._table}"  # noqa: S608
        if not include_archived:
            sql += " WHERE archived = 0"
        with _db_errors(f"list {self._entity}s"):
            rows = self._c.execute(sql + " ORDER BY name COLLATE NOCASE").fetchall()
        return [self._from_row(r) for r in rows]

    def update(self, item: M) -> M:
        """Update name, colour and archive flag.

        Raises:
            NotFoundError: If missing.
            ConflictError: If the name collides with another non-archived item.
        """
        with _db_errors(f"update {self._entity}"):
            cursor = self._c.execute(
                f"UPDATE {self._table} SET name = ?, color = ?, archived = ? WHERE id = ?",  # noqa: S608
                (item.name, item.color, int(item.archived), item.id),
            )
        if cursor.rowcount == 0:
            raise NotFoundError(f"{self._entity} {item.id} not found", details={"id": item.id})
        return item

    def set_archived(self, item_id: str, archived: bool) -> M:
        """Archive or restore an item (the safe alternative to deleting a used one)."""
        item = dataclasses.replace(self.require(item_id), archived=archived)
        return self.update(item)

    def delete(self, item_id: str, audit: AuditLogRepository | None = None) -> None:
        """Delete an item that is not referenced anywhere.

        Raises:
            NotFoundError: If missing.
            ConflictError: If sessions or mappings still use it - archive instead.
        """
        item = self.require(item_id)
        with _savepoint(self._c, f"delete_{self._entity}"):
            with _db_errors(f"delete {self._entity}"):
                self._c.execute(f"DELETE FROM {self._table} WHERE id = ?", (item_id,))  # noqa: S608
            if audit is not None:
                audit.add("delete", self._entity, item_id, f"name={item.name}")


class ActivityRepository(_NamedRepository[Activity]):
    """Persistence of activities."""

    _table = "activities"
    _entity = "activity"
    _model = Activity


class ProjectRepository(_NamedRepository[Project]):
    """Persistence of projects."""

    _table = "projects"
    _entity = "project"
    _model = Project


# ----------------------------------------------------------------------- face mappings


class FaceMappingRepository:
    """Persistence of face-to-activity assignments."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> FaceMapping:
        return _load(
            lambda: FaceMapping(
                device_id=row["device_id"],
                face=row["face"],
                activity_id=row["activity_id"],
                project_id=row["project_id"],
                revision=row["revision"],
            ),
            "face mapping",
            f"{row['device_id']}/{row['face']}",
        )

    def get(self, device_id: str, face: int) -> FaceMapping | None:
        """Return the mapping of one face or ``None``."""
        with _db_errors("read face mapping"):
            row = self._c.execute(
                "SELECT * FROM face_mappings WHERE device_id = ? AND face = ?", (device_id, face)
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_for_device(self, device_id: str) -> list[FaceMapping]:
        """Return all configured faces of a device ordered by face number."""
        with _db_errors("list face mappings"):
            rows = self._c.execute(
                "SELECT * FROM face_mappings WHERE device_id = ? ORDER BY face", (device_id,)
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def assign(
        self,
        device_id: str,
        face: int,
        activity_id: str | None,
        project_id: str | None = None,
    ) -> FaceMapping:
        """Create or change a mapping; the revision increases when the target changes.

        Re-assigning the identical target does not bump the revision.

        Raises:
            ValidationError: For an invalid face number.
            ConflictError: If device, activity or project do not exist.
        """
        existing = self.get(device_id, face)
        if existing is None:
            mapping = FaceMapping(device_id, face, activity_id, project_id, revision=1)
        elif (existing.activity_id, existing.project_id) == (activity_id, project_id):
            return existing
        else:
            mapping = dataclasses.replace(
                existing,
                activity_id=activity_id,
                project_id=project_id,
                revision=existing.revision + 1,
            )
        with _db_errors("assign face"):
            self._c.execute(
                "INSERT INTO face_mappings (device_id, face, activity_id, project_id, revision) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (device_id, face) DO UPDATE SET "
                "activity_id = excluded.activity_id, project_id = excluded.project_id, "
                "revision = excluded.revision",
                (device_id, face, activity_id, project_id, mapping.revision),
            )
        logger.info(
            "Face %d of device %s assigned (revision %d)", face, device_id[:8], mapping.revision
        )
        return mapping

    def clear(self, device_id: str, face: int) -> None:
        """Remove the mapping of a face (no error if none existed)."""
        with _db_errors("clear face mapping"):
            self._c.execute(
                "DELETE FROM face_mappings WHERE device_id = ? AND face = ?", (device_id, face)
            )


# -------------------------------------------------------------------------- integrations


def _to_json(value: Mapping[str, Any]) -> str:
    """Canonical JSON text of a small settings/parameter object."""
    return json.dumps(dict(value), sort_keys=True, ensure_ascii=False)


def _from_json(text: str) -> dict[str, Any]:
    """Decode stored JSON; anything but an object is a data integrity problem."""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataIntegrityError(f"Stored JSON is invalid: {exc}") from exc
    if not isinstance(loaded, dict):
        raise DataIntegrityError("Stored JSON is not an object")
    return loaded


class IntegrationRepository:
    """Persistence of integrations (settings only; secrets are stored elsewhere)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Integration:
        return _load(
            lambda: Integration(
                id=row["id"],
                kind=row["kind"],
                name=row["name"],
                config=_from_json(row["config"]),
                enabled=bool(row["enabled"]),
                created_at=from_db_time(row["created_at"]),
            ),
            "integration",
            row["id"],
        )

    def add(self, integration: Integration) -> Integration:
        """Insert an integration.

        Raises:
            ConflictError: If the name is already used.
        """
        with _db_errors("insert integration"):
            self._c.execute(
                "INSERT INTO integrations (id, kind, name, config, enabled, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    integration.id,
                    integration.kind,
                    integration.name,
                    _to_json(integration.config),
                    int(integration.enabled),
                    to_db_time(integration.created_at),
                ),
            )
        logger.info("Integration added: %s (%s)", integration.name, integration.kind)
        return integration

    def get(self, integration_id: str) -> Integration | None:
        """Return the integration or ``None``."""
        with _db_errors("read integration"):
            row = self._c.execute(
                "SELECT * FROM integrations WHERE id = ?", (integration_id,)
            ).fetchone()
        return None if row is None else self._from_row(row)

    def require(self, integration_id: str) -> Integration:
        """Return the integration or raise :class:`NotFoundError`."""
        integration = self.get(integration_id)
        if integration is None:
            raise NotFoundError(
                f"Integration {integration_id} not found", details={"id": integration_id}
            )
        return integration

    def list_all(self) -> list[Integration]:
        """Return all integrations ordered by name."""
        with _db_errors("list integrations"):
            rows = self._c.execute(
                "SELECT * FROM integrations ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def update(self, integration: Integration) -> Integration:
        """Change name, settings and enabled flag (the kind never changes).

        Raises:
            NotFoundError: If the integration does not exist.
            ConflictError: If the new name is already used.
        """
        with _db_errors("update integration"):
            cursor = self._c.execute(
                "UPDATE integrations SET name = ?, config = ?, enabled = ? WHERE id = ?",
                (
                    integration.name,
                    _to_json(integration.config),
                    int(integration.enabled),
                    integration.id,
                ),
            )
        if cursor.rowcount == 0:
            raise NotFoundError(
                f"Integration {integration.id} not found", details={"id": integration.id}
            )
        return integration

    def delete(self, integration_id: str, audit: AuditLogRepository | None = None) -> None:
        """Delete an integration and its queued jobs.

        Raises:
            NotFoundError: If missing.
            ConflictError: If a face still uses it (remove the action first).
        """
        integration = self.require(integration_id)
        with _savepoint(self._c, "delete_integration"):
            with _db_errors("delete integration"):
                self._c.execute("DELETE FROM integrations WHERE id = ?", (integration_id,))
            if audit is not None:
                audit.add("delete", "integration", integration_id, f"name={integration.name}")
        logger.info("Integration deleted: %s", integration.name)


class FaceActionRepository:
    """Persistence of face-to-action assignments (control mode)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> FaceAction:
        return _load(
            lambda: FaceAction(
                device_id=row["device_id"],
                face=row["face"],
                integration_id=row["integration_id"],
                label=row["label"],
                params=_from_json(row["params"]),
                revision=row["revision"],
            ),
            "face action",
            f"{row['device_id']}/{row['face']}",
        )

    def get(self, device_id: str, face: int) -> FaceAction | None:
        """Return the action of one face or ``None``."""
        with _db_errors("read face action"):
            row = self._c.execute(
                "SELECT * FROM face_actions WHERE device_id = ? AND face = ?", (device_id, face)
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_for_device(self, device_id: str) -> list[FaceAction]:
        """Return all configured actions of a device ordered by face."""
        with _db_errors("list face actions"):
            rows = self._c.execute(
                "SELECT * FROM face_actions WHERE device_id = ? ORDER BY face", (device_id,)
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def list_all(self) -> list[FaceAction]:
        """Return every action (for backups), ordered by device and face."""
        with _db_errors("list all face actions"):
            rows = self._c.execute("SELECT * FROM face_actions ORDER BY device_id, face").fetchall()
        return [self._from_row(r) for r in rows]

    def assign(
        self,
        device_id: str,
        face: int,
        integration_id: str,
        label: str,
        params: Mapping[str, Any],
    ) -> FaceAction:
        """Create or change an action; the revision grows when something changes.

        Raises:
            ValidationError: For invalid values.
            ConflictError: If the device or integration does not exist.
        """
        existing = self.get(device_id, face)
        candidate = FaceAction(device_id, face, integration_id, label, params, revision=1)
        if existing is not None:
            same = (existing.integration_id, existing.label, existing.params) == (
                candidate.integration_id,
                candidate.label,
                candidate.params,
            )
            if same:
                return existing
            candidate = dataclasses.replace(candidate, revision=existing.revision + 1)
        with _db_errors("assign face action"):
            self._c.execute(
                "INSERT INTO face_actions (device_id, face, integration_id, label, params, "
                "revision) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (device_id, face) DO UPDATE SET "
                "integration_id = excluded.integration_id, label = excluded.label, "
                "params = excluded.params, revision = excluded.revision",
                (
                    device_id,
                    face,
                    integration_id,
                    candidate.label,
                    _to_json(candidate.params),
                    candidate.revision,
                ),
            )
        logger.info(
            "Action of face %d of device %s set (revision %d)",
            face,
            device_id[:8],
            candidate.revision,
        )
        return candidate

    def clear(self, device_id: str, face: int) -> None:
        """Remove the action of a face (no error if none existed)."""
        with _db_errors("clear face action"):
            self._c.execute(
                "DELETE FROM face_actions WHERE device_id = ? AND face = ?", (device_id, face)
            )


class JobRepository:
    """The outbox of actions waiting to be sent (see :class:`IntegrationJob`)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> IntegrationJob:
        return _load(
            lambda: IntegrationJob(
                id=row["id"],
                idempotency_key=row["idempotency_key"],
                integration_id=row["integration_id"],
                device_id=row["device_id"],
                face=row["face"],
                label=row["label"],
                params=_from_json(row["params"]),
                status=JobStatus(row["status"]),
                attempts=row["attempts"],
                last_error=row["last_error"],
                created_at=from_db_time(row["created_at"]),
                expires_at=from_db_time(row["expires_at"]),
                next_attempt_at=from_db_time(row["next_attempt_at"]),
                finished_at=_opt_time(row["finished_at"]),
            ),
            "integration job",
            row["id"],
        )

    def enqueue(self, job: IntegrationJob) -> bool:
        """Insert a job unless one with the same idempotency key exists.

        Returns:
            ``True`` if the job was stored, ``False`` if it was a repeat (nothing changes).
        """
        with _db_errors("enqueue job"):
            cursor = self._c.execute(
                "INSERT OR IGNORE INTO integration_jobs (id, idempotency_key, integration_id, "
                "device_id, face, label, params, status, attempts, last_error, created_at, "
                "expires_at, next_attempt_at, finished_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.id,
                    job.idempotency_key,
                    job.integration_id,
                    job.device_id,
                    job.face,
                    job.label,
                    _to_json(job.params),
                    job.status.value,
                    job.attempts,
                    job.last_error,
                    to_db_time(job.created_at),
                    to_db_time(job.expires_at),
                    to_db_time(job.next_attempt_at or job.created_at),
                    None if job.finished_at is None else to_db_time(job.finished_at),
                ),
            )
        return cursor.rowcount == 1

    def get(self, job_id: str) -> IntegrationJob | None:
        """Return the job or ``None``."""
        with _db_errors("read job"):
            row = self._c.execute(
                "SELECT * FROM integration_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return None if row is None else self._from_row(row)

    def count_pending(self, integration_id: str) -> int:
        """Number of jobs of an integration that are still waiting."""
        with _db_errors("count pending jobs"):
            row = self._c.execute(
                "SELECT COUNT(*) FROM integration_jobs WHERE integration_id = ? "
                "AND status = 'pending'",
                (integration_id,),
            ).fetchone()
        return int(row[0])

    def due(self, now: datetime, limit: int = 20) -> list[IntegrationJob]:
        """Pending jobs whose next attempt is due, oldest first."""
        with _db_errors("list due jobs"):
            rows = self._c.execute(
                "SELECT * FROM integration_jobs WHERE status = 'pending' AND next_attempt_at <= ? "
                "ORDER BY created_at, id LIMIT ?",
                (to_db_time(now), limit),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def _finish(
        self, job_id: str, status: JobStatus, now: datetime, attempts: int, error: str | None
    ) -> None:
        with _db_errors("finish job"):
            self._c.execute(
                "UPDATE integration_jobs SET status = ?, attempts = ?, last_error = ?, "
                "finished_at = ? WHERE id = ?",
                (status.value, attempts, error, to_db_time(now), job_id),
            )

    def mark_done(self, job_id: str, now: datetime, attempts: int) -> None:
        """The action was sent."""
        self._finish(job_id, JobStatus.DONE, now, attempts, None)

    def mark_failed(self, job_id: str, now: datetime, attempts: int, error: str) -> None:
        """Give up on a job (permanent error or attempts used up)."""
        self._finish(job_id, JobStatus.FAILED, now, attempts, error)

    def mark_expired(self, job_id: str, now: datetime, attempts: int, error: str) -> None:
        """Drop a job that is too late to be useful."""
        self._finish(job_id, JobStatus.EXPIRED, now, attempts, error)

    def mark_retry(self, job_id: str, attempts: int, next_attempt_at: datetime, error: str) -> None:
        """Keep the job pending and try again at ``next_attempt_at``."""
        with _db_errors("retry job"):
            self._c.execute(
                "UPDATE integration_jobs SET attempts = ?, last_error = ?, next_attempt_at = ? "
                "WHERE id = ?",
                (attempts, error, to_db_time(next_attempt_at), job_id),
            )

    def expire_overdue(self, now: datetime, message: str) -> int:
        """Expire every pending job whose time ran out; returns how many."""
        with _db_errors("expire jobs"):
            cursor = self._c.execute(
                "UPDATE integration_jobs SET status = 'expired', last_error = ?, finished_at = ? "
                "WHERE status = 'pending' AND expires_at <= ?",
                (message, to_db_time(now), to_db_time(now)),
            )
        return cursor.rowcount

    def list_recent(self, limit: int = 50) -> list[IntegrationJob]:
        """The newest jobs first (for the history)."""
        with _db_errors("list jobs"):
            rows = self._c.execute(
                "SELECT * FROM integration_jobs ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def delete_finished_before(self, cutoff: datetime) -> int:
        """Remove finished jobs older than ``cutoff`` (keeps the history small)."""
        with _db_errors("purge jobs"):
            cursor = self._c.execute(
                "DELETE FROM integration_jobs WHERE status != 'pending' AND finished_at < ?",
                (to_db_time(cutoff),),
            )
        return cursor.rowcount


# ------------------------------------------------------------------------------- events


@dataclass(frozen=True, slots=True)
class RangeStats:
    """What a bulk deletion of sessions would touch (shown before anything is deleted)."""

    count: int
    with_note: int
    first: datetime | None
    last: datetime | None
    #: A running session exists; it is never deleted by a bulk operation.
    running_left_out: bool


class RawEventRepository:
    """Persistence of unmodified tracker observations."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RawEvent:
        return _load(
            lambda: RawEvent(
                id=row["id"],
                device_id=row["device_id"],
                kind=EventKind(row["kind"]),
                sequence=row["sequence"],
                connection_id=row["connection_id"],
                received_at=from_db_time(row["received_at"]),
                raw_value=row["raw_value"],
                detail=row["detail"],
            ),
            "raw event",
            row["id"],
        )

    _INSERT = (
        "INSERT INTO raw_events (id, device_id, kind, raw_value, sequence, connection_id, "
        "received_at, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )

    @staticmethod
    def _params(event: RawEvent) -> tuple[Any, ...]:
        return (
            event.id,
            event.device_id,
            event.kind.value,
            event.raw_value,
            event.sequence,
            event.connection_id,
            to_db_time(event.received_at),
            event.detail,
        )

    def add(self, event: RawEvent) -> RawEvent:
        """Insert one event."""
        with _db_errors("insert event"):
            self._c.execute(self._INSERT, self._params(event))
        return event

    def add_many(self, events: Sequence[RawEvent]) -> int:
        """Insert several events in one statement batch; returns the count."""
        with _db_errors("insert events"):
            self._c.executemany(self._INSERT, [self._params(e) for e in events])
        return len(events)

    def list_for_device(
        self, device_id: str, *, since: datetime | None = None, limit: int = 1000
    ) -> list[RawEvent]:
        """Return the newest events of a device (newest first).

        Args:
            device_id: The device.
            since: Only events received at or after this time.
            limit: Maximum number of rows (1..100000).
        """
        if not 1 <= limit <= 100_000:
            raise ValidationError("limit must be 1..100000")
        sql = "SELECT * FROM raw_events WHERE device_id = ?"
        params: list[Any] = [device_id]
        if since is not None:
            sql += " AND received_at >= ?"
            params.append(to_db_time(since))
        sql += " ORDER BY received_at DESC, sequence DESC LIMIT ?"
        params.append(limit)
        with _db_errors("list events"):
            rows = self._c.execute(sql, params).fetchall()
        return [self._from_row(r) for r in rows]

    def list_all(self) -> list[RawEvent]:
        """Return every stored event, oldest first (used by backup)."""
        with _db_errors("list all events"):
            rows = self._c.execute(
                "SELECT * FROM raw_events ORDER BY received_at, sequence, id"
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def count(self, device_id: str | None = None) -> int:
        """Return the number of stored events (optionally of one device)."""
        sql, params = "SELECT COUNT(*) FROM raw_events", ()
        if device_id is not None:
            sql, params = sql + " WHERE device_id = ?", (device_id,)  # type: ignore[assignment]
        with _db_errors("count events"):
            return int(self._c.execute(sql, params).fetchone()[0])

    def delete_older_than(self, cutoff: datetime, audit: AuditLogRepository | None = None) -> int:
        """Delete events received before ``cutoff`` (explicit retention rule).

        Returns:
            Number of deleted rows. The action is recorded in the audit log.
        """
        with _savepoint(self._c, "purge_events"):
            with _db_errors("purge events"):
                cursor = self._c.execute(
                    "DELETE FROM raw_events WHERE received_at < ?", (to_db_time(cutoff),)
                )
            if audit is not None and cursor.rowcount:
                audit.add(
                    "purge", "raw_event", None, f"{cursor.rowcount} before {to_db_time(cutoff)}"
                )
        return cursor.rowcount

    def delete_range(
        self,
        start: datetime | None,
        end: datetime | None,
        audit: AuditLogRepository | None = None,
    ) -> int:
        """Delete events received in ``[start, end)`` (``None`` leaves a side open)."""
        clauses, params = [], []
        if start is not None:
            clauses.append("received_at >= ?")
            params.append(to_db_time(start))
        if end is not None:
            clauses.append("received_at < ?")
            params.append(to_db_time(end))
        where = " AND ".join(clauses) or "1=1"
        with _savepoint(self._c, "delete_events_range"):
            with _db_errors("delete events in range"):
                cursor = self._c.execute(f"DELETE FROM raw_events WHERE {where}", params)  # noqa: S608
            if audit is not None and cursor.rowcount:
                audit.add("delete", "raw_events", None, f"{cursor.rowcount} events in range")
        return int(cursor.rowcount)

    def delete_all_of_device(self, device_id: str) -> int:
        """Delete every event of a device (used when removing it)."""
        with _db_errors("delete events of a device"):
            cursor = self._c.execute("DELETE FROM raw_events WHERE device_id = ?", (device_id,))
        return int(cursor.rowcount)


# ----------------------------------------------------------------------------- sessions


class SessionRepository:
    """Persistence of sessions and their audited corrections."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Session:
        return _load(
            lambda: Session(
                id=row["id"],
                activity_id=row["activity_id"],
                project_id=row["project_id"],
                device_id=row["device_id"],
                started_at=from_db_time(row["started_at"]),
                ended_at=_opt_time(row["ended_at"]),
                source=SessionSource(row["source"]),
                quality=Quality(row["quality"]),
                note=row["note"],
                revision=row["revision"],
            ),
            "session",
            row["id"],
        )

    def add(self, session: Session) -> Session:
        """Insert a session.

        Raises:
            ConflictError: On overlap with another session, a second running session or an
                unknown activity/project/device.
        """
        with _db_errors("insert session"):
            self._c.execute(
                "INSERT INTO sessions (id, activity_id, project_id, device_id, started_at, "
                "ended_at, source, quality, note, revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.activity_id,
                    session.project_id,
                    session.device_id,
                    to_db_time(session.started_at),
                    None if session.ended_at is None else to_db_time(session.ended_at),
                    session.source.value,
                    session.quality.value,
                    session.note,
                    session.revision,
                ),
            )
        logger.info("Session started/added: %s", session.id[:8])
        return session

    def get(self, session_id: str) -> Session | None:
        """Return the session or ``None``."""
        with _db_errors("read session"):
            row = self._c.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return None if row is None else self._from_row(row)

    def require(self, session_id: str) -> Session:
        """Return the session or raise :class:`NotFoundError`."""
        session = self.get(session_id)
        if session is None:
            raise NotFoundError(f"Session {session_id} not found", details={"id": session_id})
        return session

    def get_running(self) -> Session | None:
        """Return the single running session, if any."""
        with _db_errors("read running session"):
            row = self._c.execute("SELECT * FROM sessions WHERE ended_at IS NULL").fetchone()
        return None if row is None else self._from_row(row)

    def list_between(
        self,
        start: datetime,
        end: datetime,
        *,
        device_id: str | None = None,
        activity_id: str | None = None,
        project_id: str | None = None,
    ) -> list[Session]:
        """Return sessions that overlap ``[start, end)``, oldest first.

        A running session counts as extending into the future. Sessions are returned
        **whole** (not clipped); reports split and clip them (see ``time_rules``).
        """
        sql = "SELECT * FROM sessions WHERE started_at < ? AND COALESCE(ended_at, ?) > ?"
        params: list[Any] = [to_db_time(end), _FAR_FUTURE, to_db_time(start)]
        for column, value in (
            ("device_id", device_id),
            ("activity_id", activity_id),
            ("project_id", project_id),
        ):
            if value is not None:
                sql += f" AND {column} = ?"
                params.append(value)
        with _db_errors("list sessions"):
            rows = self._c.execute(sql + " ORDER BY started_at, id", params).fetchall()
        return [self._from_row(r) for r in rows]

    def list_all(self) -> list[Session]:
        """Return every session, oldest first (used by export)."""
        with _db_errors("list all sessions"):
            rows = self._c.execute("SELECT * FROM sessions ORDER BY started_at, id").fetchall()
        return [self._from_row(r) for r in rows]

    def end(self, session_id: str, ended_at: datetime, quality: Quality | None = None) -> Session:
        """End a running session (system action, not a user correction).

        Raises:
            NotFoundError: If missing.
            ValidationError: If it is not running or ``ended_at`` precedes its start.
        """
        session = self.require(session_id)
        if not session.is_running:
            raise ValidationError(f"Session {session_id} is not running")
        updated = dataclasses.replace(
            session, ended_at=ended_at, quality=quality or session.quality
        )  # re-validates the interval
        with _db_errors("end session"):
            self._c.execute(
                "UPDATE sessions SET ended_at = ?, quality = ? WHERE id = ?",
                (to_db_time(updated.ended_at or ended_at), updated.quality.value, session_id),
            )
        logger.info("Session ended: %s", session_id[:8])
        return updated

    def set_quality(self, session_id: str, quality: Quality) -> Session:
        """Set the quality flag as a **system** action (e.g. mark uncertain after a loss).

        User-initiated changes go through :meth:`correct`, which records the reason.
        """
        session = self.require(session_id)
        if session.quality is quality:
            return session
        with _db_errors("set session quality"):
            self._c.execute(
                "UPDATE sessions SET quality = ? WHERE id = ?", (quality.value, session_id)
            )
        logger.info("Session %s marked %s", session_id[:8], quality.value)
        return dataclasses.replace(session, quality=quality)

    def last_ended(self) -> datetime | None:
        """Return the latest end time of any finished session, or ``None``."""
        with _db_errors("read last session end"):
            row = self._c.execute("SELECT MAX(ended_at) FROM sessions").fetchone()
        return None if row[0] is None else from_db_time(row[0])

    def list_by_quality(self, quality: Quality) -> list[Session]:
        """Return sessions with the given quality, oldest first (e.g. the uncertain ones)."""
        with _db_errors("list sessions by quality"):
            rows = self._c.execute(
                "SELECT * FROM sessions WHERE quality = ? ORDER BY started_at, id",
                (quality.value,),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def correct(
        self,
        session_id: str,
        changes: Mapping[str, object],
        reason: str,
        *,
        corrected_at: datetime | None = None,
    ) -> Session:
        """Change a session and record **every** changed field in the audit trail.

        The original values stay available in ``corrections``; the session revision
        increases by one. The whole operation is atomic.

        Args:
            session_id: Session to change.
            changes: Mapping of field name to new value; allowed fields are
                :data:`CORRECTABLE_FIELDS`. Fields whose value does not actually change
                are ignored.
            reason: Why the change is made (required).
            corrected_at: Time of the correction (default: now).

        Returns:
            The updated session.

        Raises:
            NotFoundError: If the session does not exist.
            ValidationError: For unknown fields, invalid values, an empty reason or when
                nothing changes.
            ConflictError: If the change would overlap another session.
        """
        unknown = sorted(set(changes) - CORRECTABLE_FIELDS)
        if unknown:
            raise ValidationError(
                f"Fields cannot be corrected: {', '.join(unknown)}",
                user_message=f"Diese Felder können nicht korrigiert werden: {', '.join(unknown)}.",
                details={"fields": unknown},
            )
        old = self.require(session_id)
        normalised: dict[str, Any] = dict(changes)
        if normalised.get("quality") is not None:
            try:
                normalised["quality"] = Quality(normalised["quality"])
            except ValueError as exc:
                raise ValidationError(
                    f"Unknown quality {normalised['quality']!r}",
                    user_message="Die Qualität muss „confirmed“ oder „uncertain“ sein.",
                ) from exc
        # Only fields whose value really differs are corrections (aware datetimes compare
        # by instant, so the same moment in another timezone is not a change).
        changed = [name for name, value in normalised.items() if getattr(old, name) != value]
        if not changed:
            raise ValidationError(
                "Correction changes nothing",
                user_message="Es wurde nichts geändert.",
            )
        # replace() re-validates the whole session (interval, ids, enums, ...).
        new = dataclasses.replace(
            old, revision=old.revision + 1, **{name: normalised[name] for name in changed}
        )
        when = corrected_at or utc_now()
        records = [
            Correction(
                session_id=session_id,
                field_name=name,
                old_value=self._text(getattr(old, name)),
                new_value=self._text(getattr(new, name)),
                reason=reason,
                revision=new.revision,
                corrected_at=when,
            )
            for name in changed
        ]
        with _savepoint(self._c, "correct_session"):
            with _db_errors("correct session"):
                self._c.execute(
                    "UPDATE sessions SET activity_id = ?, project_id = ?, started_at = ?, "
                    "ended_at = ?, quality = ?, note = ?, revision = ? WHERE id = ?",
                    (
                        new.activity_id,
                        new.project_id,
                        to_db_time(new.started_at),
                        None if new.ended_at is None else to_db_time(new.ended_at),
                        new.quality.value,
                        new.note,
                        new.revision,
                        session_id,
                    ),
                )
                self._c.executemany(
                    "INSERT INTO corrections (id, session_id, field_name, old_value, new_value, "
                    "reason, revision, corrected_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            r.id,
                            r.session_id,
                            r.field_name,
                            r.old_value,
                            r.new_value,
                            r.reason,
                            r.revision,
                            to_db_time(r.corrected_at),
                        )
                        for r in records
                    ],
                )
        logger.info(
            "Session %s corrected (%s) -> revision %d",
            session_id[:8],
            ", ".join(changed),
            new.revision,
        )
        return new

    @staticmethod
    def _text(value: object) -> str | None:
        """Render a field value as audit text."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return to_db_time(value)
        if isinstance(value, Quality):
            return value.value
        return str(value)

    def list_corrections(self, session_id: str | None = None) -> list[Correction]:
        """Return the audit trail of one session (or of all sessions), oldest first."""
        sql = "SELECT * FROM corrections"
        params: tuple[str, ...] = ()
        if session_id is not None:
            sql, params = sql + " WHERE session_id = ?", (session_id,)
        with _db_errors("list corrections"):
            rows = self._c.execute(
                sql + " ORDER BY corrected_at, revision, field_name, id", params
            ).fetchall()
        return [
            _load(
                lambda r=r: Correction(  # type: ignore[misc]
                    id=r["id"],
                    session_id=r["session_id"],
                    field_name=r["field_name"],
                    old_value=r["old_value"],
                    new_value=r["new_value"],
                    reason=r["reason"],
                    revision=r["revision"],
                    corrected_at=from_db_time(r["corrected_at"]),
                ),
                "correction",
                r["id"],
            )
            for r in rows
        ]

    def delete(self, session_id: str, reason: str, audit: AuditLogRepository) -> None:
        """Delete a session; the deletion (with reason) is recorded in the audit log.

        Raises:
            NotFoundError: If missing.
            ValidationError: If the reason is empty.
        """
        if not reason.strip():
            raise ValidationError("A reason is required to delete a session")
        session = self.require(session_id)
        with _savepoint(self._c, "delete_session"):
            with _db_errors("delete session"):
                self._c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            audit.add(
                "delete",
                "session",
                session_id,
                f"{to_db_time(session.started_at)}.."
                f"{session.ended_at and to_db_time(session.ended_at)} "
                f"activity={session.activity_id} reason={reason.strip()}",
            )

    # ------------------------------------------------------------- bulk (data management)

    @staticmethod
    def _range_clause(
        start: datetime | None, end: datetime | None, device_id: str | None = None
    ) -> tuple[str, list[str]]:
        """SQL condition for *finished* sessions that started in ``[start, end)``.

        Running sessions are never part of a bulk operation: they are still being recorded.
        """
        clauses = ["ended_at IS NOT NULL"]
        params: list[str] = []
        if start is not None:
            clauses.append("started_at >= ?")
            params.append(to_db_time(start))
        if end is not None:
            clauses.append("started_at < ?")
            params.append(to_db_time(end))
        if device_id is not None:
            clauses.append("device_id = ?")
            params.append(device_id)
        return " AND ".join(clauses), params

    def range_stats(self, start: datetime | None = None, end: datetime | None = None) -> RangeStats:
        """Count the finished sessions that started in ``[start, end)`` (preview of a deletion).

        ``None`` leaves that side open. Also reports how many sessions have a note, the
        first and the last start, and whether a running session was left out.
        """
        where, params = self._range_clause(start, end)
        with _db_errors("count sessions in range"):
            row = self._c.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(note IS NOT NULL AND note <> ''), 0) AS notes, "
                f"MIN(started_at) AS first, MAX(started_at) AS last FROM sessions WHERE {where}",  # noqa: S608
                params,
            ).fetchone()
            running = self._c.execute(
                "SELECT COUNT(*) FROM sessions WHERE ended_at IS NULL"
            ).fetchone()[0]
        return RangeStats(
            count=int(row["n"]),
            with_note=int(row["notes"]),
            first=_opt_time(row["first"]),
            last=_opt_time(row["last"]),
            running_left_out=int(running) > 0,
        )

    def delete_range(
        self,
        start: datetime | None,
        end: datetime | None,
        audit: AuditLogRepository,
        device_id: str | None = None,
    ) -> int:
        """Delete finished sessions that started in ``[start, end)`` (and their corrections).

        One summary entry (not one per session) goes into the audit log.

        Returns:
            Number of deleted sessions.
        """
        where, params = self._range_clause(start, end, device_id)
        with _savepoint(self._c, "delete_sessions_range"):
            with _db_errors("delete sessions in range"):
                cursor = self._c.execute(f"DELETE FROM sessions WHERE {where}", params)  # noqa: S608
            if cursor.rowcount:
                audit.add(
                    "delete",
                    "sessions",
                    device_id,
                    f"{cursor.rowcount} sessions, range "
                    f"{start and to_db_time(start)}..{end and to_db_time(end)}",
                )
        return int(cursor.rowcount)

    def delete_all_of_device(self, device_id: str, audit: AuditLogRepository) -> int:
        """Delete every session of a device, a running one included (used when removing it)."""
        with _savepoint(self._c, "delete_device_sessions"):
            with _db_errors("delete sessions of a device"):
                cursor = self._c.execute("DELETE FROM sessions WHERE device_id = ?", (device_id,))
            if cursor.rowcount:
                audit.add("delete", "sessions", device_id, f"{cursor.rowcount} sessions of device")
        return int(cursor.rowcount)

    def count_all(self) -> int:
        """Total number of sessions (running one included)."""
        with _db_errors("count sessions"):
            return int(self._c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])


# ------------------------------------------------------------------------------- audit


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One line of the audit log."""

    id: str
    at: datetime
    action: str
    entity: str
    entity_id: str | None
    detail: str | None


class AuditLogRepository:
    """Append-only log of destructive actions."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    def add(
        self, action: str, entity: str, entity_id: str | None, detail: str | None = None
    ) -> AuditEntry:
        """Append an entry (timestamped now)."""
        entry = AuditEntry(new_id(), utc_now(), action, entity, entity_id, detail)
        with _db_errors("write audit log"):
            self._c.execute(
                "INSERT INTO audit_log (id, at, action, entity, entity_id, detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (entry.id, to_db_time(entry.at), action, entity, entity_id, detail),
            )
        return entry

    def list_all(self) -> list[AuditEntry]:
        """Return every audit entry, oldest first (used by backup)."""
        with _db_errors("read audit log"):
            rows = self._c.execute("SELECT * FROM audit_log ORDER BY at, id").fetchall()
        return [
            AuditEntry(
                r["id"],
                from_db_time(r["at"]),
                r["action"],
                r["entity"],
                r["entity_id"],
                r["detail"],
            )
            for r in rows
        ]

    def recent(self, limit: int = 100) -> list[AuditEntry]:
        """Return the newest entries first."""
        if not 1 <= limit <= 10_000:
            raise ValidationError("limit must be 1..10000")
        with _db_errors("read audit log"):
            rows = self._c.execute(
                "SELECT * FROM audit_log ORDER BY at DESC, id LIMIT ?", (limit,)
            ).fetchall()
        return [
            AuditEntry(
                r["id"],
                from_db_time(r["at"]),
                r["action"],
                r["entity"],
                r["entity_id"],
                r["detail"],
            )
            for r in rows
        ]


# --------------------------------------------------------------------------- app state


class AttentionRepository:
    """Questions waiting for a decision of the user (see :class:`AttentionItem`)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AttentionItem:
        return _load(
            lambda: AttentionItem(
                id=row["id"],
                kind=AttentionKind(row["kind"]),
                created_at=from_db_time(row["created_at"]),
                session_id=row["session_id"],
                payload=_from_json(row["payload"]),
                status=AttentionStatus(row["status"]),
                resolved_at=_opt_time(row["resolved_at"]),
                resolution=row["resolution"],
            ),
            "attention item",
            row["id"],
        )

    def add(self, item: AttentionItem) -> AttentionItem:
        """Store a new item."""
        with _db_errors("add attention item"):
            self._c.execute(
                "INSERT INTO attention_items (id, kind, created_at, session_id, payload, status, "
                "resolved_at, resolution) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.kind.value,
                    to_db_time(item.created_at),
                    item.session_id,
                    _to_json(item.payload),
                    item.status.value,
                    None if item.resolved_at is None else to_db_time(item.resolved_at),
                    item.resolution,
                ),
            )
        return item

    def get(self, item_id: str) -> AttentionItem | None:
        """Return an item or ``None``."""
        with _db_errors("read attention item"):
            row = self._c.execute(
                "SELECT * FROM attention_items WHERE id = ?", (item_id,)
            ).fetchone()
        return None if row is None else self._from_row(row)

    def require(self, item_id: str) -> AttentionItem:
        """Return an item or raise :class:`NotFoundError`."""
        item = self.get(item_id)
        if item is None:
            raise NotFoundError(
                f"Attention item {item_id} not found",
                user_message="Diese Rückfrage gibt es nicht (mehr).",
            )
        return item

    def list_open(self) -> list[AttentionItem]:
        """Return all open items, oldest first."""
        with _db_errors("list attention items"):
            rows = self._c.execute(
                "SELECT * FROM attention_items WHERE status = 'open' ORDER BY created_at, id"
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def list_recent(self, limit: int = 50) -> list[AttentionItem]:
        """Return the newest items of any status, newest first."""
        with _db_errors("list attention items"):
            rows = self._c.execute(
                "SELECT * FROM attention_items ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def update_payload(self, item_id: str, payload: Mapping[str, Any]) -> None:
        """Replace the payload of an item (used to add facts such as the return time)."""
        with _db_errors("update attention payload"):
            self._c.execute(
                "UPDATE attention_items SET payload = ? WHERE id = ?",
                (_to_json(payload), item_id),
            )

    def close(
        self, item_id: str, status: AttentionStatus, resolution: str | None, at: datetime
    ) -> None:
        """Mark an item as answered (``resolved``), ``dismissed`` or ``expired``."""
        with _db_errors("close attention item"):
            self._c.execute(
                "UPDATE attention_items SET status = ?, resolution = ?, resolved_at = ? "
                "WHERE id = ?",
                (status.value, resolution, to_db_time(at), item_id),
            )

    def expire_open_before(self, cutoff: datetime, now: datetime) -> int:
        """Mark open items created before ``cutoff`` as ``expired``; time data is untouched."""
        with _db_errors("expire attention items"):
            cursor = self._c.execute(
                "UPDATE attention_items SET status = 'expired', resolved_at = ? "
                "WHERE status = 'open' AND created_at < ?",
                (to_db_time(now), to_db_time(cutoff)),
            )
        return cursor.rowcount


class DeviceButtonRepository:
    """What a press of the cube's button does, per device (no row = nothing happens)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    def get_all(self, device_id: str) -> dict[str, str]:
        """Return ``press -> action`` for the presses that have an action."""
        with _db_errors("read device buttons"):
            rows = self._c.execute(
                "SELECT press, action FROM device_buttons WHERE device_id = ?", (device_id,)
            ).fetchall()
        return {str(r["press"]): str(r["action"]) for r in rows}

    def get(self, device_id: str, press: str) -> ButtonAction | None:
        """Return the action of one press, or ``None`` for "nothing"."""
        action = self.get_all(device_id).get(press)
        return None if action is None else ButtonAction(action)

    def set(self, device_id: str, press: ButtonPress, action: ButtonAction | None) -> None:
        """Assign an action (``None`` removes the assignment)."""
        with _db_errors("write device button"):
            if action is None:
                self._c.execute(
                    "DELETE FROM device_buttons WHERE device_id = ? AND press = ?",
                    (device_id, press.value),
                )
            else:
                self._c.execute(
                    "INSERT INTO device_buttons (device_id, press, action) VALUES (?, ?, ?) "
                    "ON CONFLICT (device_id, press) DO UPDATE SET action = excluded.action",
                    (device_id, press.value, action.value),
                )


class StateRepository:
    """Tiny persistent key/value store for application state (active tracker, pause)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Bind to an open connection."""
        self._c = connection

    def get(self, key: str) -> str | None:
        """Return the stored value or ``None``."""
        with _db_errors("read state"):
            row = self._c.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set(self, key: str, value: str) -> None:
        """Create or replace a value."""
        with _db_errors("write state"):
            self._c.execute(
                "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, value, to_db_time(utc_now())),
            )

    def items(self) -> dict[str, str]:
        """Return all stored key/value pairs."""
        with _db_errors("read state"):
            rows = self._c.execute("SELECT key, value FROM app_state ORDER BY key").fetchall()
        return {str(r["key"]): str(r["value"]) for r in rows}

    def delete(self, key: str) -> None:
        """Remove a value (no error if absent)."""
        with _db_errors("delete state"):
            self._c.execute("DELETE FROM app_state WHERE key = ?", (key,))


# ---------------------------------------------------------------------------- backup


@dataclass(frozen=True, slots=True)
class BackupContent:
    """The complete, validated content of a backup (domain objects only)."""

    devices: tuple[Device, ...] = ()
    activities: tuple[Activity, ...] = ()
    projects: tuple[Project, ...] = ()
    mappings: tuple[FaceMapping, ...] = ()
    events: tuple[RawEvent, ...] = ()
    sessions: tuple[Session, ...] = ()
    corrections: tuple[Correction, ...] = ()
    audit: tuple[AuditEntry, ...] = ()
    state: Mapping[str, str] | None = None
    integrations: tuple[Integration, ...] = ()
    actions: tuple[FaceAction, ...] = ()

    def counts(self) -> dict[str, int]:
        """Number of records per entity (for previews and summaries)."""
        return {
            "devices": len(self.devices),
            "activities": len(self.activities),
            "projects": len(self.projects),
            "face_mappings": len(self.mappings),
            "raw_events": len(self.events),
            "sessions": len(self.sessions),
            "corrections": len(self.corrections),
            "audit_log": len(self.audit),
            "integrations": len(self.integrations),
            "face_actions": len(self.actions),
        }


class BackupRepository:
    """Read the complete content and replace it with a validated :class:`BackupContent`.

    ``replace_all`` must run inside a transaction opened by the caller so that a failure
    leaves the previous content untouched.
    """

    #: Tables in the order they can be emptied without violating foreign keys.
    _CLEAR_ORDER = (
        "integration_jobs",
        "face_actions",
        "integrations",
        "corrections",
        "sessions",
        "raw_events",
        "face_mappings",
        "activities",
        "projects",
        "devices",
        "audit_log",
        "app_state",
    )

    def __init__(self, connection: sqlite3.Connection, repos: Repositories) -> None:
        """Bind to a connection and the repositories on it."""
        self._c = connection
        self._repos = repos

    def snapshot(self) -> BackupContent:
        """Read the complete current content."""
        r = self._repos
        devices = r.devices.list_all()
        return BackupContent(
            devices=tuple(devices),
            activities=tuple(r.activities.list_all(include_archived=True)),
            projects=tuple(r.projects.list_all(include_archived=True)),
            mappings=tuple(m for d in devices for m in r.mappings.list_for_device(d.id)),
            events=tuple(r.events.list_all()),
            sessions=tuple(r.sessions.list_all()),
            corrections=tuple(r.sessions.list_corrections()),
            audit=tuple(r.audit.list_all()),
            state=r.state.items(),
            integrations=tuple(r.integrations.list_all()),
            actions=tuple(r.actions.list_all()),
        )

    def replace_all(self, content: BackupContent) -> None:
        """Delete everything and insert ``content`` (the caller provides the transaction).

        Raises:
            ConflictError: If the data violates a database rule (overlap, reference ...).
        """
        r = self._repos
        with _db_errors("clear database for restore"):
            for table in self._CLEAR_ORDER:
                self._c.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table names
        for device in content.devices:
            r.devices.add(device)
        for activity in content.activities:
            r.activities.add(activity)
        for project in content.projects:
            r.projects.add(project)
        for integration in content.integrations:
            r.integrations.add(integration)
        with _db_errors("restore face actions"):
            self._c.executemany(
                "INSERT INTO face_actions (device_id, face, integration_id, label, params, "
                "revision) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        a.device_id,
                        a.face,
                        a.integration_id,
                        a.label,
                        _to_json(a.params),
                        a.revision,
                    )
                    for a in content.actions
                ],
            )
        with _db_errors("restore face mappings"):
            self._c.executemany(
                "INSERT INTO face_mappings (device_id, face, activity_id, project_id, revision) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (m.device_id, m.face, m.activity_id, m.project_id, m.revision)
                    for m in content.mappings
                ],
            )
        for session in content.sessions:
            r.sessions.add(session)
        with _db_errors("restore corrections"):
            self._c.executemany(
                "INSERT INTO corrections (id, session_id, field_name, old_value, new_value, "
                "reason, revision, corrected_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        c.id,
                        c.session_id,
                        c.field_name,
                        c.old_value,
                        c.new_value,
                        c.reason,
                        c.revision,
                        to_db_time(c.corrected_at),
                    )
                    for c in content.corrections
                ],
            )
        r.events.add_many(list(content.events))
        with _db_errors("restore audit log"):
            self._c.executemany(
                "INSERT INTO audit_log (id, at, action, entity, entity_id, detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (a.id, to_db_time(a.at), a.action, a.entity, a.entity_id, a.detail)
                    for a in content.audit
                ],
            )
        for key, value in (content.state or {}).items():
            r.state.set(key, value)


# ---------------------------------------------------------------------------- facade


@dataclass(frozen=True, slots=True)
class Repositories:
    """All repositories bound to the same connection (and therefore transaction)."""

    devices: DeviceRepository
    activities: ActivityRepository
    projects: ProjectRepository
    mappings: FaceMappingRepository
    events: RawEventRepository
    sessions: SessionRepository
    audit: AuditLogRepository
    state: StateRepository
    backup: BackupRepository
    integrations: IntegrationRepository
    actions: FaceActionRepository
    jobs: JobRepository
    attention: AttentionRepository
    buttons: DeviceButtonRepository

    @classmethod
    def bind(cls, connection: sqlite3.Connection) -> Repositories:
        """Create the bundle for ``connection``."""
        bundle = cls.__new__(cls)
        # BackupRepository needs the finished bundle, so the frozen slotted dataclass is
        # filled field by field via object.__setattr__ (construction time only).
        for name, value in (
            ("devices", DeviceRepository(connection)),
            ("activities", ActivityRepository(connection)),
            ("projects", ProjectRepository(connection)),
            ("mappings", FaceMappingRepository(connection)),
            ("events", RawEventRepository(connection)),
            ("sessions", SessionRepository(connection)),
            ("audit", AuditLogRepository(connection)),
            ("state", StateRepository(connection)),
            ("integrations", IntegrationRepository(connection)),
            ("actions", FaceActionRepository(connection)),
            ("jobs", JobRepository(connection)),
            ("attention", AttentionRepository(connection)),
            ("buttons", DeviceButtonRepository(connection)),
        ):
            object.__setattr__(bundle, name, value)
        object.__setattr__(bundle, "backup", BackupRepository(connection, bundle))
        return bundle


class Storage:
    """Entry point for the services: hands out repositories per transaction/read."""

    def __init__(self, database: Database) -> None:
        """Wrap an initialised :class:`Database`."""
        self._database = database

    @property
    def database(self) -> Database:
        """The underlying database (for backup and diagnostics)."""
        return self._database

    @contextmanager
    def transaction(self) -> Iterator[Repositories]:
        """Yield repositories inside one atomic write transaction.

        Commits on success and rolls back on any exception, so several repository calls
        succeed or fail together.
        """
        with self._database.transaction() as connection:
            yield Repositories.bind(connection)

    @contextmanager
    def read(self) -> Iterator[Repositories]:
        """Yield repositories on a read connection (no write transaction)."""
        with self._database.connect() as connection:
            yield Repositories.bind(connection)

    @contextmanager
    def snapshot(self) -> Iterator[Repositories]:
        """Yield repositories that all see ONE consistent point in time.

        A deferred read transaction (WAL snapshot isolation) keeps several ``SELECT``
        statements consistent with each other while the agent keeps writing, which a backup
        needs. It does not block the writer.
        """
        with self._database.connect() as connection:
            try:
                connection.execute("BEGIN")
            except sqlite3.Error as exc:
                raise translate_sqlite_error(exc, "begin snapshot") from exc
            try:
                yield Repositories.bind(connection)
            finally:
                try:
                    connection.execute("ROLLBACK")  # read only: nothing to commit
                except sqlite3.Error:
                    logger.debug("Snapshot already closed")
