"""Read-outs of a cube: the data sheet and short accelerometer recordings (AP-56).

Responsibility
--------------
* Ask the running agent to read out a **connected** cube (read only, see ``domain/readout.py``),
  store the result as a snapshot and hand it to the interface.
* Keep the snapshots (the newest twenty per cube) and let the user look at, export or delete them.

Nothing here writes to a cube; the agent's read-out functions only read. Limits: a recording lasts
5 to 30 seconds with 200 to 2000 ms between two reads, so it can neither flood the cube nor the
database.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from octaledger.core.errors import ApiUnavailableError, NotFoundError, ValidationError
from octaledger.domain.models import new_id
from octaledger.domain.readout import Reading, Snapshot
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

MIN_SECONDS, MAX_SECONDS = 5, 30
MIN_INTERVAL_MS, MAX_INTERVAL_MS = 200, 2000


class ReadoutSource(Protocol):
    """What the service needs from the agent (implemented by the BLE agent)."""

    def read_out(
        self, device_id: str, kind: str, seconds: float = 0.0, interval_ms: int = 500
    ) -> list[Reading]:
        """Read out a connected cube (``datasheet`` or ``accelerometer``)."""
        ...


class ReadoutService:
    """Take, store and list read-outs (see the module docstring)."""

    def __init__(
        self,
        storage: Storage,
        source: Callable[[], ReadoutSource | None],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create the service.

        Args:
            storage: The database.
            source: Returns the agent (``None`` while the API runs without one).
            clock: Returns the current UTC time.
        """
        self._storage = storage
        self._source = source
        self._clock = clock

    def _agent(self) -> ReadoutSource:
        agent = self._source()
        if agent is None:
            raise ApiUnavailableError("The BLE agent is not running in this process")
        return agent

    def take(self, device_id: str) -> Snapshot:
        """Read the data sheet of a connected cube and store it.

        Raises:
            NotFoundError: If the cube does not exist.
            BleConnectionError: If the cube is not connected or a read fails as a whole.
        """
        return self._store(device_id, "datasheet", None, self._read(device_id, "datasheet", 0, 500))

    def record(self, device_id: str, seconds: int, interval_ms: int) -> Snapshot:
        """Record the accelerometer characteristic for a short time and store the readings.

        Raises:
            ValidationError: For a duration or interval outside the allowed range.
            NotFoundError: If the cube does not exist.
            BleConnectionError: If the cube is not connected or has no readable accelerometer.
        """
        if not MIN_SECONDS <= seconds <= MAX_SECONDS:
            raise ValidationError(
                f"Duration out of range: {seconds}",
                user_message=f"Die Dauer muss {MIN_SECONDS} bis {MAX_SECONDS} Sekunden betragen.",
            )
        if not MIN_INTERVAL_MS <= interval_ms <= MAX_INTERVAL_MS:
            raise ValidationError(
                f"Interval out of range: {interval_ms}",
                user_message=f"Der Abstand muss {MIN_INTERVAL_MS} bis {MAX_INTERVAL_MS} "
                "Millisekunden betragen.",
            )
        readings = self._read(device_id, "accelerometer", seconds, interval_ms)
        return self._store(device_id, "accelerometer", interval_ms, readings)

    def _read(self, device_id: str, kind: str, seconds: int, interval_ms: int) -> list[Reading]:
        with self._storage.read() as repos:
            repos.devices.require(device_id)
        return self._agent().read_out(device_id, kind, seconds, interval_ms)

    def _store(
        self, device_id: str, kind: str, interval_ms: int | None, readings: list[Reading]
    ) -> Snapshot:
        snapshot = Snapshot(
            id=new_id(),
            device_id=device_id,
            taken_at=ensure_utc(self._clock()),
            kind=kind,
            readings=tuple(readings),
            interval_ms=interval_ms,
        )
        with self._storage.transaction() as repos:
            repos.snapshots.add(snapshot)
        logger.info("Read-out stored (%s, %d readings)", kind, len(readings))
        return snapshot

    def list(self, device_id: str) -> list[Snapshot]:
        """The snapshots of a cube, newest first."""
        with self._storage.read() as repos:
            repos.devices.require(device_id)
            return repos.snapshots.list_for_device(device_id)

    def get(self, snapshot_id: str) -> Snapshot:
        """One snapshot.

        Raises:
            NotFoundError: If it does not exist.
        """
        with self._storage.read() as repos:
            snapshot = repos.snapshots.get(snapshot_id)
        if snapshot is None:
            raise NotFoundError(f"Snapshot {snapshot_id} not found", details={"id": snapshot_id})
        return snapshot

    def delete(self, snapshot_id: str) -> None:
        """Delete a snapshot.

        Raises:
            NotFoundError: If it does not exist.
        """
        with self._storage.transaction() as repos:
            if not repos.snapshots.delete(snapshot_id):
                raise NotFoundError(
                    f"Snapshot {snapshot_id} not found", details={"id": snapshot_id}
                )
