"""Tests for the data model of control mode: models, repositories, outbox and backup v2."""

import dataclasses
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from octaledger.application.export_service import BACKUP_SCHEMA_VERSION, ExportService
from octaledger.core.errors import ConflictError, ImportDataError, NotFoundError, ValidationError
from octaledger.domain.models import (
    MAX_JSON_BYTES,
    Activity,
    Device,
    DeviceMode,
    FaceAction,
    Integration,
    IntegrationJob,
    JobStatus,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
MIN = timedelta(minutes=1)


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    return Storage(database)


def job(integration_id: str, key: str = "evt-1", **kwargs: Any) -> IntegrationJob:
    defaults: dict[str, Any] = {
        "label": "Lampe",
        "params": {"action": "toggle"},
        "created_at": T0,
        "expires_at": T0 + MIN,
    }
    return IntegrationJob(key, integration_id, **(defaults | kwargs))


# ------------------------------------------------------------------------------ models


def test_devices_start_in_time_mode_and_accept_only_known_modes() -> None:
    assert Device(alias="A").mode is DeviceMode.TIME
    assert Device(alias="B", mode="control").mode is DeviceMode.CONTROL  # type: ignore[arg-type]
    with pytest.raises(ValidationError) as info:
        Device(alias="C", mode="turbo")  # type: ignore[arg-type]
    assert "Zeiterfassung" in info.value.user_message


def test_integration_validates_kind_name_and_settings() -> None:
    integration = Integration("mqtt", "  Mein Broker ", {"host": "10.0.0.2", "port": 1883})
    assert integration.name == "Mein Broker" and integration.enabled
    for kind in ("", "MQTT", "mq tt", "1mqtt", "x" * 41):
        with pytest.raises(ValidationError):
            Integration(kind, "x")
    with pytest.raises(ValidationError):
        Integration("mqtt", "   ")
    with pytest.raises(ValidationError):
        Integration("mqtt", "x", enabled="yes")  # type: ignore[arg-type]


def test_settings_must_be_a_small_json_object_and_are_copied() -> None:
    source = {"host": "h"}
    integration = Integration("mqtt", "x", source)
    source["host"] = "changed afterwards"
    assert integration.config == {"host": "h"}  # the stored value is a copy
    for bad in (["list"], {1: "key"}, {"x": object()}, {"x": "y" * (MAX_JSON_BYTES + 1)}):
        with pytest.raises(ValidationError):
            Integration("mqtt", "x", bad)  # type: ignore[arg-type]


def test_face_action_validates_face_label_and_revision() -> None:
    action = FaceAction("d", 3, "i", " Lampe ", {"action": "toggle"})
    assert action.label == "Lampe" and action.revision == 1
    for kwargs in ({"face": 0}, {"face": 9}, {"label": " "}, {"revision": 0}):
        values: dict[str, Any] = {"face": 1, "label": "x", "revision": 1} | kwargs
        with pytest.raises(ValidationError):
            FaceAction("d", values["face"], "i", values["label"], {}, values["revision"])


def test_job_defaults_and_validation() -> None:
    pending = job("i")
    assert pending.status is JobStatus.PENDING and pending.attempts == 0
    assert pending.next_attempt_at == T0  # due at once
    for kwargs in ({"face": 0}, {"attempts": -1}, {"label": ""}):
        with pytest.raises(ValidationError):
            job("i", **kwargs)
    with pytest.raises(ValidationError):
        IntegrationJob(
            "", "i", label="x", params={}, expires_at=T0
        )  # the idempotency key is required


# ------------------------------------------------------------- repositories: devices


def test_device_mode_is_stored_and_changeable(storage: Storage) -> None:
    with storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Würfel"))
        assert repos.devices.require(device.id).mode is DeviceMode.TIME
        repos.devices.update(dataclasses.replace(device, mode=DeviceMode.CONTROL))
    with storage.read() as repos:
        assert repos.devices.require(device.id).mode is DeviceMode.CONTROL


def test_migration_keeps_existing_devices_in_time_mode(tmp_path: Path) -> None:
    """A database created before migration 0003 upgrades without touching its trackers."""
    database = Database(tmp_path / "old.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    with sqlite3.connect(database.path) as connection:
        connection.execute("DELETE FROM schema_migrations WHERE version = 3")
        connection.executescript(
            "DROP TABLE integration_jobs; DROP TABLE face_actions; DROP TABLE integrations;"
            "ALTER TABLE devices DROP COLUMN mode;"
            "INSERT INTO devices (id, alias, created_at) VALUES "
            "('old', 'Alt', '2026-01-05T08:00:00.000000Z');"
        )
    upgraded = Database(tmp_path / "old.sqlite3", backup_dir=tmp_path / "bk")
    upgraded.initialize()
    with Storage(upgraded).read() as repos:
        assert repos.devices.require("old").mode is DeviceMode.TIME


# ------------------------------------------------------- repositories: integrations


def test_integration_crud_and_unique_names(storage: Storage) -> None:
    with storage.transaction() as repos:
        added = repos.integrations.add(Integration("webhook", "Licht", {"url": "http://x"}))
        with pytest.raises(ConflictError):
            repos.integrations.add(Integration("mqtt", "licht"))  # names are case-insensitive
        repos.integrations.update(
            Integration(
                "webhook", "Lichtschalter", {"url": "http://y"}, False, added.id, added.created_at
            )
        )
        loaded = repos.integrations.require(added.id)
        assert loaded.name == "Lichtschalter" and loaded.config == {"url": "http://y"}
        assert not loaded.enabled
        assert [i.name for i in repos.integrations.list_all()] == ["Lichtschalter"]
        with pytest.raises(NotFoundError):
            repos.integrations.require("ghost")
        with pytest.raises(NotFoundError):
            repos.integrations.update(Integration("webhook", "x", id="ghost"))


def test_an_integration_in_use_cannot_be_deleted_but_its_jobs_go_with_it(storage: Storage) -> None:
    with storage.transaction() as repos:
        device = repos.devices.add(Device(alias="D", mode=DeviceMode.CONTROL))
        integration = repos.integrations.add(Integration("webhook", "Licht"))
        repos.actions.assign(device.id, 1, integration.id, "Lampe", {"action": "x"})
        with pytest.raises(ConflictError):
            repos.integrations.delete(integration.id)  # a face still uses it
        repos.actions.clear(device.id, 1)
        repos.jobs.enqueue(job(integration.id))
        repos.integrations.delete(integration.id, repos.audit)
        assert repos.jobs.list_recent() == []  # queued jobs are removed with it
        assert any(
            a.action == "delete" and a.entity == "integration" for a in repos.audit.list_all()
        )


# ------------------------------------------------------------ repositories: actions


def test_face_actions_assign_change_clear_and_cascade(storage: Storage) -> None:
    with storage.transaction() as repos:
        device = repos.devices.add(Device(alias="D", mode=DeviceMode.CONTROL))
        integration = repos.integrations.add(Integration("webhook", "Licht"))
        first = repos.actions.assign(device.id, 2, integration.id, "Lampe", {"action": "on"})
        assert first.revision == 1
        same = repos.actions.assign(device.id, 2, integration.id, "Lampe", {"action": "on"})
        assert same.revision == 1  # an identical assignment is not a change
        changed = repos.actions.assign(device.id, 2, integration.id, "Lampe", {"action": "off"})
        assert changed.revision == 2 and repos.actions.get(device.id, 2) == changed
        assert [a.face for a in repos.actions.list_for_device(device.id)] == [2]
        with pytest.raises(ConflictError):
            repos.actions.assign(device.id, 3, "ghost", "x", {})  # unknown integration
        repos.actions.clear(device.id, 2)
        repos.actions.clear(device.id, 2)  # clearing twice is fine
        assert repos.actions.get(device.id, 2) is None
        repos.actions.assign(device.id, 4, integration.id, "Radio", {})
        repos.devices.delete(device.id)
        assert repos.actions.list_all() == []  # actions follow their device


# ---------------------------------------------------------------- repositories: jobs


def test_jobs_are_idempotent_and_listed_when_due(storage: Storage) -> None:
    with storage.transaction() as repos:
        integration = repos.integrations.add(Integration("webhook", "Licht"))
        assert repos.jobs.enqueue(job(integration.id, "evt-1")) is True
        assert repos.jobs.enqueue(job(integration.id, "evt-1")) is False  # the same trigger again
        repos.jobs.enqueue(
            job(integration.id, "evt-2", created_at=T0 + MIN, expires_at=T0 + 2 * MIN)
        )
        assert repos.jobs.count_pending(integration.id) == 2
        assert [j.idempotency_key for j in repos.jobs.due(T0)] == ["evt-1"]
        assert [j.idempotency_key for j in repos.jobs.due(T0 + MIN)] == ["evt-1", "evt-2"]
        assert len(repos.jobs.due(T0 + MIN, limit=1)) == 1


def test_job_life_cycle_retry_done_failed_expired(storage: Storage) -> None:
    with storage.transaction() as repos:
        integration = repos.integrations.add(Integration("webhook", "Licht"))
        for key in ("a", "b", "c", "d"):
            repos.jobs.enqueue(job(integration.id, key))
        ids = {j.idempotency_key: j.id for j in repos.jobs.due(T0)}
        repos.jobs.mark_retry(ids["a"], 1, T0 + 5 * MIN, "keine Verbindung")
        retried = repos.jobs.get(ids["a"])
        assert retried and retried.status is JobStatus.PENDING and retried.attempts == 1
        assert retried.last_error == "keine Verbindung" and retried.next_attempt_at == T0 + 5 * MIN
        assert ids["a"] not in {j.id for j in repos.jobs.due(T0)}  # not due until its time
        repos.jobs.mark_done(ids["b"], T0, 1)
        repos.jobs.mark_failed(ids["c"], T0, 3, "abgelehnt")
        repos.jobs.mark_expired(ids["d"], T0, 0, "zu spät")
        states = {j.idempotency_key: j.status for j in repos.jobs.list_recent()}
        assert states == {
            "a": JobStatus.PENDING,
            "b": JobStatus.DONE,
            "c": JobStatus.FAILED,
            "d": JobStatus.EXPIRED,
        }
        done = repos.jobs.get(ids["b"])
        assert done and done.finished_at == T0 and done.last_error is None


def test_overdue_jobs_expire_and_old_history_is_purged(storage: Storage) -> None:
    with storage.transaction() as repos:
        integration = repos.integrations.add(Integration("webhook", "Licht"))
        repos.jobs.enqueue(job(integration.id, "old"))  # expires at T0 + 1 min
        repos.jobs.enqueue(job(integration.id, "new", expires_at=T0 + 10 * MIN))
        assert repos.jobs.expire_overdue(T0 + 2 * MIN, "zu spät") == 1
        by_key = {j.idempotency_key: j for j in repos.jobs.list_recent()}
        assert by_key["old"].status is JobStatus.EXPIRED and by_key["old"].last_error == "zu spät"
        assert by_key["new"].status is JobStatus.PENDING
        assert repos.jobs.delete_finished_before(T0 + 3 * MIN) == 1
        assert [j.idempotency_key for j in repos.jobs.list_recent()] == ["new"]  # pending is kept


def test_a_device_can_be_deleted_while_old_jobs_remember_it(storage: Storage) -> None:
    with storage.transaction() as repos:
        device = repos.devices.add(Device(alias="D", mode=DeviceMode.CONTROL))
        integration = repos.integrations.add(Integration("webhook", "Licht"))
        repos.jobs.enqueue(job(integration.id, device_id=device.id, face=1))
        repos.devices.delete(device.id)
        (remaining,) = repos.jobs.list_recent()
        assert remaining.device_id is None and remaining.face == 1  # kept for the history


# ----------------------------------------------------------------------- backup v2


class Backup:
    def __init__(self, tmp_path: Path, name: str) -> None:
        base = tmp_path / name
        database = Database(base / "db.sqlite3", backup_dir=base / "backups")
        database.initialize()
        self.storage = Storage(database)
        self.service = ExportService(
            self.storage,
            exports_dir=base / "exports",
            backup_dir=base / "backups",
            clock=lambda: T0,
        )

    def fill(self) -> None:
        with self.storage.transaction() as repos:
            time_device = repos.devices.add(Device(alias="Zeit"))
            control = repos.devices.add(Device(alias="Steuerung", mode=DeviceMode.CONTROL))
            integration = repos.integrations.add(
                Integration("homeassistant", "Zuhause", {"base_url": "http://ha.local:8123"})
            )
            repos.integrations.add(Integration("webhook", "Aus", enabled=False))
            repos.actions.assign(
                control.id, 3, integration.id, "Schreibtisch", {"action": "call_service"}
            )
            repos.activities.add(Activity(name="Meeting"))
            repos.jobs.enqueue(job(integration.id))  # runtime data: must not travel in a backup
        self.time_device, self.control = time_device.id, control.id

    def snapshot(self) -> Any:
        with self.storage.snapshot() as repos:
            return repos.backup.snapshot()


def test_backup_v2_roundtrips_modes_integrations_and_actions(tmp_path: Path) -> None:
    source, target = Backup(tmp_path, "source"), Backup(tmp_path, "target")
    source.fill()
    path = source.service.export_backup(filename="b.json").path
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema_version"] == BACKUP_SCHEMA_VERSION == 3
    assert document["counts"]["integrations"] == 2 and document["counts"]["face_actions"] == 1
    result = target.service.restore_backup(path)
    assert result.summary.counts["face_actions"] == 1
    original, restored = source.snapshot(), target.snapshot()
    assert restored.devices == original.devices
    assert restored.integrations == original.integrations
    assert restored.actions == original.actions
    assert {d.alias: d.mode for d in restored.devices} == {
        "Zeit": DeviceMode.TIME,
        "Steuerung": DeviceMode.CONTROL,
    }
    with target.storage.read() as repos:
        assert repos.jobs.list_recent() == []  # the outbox is runtime data, not backup content


def test_restore_replaces_integrations_and_clears_the_outbox(tmp_path: Path) -> None:
    source, target = Backup(tmp_path, "source"), Backup(tmp_path, "target")
    source.fill()
    with target.storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Alt", mode=DeviceMode.CONTROL))
        old = repos.integrations.add(Integration("webhook", "Nur im Ziel"))
        repos.actions.assign(device.id, 1, old.id, "x", {})
        repos.jobs.enqueue(job(old.id))
    target.service.restore_backup(source.service.export_backup(filename="b.json").path)
    with target.storage.read() as repos:
        assert {i.name for i in repos.integrations.list_all()} == {"Zuhause", "Aus"}
        assert repos.jobs.list_recent() == []


def test_a_v1_backup_is_still_readable(tmp_path: Path) -> None:
    """Older files have no modes, integrations or actions: every tracker is a time tracker."""
    source, target = Backup(tmp_path, "source"), Backup(tmp_path, "target")
    source.fill()
    document = json.loads(source.service.create_backup_text())
    data = document["data"]
    del data["integrations"], data["face_actions"], data["tables"]
    for device in data["devices"]:
        del device["mode"]
    document["schema_version"] = 1
    document["checksum"] = ExportService._checksum(data)
    summary = target.service.inspect_backup_text(json.dumps(document))
    assert summary.schema_version == 1 and summary.counts["integrations"] == 0
    target.service.restore_backup_text(json.dumps(document))
    restored = target.snapshot()
    assert {d.mode for d in restored.devices} == {DeviceMode.TIME}
    assert restored.integrations == () and restored.actions == ()


def reseal(document: dict[str, Any]) -> str:
    document["checksum"] = ExportService._checksum(document["data"])
    return json.dumps(document)


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda d: d["integrations"].append(dict(d["integrations"][0], id="x")), "doppelte Namen"),
        (lambda d: d["face_actions"].append(dict(d["face_actions"][0])), "doppelte Aktion"),
        (lambda d: d["face_actions"][0].update(integration_id="ghost"), "nicht vorhandene"),
        (lambda d: d["face_actions"][0].update(device_id="ghost"), "nicht vorhandene"),
        (lambda d: d["devices"][0].update(mode="turbo"), "ungültig"),
        (lambda d: d["integrations"][0].update(kind="BAD KIND"), "ungültig"),
        (lambda d: d["integrations"][0].update(secret="x"), "ungültig"),  # no unknown fields
        (lambda d: d.pop("face_actions"), "Abschnitte"),
    ],
)
def test_invalid_v2_content_is_rejected_before_anything_changes(
    tmp_path: Path, mutate: Any, fragment: str
) -> None:
    source, target = Backup(tmp_path, "source"), Backup(tmp_path, "target")
    source.fill()
    document = json.loads(source.service.create_backup_text())
    mutate(document["data"])
    with pytest.raises(ImportDataError) as info:
        target.service.restore_backup_text(reseal(document))
    assert fragment in info.value.user_message
    assert target.snapshot().devices == ()  # nothing was touched
