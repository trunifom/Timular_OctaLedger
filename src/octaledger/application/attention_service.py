"""The attention centre service: list, dismiss and expire questions waiting for the user.

Answering a question changes data and therefore belongs to the service that owns that data
(for a gap: :meth:`TrackingService.resolve_gap`). This service only manages the questions
themselves and never touches time data.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from octaledger.domain.attention import AttentionItem, AttentionStatus
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

#: Open questions older than this many days are marked expired (their time data is untouched).
EXPIRE_AFTER_DAYS = 30


class AttentionService:
    """Reads and closes attention items."""

    def __init__(self, storage: Storage, *, clock: Callable[[], datetime] = utc_now) -> None:
        """Create the service.

        Args:
            storage: Transactional storage.
            clock: Returns the current UTC time (injectable for tests).
        """
        self._storage = storage
        self._clock = clock

    def list_open(self) -> list[AttentionItem]:
        """Return all open questions, oldest first."""
        with self._storage.read() as repos:
            return repos.attention.list_open()

    def list_recent(self, limit: int = 50) -> list[AttentionItem]:
        """Return the newest questions of any status."""
        with self._storage.read() as repos:
            return repos.attention.list_recent(limit)

    def get(self, item_id: str) -> AttentionItem:
        """Return one question.

        Raises:
            NotFoundError: If it does not exist.
        """
        with self._storage.read() as repos:
            return repos.attention.require(item_id)

    def dismiss(self, item_id: str) -> AttentionItem:
        """Close a question without acting on it (the entry stays as it is).

        Raises:
            NotFoundError: If the item does not exist.
        """
        with self._storage.transaction() as repos:
            item = repos.attention.require(item_id)
            if item.status is AttentionStatus.OPEN:
                repos.attention.close(
                    item_id, AttentionStatus.DISMISSED, "dismissed", ensure_utc(self._clock())
                )
                repos.audit.add("dismiss_attention", "attention", item_id, item.kind.value)
            return repos.attention.require(item_id)

    def expire_old(self) -> int:
        """Mark very old open questions as expired; returns how many."""
        now = ensure_utc(self._clock())
        with self._storage.transaction() as repos:
            count = repos.attention.expire_open_before(now - timedelta(days=EXPIRE_AFTER_DAYS), now)
        if count:
            logger.info("%d old attention item(s) expired", count)
        return count
