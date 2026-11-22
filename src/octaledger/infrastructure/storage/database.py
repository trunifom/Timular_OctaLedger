"""SQLite connections, transactions and the migration lifecycle.

Responsibility
--------------
* Open correctly configured connections (:class:`Database.connect`).
* Provide explicit, atomic transactions (:class:`Database.transaction`).
* Apply versioned SQL migrations from ``migrations/NNNN_name.sql`` in order, each in one
  transaction, with a verified checksum for every applied migration and an automatic
  **backup before any migration of an existing database**.
* Translate ``sqlite3`` errors into OctaLedger errors (:func:`translate_sqlite_error`).

Design decisions
----------------
* **One short-lived connection per operation.** SQLite connections are cheap and not
  thread-safe by default. With WAL journaling, readers (the API threads) never block the
  single writer (the agent).
* **Explicit transactions.** Connections run in autocommit mode (``isolation_level=None``)
  and :meth:`Database.transaction` issues ``BEGIN IMMEDIATE`` / ``COMMIT`` / ``ROLLBACK``
  itself, so there is no hidden implicit transaction behaviour.
* **Migrations are plain SQL files** that can be reviewed in diffs. A database whose
  schema is *newer* than the program is never touched.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Final

from octaledger.core.errors import (
    ConflictError,
    DataIntegrityError,
    MigrationError,
    OctaLedgerError,
    StorageError,
)

logger = logging.getLogger(__name__)

#: Milliseconds SQLite waits for a lock before reporting "database is locked".
BUSY_TIMEOUT_MS: Final = 5000
_MIGRATION_FILE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


# ------------------------------------------------------------------------- error mapping


def translate_sqlite_error(exc: sqlite3.Error, action: str) -> OctaLedgerError:
    """Map a ``sqlite3`` exception to the matching OctaLedger error.

    Args:
        exc: The original exception (kept as ``__cause__`` by the caller via ``from``).
        action: Short English description of what was attempted ("insert device").

    Returns:
        * ``ConflictError`` for constraint violations (duplicates, foreign keys, the
          overlap trigger) - the user can fix the data,
        * ``DataIntegrityError`` for corrupt or non-database files,
        * ``StorageError`` for everything else (locked, I/O, ...).
    """
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, sqlite3.IntegrityError):
        return ConflictError(
            f"Constraint violated while trying to {action}: {text}",
            user_message=(
                "Die Änderung widerspricht bestehenden Daten "
                "(z. B. doppelter Name, Überschneidung oder noch verwendeter Eintrag)."
            ),
            details={"action": action, "sqlite": text},
        )
    if "not a database" in lowered or "malformed" in lowered or "corrupt" in lowered:
        return DataIntegrityError(
            f"Database file damaged while trying to {action}: {text}",
            details={"action": action},
        )
    if "locked" in lowered or "busy" in lowered:
        return StorageError(
            f"Database busy while trying to {action}: {text}",
            user_message="Die Datenbank ist gerade belegt. Bitte in einem Moment erneut versuchen.",
            details={"action": action},
        )
    return StorageError(
        f"Database error while trying to {action}: {text}", details={"action": action}
    )


# ---------------------------------------------------------------------------- migrations


@dataclass(frozen=True, slots=True)
class Migration:
    """One schema migration loaded from an SQL file."""

    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        """SHA-256 of the SQL text; stored to detect later modification."""
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def load_migrations() -> list[Migration]:
    """Load all packaged migrations, validated and sorted by version.

    Raises:
        MigrationError: If a file name is malformed, versions repeat or are not
            consecutive starting at 1.
    """
    directory = resources.files("octaledger.infrastructure.storage").joinpath("migrations")
    migrations: list[Migration] = []
    for entry in directory.iterdir():
        if not entry.name.endswith(".sql"):
            continue
        match = _MIGRATION_FILE.match(entry.name)
        if match is None:
            raise MigrationError(f"Malformed migration file name: {entry.name}")
        migrations.append(
            Migration(
                int(match[1]), match[2], entry.read_text(encoding="utf-8").replace("\r\n", "\n")
            )
        )
    migrations.sort(key=lambda m: m.version)
    expected = list(range(1, len(migrations) + 1))
    if [m.version for m in migrations] != expected:
        raise MigrationError(
            "Migration versions must be consecutive starting at 1",
            details={"found": [m.version for m in migrations]},
        )
    return migrations


def split_statements(sql: str) -> list[str]:
    """Split an SQL script into complete statements (handles triggers and comments).

    ``sqlite3.complete_statement`` recognises ``;`` inside ``CREATE TRIGGER ... END;``
    bodies correctly, which a naive ``split(";")`` would not.
    """
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip() and not all(
        part.strip().startswith("--") or not part.strip() for part in buffer.splitlines()
    ):
        raise MigrationError("Migration ends with an incomplete SQL statement")
    return statements


# ---------------------------------------------------------------------------------- Database


class Database:
    """Access point to the OctaLedger SQLite database file."""

    def __init__(self, path: Path, *, backup_dir: Path | None = None) -> None:
        """Create the accessor (nothing is opened or created yet).

        Args:
            path: Database file.
            backup_dir: Where pre-migration backups go; ``None`` disables them
                (only for tests and brand-new databases).
        """
        self._path = path
        self._backup_dir = backup_dir

    @property
    def path(self) -> Path:
        """The database file path."""
        return self._path

    # ----------------------------------------------------------------- connections

    def _open(self) -> sqlite3.Connection:
        """Open and configure a new connection.

        Raises:
            StorageError / DataIntegrityError: If the file cannot be opened.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self._path,
                timeout=BUSY_TIMEOUT_MS / 1000,
                isolation_level=None,  # autocommit; transactions are explicit
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error as exc:
            raise translate_sqlite_error(exc, f"open database {self._path.name}") from exc
        except OSError as exc:
            raise StorageError(
                f"Cannot prepare database directory {self._path.parent}: {exc}",
                details={"path": str(self._path)},
            ) from exc
        return connection

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and always close it afterwards."""
        connection = self._open()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection inside one atomic write transaction.

        ``BEGIN IMMEDIATE`` takes the write lock up front (no late "database is locked"
        in the middle of the work). The transaction commits on normal exit and rolls back
        on any exception, which is re-raised (``sqlite3`` errors are translated).
        """
        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as exc:
                raise translate_sqlite_error(exc, "begin transaction") from exc
            try:
                yield connection
            except sqlite3.Error as exc:
                self._rollback(connection)
                raise translate_sqlite_error(exc, "run transaction") from exc
            except BaseException:
                self._rollback(connection)
                raise
            try:
                connection.execute("COMMIT")
            except sqlite3.Error as exc:
                self._rollback(connection)
                raise translate_sqlite_error(exc, "commit transaction") from exc

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        """Roll back, ignoring the error if no transaction is active any more."""
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            logger.debug("Rollback skipped, no active transaction")

    # ------------------------------------------------------------------- migrations

    def schema_version(self) -> int:
        """Return the highest applied migration version (``0`` for a new database)."""
        with self.connect() as connection:
            try:
                return max(self._applied(connection), default=0)
            except sqlite3.Error as exc:
                raise translate_sqlite_error(exc, "read schema version") from exc

    @staticmethod
    def _applied(connection: sqlite3.Connection) -> dict[int, tuple[str, str]]:
        """Return ``{version: (name, checksum)}`` of applied migrations."""
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if exists is None:
            return {}
        rows = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations"
        ).fetchall()
        return {int(r["version"]): (str(r["name"]), str(r["checksum"])) for r in rows}

    def initialize(self) -> list[int]:
        """Create the database or bring it to the newest schema version.

        Steps: load migrations, verify the checksums of already applied ones, refuse a
        database that is newer than this program, back up an existing database before
        applying anything, then apply each pending migration atomically.

        Returns:
            The versions that were applied by this call (empty if up to date).

        Raises:
            MigrationError: On checksum mismatch, newer schema, or a failing migration
                (the failing migration is rolled back; earlier ones stay applied).
            StorageError / DataIntegrityError: On database problems.
        """
        migrations = load_migrations()
        latest = len(migrations)
        with self.connect() as connection:
            try:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                    "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
                )
                applied = self._applied(connection)
            except sqlite3.Error as exc:
                raise translate_sqlite_error(exc, "read migration state") from exc

            newest_applied = max(applied, default=0)
            if newest_applied > latest:
                raise MigrationError(
                    f"Database schema v{newest_applied} is newer than this program (v{latest})",
                    user_message=(
                        "Die Datenbank stammt von einer neueren OctaLedger-Version. "
                        "Bitte das Programm aktualisieren. Die Daten wurden nicht verändert."
                    ),
                    details={"database": newest_applied, "program": latest},
                )
            for migration in migrations:
                if migration.version in applied:
                    stored_name, stored_checksum = applied[migration.version]
                    if stored_checksum != migration.checksum:
                        raise MigrationError(
                            f"Migration {migration.version} ({stored_name}) was modified after "
                            "it was applied",
                            details={"version": migration.version},
                        )
            pending = [m for m in migrations if m.version not in applied]
            if not pending:
                logger.debug("Database schema up to date (v%d)", newest_applied)
                return []

            if newest_applied > 0:
                self._backup_before_migration(connection, newest_applied, latest)

            done: list[int] = []
            for migration in pending:
                self._apply(connection, migration)
                done.append(migration.version)
            logger.info("Database migrated to schema v%d (applied %s)", latest, done)
            return done

    def _apply(self, connection: sqlite3.Connection, migration: Migration) -> None:
        """Apply one migration inside one transaction (all or nothing)."""
        logger.info("Applying migration %04d_%s", migration.version, migration.name)
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in split_statements(migration.sql):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version, name, checksum, applied_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
            connection.execute("COMMIT")
        except (sqlite3.Error, MigrationError) as exc:
            self._rollback(connection)
            raise MigrationError(
                f"Migration {migration.version:04d}_{migration.name} failed: {exc}",
                details={"version": migration.version},
            ) from exc

    def _backup_before_migration(self, connection: sqlite3.Connection, old: int, new: int) -> None:
        """Copy the database into the backup folder before changing its schema."""
        if self._backup_dir is None:
            logger.warning("No backup directory configured; migrating without backup")
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = self._backup_dir / f"octaledger-pre-migration-v{old}-to-v{new}-{stamp}.sqlite3"
        self._copy_to(connection, target)
        logger.info("Pre-migration backup written to %s", target)

    # ---------------------------------------------------------------------- backup

    @staticmethod
    def _copy_to(source: sqlite3.Connection, target: Path) -> None:
        """Copy ``source`` to ``target`` atomically using the SQLite backup API.

        The copy is verified with ``PRAGMA integrity_check`` before it replaces the
        target, so a half-written or damaged backup never appears under its final name.
        """
        temporary = target.with_name(f".{target.name}.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(temporary)) as destination:
                source.backup(destination)
                result = destination.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise DataIntegrityError(
                    "Backup copy failed its integrity check", details={"result": str(result)}
                )
            os.replace(temporary, target)
        except sqlite3.Error as exc:
            raise translate_sqlite_error(exc, f"back up database to {target.name}") from exc
        except OSError as exc:
            raise StorageError(
                f"Cannot write backup {target}: {exc}",
                user_message="Die Datensicherung konnte nicht geschrieben werden.",
                details={"path": str(target)},
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    def backup_to(self, target: Path) -> Path:
        """Write a consistent, verified copy of the live database to ``target``.

        Safe while the agent is writing (SQLite backup API). Returns ``target``.
        """
        with self.connect() as connection:
            self._copy_to(connection, target)
        logger.info("Database backup written to %s", target)
        return target

    # ------------------------------------------------------------------- diagnostics

    def integrity_check(self) -> list[str]:
        """Run SQLite's integrity and foreign-key checks.

        Returns:
            A list of problem descriptions; empty means the database is healthy.
        """
        problems: list[str] = []
        with self.connect() as connection:
            try:
                for row in connection.execute("PRAGMA integrity_check"):
                    if row[0] != "ok":
                        problems.append(f"integrity: {row[0]}")
                for row in connection.execute("PRAGMA foreign_key_check"):
                    problems.append(
                        f"foreign key: table {row['table']} row {row['rowid']} -> {row['parent']}"
                    )
            except sqlite3.Error as exc:
                raise translate_sqlite_error(exc, "check integrity") from exc
        return problems
