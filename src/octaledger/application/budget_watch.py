"""Budget warnings: one reminder at 80 % and one at 100 % of a project's budget.

The check reads all entries of projects that have a budget, so it only runs about once a minute
(called by the housekeeper). Each level is announced **once**; the state is kept in the
database, so a restart does not repeat a warning. If the budget is raised so that the usage
falls below 80 % again, the levels are reset and can warn again.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime

from octaledger.application.reporting_service import ReportService
from octaledger.domain.attention import AttentionItem, AttentionKind
from octaledger.domain.time_rules import utc_now
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

STATE_PREFIX = "budget:"
#: Seconds between two checks (the work is proportional to the number of entries).
CHECK_INTERVAL = 60.0


class BudgetWatch:
    """Raises budget reminders (see the module docstring)."""

    def __init__(
        self,
        storage: Storage,
        reports: ReportService,
        *,
        clock: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        interval: float = CHECK_INTERVAL,
    ) -> None:
        """Create the watch.

        Args:
            storage: Where reminders and the warned levels are stored.
            reports: Source of the budget use per project.
            clock: Returns the current UTC time.
            monotonic: Time source for the check interval (injectable for tests).
            interval: Seconds between two checks.
        """
        self._storage = storage
        self._reports = reports
        self._clock = clock
        self._monotonic = monotonic
        self._interval = interval
        self._last: float | None = None

    def check(self, *, force: bool = False) -> list[AttentionItem]:
        """Warn about projects that reached 80 % or 100 % of their budget."""
        now = self._monotonic()
        if not force and self._last is not None and now - self._last < self._interval:
            return []
        self._last = now
        raised: list[AttentionItem] = []
        for budget in self._reports.budgets():
            if budget.budget_minutes is None or budget.fraction is None:
                continue
            level = 100 if budget.fraction >= 1.0 else 80 if budget.fraction >= 0.8 else 0
            key = STATE_PREFIX + budget.project_id
            with self._storage.transaction() as repos:
                raw = repos.state.get(key)
                known = json.loads(raw) if raw else {"budget": budget.budget_minutes, "level": 0}
                if known["budget"] != budget.budget_minutes:
                    known = {"budget": budget.budget_minutes, "level": 0}  # budget changed
                if level < known["level"]:
                    known["level"] = level if level == 0 else known["level"]
                if level > known["level"]:
                    known["level"] = level
                    raised.append(
                        repos.attention.add(
                            AttentionItem(
                                kind=AttentionKind.REMINDER,
                                created_at=self._clock(),
                                payload={
                                    "reason": "budget",
                                    "project": budget.name,
                                    "percent": level,
                                    "used_minutes": round(budget.used.total_seconds() / 60),
                                    "budget_minutes": budget.budget_minutes,
                                },
                            )
                        )
                    )
                    logger.warning("Budget warning raised (%d %%)", level)
                repos.state.set(key, json.dumps(known))
        return raised
