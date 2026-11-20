"""Transport abstraction between the agent logic and a real Bluetooth stack.

Responsibility
--------------
:class:`DeviceTransport` is the **only** interface the agent uses to talk to one tracker.
It exists so that

* the supervisor, reconnect and session logic can be tested deterministically with
  :class:`~octaledger.infrastructure.ble.fake.FakeTransport` (no hardware, synthetic data),
* the real implementation (:class:`~octaledger.infrastructure.ble.client.BleakTransport`)
  can stay small and be tested manually on hardware, and
* **writing to the device is impossible by construction**: the protocol has no write
  method (Pflichtenheft section 2, ``docs/BLE_PROTOCOL.md``).

All methods run on the agent's single asyncio event loop. Callbacks registered with
:meth:`DeviceTransport.start_notify` and :meth:`DeviceTransport.set_disconnected_callback`
must be short and synchronous (validate, hand over, return); they must never call the GUI
or do slow work (architecture rule "no UI calls in the BLE callback").
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from octaledger.infrastructure.ble.protocol import GattService

#: Called with the raw bytes of one notification.
NotificationCallback = Callable[[bytes], None]
#: Called (without arguments) when the link to the device was lost.
DisconnectCallback = Callable[[], None]


class DeviceTransport(Protocol):
    """One Bluetooth LE connection to one tracker (read and subscribe only)."""

    @property
    def is_connected(self) -> bool:
        """Whether the link is currently up."""
        ...

    def set_disconnected_callback(self, callback: DisconnectCallback | None) -> None:
        """Register (or clear) the callback invoked when the link drops unexpectedly."""
        ...

    async def connect(self) -> None:
        """Open the connection.

        Raises:
            BleConnectionError: If the device cannot be reached.
        """
        ...

    async def disconnect(self) -> None:
        """Close the connection (idempotent, never raises for an already closed link)."""
        ...

    async def discover(self) -> list[GattService]:
        """Return the GATT services of the connected device.

        Raises:
            BleConnectionError: If discovery fails.
        """
        ...

    async def read(self, characteristic_uuid: str) -> bytes:
        """Read a characteristic.

        Raises:
            BleConnectionError: If the read fails or the link is down.
        """
        ...

    async def start_notify(self, characteristic_uuid: str, callback: NotificationCallback) -> None:
        """Subscribe to notifications/indications of a characteristic.

        Raises:
            BleConnectionError: If subscribing fails.
        """
        ...

    async def stop_notify(self, characteristic_uuid: str) -> None:
        """Cancel a subscription (idempotent)."""
        ...


class TransportFactory(Protocol):
    """Creates a fresh transport for a device address (one per connection attempt)."""

    def create(self, address: str) -> DeviceTransport:
        """Return a new, unconnected transport for ``address``."""
        ...
