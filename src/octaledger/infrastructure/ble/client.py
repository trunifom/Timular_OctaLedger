"""Bleak connection lifecycle on the agent event loop.

Responsibility
--------------
:class:`BleakTransport` implements :class:`~octaledger.infrastructure.ble.transport.DeviceTransport`
on top of Bleak. It is intentionally thin: translate between Bleak and the neutral types, map
every Bleak/OS failure to :class:`BleConnectionError`, and expose **no write operation**.

Rules from the architecture (``docs/ARCHITEKTUR.md``)
------------------------------------------------------
* All operations of a connection run on **one** long-lived asyncio loop (Bleak requires the
  related calls to share a running loop).
* A new :class:`BleakTransport` is created for every connection cycle; old instances are
  never reused, so late callbacks of an old cycle cannot touch a new one.
* Bleak callbacks are short and synchronous: they only forward bytes / the loss signal.

Hardware note: this class is exercised by stub-based unit tests only. Behaviour with real
trackers (parallel connections, wake-up, range, Windows adapters) must be verified manually
(``tests/hardware`` and ``docs/TESTPLAN.md``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

from bleak import BleakClient
from bleak.exc import BleakError

from octaledger.core.errors import BleConnectionError
from octaledger.infrastructure.ble.protocol import GattCharacteristic, GattService
from octaledger.infrastructure.ble.transport import (
    DeviceTransport,
    DisconnectCallback,
    NotificationCallback,
)

logger = logging.getLogger(__name__)

#: Seconds Bleak may take to establish a connection.
CONNECT_TIMEOUT_SECONDS: Final = 15.0
#: Failures of the Bluetooth stack that must become a :class:`BleConnectionError`.
_BLE_FAILURES: Final = (BleakError, OSError, TimeoutError, asyncio.TimeoutError)


class BleakTransport:
    """A single Bleak connection to one tracker (read and subscribe only)."""

    def __init__(self, address: str, *, timeout: float = CONNECT_TIMEOUT_SECONDS) -> None:
        """Create an unconnected transport.

        Args:
            address: Platform address/identifier of the device.
            timeout: Connect timeout in seconds.
        """
        self._address = address
        self._timeout = timeout
        self._on_disconnect: DisconnectCallback | None = None
        self._client: Any = None
        self._deliberate_close = False

    # -------------------------------------------------------------------- helpers

    def _handle_disconnect(self, _client: object) -> None:
        """Bleak callback: forward an *unexpected* loss; ignore deliberate disconnects."""
        if self._deliberate_close:
            return
        logger.warning("BLE link lost")
        if self._on_disconnect is not None:
            self._on_disconnect()

    def _require_client(self) -> Any:
        if self._client is None or not self._client.is_connected:
            raise BleConnectionError("Not connected", details={"stage": "not_connected"})
        return self._client

    # --------------------------------------------------------------- DeviceTransport

    @property
    def is_connected(self) -> bool:
        """Whether the link is currently up."""
        return bool(self._client is not None and self._client.is_connected)

    def set_disconnected_callback(self, callback: DisconnectCallback | None) -> None:
        """Register the link-loss callback."""
        self._on_disconnect = callback

    async def connect(self) -> None:
        """Open the connection.

        Raises:
            BleConnectionError: On timeout, out-of-range device, adapter problems ...
        """
        self._deliberate_close = False
        self._client = BleakClient(
            self._address, disconnected_callback=self._handle_disconnect, timeout=self._timeout
        )
        try:
            await self._client.connect()
        except _BLE_FAILURES as exc:
            raise BleConnectionError(
                f"Connect failed: {exc}", details={"stage": "connect"}
            ) from exc
        logger.info("BLE connected")

    async def disconnect(self) -> None:
        """Close the connection; safe to call repeatedly."""
        self._deliberate_close = True
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.disconnect()
        except _BLE_FAILURES as exc:
            # A failing disconnect of an already broken link is not worth failing over.
            logger.debug("Ignoring error while disconnecting: %s", exc)

    async def discover(self) -> list[GattService]:
        """Return the GATT services of the connected device."""
        client = self._require_client()
        try:
            services = client.services
            return [
                GattService(
                    uuid=str(service.uuid),
                    characteristics=tuple(
                        GattCharacteristic(
                            uuid=str(char.uuid),
                            properties=frozenset(str(p).lower() for p in char.properties),
                        )
                        for char in service.characteristics
                    ),
                )
                for service in services
            ]
        except _BLE_FAILURES as exc:
            raise BleConnectionError(
                f"Service discovery failed: {exc}", details={"stage": "discover"}
            ) from exc

    async def read(self, characteristic_uuid: str) -> bytes:
        """Read a characteristic."""
        client = self._require_client()
        try:
            return bytes(await client.read_gatt_char(characteristic_uuid))
        except _BLE_FAILURES as exc:
            raise BleConnectionError(
                f"Read failed: {exc}", details={"stage": "read", "uuid": characteristic_uuid}
            ) from exc

    async def start_notify(self, characteristic_uuid: str, callback: NotificationCallback) -> None:
        """Subscribe to notifications; ``callback`` receives the raw bytes."""
        client = self._require_client()

        def forward(_characteristic: object, data: bytearray) -> None:
            callback(bytes(data))

        try:
            await client.start_notify(characteristic_uuid, forward)
        except _BLE_FAILURES as exc:
            raise BleConnectionError(
                f"Subscribe failed: {exc}", details={"stage": "subscribe"}
            ) from exc

    async def stop_notify(self, characteristic_uuid: str) -> None:
        """Cancel a subscription; errors on an already broken link are ignored."""
        if self._client is None or not self._client.is_connected:
            return
        try:
            await self._client.stop_notify(characteristic_uuid)
        except _BLE_FAILURES as exc:
            logger.debug("Ignoring error while unsubscribing: %s", exc)


class BleakTransportFactory:
    """Creates a fresh :class:`BleakTransport` per connection attempt."""

    def __init__(self, timeout: float = CONNECT_TIMEOUT_SECONDS) -> None:
        """Remember the connect timeout used for every transport."""
        self._timeout = timeout

    def create(self, address: str) -> DeviceTransport:
        """Return a new, unconnected transport for ``address``."""
        return BleakTransport(address, timeout=self._timeout)
