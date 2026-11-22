"""Tests for the device service (registration, calibration) and the catalog service."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octaledger.application.catalog_service import PALETTE, CatalogService
from octaledger.application.device_service import DeviceService
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import ConflictError, NotFoundError, ValidationError
from octaledger.domain.models import EventKind, RawEvent
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    return Storage(database)


@pytest.fixture
def devices(storage: Storage) -> DeviceService:
    return DeviceService(storage)


@pytest.fixture
def catalog(storage: Storage) -> CatalogService:
    return CatalogService(storage)


# ----------------------------------------------------------------------- registration


def test_first_registered_device_becomes_active(storage: Storage, devices: DeviceService) -> None:
    first = devices.register("Büro", model="ZEI", firmware="1.0")
    second = devices.register("Zuhause")
    infos = {i.device.alias: i for i in devices.list_devices()}
    assert infos["Büro"].is_active and not infos["Zuhause"].is_active
    assert infos["Büro"].device.model == "ZEI" and infos["Zuhause"].device.model is None
    assert TrackingService(storage).get_active_device_id() == first.id
    assert second.id != first.id


def test_register_validation_and_duplicates(devices: DeviceService) -> None:
    with pytest.raises(ValidationError):
        devices.register("  ")
    devices.register("Büro")
    with pytest.raises(ConflictError):
        devices.register("büro")


def test_get_and_missing(devices: DeviceService) -> None:
    device = devices.register("A")
    assert devices.get(device.id).device == device
    with pytest.raises(NotFoundError):
        devices.get("missing")


def test_rename_and_unique_alias(devices: DeviceService) -> None:
    a, _ = devices.register("A"), devices.register("B")
    assert devices.rename(a.id, "Alpha").alias == "Alpha"
    with pytest.raises(ConflictError):
        devices.rename(a.id, "b")
    with pytest.raises(NotFoundError):
        devices.rename("missing", "X")


def test_update_hardware_info_keeps_unset_values(devices: DeviceService) -> None:
    device = devices.register("A", model="M1", firmware="1.0")
    updated = devices.update_hardware_info(device.id, firmware="1.2", platform_address="AA:BB")
    assert (updated.model, updated.firmware, updated.platform_address) == ("M1", "1.2", "AA:BB")
    again = devices.update_hardware_info(device.id)  # nothing new: nothing lost
    assert again == updated
    with pytest.raises(NotFoundError):
        devices.update_hardware_info("missing", model="x")


def test_remove_clears_active_selection(storage: Storage, devices: DeviceService) -> None:
    device = devices.register("A")
    devices.remove(device.id)
    assert devices.list_devices() == []
    assert TrackingService(storage).get_active_device_id() is None
    with pytest.raises(NotFoundError):
        devices.remove(device.id)


def test_remove_device_with_history_is_refused_with_clear_message(
    storage: Storage, devices: DeviceService
) -> None:
    device = devices.register("A")
    with storage.transaction() as repos:
        repos.events.add(
            RawEvent(device_id=device.id, kind=EventKind.RECONNECT, sequence=0, connection_id="c")
        )
    with pytest.raises(ConflictError) as info:
        devices.remove(device.id)
    assert "aufgezeichnete Daten" in info.value.user_message
    assert len(devices.list_devices()) == 1
    assert devices.list_devices()[0].is_active  # selection untouched after the failed removal


# ------------------------------------------------------------------------ calibration


def test_calibration_progress(devices: DeviceService, catalog: CatalogService) -> None:
    device = devices.register("A")
    activity = catalog.create_activity("Meeting")
    assert devices.get(device.id).configured_faces == 0
    for face in range(1, 8):
        devices.assign_face(device.id, face, activity.id)
    info = devices.get(device.id)
    assert info.configured_faces == 7 and not info.is_fully_calibrated
    devices.assign_face(device.id, 8, activity.id)
    assert devices.get(device.id).is_fully_calibrated
    devices.clear_face(device.id, 8)
    assert not devices.get(device.id).is_fully_calibrated


def test_empty_assignment_does_not_count_as_configured(
    devices: DeviceService, catalog: CatalogService
) -> None:
    device = devices.register("A")
    devices.assign_face(device.id, 1, None)
    info = devices.get(device.id)
    assert 1 in info.mappings and info.configured_faces == 0


def test_assign_face_errors(devices: DeviceService, catalog: CatalogService) -> None:
    device = devices.register("A")
    activity = catalog.create_activity("Meeting")
    with pytest.raises(ValidationError):
        devices.assign_face(device.id, 0, activity.id)
    with pytest.raises(NotFoundError):
        devices.assign_face("missing", 1, activity.id)
    with pytest.raises(NotFoundError):
        devices.assign_face(device.id, 1, "missing")
    with pytest.raises(NotFoundError):
        devices.assign_face(device.id, 1, activity.id, "missing")
    with pytest.raises(NotFoundError):
        devices.clear_face("missing", 1)
    assert devices.get(device.id).mappings == {}


def test_last_observed_face(storage: Storage, devices: DeviceService) -> None:
    device = devices.register("A")
    assert devices.last_observed_face(device.id) is None

    def add(kind: EventKind, value: int | None, minute: int) -> None:
        with storage.transaction() as repos:
            repos.events.add(
                RawEvent(
                    device_id=device.id,
                    kind=kind,
                    sequence=minute,
                    connection_id="c",
                    raw_value=value,
                    received_at=T0 + timedelta(minutes=minute),
                )
            )

    add(EventKind.BASELINE, 3, 0)
    add(EventKind.FACE_CHANGE, 5, 1)
    add(EventKind.DISCONNECT, None, 2)  # newest event carries no face: skipped
    observed = devices.last_observed_face(device.id)
    assert observed is not None and observed.face == 5 and observed.kind is EventKind.FACE_CHANGE
    add(EventKind.NEUTRAL, 0, 3)
    neutral = devices.last_observed_face(device.id)
    assert neutral is not None and neutral.face == 0
    with pytest.raises(NotFoundError):
        devices.last_observed_face("missing")


# --------------------------------------------------------------------------- catalog


def test_activity_lifecycle(catalog: CatalogService) -> None:
    activity = catalog.create_activity("Meeting", "#112233")
    assert activity.color == "#112233"
    renamed = catalog.update_activity(activity.id, name="Besprechung")
    assert renamed.name == "Besprechung" and renamed.color == "#112233"
    recoloured = catalog.update_activity(activity.id, color="#445566")
    assert recoloured.name == "Besprechung" and recoloured.color == "#445566"
    catalog.archive_activity(activity.id)
    assert catalog.list_activities() == []
    assert len(catalog.list_activities(include_archived=True)) == 1
    catalog.archive_activity(activity.id, False)
    assert len(catalog.list_activities()) == 1
    catalog.delete_activity(activity.id)
    assert catalog.list_activities(include_archived=True) == []


def test_project_lifecycle(catalog: CatalogService) -> None:
    project = catalog.create_project("Alpha")
    assert project.color in PALETTE
    assert catalog.update_project(project.id, name="Beta").name == "Beta"
    catalog.archive_project(project.id)
    assert catalog.list_projects() == [] and len(catalog.list_projects(include_archived=True)) == 1
    catalog.archive_project(project.id, False)
    catalog.delete_project(project.id)
    assert catalog.list_projects(include_archived=True) == []


def test_automatic_colors_cycle_through_palette(catalog: CatalogService) -> None:
    colors = [catalog.create_activity(f"A{i}").color for i in range(len(PALETTE))]
    assert colors == list(PALETTE)  # each palette colour used once before any repeats
    assert catalog.create_activity("again").color == PALETTE[0]


def test_invalid_input_and_duplicates(catalog: CatalogService) -> None:
    with pytest.raises(ValidationError):
        catalog.create_activity("")
    with pytest.raises(ValidationError):
        catalog.create_project("x", "red")
    catalog.create_activity("Meeting")
    with pytest.raises(ConflictError):
        catalog.create_activity("MEETING")
    with pytest.raises(NotFoundError):
        catalog.update_activity("missing", name="x")
    with pytest.raises(NotFoundError):
        catalog.archive_project("missing")


def test_used_items_cannot_be_deleted_but_can_be_archived(
    storage: Storage, catalog: CatalogService, devices: DeviceService
) -> None:
    activity = catalog.create_activity("Meeting")
    project = catalog.create_project("Alpha")
    tracking = TrackingService(storage, clock=lambda: T0)
    tracking.start_manual(activity.id, project.id)
    with pytest.raises(ConflictError) as info:
        catalog.delete_activity(activity.id)
    assert "archivieren" in info.value.user_message and "Tätigkeit" in info.value.user_message
    with pytest.raises(ConflictError) as info:
        catalog.delete_project(project.id)
    assert "Projekt" in info.value.user_message
    catalog.archive_activity(activity.id)  # the safe alternative works
    assert catalog.list_activities(include_archived=True)[0].archived


def test_activity_used_by_face_mapping_cannot_be_deleted(
    catalog: CatalogService, devices: DeviceService
) -> None:
    device = devices.register("A")
    activity = catalog.create_activity("Meeting")
    devices.assign_face(device.id, 1, activity.id)
    with pytest.raises(ConflictError):
        catalog.delete_activity(activity.id)
