"""Tests for deliberate data deletion: preview, safety backup, device removal, reset."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octaledger.application.data_service import DataService
from octaledger.application.export_service import ExportService
from octaledger.core.errors import ConflictError, InvalidStateError, ValidationError
from octaledger.core.settings import Settings, SettingsStore, TrackingSettings
from octaledger.domain.models import (
    Activity,
    Device,
    EventKind,
    RawEvent,
    Session,
    SessionSource,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
H = timedelta(hours=1)
NOW = T0 + timedelta(days=30)


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "db.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.backups = tmp_path / "backups"
        self.exports = ExportService(
            self.storage, exports_dir=tmp_path / "ex", backup_dir=self.backups, clock=lambda: NOW
        )
        self.settings = SettingsStore(tmp_path / "settings.toml", Settings())
        self.service = DataService(
            self.storage, self.exports, settings=self.settings, clock=lambda: NOW
        )
        with self.storage.transaction() as repos:
            self.cube = repos.devices.add(Device(alias="Büro", platform_address="AA:BB"))
            self.other = repos.devices.add(Device(alias="Zuhause"))
            self.activity = repos.activities.add(Activity(name="Meeting", color="#112233"))
            for day in range(5):  # five finished entries, one per day, two of them with a note
                repos.sessions.add(
                    Session(
                        activity_id=self.activity.id,
                        device_id=self.cube.id if day < 4 else self.other.id,
                        source=SessionSource.DEVICE,
                        started_at=T0 + timedelta(days=day),
                        ended_at=T0 + timedelta(days=day) + H,
                        note="n" if day in (1, 2) else None,
                    )
                )
            repos.events.add_many(
                [
                    RawEvent(
                        device_id=self.cube.id,
                        kind=EventKind.FACE_CHANGE,
                        sequence=n,
                        connection_id="c",
                        received_at=T0 + timedelta(days=n),
                        raw_value=1,
                    )
                    for n in range(5)
                ]
            )

    def backups_written(self) -> list[str]:
        return sorted(p.name for p in self.backups.glob("*.json"))


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_overview_counts_everything(env: Env) -> None:
    o = env.service.overview()
    assert (o.sessions, o.raw_events, o.devices, o.activities) == (5, 5, 2, 1)
    assert o.first_session == T0 and o.last_session == T0 + timedelta(days=4)


def test_preview_names_count_notes_and_period_without_changing_anything(env: Env) -> None:
    stats = env.service.preview_entries(T0 + timedelta(days=1), T0 + timedelta(days=4))
    assert (stats.count, stats.with_note) == (3, 2)
    assert stats.first == T0 + timedelta(days=1) and stats.last == T0 + timedelta(days=3)
    assert env.service.overview().sessions == 5
    assert env.backups_written() == []


def test_the_end_is_exclusive_and_must_follow_the_start(env: Env) -> None:
    assert env.service.preview_entries(T0, T0 + timedelta(days=1)).count == 1
    with pytest.raises(ValidationError):
        env.service.preview_entries(T0 + H, T0)


def test_delete_range_makes_a_safety_backup_first_and_removes_only_that_range(
    env: Env,
) -> None:
    result = env.service.delete_entries(
        T0 + timedelta(days=1), T0 + timedelta(days=3), expected_count=2
    )
    assert result.sessions == 2 and result.raw_events == 0
    assert result.safety_backup in env.backups_written()
    assert env.service.overview().sessions == 3
    assert env.service.overview().raw_events == 5  # events stay unless asked for


def test_the_safety_backup_restores_what_was_deleted(env: Env) -> None:
    result = env.service.delete_entries(None, None, expected_count=5)
    assert env.service.overview().sessions == 0
    text = (env.backups / result.safety_backup).read_text(encoding="utf-8")
    env.exports.restore_backup_text(text)
    assert env.service.overview().sessions == 5


def test_events_of_the_period_can_be_deleted_too(env: Env) -> None:
    result = env.service.delete_entries(
        T0, T0 + timedelta(days=2), expected_count=2, include_events=True
    )
    assert (result.sessions, result.raw_events) == (2, 2)


def test_a_changed_count_aborts_and_deletes_nothing(env: Env) -> None:
    with pytest.raises(InvalidStateError) as error:
        env.service.delete_entries(None, None, expected_count=4)
    assert "Anzahl hat sich geändert" in error.value.user_message
    assert env.service.overview().sessions == 5
    assert env.backups_written() == []


def test_deleting_an_empty_range_is_refused(env: Env) -> None:
    with pytest.raises(InvalidStateError):
        env.service.delete_entries(NOW, None, expected_count=0)


def test_a_running_entry_is_never_deleted_by_a_bulk_operation(env: Env) -> None:
    with env.storage.transaction() as repos:
        repos.sessions.add(Session(activity_id=env.activity.id, started_at=NOW - H))
    stats = env.service.preview_entries(None, None)
    assert stats.count == 5 and stats.running_left_out
    env.service.delete_entries(None, None, expected_count=5)
    assert env.service.overview().running_sessions == 1


def test_the_deletion_is_recorded_in_the_audit_log(env: Env) -> None:
    env.service.delete_entries(None, None, expected_count=5)
    with env.storage.read() as repos:
        entries = [(a.action, a.entity) for a in repos.audit.list_all()]
    assert ("delete", "sessions") in entries


def test_removing_a_cube_with_data_needs_the_data_to_go_too(env: Env) -> None:
    with pytest.raises(ConflictError):
        env.service.remove_device(env.cube.id, delete_data=False)
    assert env.service.overview().devices == 2


def test_removing_a_cube_without_data_is_plain(env: Env) -> None:
    with env.storage.transaction() as repos:
        empty = repos.devices.add(Device(alias="Leer"))
    removed = env.service.remove_device(empty.id, delete_data=False)
    assert removed.safety_backup is None and env.service.overview().devices == 2


def test_removing_a_cube_with_its_data_keeps_other_cubes_data(env: Env) -> None:
    removed = env.service.remove_device(env.cube.id, delete_data=True)
    assert (removed.sessions, removed.raw_events) == (4, 5)
    assert removed.safety_backup in env.backups_written()
    o = env.service.overview()
    assert (o.devices, o.sessions, o.raw_events) == (1, 1, 0)


def test_removing_the_active_cube_clears_the_selection(env: Env) -> None:
    with env.storage.transaction() as repos:
        repos.state.set("active_device", env.cube.id)
    env.service.remove_device(env.cube.id, delete_data=True)
    with env.storage.read() as repos:
        assert repos.state.get("active_device") is None


def test_factory_reset_empties_everything_after_a_backup_and_restores_defaults(
    env: Env,
) -> None:
    env.settings.update(Settings(tracking=TrackingSettings(debounce_ms=900)))
    result = env.service.factory_reset()
    assert result.counts["sessions"] == 5 and result.settings_reset
    assert result.safety_backup in env.backups_written()
    o = env.service.overview()
    assert (o.sessions, o.devices, o.activities, o.raw_events) == (0, 0, 0, 0)
    assert env.settings.settings.tracking.debounce_ms == Settings().tracking.debounce_ms


def test_factory_reset_can_keep_the_settings(env: Env) -> None:
    env.settings.update(Settings(tracking=TrackingSettings(debounce_ms=900)))
    result = env.service.factory_reset(reset_settings=False)
    assert not result.settings_reset and env.settings.settings.tracking.debounce_ms == 900


def test_unpairing_forgets_only_the_address(env: Env) -> None:
    from octaledger.application.device_service import DeviceService

    devices = DeviceService(env.storage)
    device = devices.forget_address(env.cube.id)
    assert device.platform_address is None and device.alias == "Büro"
    assert env.service.overview().sessions == 5
