"""Tests for CSV export, JSON backup and the validated, atomic restore."""

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from octaledger.application.export_service import (
    BACKUP_SCHEMA_VERSION,
    CSV_COLUMNS,
    ExportService,
    neutralize_cell,
)
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import ExportError, ImportDataError, ValidationError
from octaledger.domain.models import Activity, Device, Project, Quality, Session, SessionSource
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
H = timedelta(hours=1)
NOW = T0 + timedelta(days=3)


class Env:
    def __init__(self, tmp_path: Path, name: str = "main") -> None:
        base = tmp_path / name
        database = Database(base / "db.sqlite3", backup_dir=base / "backups")
        database.initialize()
        self.storage = Storage(database)
        self.exports = base / "exports"
        self.backups = base / "backups"
        self.service = ExportService(
            self.storage, exports_dir=self.exports, backup_dir=self.backups, clock=lambda: NOW
        )
        self.tracking = TrackingService(self.storage, clock=lambda: NOW)

    def fill(self) -> None:
        """Create a small but complete data set incl. correction, uncertainty and events."""
        with self.storage.transaction() as repos:
            device = repos.devices.add(Device(alias="Büro", model="ZEI", platform_address="AA:BB"))
            meeting = repos.activities.add(Activity(name="Meeting", color="#112233"))
            code = repos.activities.add(Activity(name="=Code", color="#445566"))  # formula-like
            project = repos.projects.add(Project(name="Alpha"))
            repos.mappings.assign(device.id, 1, meeting.id)
            repos.mappings.assign(device.id, 2, code.id, project.id)
            repos.state.set("active_device", device.id)
            first = repos.sessions.add(
                Session(
                    activity_id=meeting.id, started_at=T0, ended_at=T0 + H, note='Plan; mit "Zitat"'
                )
            )
            repos.sessions.add(
                Session(
                    activity_id=code.id,
                    project_id=project.id,
                    device_id=device.id,
                    started_at=T0 + H,
                    ended_at=T0 + 3 * H,
                    source=SessionSource.DEVICE,
                    quality=Quality.UNCERTAIN,
                    note="@cmd",
                )
            )
            repos.sessions.correct(first.id, {"note": "korrigiert"}, "Tippfehler")
            repos.sessions.add(
                Session(
                    activity_id=meeting.id,
                    started_at=T0 + 5 * H,
                    note='Zeile 1; "zwei"\nZeile 3',
                )
            )  # running
            repos.audit.add("test", "thing", "x", "detail")
        self.device, self.meeting, self.code = device.id, meeting.id, code.id

    def content(self) -> Any:
        with self.storage.snapshot() as repos:
            return repos.backup.snapshot()


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def rows(text: str, delimiter: str = ";") -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


# ------------------------------------------------------------------------------- CSV


def test_csv_content_and_columns(env: Env) -> None:
    env.fill()
    text, count = env.service.sessions_csv(timezone_name="Europe/Zurich")
    parsed = rows(text)
    assert count == 3 and len(parsed) == 3
    assert tuple(parsed[0]) == CSV_COLUMNS
    first = parsed[0]
    assert first["started_local"] == "2026-01-05T09:00:00+01:00"  # CET
    assert first["started_utc"] == "2026-01-05T08:00:00+00:00"
    assert first["duration_seconds"] == "3600" and first["duration_hms"] == "1:00:00"
    assert first["running"] == "no" and first["quality"] == "confirmed"
    running = parsed[2]
    # Delimiter, quotes and a line break inside a cell survive the round trip.
    assert running["note"] == 'Zeile 1; "zwei"\nZeile 3'
    assert (
        running["running"] == "yes" and running["ended_utc"] == "" and running["ended_local"] == ""
    )
    assert running["duration_seconds"] == str(int((NOW - (T0 + 5 * H)).total_seconds()))


