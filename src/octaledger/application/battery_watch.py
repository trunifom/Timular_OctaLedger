"""Low-battery warning: one question in the attention centre per discharge cycle.

An empty cube behaves like a lost connection, so the user is warned **once** when the battery
falls below the configured percentage. The warning is a ``reminder`` attention item; it is not
raised again until the battery has recovered (charged) and fallen below the limit once more.
The percentage comes from the periodic read-only battery reads of the agent.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime

from octaledger.agent.supervisor import DeviceStatus
from octaledger.core.settings import NotificationSettings
from octaledger.domain.attention import AttentionItem, AttentionKind
from octaledger.domain.time_rules import utc_now
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

#: The battery must rise this many percent above the limit before a new warning is possible.
HYSTERESIS_PERCENT = 5


class BatteryWatch:
    """Raises a reminder when a cube's battery is low (called by the housekeeper)."""

    def __init__(
        self,
        storage: Storage,
        statuses: Callable[[], Sequence[DeviceStatus]],
        settings: Callable[[], NotificationSettings],
        names: Callable[[str], str],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create the watch.

        Args:
            storage: Where the reminder is stored.
            statuses: Returns the live status of the started devices.
            settings: Returns the current notification settings.
            names: Maps a device id to its name for the message.
            clock: Returns the current UTC time.
        """
        self._storage = storage
        self._statuses = statuses
        self._settings = settings
        self._names = names
        self._clock = clock
        self._warned: set[str] = set()

    def check(self) -> list[AttentionItem]:
        """Warn about every cube below the limit that was not warned about yet."""
        limit = self._settings().battery_warning_percent
        raised: list[AttentionItem] = []
        for status in self._statuses():
            level = status.battery_percent
            if level is None or limit == 0:
                continue
            if level > limit + HYSTERESIS_PERCENT:
                self._warned.discard(status.device_id)
                continue
            if level > limit or status.device_id in self._warned:
                continue
            self._warned.add(status.device_id)
            with self._storage.transaction() as repos:
                already = any(
                    i.kind is AttentionKind.REMINDER
                    and i.payload.get("reason") == "battery"
                    and i.payload.get("device_id") == status.device_id
                    for i in repos.attention.list_open()
                )
                if already:
                    continue
                item = repos.attention.add(
                    AttentionItem(
                        kind=AttentionKind.REMINDER,
                        created_at=self._clock(),
                        payload={
                            "reason": "battery",
                            "device_id": status.device_id,
                            "alias": self._names(status.device_id),
                            "percent": level,
                        },
                    )
                )
            raised.append(item)
            logger.warning("Low battery warning raised (%d %%)", level)
        return raised
