"""Tests for the SQLite layer: schema, constraints, transactions, migrations, backup."""

import sqlite3
from pathlib import Path

import pytest

from octaledger.core.errors import (
    ConflictError,
    DataIntegrityError,
    MigrationError,
    StorageError,
)
from octaledger.infrastructure.storage import database as dbmod
from octaledger.infrastructure.storage.database import (
    Database,
    Migration,
    load_migrations,
    split_statements,
    translate_sqlite_error,
)

T1 = "2026-01-05T08:00:00.000000Z"
T2 = "2026-01-05T09:00:00.000000Z"
T3 = "2026-01-05T10:00:00.000000Z"
T4 = "2026-01-05T11:00:00.000000Z"


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "data" / "test.sqlite3", backup_dir=tmp_path / "backups")
    database.initialize()
    return database


def add_activity(conn: sqlite3.Connection, name: str = "Meeting", id_: str = "a1") -> None:
    conn.execute("INSERT INTO activities (id, name, color) VALUES (?, ?, '#AABBCC')", (id_, name))


def add_session(
    conn: sqlite3.Connection, id_: str, start: str, end: str | None, activity: str = "a1"
) -> None:
    conn.execute(
        "INSERT INTO sessions (id, activity_id, started_at, ended_at, source, quality, revision) "
        "VALUES (?, ?, ?, ?, 'manual', 'confirmed', 1)",
        (id_, activity, start, end),
    )


# ------------------------------------------------------------------------- initialisation


def test_initialize_creates_schema(db: Database) -> None:
    assert db.schema_version() == 1
    with db.connect() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "devices",
        "activities",
        "projects",
        "face_mappings",
        "raw_events",
        "sessions",
        "corrections",
        "audit_log",
        "schema_migrations",
    } <= tables


def test_initialize_is_idempotent(db: Database) -> None:
    assert db.initialize() == []
    assert db.schema_version() == 1


def test_initialize_returns_applied_versions(tmp_path: Path) -> None:
    assert Database(tmp_path / "x.sqlite3").initialize() == [1]


def test_connection_pragmas(db: Database) -> None:
    with db.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 1000


def test_new_database_gets_no_backup(tmp_path: Path) -> None:
    Database(tmp_path / "x.sqlite3", backup_dir=tmp_path / "b").initialize()
    assert not (tmp_path / "b").exists()


def test_integrity_check_healthy(db: Database) -> None:
    assert db.integrity_check() == []


# ---------------------------------------------------------------------------- constraints


def test_invalid_colour_rejected_by_check(db: Database) -> None:
    with db.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO activities (id, name, color) VALUES ('x', 'n', 'red')")


def test_active_activity_names_unique_case_insensitive(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn, "Meeting", "a1")
        with pytest.raises(sqlite3.IntegrityError):
            add_activity(conn, "MEETING", "a2")


def test_archived_activity_name_can_be_reused(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn, "Meeting", "a1")
        conn.execute("UPDATE activities SET archived = 1 WHERE id = 'a1'")
        add_activity(conn, "Meeting", "a2")  # allowed: old one is archived


def test_device_alias_unique(db: Database) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO devices (id, alias, created_at) VALUES ('d1', 'Büro', ?)", (T1,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO devices (id, alias, created_at) VALUES ('d2', 'büro', ?)", (T1,)
            )


def test_face_must_be_1_to_8(db: Database) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO devices (id, alias, created_at) VALUES ('d1', 'A', ?)", (T1,))
        for face in (0, 9):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO face_mappings (device_id, face, revision) VALUES ('d1', ?, 1)",
                    (face,),
                )


def test_foreign_key_enforced(db: Database) -> None:
    with db.connect() as conn, pytest.raises(sqlite3.IntegrityError):
        add_session(conn, "s1", T1, T2, activity="missing")


def test_cannot_delete_activity_used_by_session(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn)
        add_session(conn, "s1", T1, T2)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM activities WHERE id = 'a1'")


def test_deleting_device_removes_its_mappings_but_keeps_history_protected(db: Database) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO devices (id, alias, created_at) VALUES ('d1', 'A', ?)", (T1,))
        conn.execute("INSERT INTO face_mappings (device_id, face, revision) VALUES ('d1', 1, 1)")
        conn.execute(
            "INSERT INTO raw_events (id, device_id, kind, raw_value, sequence, connection_id, "
            "received_at) VALUES ('e1', 'd1', 'baseline', 1, 0, 'c', ?)",
            (T1,),
        )
        with pytest.raises(sqlite3.IntegrityError):  # events keep the device alive
            conn.execute("DELETE FROM devices WHERE id = 'd1'")
        conn.execute("DELETE FROM raw_events WHERE id = 'e1'")
        conn.execute("DELETE FROM devices WHERE id = 'd1'")
        assert conn.execute("SELECT COUNT(*) FROM face_mappings").fetchone()[0] == 0


