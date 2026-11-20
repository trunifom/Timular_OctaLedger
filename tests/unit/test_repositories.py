"""Tests for repositories: CRUD, constraints, corrections, audit and transactions."""

import dataclasses
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from octaledger.core.errors import (
    ConflictError,
    DataIntegrityError,
    NotFoundError,
    ValidationError,
)
from octaledger.domain.models import (
    Activity,
    Device,
    EventKind,
    Project,
    Quality,
    RawEvent,
    Session,
    SessionSource,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import (
    Repositories,
    Storage,
    from_db_time,
    to_db_time,
)

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
H = timedelta(hours=1)


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    return Storage(database)


@pytest.fixture
def seeded(storage: Storage) -> dict[str, str]:
    """Create one device, two activities and one project; return their ids."""
    with storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Büro"))
        a1 = repos.activities.add(Activity(name="Meeting"))
        a2 = repos.activities.add(Activity(name="Code"))
        project = repos.projects.add(Project(name="Alpha"))
    return {"device": device.id, "a1": a1.id, "a2": a2.id, "project": project.id}


# ------------------------------------------------------------------------- time codec


def test_time_codec_roundtrip_and_fixed_width() -> None:
    value = datetime(2026, 1, 5, 8, 0, 0, 123, tzinfo=timezone.utc)
    text = to_db_time(value)
    assert text == "2026-01-05T08:00:00.000123Z"
    assert from_db_time(text) == value
    assert len(to_db_time(T0)) == len(text)  # fixed width


def test_time_codec_converts_offsets() -> None:
    plus_two = timezone(timedelta(hours=2))
    assert to_db_time(datetime(2026, 1, 5, 10, tzinfo=plus_two)) == to_db_time(T0)


def test_time_codec_ordering_matches_chronology() -> None:
    times = [T0 + timedelta(microseconds=i * 777_777) for i in range(50)]
    assert sorted(to_db_time(t) for t in times) == [to_db_time(t) for t in times]


@pytest.mark.parametrize("bad", ["", "2026-01-05", "2026-01-05T08:00:00Z", None])
def test_from_db_time_rejects_bad_text(bad: object) -> None:
    with pytest.raises(DataIntegrityError):
        from_db_time(bad)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------ devices


def test_device_crud(storage: Storage) -> None:
    with storage.transaction() as repos:
        device = repos.devices.add(Device(alias="A", model="X", firmware="1.0"))
        assert repos.devices.get(device.id) == device
        updated = repos.devices.update(dataclasses.replace(device, alias="B", firmware="1.1"))
        assert repos.devices.require(device.id).alias == "B"
        assert updated.firmware == "1.1"
        assert [d.alias for d in repos.devices.list_all()] == ["B"]
        repos.devices.delete(device.id, repos.audit)
        assert repos.devices.get(device.id) is None
        assert repos.audit.recent()[0].entity == "device"


def test_device_missing(storage: Storage) -> None:
    with storage.read() as repos:
        assert repos.devices.get("nope") is None
        with pytest.raises(NotFoundError):
            repos.devices.require("nope")
    with storage.transaction() as repos, pytest.raises(NotFoundError):
        repos.devices.update(Device(alias="ghost"))
    with storage.transaction() as repos, pytest.raises(NotFoundError):
        repos.devices.delete("nope")


def test_duplicate_device_alias_conflicts(storage: Storage) -> None:
    with pytest.raises(ConflictError):
        with storage.transaction() as repos:
            repos.devices.add(Device(alias="A"))
            repos.devices.add(Device(alias="a"))


def test_devices_listed_alphabetically_case_insensitive(storage: Storage) -> None:
    with storage.transaction() as repos:
        for alias in ("beta", "Alpha", "Gamma"):
            repos.devices.add(Device(alias=alias))
        assert [d.alias for d in repos.devices.list_all()] == ["Alpha", "beta", "Gamma"]


def test_device_with_events_cannot_be_deleted(storage: Storage, seeded: dict[str, str]) -> None:
    with storage.transaction() as repos:
        repos.events.add(
            RawEvent(
                device_id=seeded["device"], kind=EventKind.DISCONNECT, sequence=0, connection_id="c"
            )
        )
    with pytest.raises(ConflictError):
        with storage.transaction() as repos:
            repos.devices.delete(seeded["device"], repos.audit)


def test_failed_delete_leaves_no_audit_entry(storage: Storage, seeded: dict[str, str]) -> None:
    with storage.transaction() as repos:
        repos.sessions.add(Session(activity_id=seeded["a1"], started_at=T0, ended_at=T0 + H))
    with storage.transaction() as repos:
        with pytest.raises(ConflictError):
            repos.activities.delete(seeded["a1"], repos.audit)
        assert repos.audit.recent() == []  # savepoint rolled the audit entry back


# ----------------------------------------------------------- activities and projects


@pytest.mark.parametrize("kind", ["activities", "projects"])
def test_named_repository_lifecycle(storage: Storage, kind: str) -> None:
    model = Activity if kind == "activities" else Project
    with storage.transaction() as repos:
        repo = getattr(repos, kind)
        item = repo.add(model(name="One", color="#112233"))
        assert repo.get(item.id) == item
        repo.update(dataclasses.replace(item, name="Uno", color="#445566"))
        assert repo.require(item.id).name == "Uno"
        repo.set_archived(item.id, True)
        assert repo.list_all() == []  # archived hidden by default
        assert [i.name for i in repo.list_all(include_archived=True)] == ["Uno"]
        repo.set_archived(item.id, False)
        assert len(repo.list_all()) == 1
        repo.delete(item.id, repos.audit)
        assert repo.get(item.id) is None
        with pytest.raises(NotFoundError):
            repo.require(item.id)
        with pytest.raises(NotFoundError):
            repo.update(item)


def test_archived_name_can_be_reused(storage: Storage) -> None:
    with storage.transaction() as repos:
        old = repos.activities.add(Activity(name="Meeting"))
        repos.activities.set_archived(old.id, True)
        repos.activities.add(Activity(name="meeting"))
        assert len(repos.activities.list_all(include_archived=True)) == 2


def test_duplicate_active_name_conflicts(storage: Storage) -> None:
    with pytest.raises(ConflictError):
        with storage.transaction() as repos:
            repos.projects.add(Project(name="P"))
            repos.projects.add(Project(name="p"))


# ---------------------------------------------------------------------------- mappings


def test_mapping_assign_revision_and_clear(storage: Storage, seeded: dict[str, str]) -> None:
    d, a1, a2 = seeded["device"], seeded["a1"], seeded["a2"]
    with storage.transaction() as repos:
        first = repos.mappings.assign(d, 3, a1)
        assert first.revision == 1
        assert repos.mappings.assign(d, 3, a1).revision == 1  # identical: no bump
        second = repos.mappings.assign(d, 3, a2, seeded["project"])
        assert second.revision == 2
        assert repos.mappings.get(d, 3) == second
        repos.mappings.assign(d, 1, None)  # configured-as-empty is allowed
        assert [m.face for m in repos.mappings.list_for_device(d)] == [1, 3]
        repos.mappings.clear(d, 3)
        repos.mappings.clear(d, 3)  # idempotent
        assert repos.mappings.get(d, 3) is None


def test_mapping_invalid_face_and_unknown_references(
    storage: Storage, seeded: dict[str, str]
) -> None:
    with storage.transaction() as repos:
        with pytest.raises(ValidationError):
            repos.mappings.assign(seeded["device"], 9, seeded["a1"])
    with pytest.raises(ConflictError):
        with storage.transaction() as repos:
            repos.mappings.assign(seeded["device"], 1, "missing-activity")
    with pytest.raises(ConflictError):
        with storage.transaction() as repos:
            repos.mappings.assign("missing-device", 1, seeded["a1"])


def test_mappings_removed_with_device(storage: Storage, seeded: dict[str, str]) -> None:
    with storage.transaction() as repos:
        repos.mappings.assign(seeded["device"], 1, seeded["a1"])
        repos.devices.delete(seeded["device"], repos.audit)
        assert repos.mappings.list_for_device(seeded["device"]) == []


# ------------------------------------------------------------------------------ events


def _event(device_id: str, seq: int, minutes: int = 0, **kw: object) -> RawEvent:
    return RawEvent(
        device_id=device_id,
        kind=kw.pop("kind", EventKind.FACE_CHANGE),  # type: ignore[arg-type]
        sequence=seq,
        connection_id="c1",
        received_at=T0 + timedelta(minutes=minutes),
        raw_value=kw.pop("raw_value", 2),  # type: ignore[arg-type]
        **kw,  # type: ignore[arg-type]
    )


def test_events_roundtrip_ordering_and_filters(storage: Storage, seeded: dict[str, str]) -> None:
    d = seeded["device"]
    with storage.transaction() as repos:
        assert repos.events.add_many([_event(d, i, i) for i in range(5)]) == 5
        repos.events.add(
            _event(d, 9, 9, kind=EventKind.INVALID, raw_value=None, detail="bad length")
        )
        newest_first = repos.events.list_for_device(d)
        assert [e.sequence for e in newest_first] == [9, 4, 3, 2, 1, 0]
        assert newest_first[0].detail == "bad length"
        assert [e.sequence for e in repos.events.list_for_device(d, limit=2)] == [9, 4]
        recent = repos.events.list_for_device(d, since=T0 + timedelta(minutes=3))
        assert [e.sequence for e in recent] == [9, 4, 3]
        assert repos.events.count() == 6 and repos.events.count(d) == 6
        assert repos.events.count("other") == 0


@pytest.mark.parametrize("limit", [0, 100_001, -1])
def test_event_limit_validated(storage: Storage, limit: int) -> None:
    with storage.read() as repos, pytest.raises(ValidationError):
        repos.events.list_for_device("d", limit=limit)


def test_purge_old_events_records_audit(storage: Storage, seeded: dict[str, str]) -> None:
    d = seeded["device"]
    with storage.transaction() as repos:
        repos.events.add_many([_event(d, i, i * 10) for i in range(5)])
        deleted = repos.events.delete_older_than(T0 + timedelta(minutes=25), repos.audit)
        assert deleted == 3 and repos.events.count() == 2
        assert repos.audit.recent()[0].action == "purge"
        assert repos.events.delete_older_than(T0 - H, repos.audit) == 0  # nothing: no audit spam
        assert len(repos.audit.recent()) == 1


def test_event_with_unknown_device_conflicts(storage: Storage) -> None:
    with pytest.raises(ConflictError):
        with storage.transaction() as repos:
            repos.events.add(_event("missing", 0))


# ----------------------------------------------------------------------------- sessions


def _session(ids: dict[str, str], start: datetime, end: datetime | None, **kw: object) -> Session:
    return Session(
        activity_id=kw.pop("activity_id", ids["a1"]),  # type: ignore[arg-type]
        started_at=start,
        ended_at=end,
        **kw,  # type: ignore[arg-type]
    )


def test_session_roundtrip_all_fields(storage: Storage, seeded: dict[str, str]) -> None:
    session = Session(
        activity_id=seeded["a1"],
        project_id=seeded["project"],
        device_id=seeded["device"],
        started_at=T0,
        ended_at=T0 + H,
        source=SessionSource.DEVICE,
        quality=Quality.UNCERTAIN,
        note="Notiz",
    )
    with storage.transaction() as repos:
        repos.sessions.add(session)
    with storage.read() as repos:
        assert repos.sessions.get(session.id) == session
        assert repos.sessions.require(session.id) == session
        assert repos.sessions.get_running() is None


def test_running_session_and_end(storage: Storage, seeded: dict[str, str]) -> None:
    with storage.transaction() as repos:
        running = repos.sessions.add(_session(seeded, T0, None))
        assert repos.sessions.get_running() == running
        ended = repos.sessions.end(running.id, T0 + H, Quality.UNCERTAIN)
        assert ended.ended_at == T0 + H and ended.quality is Quality.UNCERTAIN
        assert repos.sessions.get_running() is None
        with pytest.raises(ValidationError):  # already ended
            repos.sessions.end(running.id, T0 + 2 * H)


def test_end_before_start_rejected(storage: Storage, seeded: dict[str, str]) -> None:
    with storage.transaction() as repos:
        running = repos.sessions.add(_session(seeded, T0, None))
        with pytest.raises(ValidationError):
            repos.sessions.end(running.id, T0 - H)
        with pytest.raises(NotFoundError):
            repos.sessions.end("missing", T0)


def test_overlap_and_second_running_conflict(storage: Storage, seeded: dict[str, str]) -> None:
    with storage.transaction() as repos:
        repos.sessions.add(_session(seeded, T0, T0 + 2 * H))
        repos.sessions.add(_session(seeded, T0 + 2 * H, T0 + 3 * H))  # touching: fine
    with pytest.raises(ConflictError):
        with storage.transaction() as repos:
            repos.sessions.add(_session(seeded, T0 + H, T0 + 4 * H))
    with storage.transaction() as repos:
        repos.sessions.add(_session(seeded, T0 + 5 * H, None))
    with pytest.raises(ConflictError):
        with storage.transaction() as repos:
            repos.sessions.add(_session(seeded, T0 + 9 * H, None))


def test_list_between_filters_and_running(storage: Storage, seeded: dict[str, str]) -> None:
    with storage.transaction() as repos:
        s1 = repos.sessions.add(_session(seeded, T0, T0 + H))
        s2 = repos.sessions.add(_session(seeded, T0 + H, T0 + 2 * H, activity_id=seeded["a2"]))
        s3 = repos.sessions.add(_session(seeded, T0 + 3 * H, None, project_id=seeded["project"]))
        window = (T0 + 30 * timedelta(minutes=1), T0 + 4 * H)
        assert [s.id for s in repos.sessions.list_between(*window)] == [s1.id, s2.id, s3.id]
        # Half-open: a session ending exactly at window start is excluded.
        assert [s.id for s in repos.sessions.list_between(T0 + H, T0 + 2 * H)] == [s2.id]
        assert [s.id for s in repos.sessions.list_between(*window, activity_id=seeded["a2"])] == [
            s2.id
        ]
        assert [
            s.id for s in repos.sessions.list_between(*window, project_id=seeded["project"])
        ] == [s3.id]
        assert repos.sessions.list_between(*window, device_id=seeded["device"]) == []
        assert [s.id for s in repos.sessions.list_all()] == [s1.id, s2.id, s3.id]
        far_future = T0 + timedelta(days=3650)
        assert [s.id for s in repos.sessions.list_between(far_future, far_future + H)] == [s3.id]


def test_session_missing(storage: Storage) -> None:
    with storage.read() as repos:
        assert repos.sessions.get("nope") is None
        with pytest.raises(NotFoundError):
            repos.sessions.require("nope")


# --------------------------------------------------------------------------- corrections


def test_correction_records_every_changed_field(storage: Storage, seeded: dict[str, str]) -> None:
    with storage.transaction() as repos:
        session = repos.sessions.add(_session(seeded, T0, T0 + H, note="alt"))
        updated = repos.sessions.correct(
            session.id,
            {
                "activity_id": seeded["a2"],
                "ended_at": T0 + 2 * H,
                "note": "neu",
                "quality": "uncertain",
            },
            reason="Falsch erfasst",
        )
        assert updated.revision == 2
        assert updated.activity_id == seeded["a2"] and updated.note == "neu"
        assert updated.quality is Quality.UNCERTAIN
        trail = {c.field_name: c for c in repos.sessions.list_corrections(session.id)}
        assert set(trail) == {"activity_id", "ended_at", "note", "quality"}
        assert trail["note"].old_value == "alt" and trail["note"].new_value == "neu"
        assert trail["activity_id"].old_value == seeded["a1"]
        assert trail["ended_at"].new_value == to_db_time(T0 + 2 * H)
        assert all(c.reason == "Falsch erfasst" and c.revision == 2 for c in trail.values())
        assert repos.sessions.require(session.id) == updated


def test_second_correction_bumps_revision_again(storage: Storage, seeded: dict[str, str]) -> None:
    with storage.transaction() as repos:
        session = repos.sessions.add(_session(seeded, T0, T0 + H))
        repos.sessions.correct(session.id, {"note": "a"}, "r1")
        again = repos.sessions.correct(session.id, {"note": None}, "r2")
        assert again.revision == 3 and again.note is None
        trail = repos.sessions.list_corrections(session.id)
        assert [c.revision for c in trail] == [2, 3]
        assert trail[1].old_value == "a" and trail[1].new_value is None


def test_unchanged_fields_are_ignored_and_empty_correction_rejected(
    storage: Storage, seeded: dict[str, str]
) -> None:
    with storage.transaction() as repos:
        session = repos.sessions.add(_session(seeded, T0, T0 + H, note="x"))
        plus_two = timezone(timedelta(hours=2))
        same_instant = (T0 + H).astimezone(plus_two)
        with pytest.raises(ValidationError, match="nothing"):
            repos.sessions.correct(session.id, {"note": "x", "ended_at": same_instant}, "r")
        result = repos.sessions.correct(session.id, {"note": "x", "quality": "uncertain"}, "r")
        assert [c.field_name for c in repos.sessions.list_corrections(session.id)] == ["quality"]
        assert result.revision == 2


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"id": "x"}, "r"),  # not correctable
        ({"source": "device"}, "r"),
        ({"note": "x"}, ""),  # reason required
        ({"note": "x"}, "   "),
        ({"quality": "great"}, "r"),
        ({"started_at": datetime(2026, 1, 5, 9)}, "r"),  # naive
        ({"ended_at": T0 - H}, "r"),  # before start
        ({"activity_id": ""}, "r"),
    ],
)
def test_invalid_corrections_change_nothing(
    storage: Storage, seeded: dict[str, str], changes: dict[str, object], reason: str
) -> None:
    with storage.transaction() as repos:
        session = repos.sessions.add(_session(seeded, T0, T0 + H))
    with storage.transaction() as repos:
        with pytest.raises(ValidationError):
            repos.sessions.correct(session.id, changes, reason)
    with storage.read() as repos:
        assert repos.sessions.require(session.id) == session
        assert repos.sessions.list_corrections(session.id) == []