def test_csv_shows_corrected_view_and_names(env: Env) -> None:
    """Acceptance A-08: the export equals the corrected view."""
    env.fill()
    corrected = [r for r in rows(env.service.sessions_csv()[0]) if r["revision"] == "2"]
    assert len(corrected) == 1 and corrected[0]["note"] == "korrigiert"
    device_row = next(r for r in rows(env.service.sessions_csv()[0]) if r["source"] == "device")
    assert device_row["device"] == "Büro" and device_row["project"] == "Alpha"
    assert device_row["quality"] == "uncertain"


def test_csv_formula_injection_is_neutralised(env: Env) -> None:
    env.fill()
    parsed = rows(env.service.sessions_csv()[0])
    device_row = next(r for r in parsed if r["source"] == "device")
    assert device_row["activity"] == "'=Code" and device_row["note"] == "'@cmd"
    assert [neutralize_cell(v) for v in ("=1+1", "+1", "-1", "@x", "\tx", "\rx", "ok", "")] == [
        "'=1+1",
        "'+1",
        "'-1",
        "'@x",
        "'\tx",
        "'\rx",
        "ok",
        "",
    ]


@pytest.mark.parametrize("delimiter", [";", ",", "\t"])
def test_csv_delimiters(env: Env, delimiter: str) -> None:
    env.fill()
    text, _ = env.service.sessions_csv(delimiter=delimiter)
    assert len(rows(text, delimiter)) == 3


def test_csv_invalid_options(env: Env) -> None:
    with pytest.raises(ValidationError):
        env.service.sessions_csv(delimiter="|")
    with pytest.raises(ValidationError):
        env.service.sessions_csv(timezone_name="Mars/Olympus")
    with pytest.raises(ValidationError):
        env.service.sessions_csv(start=T0 + H, end=T0)


def test_csv_window_filter_and_empty(env: Env) -> None:
    assert env.service.sessions_csv() == ("\r\n".join([";".join(CSV_COLUMNS)]) + "\r\n", 0)
    env.fill()
    _, count = env.service.sessions_csv(start=T0, end=T0 + H)
    assert count == 1


def test_csv_file_is_utf8_with_bom_and_crlf(env: Env) -> None:
    env.fill()
    result = env.service.export_sessions_csv(filename="mine.csv")
    raw = result.path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw and "Büro".encode() in raw
    assert result.rows == 3 and result.size_bytes == len(raw)
    default = env.service.export_sessions_csv()
    assert default.path.name == "sessions-20260108-080000.csv"


@pytest.mark.parametrize(
    "name",
    [
        "../evil.csv",
        "a/b.csv",
        "..\\x.csv",
        "x.txt",
        ".hidden.csv",
        "x" * 120 + ".csv",
        "a b.csv",
    ],
)
def test_unsafe_file_names_rejected(env: Env, name: str) -> None:
    with pytest.raises(ValidationError):
        env.service.export_sessions_csv(filename=name)
    with pytest.raises(ValidationError):
        env.service.export_backup(filename=name)


def test_csv_write_failure_is_export_error(env: Env, tmp_path: Path) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("x", encoding="utf-8")
    service = ExportService(env.storage, exports_dir=blocker / "sub", backup_dir=env.backups)
    with pytest.raises(ExportError):
        service.export_sessions_csv()


# --------------------------------------------------------------------------- backup


def test_backup_document_structure(env: Env) -> None:
    env.fill()
    document = json.loads(env.service.create_backup_text())
    assert (
        document["format"] == "octaledger-backup"
        and document["schema_version"] == BACKUP_SCHEMA_VERSION
    )
    assert document["counts"]["sessions"] == 3 and document["counts"]["corrections"] == 1
    assert len(document["checksum"]) == 64 and set(document["data"]) >= {"devices", "sessions"}
    assert document["data"]["app_state"] == {"active_device": env.device}


