"""Stub-based tests for the Bleak scanner and transport (no radio, no hardware)."""

import asyncio
from collections.abc import Callable, Coroutine
from types import SimpleNamespace
from typing import Any, TypeVar

import pytest
from bleak.exc import BleakError

from octaledger.core.errors import BleConnectionError, ValidationError
from octaledger.infrastructure.ble import client as client_module
from octaledger.infrastructure.ble.client import BleakTransport, BleakTransportFactory
from octaledger.infrastructure.ble.protocol import (
    ORIENTATION_CHARACTERISTIC_UUID,
    ORIENTATION_SERVICE_UUID,
    discover_capabilities,
)
from octaledger.infrastructure.ble.scanner import ScanResult, scan, sort_results

T = TypeVar("T")


def run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# ------------------------------------------------------------------------------ scanner


def adv(name: str | None, rssi: int | None, uuids: list[str]) -> Any:
    return SimpleNamespace(local_name=name, rssi=rssi, service_uuids=uuids)


def fake_discover(found: dict[str, tuple[Any, Any]]) -> Callable[..., Any]:
    async def discover(**_kwargs: Any) -> dict[str, tuple[Any, Any]]:
        return found

    return discover


def test_scan_flags_candidates_and_sorts_them_first() -> None:
    found = {
        "AA": (SimpleNamespace(name="Kopfhörer"), adv(None, -40, [])),
        "BB": (SimpleNamespace(name=None), adv("ZEI", -70, [ORIENTATION_SERVICE_UUID.upper()])),
        "CC": (SimpleNamespace(name=None), adv("Weit weg", -90, [ORIENTATION_SERVICE_UUID])),
        "DD": (SimpleNamespace(name="Namenlos"), adv(None, None, [])),
    }
    results = run(scan(2.0, discover=fake_discover(found)))
    assert [r.address for r in results] == ["BB", "CC", "AA", "DD"]  # candidates, then signal
    assert results[0].is_candidate and results[0].name == "ZEI"
    assert not results[2].is_candidate and results[2].name == "Kopfhörer"  # device name fallback
    assert results[3].rssi is None


def test_nothing_is_filtered_out() -> None:
    found = {f"X{i}": (SimpleNamespace(name=f"d{i}"), adv(None, -50, [])) for i in range(5)}
    assert len(run(scan(2.0, discover=fake_discover(found)))) == 5


def test_empty_scan() -> None:
    assert run(scan(2.0, discover=fake_discover({}))) == []


@pytest.mark.parametrize("timeout", [0.5, 31, -1])
def test_scan_timeout_validated(timeout: float) -> None:
    with pytest.raises(ValidationError):
        run(scan(timeout, discover=fake_discover({})))


@pytest.mark.parametrize(
    "error", [BleakError("Bluetooth off"), OSError("no adapter"), TimeoutError()]
)
def test_scan_failures_become_ble_connection_error(error: Exception) -> None:
    async def failing(**_kwargs: Any) -> dict[str, tuple[Any, Any]]:
        raise error

    with pytest.raises(BleConnectionError) as info:
        run(scan(2.0, discover=failing))
    assert "Bluetooth" in info.value.user_message
    assert info.value.__cause__ is error


def test_labels_and_sort_stability() -> None:
    named = ScanResult("A", "ZEI", -60, (), True)
    unnamed = ScanResult("B", None, None, (), False)
    assert named.label == "ZEI (-60 dBm)" and unnamed.label == "Unbenanntes Gerät"
    assert sort_results([unnamed, named]) == [named, unnamed]


def test_tracker_is_recognised_by_name_even_without_the_service_and_sorted_first() -> None:
    """A tracker may announce its services only after connecting: the name is a hint."""
    named = ScanResult("A", "Timeular Tra", -52, (), False)
    zei = ScanResult("B", "ZEI", -90, (), False)
    other = ScanResult("C", "JLab GO Pods", -40, (), False)
    unnamed = ScanResult("D", None, -30, (), False)
    service = ScanResult("E", None, -99, ("c7e70010-c847-11e6-8175-8c89a55d403c",), True)
    assert named.looks_like_tracker and zei.looks_like_tracker and service.looks_like_tracker
    assert not other.looks_like_tracker and not unnamed.looks_like_tracker
    assert sort_results([other, unnamed, zei, named, service]) == [
        service,
        named,
        zei,
        unnamed,
        other,
    ]


# ------------------------------------------------------------------------------- client


class StubClient:
    """Minimal stand-in for ``bleak.BleakClient``."""

    instances: list["StubClient"] = []
    fail_connect: Exception | None = None

    def __init__(self, address: str, disconnected_callback: Callable[[Any], None], timeout: float):
        self.address = address
        self.disconnected_callback = disconnected_callback
        self.timeout = timeout
        self.is_connected = False
        self.notify_callbacks: dict[str, Callable[[Any, bytearray], None]] = {}
        self.fail_read: Exception | None = None
        self.fail_subscribe: Exception | None = None
        self.fail_disconnect: Exception | None = None
        self.stopped: list[str] = []
        char = SimpleNamespace(uuid=ORIENTATION_CHARACTERISTIC_UUID, properties=["Read", "Notify"])
        self.services = [SimpleNamespace(uuid=ORIENTATION_SERVICE_UUID, characteristics=[char])]
        StubClient.instances.append(self)

    async def connect(self) -> None:
        if StubClient.fail_connect is not None:
            raise StubClient.fail_connect
        self.is_connected = True

    async def disconnect(self) -> None:
        if self.fail_disconnect is not None:
            raise self.fail_disconnect
        self.is_connected = False

    async def read_gatt_char(self, uuid: str) -> bytearray:
        if self.fail_read is not None:
            raise self.fail_read
        return bytearray(b"\x03")

    async def start_notify(self, uuid: str, callback: Callable[[Any, bytearray], None]) -> None:
        if self.fail_subscribe is not None:
            raise self.fail_subscribe
        self.notify_callbacks[uuid] = callback

    async def stop_notify(self, uuid: str) -> None:
        self.stopped.append(uuid)

    def lose_link(self) -> None:
        self.is_connected = False
        self.disconnected_callback(self)