@pytest.mark.parametrize("kind, value", [("baseline", 9), ("nonsense", None), ("baseline", -1)])
def test_raw_event_checks(db: Database, kind: str, value: int | None) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO devices (id, alias, created_at) VALUES ('d1', 'A', ?)", (T1,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_events (id, device_id, kind, raw_value, sequence, connection_id, "
                "received_at) VALUES ('e', 'd1', ?, ?, 0, 'c', ?)",
                (kind, value, T1),
            )


def test_session_end_must_not_precede_start(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn)
        with pytest.raises(sqlite3.IntegrityError):
            add_session(conn, "s1", T2, T1)


def test_device_session_needs_device(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sessions (id, activity_id, started_at, source, quality, revision) "
                "VALUES ('s', 'a1', ?, 'device', 'confirmed', 1)",
                (T1,),
            )


# ------------------------------------------------------------- overlap rules (triggers)


def test_overlapping_insert_rejected(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn)
        add_session(conn, "s1", T1, T3)
        with pytest.raises(sqlite3.IntegrityError, match="overlap"):
            add_session(conn, "s2", T2, T4)


def test_touching_sessions_allowed(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn)
        add_session(conn, "s1", T1, T2)
        add_session(conn, "s2", T2, T3)  # starts exactly when the previous ends


def test_running_session_blocks_overlap_and_second_running(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn)
        add_session(conn, "s1", T2, None)  # running
        with pytest.raises(sqlite3.IntegrityError):
            add_session(conn, "s2", T3, T4)  # inside running span
        with pytest.raises(sqlite3.IntegrityError):
            add_session(conn, "s3", T1, None)  # second running session


def test_finished_session_before_running_is_allowed(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn)
        add_session(conn, "s1", T2, None)
        add_session(conn, "s0", T1, T2)


def test_update_causing_overlap_rejected_but_own_row_ignored(db: Database) -> None:
    with db.connect() as conn:
        add_activity(conn)
        add_session(conn, "s1", T1, T2)
        add_session(conn, "s2", T3, T4)
        with pytest.raises(sqlite3.IntegrityError, match="overlap"):
            # Extend s1 into s2 (10:00-11:00): proper fixed-width timestamp 10:30.
            conn.execute(
                "UPDATE sessions SET ended_at = '2026-01-05T10:30:00.000000Z' WHERE id = 's1'"
            )
        conn.execute("UPDATE sessions SET ended_at = ? WHERE id = 's1'", (T2,))  # no change: ok
        conn.execute("UPDATE sessions SET ended_at = ? WHERE id = 's2'", (T4,))  # own row only


# ----------------------------------------------------------------------------- transactions


def test_transaction_commits(db: Database) -> None:
    with db.transaction() as conn:
        add_activity(conn)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1


def test_transaction_rolls_back_on_exception(db: Database) -> None:
    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            add_activity(conn)
            raise RuntimeError("boom")
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0


def test_transaction_translates_sqlite_errors_and_rolls_back(db: Database) -> None:
    with pytest.raises(ConflictError) as info:
        with db.transaction() as conn:
            add_activity(conn, "A", "a1")
            add_activity(conn, "a", "a2")  # duplicate name
    assert info.value.error_code == "OL-STATE-002"
    assert isinstance(info.value.__cause__, sqlite3.IntegrityError)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0


def test_locked_database_reports_storage_error(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dbmod, "BUSY_TIMEOUT_MS", 100)
    with db.transaction():  # holds the write lock
        with pytest.raises(StorageError) as info:
            with db.transaction():
                pass
    assert "belegt" in info.value.user_message


# ------------------------------------------------------------------------------ migrations


def test_load_migrations_real() -> None:
    migrations = load_migrations()
    assert [m.version for m in migrations] == [1]
    assert migrations[0].name == "initial"
    assert len(migrations[0].checksum) == 64


def _fake_migrations(monkeypatch: pytest.MonkeyPatch, items: list[Migration]) -> None:
    monkeypatch.setattr(dbmod, "load_migrations", lambda: items)


def test_second_migration_is_applied_after_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "d.sqlite3", backup_dir=tmp_path / "bk")
    real = load_migrations()
    _fake_migrations(monkeypatch, real)
    database.initialize()
    with database.transaction() as conn:
        add_activity(conn)
    extra = Migration(2, "add_table", "CREATE TABLE extra (id INTEGER PRIMARY KEY);")
    _fake_migrations(monkeypatch, [*real, extra])
    assert database.initialize() == [2]
    assert database.schema_version() == 2
    backups = list((tmp_path / "bk").glob("octaledger-pre-migration-v1-to-v2-*.sqlite3"))
    assert len(backups) == 1
    # The backup holds the pre-migration state: data present, new table absent.
    with sqlite3.connect(backups[0]) as copy:
        assert copy.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1
        assert copy.execute("SELECT 1 FROM sqlite_master WHERE name = 'extra'").fetchone() is None


def test_failing_migration_rolls_back_and_keeps_earlier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "d.sqlite3", backup_dir=tmp_path / "bk")
    real = load_migrations()
    _fake_migrations(monkeypatch, real)
    database.initialize()
    bad = Migration(
        2, "bad", "CREATE TABLE half (id INTEGER);\nINSERT INTO missing_table VALUES (1);"
    )
    _fake_migrations(monkeypatch, [*real, bad])
    with pytest.raises(MigrationError) as info:
        database.initialize()
    assert info.value.details == {"version": 2}
    assert database.schema_version() == 1  # failed migration not recorded
    with database.connect() as conn:  # and its partial work was rolled back
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'half'").fetchone() is None


