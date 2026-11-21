"""Tests for BLE protocol helpers (capabilities, decoders) and the synthetic FakeTransport."""

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest

from octaledger.core.errors import BleConnectionError, ProtocolError, UnsupportedDeviceError
from octaledger.infrastructure.ble import transport as transport_module
from octaledger.infrastructure.ble.fake import FakeTransport, FakeTransportFactory, default_services
from octaledger.infrastructure.ble.protocol import (
    BATTERY_LEVEL_UUID,
    ORIENTATION_CHARACTERISTIC_UUID,
    ORIENTATION_SERVICE_UUID,
    GattCharacteristic,
    GattService,
    decode_battery_level,
    decode_orientation_payload,
    decode_text,
    discover_capabilities,
    normalize_uuid,
)

T = TypeVar("T")


def run(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion (keeps the tests free of pytest-asyncio)."""
    return asyncio.run(coro)


def orientation_service(
    properties: set[str], uuid: str = ORIENTATION_CHARACTERISTIC_UUID
) -> GattService:
    return GattService(ORIENTATION_SERVICE_UUID, (GattCharacteristic(uuid, frozenset(properties)),))


# ----------------------------------------------------------------------- capabilities


def test_full_capabilities() -> None:
    caps = discover_capabilities(default_services())
    assert caps.orientation_mode == "notify" and caps.can_read_orientation
    assert caps.has_battery and caps.has_model and caps.has_firmware
    assert ORIENTATION_SERVICE_UUID in caps.service_uuids


def test_minimal_device_without_optional_services_is_fine() -> None:
    caps = discover_capabilities(default_services(with_extras=False))
    assert not (caps.has_battery or caps.has_model or caps.has_firmware)


def test_indicate_only_is_accepted_and_notify_preferred() -> None:
    assert discover_capabilities([orientation_service({"indicate"})]).orientation_mode == "indicate"
    both = discover_capabilities([orientation_service({"indicate", "notify", "read"})])
    assert both.orientation_mode == "notify"


def test_without_read_property_initial_value_not_readable() -> None:
    assert not discover_capabilities([orientation_service({"notify"})]).can_read_orientation


def test_uuids_compare_case_insensitively() -> None:
    upper = GattService(
        ORIENTATION_SERVICE_UUID.upper(),
        (GattCharacteristic(ORIENTATION_CHARACTERISTIC_UUID.upper(), frozenset({"NOTIFY"})),),
    )
    assert discover_capabilities([upper]).orientation_mode == "notify"
    assert normalize_uuid("  ABC ") == "abc"


def test_missing_orientation_service_lists_offered_services() -> None:
    other = GattService("0000aaaa-0000-1000-8000-00805f9b34fb", ())
    with pytest.raises(UnsupportedDeviceError) as info:
        discover_capabilities([other])
    assert info.value.details["services"] == ["0000aaaa-0000-1000-8000-00805f9b34fb"]
    assert info.value.error_code == "OL-BLE-003"


def test_missing_characteristic_inside_service() -> None:
    wrong = orientation_service({"notify"}, uuid="c7e70099-c847-11e6-8175-8c89a55d403c")
    with pytest.raises(UnsupportedDeviceError):
        discover_capabilities([wrong])


def test_orientation_without_notify_or_indicate_is_unusable() -> None:
    with pytest.raises(UnsupportedDeviceError) as info:
        discover_capabilities([orientation_service({"read"})])
    assert info.value.details["properties"] == ["read"]


def test_unreadable_battery_is_not_offered() -> None:
    services = [
        orientation_service({"notify"}),
        GattService(
            "0000180f-0000-1000-8000-00805f9b34fb",
            (GattCharacteristic(BATTERY_LEVEL_UUID, frozenset({"notify"})),),  # no read
        ),
    ]
    assert not discover_capabilities(services).has_battery


def test_no_services_at_all() -> None:
    with pytest.raises(UnsupportedDeviceError):
        discover_capabilities([])


# ---------------------------------------------------------------------------- decoders


@pytest.mark.parametrize("value", range(9))
def test_orientation_payload_ok(value: int) -> None:
    assert decode_orientation_payload(bytes([value])) == value


def test_orientation_payload_base_value_ten() -> None:
    assert decode_orientation_payload(b"\x0a") == 0


@pytest.mark.parametrize("payload", [b"", b"\x01\x02", b"\x09", b"\x0b", b"\xff"])
def test_orientation_payload_invalid(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_orientation_payload(payload)


@pytest.mark.parametrize("level", [0, 50, 100])
def test_battery_ok(level: int) -> None:
    assert decode_battery_level(bytes([level])) == level


@pytest.mark.parametrize("payload", [b"", b"\x65", b"\x01\x02"])
def test_battery_invalid(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_battery_level(payload)


def test_text_decoding() -> None:
    assert decode_text(b"ZEI-2\x00\x00") == "ZEI-2"
    assert decode_text("Grüße 1.0 ".encode()) == "Grüße 1.0"


@pytest.mark.parametrize(
    "payload", [b"", b"\x00\x00", b"\xff\xfe", b"a\x01b", b"x" * 101, b"line\nbreak"]
)
def test_text_invalid(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_text(payload)


# ------------------------------------------------------------------------ FakeTransport


def test_connect_discover_read_and_disconnect() -> None:
    fake = FakeTransport()

    async def scenario() -> None:
        assert not fake.is_connected
        await fake.connect()
        assert fake.is_connected
        assert discover_capabilities(await fake.discover()).orientation_mode == "notify"
        assert await fake.read(ORIENTATION_CHARACTERISTIC_UUID) == b"\x00"
        assert decode_battery_level(await fake.read(BATTERY_LEVEL_UUID)) == 87
        await fake.disconnect()
        await fake.disconnect()  # idempotent
        assert not fake.is_connected

    run(scenario())
    assert fake.connect_calls == 1 and fake.disconnect_calls == 2


def test_scripted_connect_failures() -> None:
    fake = FakeTransport()
    fake.fail_next_connects(2, "radio busy")

    async def scenario() -> None:
        for _ in range(2):
            with pytest.raises(BleConnectionError, match="radio busy"):
                await fake.connect()
        await fake.connect()

    run(scenario())
    assert fake.is_connected and fake.connect_calls == 3


def test_notifications_reach_callback_and_update_value() -> None:
    fake = FakeTransport()
    received: list[bytes] = []

    async def scenario() -> None:
        await fake.connect()
        await fake.start_notify(ORIENTATION_CHARACTERISTIC_UUID, received.append)
        assert fake.notify_started
        fake.push(b"\x05")
        fake.push(b"\x02")
        assert await fake.read(ORIENTATION_CHARACTERISTIC_UUID) == b"\x02"
        await fake.stop_notify(ORIENTATION_CHARACTERISTIC_UUID)
        await fake.stop_notify(ORIENTATION_CHARACTERISTIC_UUID)  # idempotent
        assert not fake.notify_started

    run(scenario())
    assert received == [b"\x05", b"\x02"]


def test_push_requires_link_and_subscription() -> None:
    fake = FakeTransport()
    with pytest.raises(BleConnectionError):
        fake.push(b"\x01")

    async def scenario() -> None:
        await fake.connect()
        with pytest.raises(BleConnectionError):  # connected but nobody subscribed
            fake.push(b"\x01")

    run(scenario())


def test_link_drop_calls_callback_once_and_blocks_operations() -> None:
    fake = FakeTransport()
    drops: list[int] = []
    fake.set_disconnected_callback(lambda: drops.append(1))

    async def scenario() -> None:
        await fake.connect()
        await fake.start_notify(ORIENTATION_CHARACTERISTIC_UUID, lambda _p: None)
        fake.drop_link()
        fake.drop_link()  # already down: no second callback
        assert not fake.is_connected and not fake.notify_started
        for operation in (fake.discover(), fake.read(ORIENTATION_CHARACTERISTIC_UUID)):
            with pytest.raises(BleConnectionError):
                await operation
        with pytest.raises(BleConnectionError):
            await fake.start_notify(ORIENTATION_CHARACTERISTIC_UUID, lambda _p: None)

    run(scenario())
    assert drops == [1]


def test_deliberate_disconnect_does_not_fire_loss_callback() -> None:
    fake = FakeTransport()
    drops: list[int] = []
    fake.set_disconnected_callback(lambda: drops.append(1))

    async def scenario() -> None:
        await fake.connect()
        await fake.disconnect()

    run(scenario())
    assert drops == []


def test_read_unknown_characteristic() -> None:
    fake = FakeTransport()

    async def scenario() -> None:
        await fake.connect()
        with pytest.raises(BleConnectionError):
            await fake.read("00000000-0000-1000-8000-00805f9b34fb")

    run(scenario())


def test_custom_values_and_services() -> None:
    fake = FakeTransport(
        services=[orientation_service({"indicate"})],
        values={ORIENTATION_CHARACTERISTIC_UUID.upper(): b"\x07"},
    )

    async def scenario() -> None:
        await fake.connect()
        assert await fake.read(ORIENTATION_CHARACTERISTIC_UUID) == b"\x07"
        assert discover_capabilities(await fake.discover()).orientation_mode == "indicate"

    run(scenario())


def test_connect_delay_is_awaited() -> None:
    fake = FakeTransport(connect_delay=0.05)

    async def scenario() -> float:
        loop = asyncio.get_running_loop()
        started = loop.time()
        await fake.connect()
        return loop.time() - started

    assert run(scenario()) >= 0.04


def test_factory_creates_fresh_instances_and_applies_failures_once() -> None:
    factory = FakeTransportFactory()
    factory.pending_failures = 1
    first = factory.create("AA:BB")
    second = factory.create("AA:BB")
    assert first is not second and factory.last is second and len(factory.created) == 2

    async def scenario() -> None:
        with pytest.raises(BleConnectionError):
            await first.connect()
        await second.connect()  # failures applied only to the first instance

    run(scenario())


# ------------------------------------------------------------------------- safety rule


def test_transport_interface_offers_no_write_operation() -> None:
    """Pflichtenheft section 2: no undocumented BLE writes - impossible by construction."""
    names = {name for name in dir(transport_module.DeviceTransport) if not name.startswith("_")}
    assert not {n for n in names if "write" in n.lower()}
    assert {"connect", "disconnect", "discover", "read", "start_notify", "stop_notify"} <= names
    assert not hasattr(FakeTransport, "write")
