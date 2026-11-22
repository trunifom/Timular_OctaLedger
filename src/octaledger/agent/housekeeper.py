"""The housekeeper: a timer thread for rules that depend on time instead of events.

Responsibility
--------------
Some rules fire because time passes, not because the cube turned: the grace period after a lost
connection, later the end of the working day or reminders. The BLE loop must not be blocked for
that and API threads must not change time data "on the side", so a small **daemon thread** calls
the application services every few seconds (pattern of :class:`ActionDispatcher`).

Design notes
------------
* The thread only *ticks*; every decision is made by pure, separately tested rules.
* **Never dies:** one failing task is logged and the others still run.
* **Prompt stop:** the wait between ticks is an :class:`threading.Event`.
* A tick also runs **immediately at start**, so a grace period that ended while the agent was
  not running is handled right away (the marker lives in the database).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from typing import Final

logger = logging.getLogger(__name__)

#: Seconds between ticks.
TICK_SECONDS: Final = 5.0


class Housekeeper:
    """Runs a list of tasks periodically in a background thread."""

    def __init__(
        self, tasks: Sequence[Callable[[], object]], *, interval: float = TICK_SECONDS
    ) -> None:
        """Create the housekeeper (the thread starts with :meth:`start`).

        Args:
            tasks: Callables run on every tick, in order.
            interval: Seconds between ticks.
        """
        self._tasks = tuple(tasks)
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="octaledger-housekeeper", daemon=True
        )
        self._thread.start()
        logger.info("Housekeeper started")

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the thread to end and wait for it."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                logger.warning("The housekeeper did not stop within %.0f s", timeout)
        logger.info("Housekeeper stopped")

    @property
    def running(self) -> bool:
        """Whether the thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def tick(self) -> None:
        """Run every task once; a failing task never prevents the others."""
        for task in self._tasks:
            try:
                task()
            except Exception:
                logger.exception("A housekeeper task failed")

    def _run(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self._interval)