def test_newer_database_is_refused_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "d.sqlite3")
    real = load_migrations()
    _fake_migrations(monkeypatch, [*real, Migration(2, "future", "CREATE TABLE f (id INTEGER);")])
    database.initialize()
    _fake_migrations(monkeypatch, real)  # "older program" opens the newer database
    with pytest.raises(MigrationError) as info:
        database.initialize()
    assert info.value.details == {"database": 2, "program": 1}
    assert "neueren" in info.value.user_message


def test_modified_applied_migration_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "d.sqlite3")
    real = load_migrations()
    _fake_migrations(monkeypatch, real)
    database.initialize()
    tampered = [Migration(1, real[0].name, real[0].sql + "\n-- changed\n")]
    _fake_migrations(monkeypatch, tampered)
    with pytest.raises(MigrationError, match="modified"):
        database.initialize()


def test_missing_backup_dir_still_migrates_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    database = Database(tmp_path / "d.sqlite3")  # no backup_dir
    real = load_migrations()
    _fake_migrations(monkeypatch, real)
    database.initialize()
    _fake_migrations(monkeypatch, [*real, Migration(2, "x", "CREATE TABLE x (id INTEGER);")])
    assert database.initialize() == [2]


def test_load_migrations_validates_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "migrations"
    folder.mkdir()
    monkeypatch.setattr(dbmod.resources, "files", lambda _pkg: tmp_path)

    (folder / "0001_a.sql").write_text("SELECT 1;", encoding="utf-8")
    (folder / "0003_c.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError, match="consecutive"):
        load_migrations()

    (folder / "0003_c.sql").unlink()
    (folder / "bad name.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError, match="Malformed"):
        load_migrations()

    (folder / "bad name.sql").unlink()
    (folder / "notes.txt").write_text("ignored", encoding="utf-8")
    assert [m.version for m in load_migrations()] == [1]


# ------------------------------------------------------------------------ SQL splitting


def test_split_statements_handles_trigger_bodies() -> None:
    sql = (
        "-- comment; with semicolon\n"
        "CREATE TABLE t (a INTEGER);\n"
        "CREATE TRIGGER trg BEFORE INSERT ON t BEGIN\n"
        "  SELECT RAISE(ABORT, 'x');\n"
        "END;\n"
        "INSERT INTO t VALUES (1);\n"
        "-- trailing comment only\n"
    )
    statements = split_statements(sql)
    assert len(statements) == 3
    assert statements[1].startswith("CREATE TRIGGER") and statements[1].endswith("END;")


def test_split_statements_rejects_incomplete() -> None:
    with pytest.raises(MigrationError):
        split_statements("CREATE TABLE t (a INTEGER")


def test_split_statements_empty() -> None:
    assert split_statements("") == []
    assert split_statements("-- only comment\n") == []


# -------------------------------------------------------------------------- error mapping


@pytest.mark.parametrize(
    "exc, expected",
    [
        (sqlite3.IntegrityError("UNIQUE constraint failed"), ConflictError),
        (sqlite3.DatabaseError("file is not a database"), DataIntegrityError),
        (sqlite3.DatabaseError("database disk image is malformed"), DataIntegrityError),
        (sqlite3.OperationalError("database is locked"), StorageError),
        (sqlite3.OperationalError("disk I/O error"), StorageError),
    ],
)
def test_translate_sqlite_error(exc: sqlite3.Error, expected: type[Exception]) -> None:
    assert type(translate_sqlite_error(exc, "test")) is expected


# ----------------------------------------------------------------------------------- backup


def test_backup_to_creates_verified_copy(db: Database, tmp_path: Path) -> None:
    with db.transaction() as conn:
        add_activity(conn)
    target = db.backup_to(tmp_path / "out" / "copy.sqlite3")
    assert target.exists()
    assert not list((tmp_path / "out").glob(".*.tmp"))  # no temp leftovers
    restored = Database(target)
    assert restored.integrity_check() == []
    with restored.connect() as conn:
        assert conn.execute("SELECT name FROM activities").fetchone()[0] == "Meeting"


def test_backup_to_unwritable_target_fails(db: Database, tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(StorageError):
        db.backup_to(blocker / "copy.sqlite3")


# ----------------------------------------------------------------------------- corruption


def test_garbage_file_is_reported_as_integrity_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.sqlite3"
    path.write_bytes(b"this is definitely not a sqlite database" * 20)
    with pytest.raises(DataIntegrityError):
        Database(path).initialize()


def test_integrity_check_reports_foreign_key_violation(db: Database) -> None:
    with db.connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")  # create an orphan on purpose
        add_session(conn, "s1", T1, T2, activity="ghost")
    problems = db.integrity_check()
    assert any("foreign key" in p and "sessions" in p for p in problems)
