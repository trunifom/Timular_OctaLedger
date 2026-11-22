"""The action dispatcher: a worker thread that sends the queued actions of control mode.

Responsibility
--------------
Turning the cube must switch the light *soon*, but the BLE loop must never wait for a network
request and the dashboard must never be involved. So sending runs in its own **daemon thread**
inside the agent: it asks :class:`~octaledger.application.integration_service.IntegrationService`
for due jobs a few times a second and lets it call the adapters (blocking is fine here).

Design notes
------------
* **One thread, strict order:** jobs are sent one after another in the order they were created,
  so "on" followed by "off" arrives as "on", then "off".
* **Never dies:** an unexpected error is logged and the loop continues; a database or adapter
  problem must not silently end control mode.
* **Prompt stop:** the wait between rounds is an :class:`threading.Event`, so shutdown does not
  wait for the polling interval.
"""

from __future__ import annotations

import logging
import threading
from typing import Final

from octaledger.application.integration_service import IntegrationService

logger = logging.getLogger(__name__)

#: Seconds between polls of the queue while it is empty (the added latency of an action).
POLL_INTERVAL: Final = 0.25


class ActionDispatcher:
    """Sends queued actions in a background thread (see the module docstring)."""

    def __init__(self, service: IntegrationService, *, interval: float = POLL_INTERVAL) -> None:
        """Create the dispatcher (the thread starts with :meth:`start`)."""
        self._service = service
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the worker thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="octaledger-dispatcher", daemon=True)
        self._thread.start()
        logger.info("Action dispatcher started")

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the thread to end and wait for it (a job in flight is allowed to finish)."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                logger.warning("The action dispatcher did not stop within %.0f s", timeout)
        logger.info("Action dispatcher stopped")

    @property
    def running(self) -> bool:
        """Whether the worker thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.is_set():
            handled = 0
            try:
                handled = self._service.process_due()
            except Exception:
                logger.exception("The action dispatcher hit an unexpected error")
            if handled == 0:
                self._stop.wait(self._interval)
