"""Per-device tasks, reconnect and graceful shutdown.

Responsibility
--------------
Own the long-lived connection of every tracker inside **one asyncio event loop** (a Bleak
requirement) and turn the radio stream into clean events for the
:class:`~octaledger.application.tracking_service.TrackingService`:

``connect -> discover -> subscribe -> baseline -> ready`` and, after a loss,
``disconnected -> reconnect_wait (bounded exponential backoff) -> connecting`` - until the
user stops the device on purpose, which also ends reconnecting (Pflichtenheft F-17).

Rules implemented here (``docs/ARCHITEKTUR.md``)
------------------------------------------------
* **One owner per device**: a :class:`DeviceWorker` is the only place that touches that
  device's transport. A new connection cycle gets a new connection id and a new transport.
* **Short callbacks**: Bleak callbacks only append to a *bounded* buffer and set an event.
  Overflow rule: the **oldest** value is dropped and counted (``dropped_values``).
* **No blocking in the loop**: database work (``record_event``) runs in a worker thread, in
  strict order per device.
* **No invented history**: a loss is reported as a ``DISCONNECT`` event; the tracking
  service decides (mark uncertain / stop). A reconnect delivers ``RECONNECT`` and a fresh
  baseline.
* **Unsupported devices are not retried**: capability discovery failure stops the worker
  with a readable error instead of reconnecting forever.
* **Graceful shutdown**: workers are asked to stop, given time to disconnect and write the
  final event, and only then cancelled.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import (
    BleConnectionError,
    OctaLedgerError,
    ProtocolError,
    UnsupportedDeviceError,
    ValidationError,
)
from octaledger.domain.models import EventKind, RawEvent
from octaledger.domain.state_machine import (
    ConnectionState,
    ConnectionStateMachine,
    OrientationDebouncer,
    OrientationEvent,
    reconnect_delay_seconds,
)
from octaledger.domain.time_rules import utc_now
from octaledger.infrastructure.ble.protocol import (
    BATTERY_LEVEL_UUID,
    FIRMWARE_REVISION_UUID,
    MODEL_NUMBER_UUID,
    ORIENTATION_CHARACTERISTIC_UUID,
    DeviceCapabilities,
    decode_battery_level,
    decode_orientation_payload,
    decode_text,
    discover_capabilities,
)
from octaledger.infrastructure.ble.transport import DeviceTransport, TransportFactory

logger = logging.getLogger(__name__)

S = ConnectionState

#: Callback receiving model/firmware read from the device (persistence is up to the caller).
HardwareInfoCallback = Callable[[str, str | None, str | None], None]


@dataclass(frozen=True, slots=True)
class SupervisorTuning:
    """Timing and size knobs (defaults suit production, tests use tiny values)."""

    debounce_ms: int = 300
    buffer_size: int = 100
    connect_timeout: float = 20.0
    backoff_base: float = 1.0
    backoff_cap: float = 60.0
    baseline_timeout: float = 10.0
    shutdown_grace: float = 5.0

    def __post_init__(self) -> None:
        """Validate the knobs."""
        if self.buffer_size < 1 or self.connect_timeout <= 0 or self.baseline_timeout <= 0:
            raise ValidationError("Invalid supervisor tuning")
        if (
            self.backoff_base <= 0
            or self.backoff_cap < self.backoff_base
            or self.shutdown_grace < 0
        ):
            raise ValidationError("Invalid supervisor backoff tuning")


#: How many recent movements a worker remembers for the live view (memory only, never stored).
LIVE_HISTORY_SIZE = 30

#: ``LiveEvent.kind`` of a value that arrived from the radio but is not yet accepted.
RAW_KIND = "raw"


@dataclass(frozen=True, slots=True)
class LiveEvent:
    """One entry of the in-memory live history (what the cube just did).

    Attributes:
        at: Wall-clock time (UTC) the value or event was observed.
        kind: ``"raw"`` for a value straight from the radio (before debouncing) or an
            :class:`~octaledger.domain.models.EventKind` value for an accepted event.
        value: Orientation ``0..8`` if the entry has one.
    """

    at: datetime
    kind: str
    value: int | None


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """Snapshot of one worker for the diagnostics page and the live view.

    ``last_value`` is the *accepted* orientation (after debouncing); ``raw_value`` is the
    most recent value straight from the radio and ``pending_value`` the candidate that waits
    for ``debounce_ms`` of stability. The live view shows all three so users see why a quick
    wobble does not start anything.
    """

    device_id: str
    state: ConnectionState
    connection_id: str | None
    attempt: int
    last_error: str | None
    last_value: int | None
    last_event_at: datetime | None
    battery_percent: int | None
    dropped_values: int
    duplicates_ignored: int
    raw_value: int | None = None
    raw_at: datetime | None = None
    pending_value: int | None = None
    debounce_ms: int = 0
    recent: tuple[LiveEvent, ...] = ()


def _monotonic_ms() -> int:
    return time.monotonic_ns() // 1_000_000


class DeviceWorker:
    """Connection lifecycle and event pipeline of one tracker."""

    def __init__(
        self,
        device_id: str,
        address: str,
        factory: TransportFactory,
        tracking: TrackingService,
        *,
        tuning: SupervisorTuning | None = None,
        on_hardware_info: HardwareInfoCallback | None = None,
        mono_ms: Callable[[], int] = _monotonic_ms,
        wall_clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create a worker (nothing runs until :meth:`run` is started as a task)."""
        self.device_id = device_id
        self._address = address
        self._factory = factory
        self._tracking = tracking
        self._tuning = tuning or SupervisorTuning()
        self._on_hardware_info = on_hardware_info
        self._mono_ms = mono_ms
        self._wall = wall_clock
        self._machine = ConnectionStateMachine()
        self._debouncer = OrientationDebouncer(self._tuning.debounce_ms)
        self._values: deque[tuple[int, int]] = deque(maxlen=self._tuning.buffer_size)
        self._wake = asyncio.Event()
        self._stop = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None  # set when run() starts
        self._lost = False
        self._pending_invalid: list[str] = []
        self._sequence = 0
        self._had_connection = False  # a link was established at least once
        self._dropped = 0
        self._last_error: str | None = None
        self._last_value: int | None = None
        self._last_event_at: datetime | None = None
        self._battery: int | None = None
        self._raw_value: int | None = None
        self._raw_at: datetime | None = None
        # Appended from the radio callback and the loop: deque.append is thread-safe.
        self._recent: deque[LiveEvent] = deque(maxlen=LIVE_HISTORY_SIZE)

    # ------------------------------------------------------------------ public API

    def _set(self, event: asyncio.Event) -> None:
        """Set an asyncio event from ANY thread and make sure the worker really wakes up.

        ``asyncio.Event.set`` is not thread-safe: called from a foreign thread it does not wake
        the event loop. Bleak normally delivers callbacks on the loop thread, but that is an
        implementation detail of the platform backend, so callbacks must not rely on it.
        """
        loop = self._loop
        if loop is None:
            event.set()
            return
        try:
            on_loop_thread = asyncio.get_running_loop() is loop
        except RuntimeError:
            on_loop_thread = False
        if on_loop_thread:
            event.set()
        elif not loop.is_closed():
            loop.call_soon_threadsafe(event.set)

    def request_stop(self) -> None:
        """Ask the worker to stop for good (also cancels reconnecting). Thread-safe."""
        self._set(self._stop)
        self._set(self._wake)

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._machine.state

    def status(self) -> DeviceStatus:
        """Return a snapshot (safe to call from the loop at any time)."""
        return DeviceStatus(
            device_id=self.device_id,
            state=self._machine.state,
            connection_id=self._machine.connection_id,
            attempt=self._machine.attempt,
            last_error=self._last_error,
            last_value=self._last_value,
            last_event_at=self._last_event_at,
            battery_percent=self._battery,
            dropped_values=self._dropped,
            duplicates_ignored=self._debouncer.duplicates_ignored,
            raw_value=self._raw_value,
            raw_at=self._raw_at,
            pending_value=self._debouncer.pending_value,
            debounce_ms=self._debouncer.debounce_ms,
            recent=tuple(self._recent),
        )

    # --------------------------------------------------------------- BLE callbacks

    def _on_notification(self, payload: bytes) -> None:
        """Bleak callback: validate quickly, buffer, wake the worker (no slow work here)."""
        try:
            value = decode_orientation_payload(payload)
        except ProtocolError as exc:
            self._record_invalid(str(exc))
            return
        self._buffer_value(value)

    def _buffer_value(self, value: int) -> None:
        if len(self._values) == self._values.maxlen:
            self._dropped += 1
            if self._dropped == 1 or self._dropped % 100 == 0:
                logger.warning(
                    "Value buffer full, dropping oldest values (%d dropped so far)", self._dropped
                )
        self._values.append((value, self._mono_ms()))
        self._remember_raw(value)
        self._set(self._wake)

    def _remember_raw(self, value: int) -> None:
        """Keep the newest radio value for the live view; only a *change* enters the history."""
        now = self._wall()
        changed = value != self._raw_value
        self._raw_value, self._raw_at = value, now
        if changed:
            self._recent.append(LiveEvent(now, RAW_KIND, value))

    def _on_link_lost(self) -> None:
        """Bleak callback: flag the loss and wake the worker."""
        self._lost = True
        self._set(self._wake)

    def _record_invalid(self, detail: str) -> None:
        """Remember an invalid packet; it is stored as diagnostic event by the main loop."""
        if len(self._pending_invalid) < self._tuning.buffer_size:
            self._pending_invalid.append(detail)
        self._set(self._wake)

    # ------------------------------------------------------------------ event output

    def _wall_time(self, observed_mono_ms: int) -> datetime:
        """Convert a monotonic observation time to wall-clock UTC."""
        return self._wall() - timedelta(milliseconds=self._mono_ms() - observed_mono_ms)

    async def _emit(
        self,
        kind: EventKind,
        value: int | None,
        observed_ms: int | None = None,
        detail: str | None = None,
    ) -> None:
        """Persist one event through the tracking service (in a thread, in order)."""
        when = self._wall() if observed_ms is None else self._wall_time(observed_ms)
        event = RawEvent(
            device_id=self.device_id,
            kind=kind,
            sequence=self._sequence,
            connection_id=self._machine.connection_id or "none",
            received_at=when,
            raw_value=value,
            detail=detail,
        )
        self._sequence += 1
        self._last_event_at = when
        self._recent.append(LiveEvent(when, kind.value, value))
        try:
            await asyncio.to_thread(self._tracking.record_event, event)
        except OctaLedgerError as exc:
            # A storage problem must not kill the connection; the error is logged and visible.
            self._last_error = exc.user_message
            logger.error("Could not process %s event: %s", kind.value, exc)

    async def _emit_orientation(self, events: list[OrientationEvent]) -> None:
        for event in events:
            self._last_value = event.value
            await self._emit(event.kind, event.value, event.observed_at_ms)

    # ------------------------------------------------------------------- main loop

    async def run(self) -> None:
        """Run connection cycles until stopped. Never raises (errors are recorded)."""
        self._loop = asyncio.get_running_loop()
        logger.info("Worker for device %s started", self.device_id[:8])
        try:
            while not self._stop.is_set():
                fatal = await self._cycle()
                if fatal or self._stop.is_set():
                    break
                await self._wait_before_reconnect()
        finally:
            if self._machine.state is not S.STOPPED and self._machine.can_transition(S.STOPPED):
                self._machine.transition(S.STOPPED)
            logger.info("Worker for device %s ended", self.device_id[:8])

    async def _wait_before_reconnect(self) -> None:
        """Sleep the backoff delay, interruptible by a stop request."""
        if self._machine.state is S.DISCONNECTED:
            self._machine.transition(S.RECONNECT_WAIT)
        delay = reconnect_delay_seconds(
            self._machine.attempt, base=self._tuning.backoff_base, cap=self._tuning.backoff_cap
        )
        logger.info("Reconnecting in %.1f s (attempt %d)", delay, self._machine.attempt)
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=delay)
        except TimeoutError:
            pass

    async def _cycle(self) -> bool:
        """Run one connection cycle. Returns ``True`` if the worker must not retry."""
        if self._machine.state is S.RECONNECT_WAIT or self._machine.state is S.IDLE:
            self._machine.transition(S.CONNECTING)
        transport = self._factory.create(self._address)
        self._lost = False
        self._values.clear()
        self._raw_value = self._raw_at = None  # a new link: do not show a stale position
        self._sequence = 0
        connected_once = False
        capabilities: DeviceCapabilities | None = None
        try:
            transport.set_disconnected_callback(self._on_link_lost)
            await asyncio.wait_for(transport.connect(), timeout=self._tuning.connect_timeout)
            connected_once = True
            self._machine.transition(S.DISCOVERING)
            capabilities = discover_capabilities(await transport.discover())
            self._machine.transition(S.SUBSCRIBING)
            self._debouncer.reset()
            await transport.start_notify(ORIENTATION_CHARACTERISTIC_UUID, self._on_notification)
            self._machine.transition(S.BASELINE)
            if self._had_connection:  # only a *re*connect is reported, not the first success
                await self._emit(EventKind.RECONNECT, None)
            self._had_connection = True
            await self._read_optional(transport, capabilities)
            await self._pump(transport, capabilities)
            self._last_error = None
        except UnsupportedDeviceError as exc:
            self._last_error = exc.user_message
            logger.error("Device %s is not supported: %s", self.device_id[:8], exc)
            return True
        except (BleConnectionError, TimeoutError, OSError) as exc:
            self._last_error = (
                exc.user_message if isinstance(exc, OctaLedgerError) else "Zeitüberschreitung"
            )
            logger.warning("Connection cycle failed: %s", exc)
        finally:
            await self._close(transport, connected_once)
        return False

    async def _pump(self, transport: DeviceTransport, caps: DeviceCapabilities) -> None:
        """Process values, ticks, loss and stop until the cycle ends."""
        if caps.can_read_orientation:
            try:  # the initial value may duplicate the first notification: that is tolerated
                self._buffer_value(
                    decode_orientation_payload(
                        await transport.read(ORIENTATION_CHARACTERISTIC_UUID)
                    )
                )
            except (BleConnectionError, ProtocolError) as exc:
                logger.debug("Initial orientation read skipped: %s", exc)
        baseline_deadline = self._mono_ms() + int(self._tuning.baseline_timeout * 1000)
        while True:
            await self._drain()
            if self._stop.is_set():
                return
            if self._lost or not transport.is_connected:
                self._lost = True
                return
            if self._machine.state is S.BASELINE and self._debouncer.committed_value is not None:
                self._machine.transition(S.READY)
                logger.info("Device %s ready", self.device_id[:8])
            timeout = self._next_timeout(baseline_deadline)
            self._wake.clear()
            if self._values or self._lost or self._stop.is_set():
                continue  # something arrived between draining and clearing the event
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=timeout)
            except TimeoutError:
                await self._emit_orientation(self._debouncer.tick(self._mono_ms()))
                if (
                    self._machine.state is S.BASELINE
                    and self._debouncer.committed_value is None
                    and self._mono_ms() >= baseline_deadline
                ):
                    raise BleConnectionError(
                        "No orientation value received after subscribing",
                        user_message="Der Tracker hat keinen Anfangswert gesendet.",
                    )

    def _next_timeout(self, baseline_deadline: int) -> float | None:
        """Seconds until the next timer (debounce commit or baseline timeout) is due."""
        now = self._mono_ms()
        deadlines = []
        pending = self._debouncer.next_deadline_ms()
        if pending is not None:
            deadlines.append(pending)
        if self._machine.state is S.BASELINE and self._debouncer.committed_value is None:
            deadlines.append(baseline_deadline)
        if not deadlines:
            return None
        return max(0.0, (min(deadlines) - now) / 1000)

    async def _drain(self) -> None:
        """Feed buffered values (oldest first) to the debouncer and persist the results."""
        while self._pending_invalid:
            await self._emit(EventKind.INVALID, None, detail=self._pending_invalid.pop(0))
        while self._values:
            value, observed_ms = self._values.popleft()
            await self._emit_orientation(self._debouncer.feed(value, observed_ms))
        await self._emit_orientation(self._debouncer.tick(self._mono_ms()))

    async def _read_optional(self, transport: DeviceTransport, caps: DeviceCapabilities) -> None:
        """Best-effort read of battery, model and firmware; failures are tolerated (F-18)."""
        model = firmware = None
        try:
            if caps.has_battery:
                self._battery = decode_battery_level(await transport.read(BATTERY_LEVEL_UUID))
            if caps.has_model:
                model = decode_text(await transport.read(MODEL_NUMBER_UUID))
            if caps.has_firmware:
                firmware = decode_text(await transport.read(FIRMWARE_REVISION_UUID))
        except (BleConnectionError, ProtocolError) as exc:
            logger.info("Optional device information unavailable: %s", exc)
        if (model or firmware) and self._on_hardware_info is not None:
            try:
                await asyncio.to_thread(self._on_hardware_info, self.device_id, model, firmware)
            except OctaLedgerError as exc:
                logger.warning("Could not store hardware info: %s", exc)

    async def _close(self, transport: DeviceTransport, connected_once: bool) -> None:
        """End a cycle: unsubscribe, disconnect, report the loss, update the state."""
        was_up = connected_once and self._machine.state in (
            S.DISCOVERING,
            S.SUBSCRIBING,
            S.BASELINE,
            S.READY,
        )
        try:
            await transport.stop_notify(ORIENTATION_CHARACTERISTIC_UUID)
            await transport.disconnect()
        except Exception:  # noqa: BLE001 - closing must never fail the worker
            logger.debug("Ignoring error while closing the transport", exc_info=True)
        # Only a link that was actually established has data worth reporting as lost.
        if was_up:
            await self._emit(EventKind.DISCONNECT, None)
        self._raw_value = self._raw_at = None  # the position is unknown once the link is gone
        if self._stop.is_set():
            if self._machine.can_transition(S.STOPPED):
                self._machine.transition(S.STOPPED)
        elif self._machine.can_transition(S.DISCONNECTED):
            self._machine.transition(S.DISCONNECTED)


