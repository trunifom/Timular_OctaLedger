"""Validated CSV and versioned JSON export and restore.

Responsibility
--------------
* **CSV export** of sessions for analysis (Excel-friendly): UTF-8 with BOM, ``;`` delimiter
  by default, ISO timestamps in the chosen timezone *and* UTC, and **formula-injection
  protection** for every user-provided text cell (``= + - @`` and control characters at the
  start are neutralised with a leading apostrophe).
* **JSON backup** with a ``format``/``schema_version``, the app version, record counts and a
  SHA-256 **checksum** over the data, so damage and truncation are detected.
* **Restore** that first validates *everything* (format, version, checksum, every record
  against the domain rules, uniqueness and references), then makes an automatic
  pre-restore backup of the current database, and finally replaces the content in **one
  transaction**. Any failure leaves the current data untouched (acceptance A-09).

Safety rules (see ``CLAUDE.md`` section 7)
-------------------------------------------
Nothing in an import file is ever executed or used as a path. Export file names are
generated or strictly validated (no directories, fixed extension), so a caller cannot write
outside the export/backup folder. All writes are atomic (``core.fileio``). A backup is only
considered trustworthy after a successful restore test; the verification here is a
round-trip in the tests, not a promise about the user's media.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from octaledger import __version__
from octaledger.core.errors import (
    ExportError,
    ImportDataError,
    OctaLedgerError,
    ValidationError,
)
from octaledger.core.fileio import atomic_write_text, read_text_limited
from octaledger.domain.models import (
    Activity,
    Correction,
    Device,
    DeviceMode,
    EventKind,
    FaceAction,
    FaceMapping,
    Integration,
    Project,
    Quality,
    RawEvent,
    Session,
    SessionSource,
)
from octaledger.domain.time_rules import ensure_utc, parse_timezone, utc_now
from octaledger.infrastructure.storage.repositories import (
    SIMPLE_TABLES,
    AuditEntry,
    BackupContent,
    Storage,
    from_db_time,
    to_db_time,
)

logger = logging.getLogger(__name__)

BACKUP_FORMAT: Final = "octaledger-backup"
#: Highest backup schema version this program can read and the one it writes.
#: v2 adds the device mode, integrations (settings only, **never secrets**) and face actions;
#: v3 adds the plain tables (button assignments, target working time, absences; see
#: ``SIMPLE_TABLES``) in a ``tables`` section. v1 and v2 files are still read (the missing parts
#: are empty).
BACKUP_SCHEMA_VERSION: Final = 3
#: Largest backup file accepted (bytes).
MAX_BACKUP_BYTES: Final = 200 * 1024 * 1024

CSV_COLUMNS: Final = (
    "session_id",
    "started_local",
    "ended_local",
    "started_utc",
    "ended_utc",
    "duration_seconds",
    "duration_hms",
    "running",
    "activity",
    "project",
    "device",
    "source",
    "quality",
    "revision",
    "note",
)
_ALLOWED_DELIMITERS: Final = {";": "semicolon", ",": "comma", "\t": "tab"}
_FORMULA_PREFIXES: Final = ("=", "+", "-", "@", "\t", "\r", "\n")
_SAFE_FILENAME: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")

_DATA_KEYS_V1: Final = frozenset(
    {
        "devices",
        "activities",
        "projects",
        "face_mappings",
        "raw_events",
        "sessions",
        "corrections",
        "audit_log",
        "app_state",
    }
)
_DATA_KEYS_V2: Final = _DATA_KEYS_V1 | {"integrations", "face_actions"}
_DATA_KEYS: Final = _DATA_KEYS_V2 | {"tables"}


@dataclass(frozen=True, slots=True)
class ExportResult:
    """What an export wrote."""

    path: Path
    rows: int
    size_bytes: int


@dataclass(frozen=True, slots=True)
class BackupSummary:
    """Validated description of a backup file (also used as restore preview)."""

    schema_version: int
    app_version: str
    exported_at: datetime
    counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class RestoreResult:
    """Outcome of a successful restore."""

    summary: BackupSummary
    pre_restore_backup: Path


def neutralize_cell(value: str) -> str:
    """Neutralise spreadsheet formula injection in a user-provided text cell.

    A leading ``=``, ``+``, ``-``, ``@``, tab or line break could make Excel/LibreOffice
    evaluate the cell as a formula. A leading apostrophe turns it into plain text.
    """
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def _hms(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def _check_filename(name: str, suffix: str) -> str:
    """Validate a caller-supplied file name (no directories, fixed extension)."""
    if not _SAFE_FILENAME.match(name) or not name.lower().endswith(suffix):
        raise ValidationError(
            f"Unsafe export file name: {name!r}",
            user_message=(
                f"Der Dateiname muss auf „{suffix}“ enden und darf nur Buchstaben, Ziffern, "
                "Punkt, Unterstrich und Bindestrich enthalten."
            ),
            details={"filename": name},
        )
    return name


class ExportService:
    """CSV export, JSON backup and validated restore."""

    def __init__(
        self,
        storage: Storage,
        *,
        exports_dir: Path,
        backup_dir: Path,
        clock: Callable[[], datetime] = utc_now,
        app_version: str = __version__,
    ) -> None:
        """Create the service.

        Args:
            storage: Transactional storage.
            exports_dir: Folder for CSV exports.
            backup_dir: Folder for JSON backups and pre-restore database copies.
            clock: Injectable time source.
            app_version: Written into backups.
        """
        self._storage = storage
        self._exports_dir = exports_dir
        self._backup_dir = backup_dir
        self._clock = clock
        self._app_version = app_version

    def _stamp(self) -> str:
        return ensure_utc(self._clock()).strftime("%Y%m%d-%H%M%S")

    # ------------------------------------------------------------------------ CSV

    def sessions_csv(
        self,
        *,
        timezone_name: str = "UTC",
        start: datetime | None = None,
        end: datetime | None = None,
        delimiter: str = ";",
    ) -> tuple[str, int]:
        """Render sessions (current, corrected values) as CSV text.

        Args:
            timezone_name: IANA timezone for the ``*_local`` columns.
            start / end: Optional window ``[start, end)``; sessions overlapping it are
                included whole. Default: everything.
            delimiter: ``;`` (default, Excel in German locales), ``,`` or tab.

        Returns:
            ``(csv_text, row_count)``.

        Raises:
            ValidationError: For an unknown timezone or delimiter or an inverted window.
        """
        if delimiter not in _ALLOWED_DELIMITERS:
            raise ValidationError(
                f"Unsupported delimiter {delimiter!r}",
                user_message="Als Trennzeichen sind Semikolon, Komma und Tabulator erlaubt.",
            )
        tz = parse_timezone(timezone_name)
        now = ensure_utc(self._clock())
        with self._storage.snapshot() as repos:
            if start is not None and end is not None:
                if end <= start:
                    raise ValidationError("Export window must have positive length")
                sessions = repos.sessions.list_between(start, end)
            else:
                sessions = repos.sessions.list_all()
            activities = {a.id: a.name for a in repos.activities.list_all(include_archived=True)}
            projects = {p.id: p.name for p in repos.projects.list_all(include_archived=True)}
            devices = {d.id: d.alias for d in repos.devices.list_all()}

        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
        writer.writerow(CSV_COLUMNS)
        for session in sessions:
            seconds = int(session.duration(now).total_seconds())
            writer.writerow(
                [
                    session.id,
                    session.started_at.astimezone(tz).isoformat(timespec="seconds"),
                    session.ended_at.astimezone(tz).isoformat(timespec="seconds")
                    if session.ended_at
                    else "",
                    session.started_at.isoformat(timespec="seconds"),
                    session.ended_at.isoformat(timespec="seconds") if session.ended_at else "",
                    seconds,
                    _hms(seconds),
                    "yes" if session.is_running else "no",
                    neutralize_cell(activities.get(session.activity_id, "")),
                    neutralize_cell(
                        projects.get(session.project_id, "") if session.project_id else ""
                    ),
                    neutralize_cell(
                        devices.get(session.device_id, "") if session.device_id else ""
                    ),
                    session.source.value,
                    session.quality.value,
                    session.revision,
                    neutralize_cell(session.note or ""),
                ]
            )
        return buffer.getvalue(), len(sessions)

    def export_sessions_csv(self, *, filename: str | None = None, **options: Any) -> ExportResult:
        """Write the CSV into the exports folder (UTF-8 with BOM, atomically).

        Args:
            filename: Optional file name ending in ``.csv``; default is timestamped.
            **options: Passed to :meth:`sessions_csv`.

        Raises:
            ValidationError: For unsafe file names or bad options.
            ExportError: If the file cannot be written.
        """
        name = _check_filename(filename, ".csv") if filename else f"sessions-{self._stamp()}.csv"
        text, rows = self.sessions_csv(**options)
        path = self._exports_dir / name
        atomic_write_text(path, text, encoding="utf-8-sig", error_cls=ExportError)
        logger.info("CSV export written: %s (%d rows)", path.name, rows)
        return ExportResult(path, rows, path.stat().st_size)

    # --------------------------------------------------------------- backup (JSON)

    @staticmethod
    def _encode(content: BackupContent) -> dict[str, Any]:
        """Convert domain content to plain JSON-serialisable records."""

        def opt_time(value: datetime | None) -> str | None:
            """Encode an optional timestamp for the backup (``None`` stays ``None``)."""
            return None if value is None else to_db_time(value)

        return {
            "devices": [
                {
                    "id": d.id,
                    "alias": d.alias,
                    "platform_address": d.platform_address,
                    "model": d.model,
                    "firmware": d.firmware,
                    "created_at": to_db_time(d.created_at),
                    "mode": d.mode.value,
                }
                for d in content.devices
            ],
            "integrations": [
                {
                    "id": i.id,
                    "kind": i.kind,
                    "name": i.name,
                    "config": dict(i.config),
                    "enabled": i.enabled,
                    "created_at": to_db_time(i.created_at),
                }
                for i in content.integrations
            ],
            "face_actions": [
                {
                    "device_id": a.device_id,
                    "face": a.face,
                    "integration_id": a.integration_id,
                    "label": a.label,
                    "params": dict(a.params),
                    "revision": a.revision,
                }
                for a in content.actions
            ],
            "activities": [
                {"id": a.id, "name": a.name, "color": a.color, "archived": a.archived}
                for a in content.activities
            ],
            "projects": [
                {"id": p.id, "name": p.name, "color": p.color, "archived": p.archived}
                for p in content.projects
            ],
            "face_mappings": [
                {
                    "device_id": m.device_id,
                    "face": m.face,
                    "activity_id": m.activity_id,
                    "project_id": m.project_id,
                    "revision": m.revision,
                }
                for m in content.mappings
            ],
            "raw_events": [
                {
                    "id": e.id,
                    "device_id": e.device_id,
                    "kind": e.kind.value,
                    "raw_value": e.raw_value,
                    "sequence": e.sequence,
                    "connection_id": e.connection_id,
                    "received_at": to_db_time(e.received_at),
                    "detail": e.detail,
                }
                for e in content.events
            ],
            "sessions": [
                {
                    "id": s.id,
                    "activity_id": s.activity_id,
                    "project_id": s.project_id,
                    "device_id": s.device_id,
                    "started_at": to_db_time(s.started_at),
                    "ended_at": opt_time(s.ended_at),
                    "source": s.source.value,
                    "quality": s.quality.value,
                    "note": s.note,
                    "revision": s.revision,
                }
                for s in content.sessions
            ],
            "corrections": [
                {
                    "id": c.id,
                    "session_id": c.session_id,
                    "field_name": c.field_name,
                    "old_value": c.old_value,
                    "new_value": c.new_value,
                    "reason": c.reason,
                    "revision": c.revision,
                    "corrected_at": to_db_time(c.corrected_at),
                }
                for c in content.corrections
            ],
            "audit_log": [
                {
                    "id": a.id,
                    "at": to_db_time(a.at),
                    "action": a.action,
                    "entity": a.entity,
                    "entity_id": a.entity_id,
                    "detail": a.detail,
                }
                for a in content.audit
            ],
            "app_state": dict(content.state or {}),
            "tables": {
                name: [dict(zip(SIMPLE_TABLES[name], row, strict=True)) for row in rows]
                for name, rows in content.tables.items()
            },
        }

    @staticmethod
    def _checksum(data: Mapping[str, Any]) -> str:
        """SHA-256 over the canonical JSON text of ``data``."""
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def create_backup_text(self) -> str:
        """Return a complete, versioned JSON backup of the current database.

        The snapshot is consistent (one read transaction) and does not block the agent.
        """
        with self._storage.snapshot() as repos:
            content = repos.backup.snapshot()
        data = self._encode(content)
        document = {
            "format": BACKUP_FORMAT,
            "schema_version": BACKUP_SCHEMA_VERSION,
            "app_version": self._app_version,
            "exported_at": to_db_time(self._clock()),
            "counts": content.counts(),
            "checksum": self._checksum(data),
            "data": data,
        }
        return json.dumps(document, ensure_ascii=False, indent=1)

    def export_backup(self, *, filename: str | None = None) -> ExportResult:
        """Write a JSON backup into the backup folder (atomically).

        Raises:
            ValidationError: For unsafe file names.
            ExportError: If the file cannot be written.
        """
        name = (
            _check_filename(filename, ".json")
            if filename
            else f"octaledger-backup-{self._stamp()}.json"
        )
        text = self.create_backup_text()
        path = self._backup_dir / name
        atomic_write_text(path, text, error_cls=ExportError)
        rows = sum(json.loads(text)["counts"].values())
        logger.info("Backup written: %s (%d records)", path.name, rows)
        return ExportResult(path, rows, path.stat().st_size)

    # ----------------------------------------------------------- validation/restore

    @staticmethod
    def _fail(message: str, detail: str | None = None) -> ImportDataError:
        return ImportDataError(
            message,
            user_message=(
                f"Die Datei ist keine gültige OctaLedger-Sicherung: {detail or message}. "
                "Es wurden keine Daten verändert."
            ),
        )

    @classmethod
    def _records(cls, data: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
        records = data.get(key)
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise cls._fail(f"'{key}' must be a list of objects", f"„{key}“ ist fehlerhaft")
        return records

    @classmethod
    def _build[T](
        cls, data: Mapping[str, Any], key: str, factory: Callable[[dict[str, Any]], T]
    ) -> tuple[T, ...]:
        """Build domain objects from records; any invalid record aborts with its position."""
        result: list[T] = []
        for index, record in enumerate(cls._records(data, key)):
            try:
                result.append(factory(record))
            except (OctaLedgerError, ValueError, KeyError, TypeError) as exc:
                raise cls._fail(
                    f"Invalid {key} record #{index + 1}: {exc}",
                    f"{key} Nr. {index + 1} ist ungültig ({exc})",
                ) from exc
        return tuple(result)

    @classmethod
    def _decode(
        cls, data: Mapping[str, Any], version: int = BACKUP_SCHEMA_VERSION
    ) -> BackupContent:
        """Validate and convert the ``data`` section into domain objects.

        Args:
            data: The ``data`` section of the document.
            version: The file's schema version; a v1 file has no mode, integrations or actions.
        """
        expected = _DATA_KEYS if version >= 3 else _DATA_KEYS_V2 if version == 2 else _DATA_KEYS_V1
        if set(data) != expected:
            raise cls._fail(
                f"Unexpected data sections: {sorted(set(data) ^ expected)}",
                "Die Abschnitte der Datei stimmen nicht",
            )
        device_keys = {"id", "alias", "platform_address", "model", "firmware", "created_at"}
        if version >= 2:
            device_keys.add("mode")

        def exact(record: dict[str, Any], keys: set[str]) -> dict[str, Any]:
            """Require that a record has exactly the expected fields (no more, no fewer)."""
            if set(record) != keys:
                raise ValueError(f"fields must be exactly {sorted(keys)}")
            return record

        def opt_dt(value: Any) -> datetime | None:
            """Decode an optional timestamp from the backup (``None`` stays ``None``)."""
            return None if value is None else from_db_time(value)

        state = data["app_state"]
        if not isinstance(state, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in state.items()
        ):
            raise cls._fail("app_state must map text to text", "„app_state“ ist fehlerhaft")

        tables = cls._decode_tables(data.get("tables", {}) if version >= 3 else {})
        content = BackupContent(
            tables=tables,
            devices=cls._build(
                data,
                "devices",
                lambda r: Device(
                    **{
                        **exact(r, device_keys),
                        "created_at": from_db_time(r["created_at"]),
                        "mode": DeviceMode(r.get("mode", DeviceMode.TIME.value)),
                    }
                ),
            ),
            integrations=(
                cls._build(
                    data,
                    "integrations",
                    lambda r: Integration(
                        **{
                            **exact(r, {"id", "kind", "name", "config", "enabled", "created_at"}),
                            "created_at": from_db_time(r["created_at"]),
                        }
                    ),
                )
                if version >= 2
                else ()
            ),
            actions=(
                cls._build(
                    data,
                    "face_actions",
                    lambda r: FaceAction(
                        **exact(
                            r,
                            {"device_id", "face", "integration_id", "label", "params", "revision"},
                        )
                    ),
                )
                if version >= 2
                else ()
            ),
            activities=cls._build(
                data,
                "activities",
                lambda r: Activity(**exact(r, {"id", "name", "color", "archived"})),
            ),
            projects=cls._build(
                data, "projects", lambda r: Project(**exact(r, {"id", "name", "color", "archived"}))
            ),
            mappings=cls._build(
                data,
                "face_mappings",
                lambda r: FaceMapping(
                    **exact(r, {"device_id", "face", "activity_id", "project_id", "revision"})
                ),
            ),
            events=cls._build(
                data,
                "raw_events",
                lambda r: RawEvent(
                    **{
                        **exact(
                            r,
                            {
                                "id",
                                "device_id",
                                "kind",
                                "raw_value",
                                "sequence",
                                "connection_id",
                                "received_at",
                                "detail",
                            },
                        ),
                        "kind": EventKind(r["kind"]),
                        "received_at": from_db_time(r["received_at"]),
                    }
                ),
            ),
            sessions=cls._build(
                data,
                "sessions",
                lambda r: Session(
                    **{
                        **exact(
                            r,
                            {
                                "id",
                                "activity_id",
                                "project_id",
                                "device_id",
                                "started_at",
                                "ended_at",
                                "source",
                                "quality",
                                "note",
                                "revision",
                            },
                        ),
                        "started_at": from_db_time(r["started_at"]),
                        "ended_at": opt_dt(r["ended_at"]),
                        "source": SessionSource(r["source"]),
                        "quality": Quality(r["quality"]),
                    }
                ),
            ),
            corrections=cls._build(
                data,
                "corrections",
                lambda r: Correction(
                    **{
                        **exact(
                            r,
                            {
                                "id",
                                "session_id",
                                "field_name",
                                "old_value",
                                "new_value",
                                "reason",
                                "revision",
                                "corrected_at",
                            },
                        ),
                        "corrected_at": from_db_time(r["corrected_at"]),
                    }
                ),
            ),
            audit=cls._build(
                data,
                "audit_log",
                lambda r: AuditEntry(
                    **{
                        **exact(r, {"id", "at", "action", "entity", "entity_id", "detail"}),
                        "at": from_db_time(r["at"]),
                    }
                ),
            ),
            state=dict(state),
        )
        cls._check_integrity(content)
        return content

    @classmethod
    def _decode_tables(cls, raw: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        """Validate the ``tables`` section: known tables, exact columns, plain values."""
        if not isinstance(raw, dict) or not set(raw) <= set(SIMPLE_TABLES):
            raise cls._fail("Unknown or malformed tables section", "„tables“ ist fehlerhaft")
        tables: dict[str, tuple[tuple[Any, ...], ...]] = {}
        for name, columns in SIMPLE_TABLES.items():
            records = raw.get(name, [])
            if not isinstance(records, list):
                raise cls._fail(f"'{name}' must be a list", f"„{name}“ ist fehlerhaft")
            rows: list[tuple[Any, ...]] = []
            for index, record in enumerate(records):
                if (
                    not isinstance(record, dict)
                    or set(record) != set(columns)
                    or not all(v is None or isinstance(v, (str, int)) for v in record.values())
                ):
                    raise cls._fail(
                        f"Invalid {name} record #{index + 1}",
                        f"{name} Nr. {index + 1} ist ungültig",
                    )
                rows.append(tuple(record[c] for c in columns))
            tables[name] = tuple(rows)
        return tables

    @classmethod
    def _check_integrity(cls, content: BackupContent) -> None:
        """Check unique ids and references in memory (clear messages before touching the DB)."""
        groups = {
            "devices": [d.id for d in content.devices],
            "activities": [a.id for a in content.activities],
            "projects": [p.id for p in content.projects],
            "sessions": [s.id for s in content.sessions],
            "raw_events": [e.id for e in content.events],
            "corrections": [c.id for c in content.corrections],
            "audit_log": [a.id for a in content.audit],
            "integrations": [i.id for i in content.integrations],
        }
        for name, ids in groups.items():
            if len(ids) != len(set(ids)):
                raise cls._fail(f"Duplicate ids in {name}", f"doppelte Kennungen in „{name}“")
        keys = [(m.device_id, m.face) for m in content.mappings]
        if len(keys) != len(set(keys)):
            raise cls._fail("Duplicate face mapping", "doppelte Seitenzuordnung")
        action_keys = [(a.device_id, a.face) for a in content.actions]
        if len(action_keys) != len(set(action_keys)):
            raise cls._fail("Duplicate face action", "doppelte Aktion für eine Seite")
        names = [i.name.casefold() for i in content.integrations]
        if len(names) != len(set(names)):
            raise cls._fail("Duplicate integration name", "doppelte Namen bei den Verbindungen")
        devices, activities = set(groups["devices"]), set(groups["activities"])
        projects, sessions = set(groups["projects"]), set(groups["sessions"])
        problems = (
            [
                f"face mapping of unknown device {m.device_id}"
                for m in content.mappings
                if m.device_id not in devices
            ]
            + [
                f"face mapping with unknown activity {m.activity_id}"
                for m in content.mappings
                if m.activity_id and m.activity_id not in activities
            ]
            + [
                f"face mapping with unknown project {m.project_id}"
                for m in content.mappings
                if m.project_id and m.project_id not in projects
            ]
            + [
                f"session {s.id} with unknown activity"
                for s in content.sessions
                if s.activity_id not in activities
            ]
            + [
                f"session {s.id} with unknown project"
                for s in content.sessions
                if s.project_id and s.project_id not in projects
            ]
            + [
                f"session {s.id} with unknown device"
                for s in content.sessions
                if s.device_id and s.device_id not in devices
            ]
            + [
                f"event {e.id} of unknown device"
                for e in content.events
                if e.device_id not in devices
            ]
            + [
                f"correction {c.id} of unknown session"
                for c in content.corrections
                if c.session_id not in sessions
            ]
            + [
                f"face action of unknown device {a.device_id}"
                for a in content.actions
                if a.device_id not in devices
            ]
            + [
                f"face action with unknown integration {a.integration_id}"
                for a in content.actions
                if a.integration_id not in set(groups["integrations"])
            ]
        )
        if problems:
            raise cls._fail(problems[0], f"Verweis auf nicht vorhandene Daten ({problems[0]})")

    def inspect_backup_text(self, text: str) -> BackupSummary:
        """Validate a backup document completely **without changing anything**.

        Raises:
            ImportDataError: With a precise message if anything is wrong.
        """
        return self._parse(text)[1]

    def inspect_backup(self, path: Path) -> BackupSummary:
        """Validate a backup file without changing anything (restore preview)."""
        return self.inspect_backup_text(self._read(path))

    @staticmethod
    def _read(path: Path) -> str:
        return read_text_limited(path, encoding="utf-8-sig", max_bytes=MAX_BACKUP_BYTES)

    def _parse(self, text: str) -> tuple[BackupContent, BackupSummary]:
        """Parse and validate a backup document."""
        try:
            document = json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise self._fail(f"Not valid JSON: {exc}", "kein gültiges JSON") from exc
        if not isinstance(document, dict) or document.get("format") != BACKUP_FORMAT:
            raise self._fail("Wrong or missing format marker", "falsches oder fehlendes Format")
        version = document.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise self._fail("Invalid schema_version", "ungültige Versionsangabe")
        if version > BACKUP_SCHEMA_VERSION:
            raise ImportDataError(
                f"Backup schema v{version} is newer than supported v{BACKUP_SCHEMA_VERSION}",
                user_message=(
                    "Die Sicherung stammt von einer neueren OctaLedger-Version. "
                    "Bitte das Programm aktualisieren. Es wurden keine Daten verändert."
                ),
            )
        data = document.get("data")
        if not isinstance(data, dict):
            raise self._fail("Missing data section", "Datenabschnitt fehlt")
        if document.get("checksum") != self._checksum(data):
            raise self._fail(
                "Checksum mismatch (file damaged or modified)",
                "Prüfsumme stimmt nicht (Datei beschädigt oder verändert)",
            )
        try:
            exported_at = from_db_time(document.get("exported_at", ""))
        except OctaLedgerError as exc:
            raise self._fail("Invalid exported_at", "ungültiges Exportdatum") from exc
        content = self._decode(data, version)
        summary = BackupSummary(
            schema_version=version,
            app_version=str(document.get("app_version", "?"))[:50],
            exported_at=exported_at,
            counts=content.counts(),
        )
        return content, summary

    def restore_backup_text(self, text: str) -> RestoreResult:
        """Replace the current database content with the backup in ``text``.

        Order: validate completely (nothing changes on failure), write a verified
        pre-restore copy of the current database, then replace everything in **one**
        transaction (rolled back on any error) and record the restore in the audit log.

        Raises:
            ImportDataError: If validation or the restore fails; the previous data remains.
        """
        content, summary = self._parse(text)
        pre_restore = self._backup_dir / f"octaledger-pre-restore-{self._stamp()}.sqlite3"
        self._storage.database.backup_to(pre_restore)  # abort the restore if this fails
        try:
            with self._storage.transaction() as repos:
                repos.backup.replace_all(content)
                repos.audit.add(
                    "restore",
                    "database",
                    None,
                    f"backup of {to_db_time(summary.exported_at)}, "
                    f"{sum(summary.counts.values())} records",
                )
        except OctaLedgerError as exc:
            raise ImportDataError(
                f"Restore failed and was rolled back: {exc}",
                user_message=(
                    "Die Wiederherstellung wurde abgebrochen, weil die Daten einer Regel "
                    f"widersprechen ({exc.user_message}). Ihre bisherigen Daten sind unverändert."
                ),
                details={"cause_code": exc.error_code},
            ) from exc
        logger.warning(
            "Database restored from backup of %s; previous state kept in %s",
            summary.exported_at.isoformat(),
            pre_restore.name,
        )
        return RestoreResult(summary, pre_restore)

    def restore_backup(self, path: Path) -> RestoreResult:
        """Restore from a backup file (see :meth:`restore_backup_text`)."""
        return self.restore_backup_text(self._read(path))
