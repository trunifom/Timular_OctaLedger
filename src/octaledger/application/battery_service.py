"""Battery history, stages and estimate of the cubes (AP-52).

Responsibility
--------------
* :meth:`BatteryService.record` is called by the housekeeper with the live status of the cubes. It
  stores a reading when the value changed or six hours passed (small history), logs a WARNING when
  a cube drops to a **lower stage** (once per stage, also across restarts) and prunes old rows.
* :meth:`BatteryService.summary` answers "how is the battery?" for the interface: the live value
  (or, while the cube is not connected, the **last stored one** marked as old), the stage with its
  text, and an estimate of the remaining days when the history is long enough.
* :meth:`BatteryService.history` returns the stored course for a chart.

The percentage is the cube's own value; the estimate is a labelled guess (``domain/battery.py``).
Warnings in the attention centre for the configured limit stay with :mod:`battery_watch`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from octaledger.agent.supervisor import DeviceStatus
from octaledger.domain.battery import (
    KEEP,
    WINDOW,
    Stage,
    bar,
    describe_days,
    estimate_days_left,
    is_worse,
    should_record,
    stage_for,
)
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

#: How often old rows are pruned (the check is cheap; this only avoids doing it every 5 seconds).
_PRUNE_EVERY = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class BatterySummary:
    """What the interface shows about one cube's battery."""

    percent: int
    stage: Stage
    live: bool  # False: the cube is not connected, the value is the last stored one
    measured_at: datetime | None
    days_left: float | None

    @property
    def bar(self) -> str:
        """The five-segment bar."""
        return bar(self.percent)

    @property
    def estimate_text(self) -> str:
        """The estimate as German text (always marked as an estimate)."""
        return describe_days(self.days_left)


class BatteryService:
    """Records readings and answers battery questions (see the module docstring)."""

    def __init__(self, storage: Storage, *, clock: Callable[[], datetime] = utc_now) -> None:
        """Create the service.

        Args:
            storage: The database.
            clock: Returns the current UTC time.
        """
        self._storage = storage
        self._clock = clock
        self._stage: dict[str, Stage] = {}
        self._pruned_at: datetime | None = None

    def record(self, readings: Mapping[str, int | None]) -> int:
        """Store the readings that are due; returns how many rows were written.

        Args:
            readings: ``device id -> percent`` (``None`` for cubes without a reading).
        """
        now = ensure_utc(self._clock())
        written = 0
        with self._storage.transaction() as repos:
            for device_id, percent in readings.items():
                if percent is None:
                    continue
                last = repos.battery.latest(device_id)
                if device_id not in self._stage and last is not None:
                    self._stage[device_id] = stage_for(last[1])  # known from before a restart
                if should_record(
                    last[1] if last else None, last[0] if last else None, percent, now
                ):
                    repos.battery.add(device_id, now, percent)
                    written += 1
                stage = stage_for(percent)
                if is_worse(self._stage.get(device_id), stage):
                    log = logger.error if stage.level == "bad" else logger.warning
                    log("Battery of cube %s is %s (%d %%)", device_id[:8], stage.text, percent)
                self._stage[device_id] = stage
            if self._pruned_at is None or now - self._pruned_at >= _PRUNE_EVERY:
                self._pruned_at = now
                repos.battery.prune(now - KEEP)
        return written

    def summary(self, live: Mapping[str, int | None]) -> dict[str, BatterySummary | None]:
        """Per cube: the battery summary, or ``None`` when nothing is known yet.

        Args:
            live: ``device id -> percent`` of the connected cubes (``None``/missing: not known).
        """
        now = ensure_utc(self._clock())
        result: dict[str, BatterySummary | None] = {}
        with self._storage.read() as repos:
            for device in repos.devices.list_all():
                latest = repos.battery.latest(device.id)
                value = live.get(device.id)
                if value is None and latest is None:
                    result[device.id] = None
                    continue
                percent = value if value is not None else (latest[1] if latest else 0)
                points = repos.battery.since(device.id, now - WINDOW)
                result[device.id] = BatterySummary(
                    percent=percent,
                    stage=stage_for(percent),
                    live=value is not None,
                    measured_at=now if value is not None else (latest[0] if latest else None),
                    days_left=estimate_days_left(points, now),
                )
        return result

    def history(self, device_id: str, days: int = 60) -> list[tuple[datetime, int]]:
        """The stored readings of the last ``days`` days, oldest first."""
        start = ensure_utc(self._clock()) - timedelta(days=max(1, min(days, 400)))
        with self._storage.read() as repos:
            repos.devices.require(device_id)
            return repos.battery.since(device_id, start)


def percent_map(statuses: Sequence[DeviceStatus]) -> dict[str, int | None]:
    """``device id -> battery percent`` from the live statuses of the agent."""
    return {s.device_id: s.battery_percent for s in statuses}
