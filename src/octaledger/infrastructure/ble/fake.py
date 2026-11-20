"""Scriptable fake tracker for deterministic tests (synthetic data only).

Responsibility
--------------
:class:`FakeTransport` behaves like a tracker without any hardware so that connection
lifecycle, reconnect, baseline and debounce handling can be tested reliably and quickly.
It models what real hardware does: connecting takes time and can fail, services must be
discovered, notifications arrive via a callback, and the link can drop at any time.

Everything produced here is **synthetic**. Never present data from this module as real
working-time data (``docs/TESTPLAN.md``).
"""

from __future__ import annotations

import asyncio
from collections import deque

from octaledger.core.errors import BleConnectionError
from octaledger.infrastructure.ble.protocol import (
    BATTERY_LEVEL_UUID,
    BATTERY_SERVICE_UUID,
    DEVICE_INFO_SERVICE_UUID,
    FIRMWARE_REVISION_UUID,
    MODEL_NUMBER_UUID,
    ORIENTATION_CHARACTERISTIC_UUID,
    ORIENTATION_SERVICE_UUID,
    GattCharacteristic,
    GattService,
    normalize_uuid,
)
from octaledger.infrastructure.ble.transport import (
    DeviceTransport,
    DisconnectCallback,
    NotificationCallback,
)


def default_services(*, with_extras: bool = True) -> list[GattService]:
    """Return the GATT layout of a compatible tracker (optionally with battery/info)."""
    services = [
        GattService(
            ORIENTATION_SERVICE_UUID,
            (GattCharacteristic(ORIENTATION_CHARACTERISTIC_UUID, frozenset({"read", "notify"})),),
        )
    ]
    if with_extras:
        services += [
            GattService(
                BATTERY_SERVICE_UUID,
                (GattCharacteristic(BATTERY_LEVEL_UUID, frozenset({"read"})),),
            ),
            GattService(
                DEVICE_INFO_SERVICE_UUID,
                (
                    GattCharacteristic(MODEL_NUMBER_UUID, frozenset({"read"})),
                    GattCharacteristic(FIRMWARE_REVISION_UUID, frozenset({"read"})),
                ),
            ),
        ]
    return services


class FakeTransport:
    """In-memory :class:`DeviceTransport` with scriptable behaviour.

    Attributes:
        connect_calls / disconnect_calls: How often the methods were called.
        notify_started: Whether a notification subscription is currently active.
    """

    def __init__(
        self,
        *,
        services: list[GattService] | None = None,
        values: dict[str, bytes] | None = None,
        connect_delay: float = 0.0,
    ) -> None:
        """Create the fake.

        Args:
            services: GATT layout; defaults to :func:`default_services`.
            values: Readable characteristic values by UUID. Defaults provide orientation
                ``0``, battery 87 %, model "FAKE-1" and firmware "0.0-test".
            connect_delay: Simulated time (seconds) a connect takes.
        """
        self._services = services if services is not None else default_services()
        self.values: dict[str, bytes] = {
            normalize_uuid(ORIENTATION_CHARACTERISTIC_UUID): b"\x00",
            normalize_uuid(BATTERY_LEVEL_UUID): bytes([87]),
            normalize_uuid(MODEL_NUMBER_UUID): b"FAKE-1",
            normalize_uuid(FIRMWARE_REVISION_UUID): b"0.0-test",
        }
        if values:
            self.values.update({normalize_uuid(k): v for k, v in values.items()})
        self._connect_delay = connect_delay
        self._connected = False
        self._notify: dict[str, NotificationCallback] = {}
        self._on_disconnect: DisconnectCallback | None = None
        self._connect_failures: deque[str] = deque()
        self.connect_calls = 0
        self.disconnect_calls = 0

    # ------------------------------------------------------------------ scripting

    def fail_next_connects(self, count: int, message: str = "simulated connect failure") -> None:
        """Make the next ``count`` connect attempts fail with :class:`BleConnectionError`."""
        self._connect_failures.extend([message] * count)

    def push(self, payload: bytes) -> None:
        """Deliver a notification to the subscriber (as the radio stack would).

        Raises:
            BleConnectionError: If the link is down or nobody subscribed.
        """
        callback = self._notify.get(normalize_uuid(ORIENTATION_CHARACTERISTIC_UUID))
        if not self._connected or callback is None:
            raise BleConnectionError("Cannot push: not connected or not subscribed")
        self.values[normalize_uuid(ORIENTATION_CHARACTERISTIC_UUID)] = payload
        callback(payload)

    def drop_link(self) -> None:
        """Simulate an unexpected link loss (device out of range, battery, sleep)."""
        if not self._connected:
            return
        self._connected = False
        self._notify.clear()
        if self._on_disconnect is not None:
            self._on_disconnect()

    @property
    def notify_started(self) -> bool:
        """Whether a notification subscription is active."""
        return bool(self._notify)

    # ------------------------------------------------------------- DeviceTransport

    @property
    def is_connected(self) -> bool:
        """Whether the simulated link is up."""
        return self._connected

    def set_disconnected_callback(self, callback: DisconnectCallback | None) -> None:
        """Register the link-loss callback."""
        self._on_disconnect = callback

    async def connect(self) -> None:
        """Connect after the configured delay, or fail as scripted."""
        self.connect_calls += 1
        if self._connect_delay:
            await asyncio.sleep(self._connect_delay)
        if self._connect_failures:
            raise BleConnectionError(self._connect_failures.popleft())
        self._connected = True

    async def disconnect(self) -> None:
        """Close the link (idempotent). A deliberate disconnect does not call the callback."""
        self.disconnect_calls += 1
        self._connected = False
        self._notify.clear()

    def _require_link(self) -> None:
        if not self._connected:
            raise BleConnectionError("Not connected")

    async def discover(self) -> list[GattService]:
        """Return the scripted services."""
        self._require_link()
        return list(self._services)

    async def read(self, characteristic_uuid: str) -> bytes:
        """Return the stored value of a characteristic."""
        self._require_link()
        try:
            return self.values[normalize_uuid(characteristic_uuid)]
        except KeyError:
            raise BleConnectionError(f"Unknown characteristic {characteristic_uuid}") from None

    async def start_notify(self, characteristic_uuid: str, callback: NotificationCallback) -> None:
        """Register the notification callback."""
        self._require_link()
        self._notify[normalize_uuid(characteristic_uuid)] = callback

    async def stop_notify(self, characteristic_uuid: str) -> None:
        """Remove the notification callback (idempotent)."""
        self._notify.pop(normalize_uuid(characteristic_uuid), None)


class FakeTransportFactory:
    """Factory handing out :class:`FakeTransport` instances and remembering them."""

    def __init__(self, **transport_kwargs: object) -> None:
        """Remember the keyword arguments used for every created fake."""
        self._kwargs = transport_kwargs
        self.created: list[FakeTransport] = []
        self.pending_failures = 0

    def create(self, address: str) -> DeviceTransport:
        """Create a fresh fake; scripted failures are applied to the new instance."""
        transport = FakeTransport(**self._kwargs)  # type: ignore[arg-type]
        if self.pending_failures:
            transport.fail_next_connects(self.pending_failures)
            self.pending_failures = 0
        self.created.append(transport)
        return transport

    @property
    def last(self) -> FakeTransport:
        """The most recently created fake."""
        return self.created[-1]
