"""Notifications: tell the user about new questions without opening the dashboard.

The services only *raise* items in the attention centre (``reminder``, ``gap`` ...). This
module turns **new** items into short desktop messages. How a message appears is up to a
:class:`Notifier` (Windows toast; others can be added); the dashboard banner always exists in
addition. Texts are German and contain no notes or other sensitive content.

Rules: messages are only sent when switched on, never during quiet hours, and each item at most
once. Items that already existed when the agent started are *not* announced again.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

from octaledger.core.settings import NotificationSettings
from octaledger.domain.attention import AttentionItem, AttentionKind
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    """Shows one short message to the user."""

    def notify(self, title: str, message: str) -> None:
        """Show the message; must not raise for a failure to display."""
        ...


def _parse(text: str) -> time | None:
    if not text:
        return None
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


def in_quiet_hours(local: time, start: str, end: str) -> bool:
    """Whether ``local`` lies inside the quiet period (it may span midnight).

    Args:
        local: Local clock time.
        start: ``HH:MM`` where the quiet period begins (empty = no quiet hours).
        end: ``HH:MM`` where it ends.
    """
    begin, finish = _parse(start), _parse(end)
    if begin is None or finish is None or begin == finish:
        return False
    if begin < finish:
        return begin <= local < finish
    return local >= begin or local < finish  # spans midnight, e.g. 22:00 to 07:00


def describe(item: AttentionItem) -> tuple[str, str]:
    """German title and text for an item (never contains notes or names of entries)."""
    reason = item.payload.get("reason")
    if item.kind is AttentionKind.GAP:
        return "Lücke nach Verbindungsverlust", "Was war in der Zeit? Bitte im Dashboard antworten."
    if item.kind is AttentionKind.IDLE:
        return "Keine Eingabe", "Die Zeit läuft noch. Bitte im Dashboard entscheiden."
    if item.kind is AttentionKind.AUTO_STOP:
        return "Arbeitsende", "Ihr Eintrag wurde automatisch beendet. Haben Sie länger gearbeitet?"
    if item.kind is AttentionKind.BREAK_HINT:
        return "Pause?", "Heute viel Arbeitszeit ohne erfasste Pause (nur ein Hinweis)."
    if reason == "budget":
        return "Budget fast verbraucht", "Ein Projekt hat 80 % oder 100 % seines Budgets erreicht."
    if reason == "battery":
        return "Batterie fast leer", "Bitte den Würfel bald laden."
    if reason == "no_timer":
        return "Zeit starten?", "Es läuft keine Zeiterfassung."
    if reason == "running_long":
        return "Noch dabei?", "Ein Eintrag läuft schon sehr lange."
    return "OctaLedger", "Es wartet etwas auf Sie."


class NotificationRelay:
    """Announces new attention items through the notifiers (called by the housekeeper)."""

    def __init__(
        self,
        storage: Storage,
        notifiers: Sequence[Notifier],
        settings: Callable[[], NotificationSettings],
        timezone: Callable[[], str],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create the relay.

        Args:
            storage: Where the open items are read.
            notifiers: The ways to show a message.
            settings: Returns the notification settings (read on every call).
            timezone: Returns the display timezone name (decides what "22:00" means).
            clock: Returns the current UTC time.
        """
        self._storage = storage
        self._notifiers = tuple(notifiers)
        self._settings = settings
        self._timezone = timezone
        self._clock = clock
        self._seen: set[str] | None = None

    def check(self) -> int:
        """Announce the new items; returns how many messages were sent."""
        with self._storage.read() as repos:
            items = repos.attention.list_open()
        if self._seen is None:  # first call: what is already open was not "new"
            self._seen = {i.id for i in items}
            return 0
        new = [i for i in items if i.id not in self._seen]
        self._seen.update(i.id for i in new)
        config = self._settings()
        if not new or not config.toast or not self._notifiers:
            return 0
        local = ensure_utc(self._clock()).astimezone(ZoneInfo(self._timezone())).time()
        if in_quiet_hours(local, config.quiet_start, config.quiet_end):
            logger.info("%d new item(s) not announced (quiet hours)", len(new))
            return 0
        sent = 0
        for item in new:
            title, message = describe(item)
            for notifier in self._notifiers:
                try:
                    notifier.notify(title, message)
                    sent += 1
                except Exception:  # noqa: BLE001 - a failing display must never stop the agent
                    logger.exception("A notifier failed")
        return sent
