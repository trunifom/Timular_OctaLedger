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
from octaledger.domain.models import (
    Activity,
    Correction,
    Device,
    EventKind,
    FaceMapping,
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
                "INSERT INTO devices (id, alias, platform_address, model, firmware, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    device.id,
                    device.alias,
                    device.platform_address,
                    device.model,
                    device.firmware,
                    to_db_time(device.created_at),
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
        """Update alias, address, model and firmware of an existing device.

        Raises:
            NotFoundError: If the device does not exist.
            ConflictError: If the new alias is already used.
        """
        with _db_errors("update device"):
            cursor = self._c.execute(
                "UPDATE devices SET alias = ?, platform_address = ?, model = ?, firmware = ? "
                "WHERE id = ?",
                (device.alias, device.platform_address, device.model, device.firmware, device.id),
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


# ------------------------------------------------------------------------------- events


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

    def list_corrections(self, session_id: str) -> list[Correction]:
        """Return the audit trail of a session, oldest first."""
        with _db_errors("list corrections"):
            rows = self._c.execute(
                "SELECT * FROM corrections WHERE session_id = ? ORDER BY corrected_at, revision, "
                "field_name",
                (session_id,),
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

    @classmethod
    def bind(cls, connection: sqlite3.Connection) -> Repositories:
        """Create the bundle for ``connection``."""
        return cls(
            devices=DeviceRepository(connection),
            activities=ActivityRepository(connection),
            projects=ProjectRepository(connection),
            mappings=FaceMappingRepository(connection),
            events=RawEventRepository(connection),
            sessions=SessionRepository(connection),
            audit=AuditLogRepository(connection),
        )


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