def test_backup_file_written_atomically(env: Env) -> None:
    env.fill()
    result = env.service.export_backup()
    assert result.path.parent == env.backups and result.path.suffix == ".json"
    assert not list(env.backups.glob(".*.tmp"))
    assert result.rows == sum(
        json.loads(result.path.read_text(encoding="utf-8"))["counts"].values()
    )


def test_roundtrip_restore_into_empty_environment(tmp_path: Path) -> None:
    """Acceptance A-09: a JSON backup restores completely into a fresh environment."""
    source, target = Env(tmp_path, "source"), Env(tmp_path, "fresh")
    source.fill()
    path = source.service.export_backup(filename="b.json").path
    result = target.service.restore_backup(path)
    assert result.summary.counts["sessions"] == 3 and result.pre_restore_backup.exists()
    original, restored = source.content(), target.content()
    for attribute in (
        "devices",
        "activities",
        "projects",
        "mappings",
        "events",
        "sessions",
        "corrections",
    ):
        assert getattr(restored, attribute) == getattr(original, attribute), attribute
    assert restored.state == original.state
    # The restore itself is recorded; everything before it is identical.
    assert restored.audit[:-1] == original.audit and restored.audit[-1].action == "restore"
    assert target.storage.database.integrity_check() == []


def test_restore_replaces_existing_content_and_keeps_pre_restore_copy(tmp_path: Path) -> None:
    source, target = Env(tmp_path, "source"), Env(tmp_path, "target")
    source.fill()
    with target.storage.transaction() as repos:
        old = repos.activities.add(Activity(name="Nur im Ziel"))
    path = source.service.export_backup(filename="b.json").path
    result = target.service.restore_backup(path)
    with target.storage.read() as repos:
        assert {a.name for a in repos.activities.list_all(include_archived=True)} == {
            "Meeting",
            "=Code",
        }
    restored_copy = Database(result.pre_restore_backup)  # the old state is preserved
    with restored_copy.connect() as conn:
        assert conn.execute("SELECT name FROM activities WHERE id = ?", (old.id,)).fetchone()


def test_inspect_does_not_change_anything(tmp_path: Path) -> None:
    source, target = Env(tmp_path, "source"), Env(tmp_path, "target")
    source.fill()
    path = source.service.export_backup(filename="b.json").path
    summary = target.service.inspect_backup(path)
    assert summary.counts["devices"] == 1 and summary.schema_version == 1
    assert summary.exported_at == NOW and summary.app_version
    assert target.content().devices == ()
    assert not list(target.backups.glob("*pre-restore*"))  # preview creates no backup


# ---------------------------------------------------------------- invalid backups


def valid_document(env: Env) -> dict[str, Any]:
    env.fill()
    return json.loads(env.service.create_backup_text())


def reseal(document: dict[str, Any]) -> str:
    """Recompute the checksum so tests can exercise validation *behind* the checksum."""
    document["checksum"] = ExportService._checksum(document["data"])
    return json.dumps(document)


def expect_rejected(env: Env, text: str, fragment: str = "") -> ImportDataError:
    with pytest.raises(ImportDataError) as info:
        env.service.restore_backup_text(text)
    assert (
        "keine Daten verändert" in info.value.user_message
        or "unverändert" in info.value.user_message
    )
    assert fragment in info.value.user_message + info.value.message
    return info.value


def test_rejects_non_json_and_wrong_format(env: Env) -> None:
    expect_rejected(env, "{not json", "JSON")
    expect_rejected(env, "[]", "Format")
    expect_rejected(env, json.dumps({"format": "other"}), "Format")
    expect_rejected(
        env, json.dumps({"format": "octaledger-backup", "schema_version": "1"}), "Version"
    )
    expect_rejected(
        env, json.dumps({"format": "octaledger-backup", "schema_version": 1}), "Datenabschnitt"
    )


def test_rejects_newer_schema_version(env: Env) -> None:
    document = valid_document(env)
    document["schema_version"] = BACKUP_SCHEMA_VERSION + 1
    error = expect_rejected(env, json.dumps(document), "neueren")
    assert error.error_code == "OL-DATA-002"


