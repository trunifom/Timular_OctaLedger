"""Device registration, face calibration and explicit tracker hand-over.

Responsibility
--------------
* Register trackers with an internal id and a user alias (F-02); the first registered
  tracker becomes the active one automatically.
* Show per-device calibration state: which of the eight faces has which activity (F-05).
* Report the face that is currently up (from the latest stored observation) so the GUI can
  guide the calibration "hold a face up, see its technical number, assign an activity".
* Rename, update hardware information (model/firmware may be unknown, F-03) and remove
  devices that have no recorded history.

Hand-over between trackers lives in :class:`TrackingService` because it changes sessions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime

from octaledger.application.tracking_service import STATE_ACTIVE_DEVICE
from octaledger.core.errors import ConflictError
from octaledger.domain.models import FACE_NUMBERS, Device, EventKind, FaceMapping
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """A device together with its calibration and active flag (for the GUI)."""

    device: Device
    mappings: dict[int, FaceMapping]
    is_active: bool

    @property
    def configured_faces(self) -> int:
        """Number of faces that have an activity assigned."""
        return sum(1 for m in self.mappings.values() if m.activity_id is not None)

    @property
    def is_fully_calibrated(self) -> bool:
        """``True`` when all eight faces have an activity (acceptance A-01 precondition)."""
        return self.configured_faces == len(FACE_NUMBERS)


@dataclass(frozen=True, slots=True)
class ObservedFace:
    """The most recent face value seen from a device."""

    face: int
    received_at: datetime
    kind: EventKind


class DeviceService:
    """Use cases around registered trackers."""

    def __init__(self, storage: Storage) -> None:
        """Create the service on top of ``storage``."""
        self._storage = storage

    def register(
        self,
        alias: str,
        *,
        platform_address: str | None = None,
        model: str | None = None,
        firmware: str | None = None,
    ) -> Device:
        """Register a tracker; the first one becomes the active tracker.

        Raises:
            ValidationError: For an invalid alias.
            ConflictError: If the alias is already used.
        """
        device = Device(
            alias=alias, platform_address=platform_address, model=model, firmware=firmware
        )
        with self._storage.transaction() as repos:
            repos.devices.add(device)
            if repos.state.get(STATE_ACTIVE_DEVICE) is None:
                repos.state.set(STATE_ACTIVE_DEVICE, device.id)
                logger.info("First tracker %s became the active tracker", device.alias)
        return device

    def list_devices(self) -> list[DeviceInfo]:
        """Return all devices with calibration and active flag, ordered by alias."""
        with self._storage.read() as repos:
            active = repos.state.get(STATE_ACTIVE_DEVICE)
            return [
                DeviceInfo(
                    device=device,
                    mappings={m.face: m for m in repos.mappings.list_for_device(device.id)},
                    is_active=device.id == active,
                )
                for device in repos.devices.list_all()
            ]

    def get(self, device_id: str) -> DeviceInfo:
        """Return one device with calibration.

        Raises:
            NotFoundError: If it does not exist.
        """
        with self._storage.read() as repos:
            device = repos.devices.require(device_id)
            return DeviceInfo(
                device=device,
                mappings={m.face: m for m in repos.mappings.list_for_device(device_id)},
                is_active=repos.state.get(STATE_ACTIVE_DEVICE) == device_id,
            )

    def rename(self, device_id: str, alias: str) -> Device:
        """Change the alias (must stay unique)."""
        with self._storage.transaction() as repos:
            return repos.devices.update(replace(repos.devices.require(device_id), alias=alias))

    def update_hardware_info(
        self,
        device_id: str,
        *,
        model: str | None = None,
        firmware: str | None = None,
        platform_address: str | None = None,
    ) -> Device:
        """Store model/firmware/address when they become known (``None`` keeps the old value)."""
        with self._storage.transaction() as repos:
            current = repos.devices.require(device_id)
            return repos.devices.update(
                replace(
                    current,
                    model=model if model is not None else current.model,
                    firmware=firmware if firmware is not None else current.firmware,
                    platform_address=(
                        platform_address
                        if platform_address is not None
                        else current.platform_address
                    ),
                )
            )

    def remove(self, device_id: str) -> None:
        """Remove a device that has no recorded events or sessions.

        If it was the active tracker, the selection is cleared.

        Raises:
            NotFoundError: If missing.
            ConflictError: If events or sessions still reference it.
        """
        try:
            with self._storage.transaction() as repos:
                repos.devices.delete(device_id, repos.audit)
                if repos.state.get(STATE_ACTIVE_DEVICE) == device_id:
                    repos.state.delete(STATE_ACTIVE_DEVICE)
        except ConflictError as exc:
            raise ConflictError(
                f"Device {device_id} still has recorded data",
                user_message=(
                    "Dieses Gerät hat bereits aufgezeichnete Daten und kann nicht gelöscht werden."
                ),
                details={"id": device_id},
            ) from exc

    # ------------------------------------------------------------------ calibration

    def assign_face(
        self,
        device_id: str,
        face: int,
        activity_id: str | None,
        project_id: str | None = None,
    ) -> FaceMapping:
        """Assign an activity (and optional project) to a technical face ``1..8``.

        Raises:
            NotFoundError: If device, activity or project do not exist.
            ValidationError: If ``face`` is not ``1..8``.
        """
        with self._storage.transaction() as repos:
            repos.devices.require(device_id)
            if activity_id is not None:
                repos.activities.require(activity_id)
            if project_id is not None:
                repos.projects.require(project_id)
            return repos.mappings.assign(device_id, face, activity_id, project_id)

    def clear_face(self, device_id: str, face: int) -> None:
        """Remove the assignment of a face."""
        with self._storage.transaction() as repos:
            repos.devices.require(device_id)
            repos.mappings.clear(device_id, face)

    def last_observed_face(self, device_id: str) -> ObservedFace | None:
        """Return the face value most recently seen from ``device_id``.

        Uses stored baseline/face-change/neutral events; ``None`` if nothing was received
        yet. The GUI shows it during calibration ("this is technical face number 5").
        """
        with self._storage.read() as repos:
            repos.devices.require(device_id)
            for event in repos.events.list_for_device(device_id, limit=50):
                if event.raw_value is not None and event.kind in (
                    EventKind.BASELINE,
                    EventKind.FACE_CHANGE,
                    EventKind.NEUTRAL,
                ):
                    return ObservedFace(event.raw_value, event.received_at, event.kind)
        return None