def test_correction_creating_overlap_is_rolled_back_atomically(
    storage: Storage, seeded: dict[str, str]
) -> None:
    with storage.transaction() as repos:
        first = repos.sessions.add(_session(seeded, T0, T0 + H))
        repos.sessions.add(_session(seeded, T0 + 2 * H, T0 + 3 * H))
    with storage.transaction() as repos:
        with pytest.raises(ConflictError):
            repos.sessions.correct(first.id, {"ended_at": T0 + 150 * timedelta(minutes=1)}, "r")
        assert repos.sessions.require(first.id) == first  # session untouched
        assert repos.sessions.list_corrections(first.id) == []  # and no audit row


def test_correction_of_missing_session(storage: Storage) -> None:
    with storage.transaction() as repos, pytest.raises(NotFoundError):
        repos.sessions.correct("missing", {"note": "x"}, "r")


def test_delete_session_requires_reason_and_audits(
    storage: Storage, seeded: dict[str, str]
) -> None:
    with storage.transaction() as repos:
        session = repos.sessions.add(_session(seeded, T0, T0 + H))
        repos.sessions.correct(session.id, {"note": "n"}, "r")
        with pytest.raises(ValidationError):
            repos.sessions.delete(session.id, "  ", repos.audit)
        repos.sessions.delete(session.id, "Testdaten", repos.audit)
        assert repos.sessions.get(session.id) is None
        assert repos.sessions.list_corrections(session.id) == []  # cascade
        entry = repos.audit.recent()[0]
        assert (entry.action, entry.entity, entry.entity_id) == ("delete", "session", session.id)
        assert entry.detail is not None and "Testdaten" in entry.detail
        with pytest.raises(NotFoundError):
            repos.sessions.delete(session.id, "again", repos.audit)