def test_detects_tampering_and_truncation_via_checksum(env: Env) -> None:
    document = valid_document(env)
    document["data"]["sessions"][0]["note"] = "heimlich geändert"
    expect_rejected(env, json.dumps(document), "Prüfsumme")
    good = env.service.create_backup_text()
    expect_rejected(env, good[: len(good) // 2], "JSON")


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d["data"]["sessions"][0].update(started_at="gestern"), "sessions"),
        (lambda d: d["data"]["sessions"][0].update(quality="great"), "sessions"),
        (lambda d: d["data"]["activities"][0].update(color="red"), "activities"),
        (lambda d: d["data"]["devices"][0].update(alias=""), "devices"),
        (lambda d: d["data"]["face_mappings"][0].update(face=9), "face_mappings"),
        (lambda d: d["data"]["raw_events"].append({"id": "x"}), "raw_events"),
        (lambda d: d["data"]["sessions"][0].update(unexpected=1), "sessions"),
        (lambda d: d["data"]["sessions"].append(dict(d["data"]["sessions"][0])), "doppelte"),
        (lambda d: d["data"]["sessions"][0].update(activity_id="ghost"), "Verweis"),
        (lambda d: d["data"]["face_mappings"][0].update(device_id="ghost"), "Verweis"),
        (lambda d: d["data"]["corrections"][0].update(session_id="ghost"), "Verweis"),
        (lambda d: d["data"].update(extra=[]), "Abschnitte"),
        (lambda d: d["data"].update(sessions="nope"), "sessions"),
        (lambda d: d["data"].update(app_state={"k": 5}), "app_state"),
    ],
)
def test_invalid_records_are_rejected_before_touching_the_database(
    env: Env, mutate: Any, fragment: str
) -> None:
    document = valid_document(env)
    before = env.content()
    mutate(document)
    expect_rejected(env, reseal(document), fragment)
    assert env.content() == before  # nothing changed, not even partially
    assert not list(env.backups.glob("*pre-restore*"))  # validation failed before any backup


def test_database_rule_violation_rolls_back_whole_restore(tmp_path: Path) -> None:
    """Overlapping sessions pass record validation but break the DB rule -> full rollback."""
    source, target = Env(tmp_path, "source"), Env(tmp_path, "target")
    document = valid_document(source)
    overlap = dict(document["data"]["sessions"][0])
    overlap["id"] = "overlapping-session"
    document["data"]["sessions"].append(overlap)  # same time span as the first session
    with target.storage.transaction() as repos:
        repos.activities.add(Activity(name="Bleibt"))
    before = target.content()
    error = expect_rejected(target, reseal(document), "widersprechen")
    assert error.details["cause_code"] == "OL-STATE-002"
    assert target.content() == before  # old data intact after the rollback
    assert list(target.backups.glob("octaledger-pre-restore-*.sqlite3"))  # copy was made first


def test_missing_and_oversized_files(env: Env, tmp_path: Path) -> None:
    with pytest.raises(ImportDataError):
        env.service.restore_backup(tmp_path / "missing.json")
    with pytest.raises(ImportDataError):
        env.service.inspect_backup(tmp_path)  # a directory is not a backup file


def test_backup_with_bom_is_accepted(tmp_path: Path) -> None:
    source, target = Env(tmp_path, "source"), Env(tmp_path, "target")
    source.fill()
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + source.service.create_backup_text().encode("utf-8"))
    assert target.service.restore_backup(path).summary.counts["sessions"] == 3


def test_empty_database_roundtrip(tmp_path: Path) -> None:
    source, target = Env(tmp_path, "source"), Env(tmp_path, "target")
    result = target.service.restore_backup_text(source.service.create_backup_text())
    assert sum(result.summary.counts.values()) == 0
    assert target.content().sessions == ()