@pytest.fixture(autouse=True)
def _stub_bleak(monkeypatch: pytest.MonkeyPatch) -> None:
    StubClient.instances = []
    StubClient.fail_connect = None
    monkeypatch.setattr(client_module, "BleakClient", StubClient)


def test_connect_discover_read_notify_roundtrip() -> None:
    transport = BleakTransport("ADDR", timeout=3.0)
    received: list[bytes] = []

    async def scenario() -> None:
        assert not transport.is_connected
        await transport.connect()
        assert transport.is_connected
        caps = discover_capabilities(await transport.discover())
        assert (
            caps.orientation_mode == "notify" and caps.can_read_orientation
        )  # "Notify" lower-cased
        assert await transport.read(ORIENTATION_CHARACTERISTIC_UUID) == b"\x03"
        await transport.start_notify(ORIENTATION_CHARACTERISTIC_UUID, received.append)
        stub = StubClient.instances[0]
        stub.notify_callbacks[ORIENTATION_CHARACTERISTIC_UUID](None, bytearray(b"\x05"))
        await transport.stop_notify(ORIENTATION_CHARACTERISTIC_UUID)
        await transport.disconnect()

    run(scenario())
    stub = StubClient.instances[0]
    assert (stub.address, stub.timeout) == ("ADDR", 3.0)
    assert received == [b"\x05"] and isinstance(received[0], bytes)
    assert stub.stopped == [ORIENTATION_CHARACTERISTIC_UUID]


@pytest.mark.parametrize("error", [BleakError("not found"), OSError("adapter"), TimeoutError()])
def test_connect_failures_are_translated(error: Exception) -> None:
    StubClient.fail_connect = error
    with pytest.raises(BleConnectionError) as info:
        run(BleakTransport("ADDR").connect())
    assert info.value.details["stage"] == "connect" and info.value.__cause__ is error


def test_operations_require_connection() -> None:
    transport = BleakTransport("ADDR")

    async def scenario() -> None:
        for op in (
            transport.discover(),
            transport.read(ORIENTATION_CHARACTERISTIC_UUID),
            transport.start_notify(ORIENTATION_CHARACTERISTIC_UUID, lambda _b: None),
        ):
            with pytest.raises(BleConnectionError):
                await op
        await transport.stop_notify(ORIENTATION_CHARACTERISTIC_UUID)  # silently fine
        await transport.disconnect()  # idempotent without a client

    run(scenario())


def test_read_and_subscribe_failures_are_translated() -> None:
    transport = BleakTransport("ADDR")

    async def scenario() -> None:
        await transport.connect()
        stub = StubClient.instances[0]
        stub.fail_read = BleakError("gatt error")
        with pytest.raises(BleConnectionError) as read_info:
            await transport.read(ORIENTATION_CHARACTERISTIC_UUID)
        assert read_info.value.details["stage"] == "read"
        stub.fail_subscribe = OSError("cccd")
        with pytest.raises(BleConnectionError) as sub_info:
            await transport.start_notify(ORIENTATION_CHARACTERISTIC_UUID, lambda _b: None)
        assert sub_info.value.details["stage"] == "subscribe"

    run(scenario())


def test_unexpected_link_loss_fires_callback_but_deliberate_disconnect_does_not() -> None:
    losses: list[int] = []

    async def scenario() -> None:
        lossy = BleakTransport("ADDR")
        lossy.set_disconnected_callback(lambda: losses.append(1))
        await lossy.connect()
        StubClient.instances[0].lose_link()
        assert not lossy.is_connected

        calm = BleakTransport("ADDR")
        calm.set_disconnected_callback(lambda: losses.append(2))
        await calm.connect()
        stub = StubClient.instances[1]
        await calm.disconnect()
        stub.disconnected_callback(stub)  # Bleak reports the (deliberate) close afterwards
        await calm.disconnect()

    run(scenario())
    assert losses == [1]


def test_failing_disconnect_is_swallowed() -> None:
    transport = BleakTransport("ADDR")

    async def scenario() -> None:
        await transport.connect()
        StubClient.instances[0].fail_disconnect = BleakError("already gone")
        await transport.disconnect()
        assert not transport.is_connected

    run(scenario())


def test_factory_creates_independent_transports() -> None:
    factory = BleakTransportFactory(timeout=7.0)
    first, second = factory.create("A"), factory.create("A")
    assert first is not second

    async def scenario() -> None:
        await first.connect()
        await second.connect()

    run(scenario())
    assert {s.timeout for s in StubClient.instances} == {7.0}