class AgentSupervisor:
    """Manages the workers of all active trackers inside the agent's event loop."""

    def __init__(
        self,
        factory: TransportFactory,
        tracking: TrackingService,
        *,
        tuning: SupervisorTuning | None = None,
        on_hardware_info: HardwareInfoCallback | None = None,
    ) -> None:
        """Create the supervisor (no connections are opened yet)."""
        self._factory = factory
        self._tracking = tracking
        self._tuning = tuning or SupervisorTuning()
        self._on_hardware_info = on_hardware_info
        self._workers: dict[str, DeviceWorker] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start_device(self, device_id: str, address: str) -> DeviceWorker:
        """Start (or return the running) worker of a device.

        Raises:
            ValidationError: If ``address`` is empty (the device was never found by a scan).
        """
        if not address or not address.strip():
            raise ValidationError(
                "Device has no Bluetooth address",
                user_message="Für dieses Gerät ist keine Bluetooth-Adresse gespeichert. "
                "Bitte zuerst per Suche verbinden.",
                details={"device_id": device_id},
            )
        task = self._tasks.get(device_id)
        if task is not None and not task.done():
            return self._workers[device_id]
        worker = DeviceWorker(
            device_id,
            address,
            self._factory,
            self._tracking,
            tuning=self._tuning,
            on_hardware_info=self._on_hardware_info,
        )
        self._workers[device_id] = worker
        self._tasks[device_id] = asyncio.create_task(worker.run(), name=f"worker-{device_id[:8]}")
        return worker

    async def stop_device(self, device_id: str) -> None:
        """Stop one device on purpose (no further reconnects)."""
        worker, task = self._workers.get(device_id), self._tasks.get(device_id)
        if worker is None or task is None:
            return
        worker.request_stop()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self._tuning.shutdown_grace)
        except TimeoutError:
            logger.warning("Worker %s did not stop in time; cancelling", device_id[:8])
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def shutdown(self) -> None:
        """Stop all workers gracefully (disconnect, final events), then cancel stragglers."""
        logger.info("Supervisor shutting down (%d worker(s))", len(self._tasks))
        for worker in self._workers.values():
            worker.request_stop()
        tasks = [t for t in self._tasks.values() if not t.done()]
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=self._tuning.shutdown_grace)
            for task in pending:
                logger.warning("Cancelling worker %s", task.get_name())
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    def statuses(self) -> list[DeviceStatus]:
        """Return the status of every known worker."""
        return [worker.status() for worker in self._workers.values()]

    def status_of(self, device_id: str) -> DeviceStatus | None:
        """Return one worker's status, or ``None`` if never started."""
        worker = self._workers.get(device_id)
        return None if worker is None else worker.status()