# ---------------------------------------------------------------------- audit and facade


def test_audit_log_order_and_limit(storage: Storage) -> None:
    with storage.transaction() as repos:
        for i in range(5):
            repos.audit.add("test", "thing", str(i), f"detail {i}")
        assert len(repos.audit.recent(limit=3)) == 3
        assert all(e.entity == "thing" for e in repos.audit.recent())
        with pytest.raises(ValidationError):
            repos.audit.recent(limit=0)


def test_transaction_is_atomic_across_repositories(
    storage: Storage, seeded: dict[str, str]
) -> None:
    with pytest.raises(RuntimeError):
        with storage.transaction() as repos:
            repos.sessions.add(_session(seeded, T0, T0 + H))
            repos.audit.add("x", "y", None)
            raise RuntimeError("abort")
    with storage.read() as repos:
        assert repos.sessions.list_all() == [] and repos.audit.recent() == []


def test_read_bundle_and_database_access(storage: Storage) -> None:
    with storage.read() as repos:
        assert isinstance(repos, Repositories)
    assert storage.database.integrity_check() == []


# ------------------------------------------------------------------- corrupt stored data


def test_invalid_stored_row_is_reported_not_leaked(
    storage: Storage, seeded: dict[str, str]
) -> None:
    with storage.database.connect() as conn:
        # Bypass the application: write a color the CHECK allows but our model rejects
        # is impossible, so corrupt a timestamp instead.
        conn.execute(
            "INSERT INTO sessions (id, activity_id, started_at, source, quality, revision) "
            "VALUES ('bad', ?, 'not-a-time', 'manual', 'confirmed', 1)",
            (seeded["a1"],),
        )
    with storage.read() as repos, pytest.raises(DataIntegrityError):
        repos.sessions.require("bad")


def test_sqlite_errors_are_translated(storage: Storage) -> None:
    with storage.database.connect() as conn:
        conn.execute("DROP TABLE audit_log")
        repos = Repositories.bind(conn)
        with pytest.raises(Exception) as info:
            repos.audit.add("a", "b", None)
        assert not isinstance(info.value, sqlite3.Error)  # translated to OctaLedgerError
