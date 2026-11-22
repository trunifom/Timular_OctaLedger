"""The data sheet: wording of values, the read-out on the link, service and API (AP-56)."""

import asyncio
from pathlib import Path

import pytest

from octaledger.core.errors import BleConnectionError, NotFoundError, ValidationError
from octaledger.domain.readout import (
    ACCELEROMETER,
    DFU_SERVICE,
    Reading,
    from_json,
    interpret,
    is_forbidden,
    name_of,
    readable,
    rows,
    service_name,
    short_uuid,
    to_json,
)
from octaledger.infrastructure.ble.fake import FakeTransportFactory, default_services
from octaledger.infrastructure.ble.protocol import GattCharacteristic, GattService
from tests.conftest import FakeAgent, RunningApi
from tests.unit.test_supervisor import (
    ORIENT,
    Env,
    factory,
    finish,
    run,
    start_ready,
)


@pytest.fixture
def supervisor_env(tmp_path: Path) -> Env:
    return Env(tmp_path)


ACCEL_SERVICE = "c7e70010-c847-11e6-8175-8c89a55d403c"
VENDOR = "c7e70020-c847-11e6-8175-8c89a55d403c"


def r(uuid: str, raw: bytes | None, props: tuple[str, ...] = ("read",), **kw: str) -> Reading:
    return Reading("svc", uuid, props, None if raw is None else raw.hex(), **kw)


# ----------------------------------------------------------------------------- wording


def test_short_uuids() -> None:
    assert short_uuid("00002a19-0000-1000-8000-00805f9b34fb") == "2a19"
    assert short_uuid("C7E70012-C847-11E6-8175-8C89A55D403C") == "c7e70012"
    assert (
        short_uuid("12345678-1234-1234-1234-123456789abc") == "12345678-1234-1234-1234-123456789abc"
    )
    assert name_of("00002a24-0000-1000-8000-00805f9b34fb") == "Modell"
    assert name_of("12345678-1234-1234-1234-123456789abc") == "Unbekannt"
    assert service_name("0000180f-0000-1000-8000-00805f9b34fb") == "Batterie"


@pytest.mark.parametrize(
    ("uuid", "raw", "text"),
    [
        ("00002a19-0000-1000-8000-00805f9b34fb", bytes([62]), "62 %"),
        ("00002a19-0000-1000-8000-00805f9b34fb", bytes([200]), "Länge oder Wert unerwartet"),
        ("00002a24-0000-1000-8000-00805f9b34fb", b"Tracker_001\x00", "Tracker_001"),
        ("00002a07-0000-1000-8000-00805f9b34fb", bytes([0xF8]), "-8 dBm"),
        (ORIENT, bytes([0]), "0 (neutral / Halterung)"),
        (ORIENT, bytes([5]), "Seite 5"),
        (ORIENT, bytes([13]), "Wert 13 (nicht zuordenbar)"),
        (ORIENT, bytes([1, 2]), "Länge unerwartet"),
        ("c7e70021-c847-11e6-8175-8c89a55d403c", bytes([1]), "langer Druck"),
    ],
)
def test_known_values_are_worded(uuid: str, raw: bytes, text: str) -> None:
    assert interpret(r(uuid, raw)) == text


def test_the_accelerometer_gets_only_its_length_never_a_deutung() -> None:
    meaning = interpret(r(ACCELEROMETER, bytes(6)))
    assert meaning is not None and meaning.startswith("6 Byte") and "nicht bestätigt" in meaning
    assert "x=" not in meaning and "g" not in meaning.split("(")[0]


def test_unknown_or_unread_values_are_not_interpreted() -> None:
    assert interpret(r("12345678-1234-1234-1234-123456789abc", b"\x01\x02")) is None
    assert interpret(r(ORIENT, None)) is None


def test_rows_say_what_was_not_touched() -> None:
    table = rows(
        [
            r(ORIENT, bytes([3])),
            r("c7e70022-c847-11e6-8175-8c89a55d403c", None, ("write",)),
            r("c7e70001-c847-11e6-8175-8c89a55d403c", None, ("write",), error="wird nie gelesen"),
        ]
    )
    assert table[0]["Deutung"] == "Seite 3" and table[0]["Länge"] == 1
    assert table[1]["Hinweis"] == "nicht lesbar, nicht angefasst" and table[1]["Wert (hex)"] == ""
    assert table[2]["Hinweis"] == "wird nie gelesen"


def test_the_stored_form_round_trips_and_skips_garbage() -> None:
    readings = [r(ORIENT, bytes([3])), r(ORIENT, None, ("write",), error="x")]
    assert from_json(to_json(readings)) == readings
    garbage = [{"service": "s"}, {"service": "s", "uuid": "u", "raw_hex": "zz"}, *to_json(readings)]
    assert from_json(garbage) == readings


def test_the_firmware_update_service_is_forbidden_and_only_readable_is_read() -> None:
    assert is_forbidden(DFU_SERVICE.upper()) and not is_forbidden(ACCEL_SERVICE)
    assert readable(("read", "notify")) and not readable(("write", "notify"))


# ------------------------------------------------------------- the read-out on the link


def vendor_services() -> list[GattService]:
    return [
        *default_services(with_button=True),
        GattService(
            ACCEL_SERVICE,
            (GattCharacteristic(ACCELEROMETER, frozenset({"read"})),),
        ),
        GattService(
            VENDOR,
            (GattCharacteristic("c7e70022-c847-11e6-8175-8c89a55d403c", frozenset({"write"})),),
        ),
        GattService(
            DFU_SERVICE,
            (
                GattCharacteristic(
                    "c7e70001-c847-11e6-8175-8c89a55d403c", frozenset({"write", "notify", "read"})
                ),
            ),
        ),
    ]


def test_the_data_sheet_reads_readable_values_and_touches_nothing_else(supervisor_env: Env) -> None:
    async def scenario() -> None:
        fac = FakeTransportFactory(
            services=vendor_services(),
            values={ORIENT: bytes([4]), ACCELEROMETER: bytes(6)},
        )
        worker, task = await start_ready(supervisor_env, fac)
        readings = await worker.read_out("datasheet")
        by_uuid = {x.uuid: x for x in readings}
        assert by_uuid[ORIENT].raw_hex == "04"
        assert by_uuid[ACCELEROMETER].length == 6
        assert by_uuid["c7e70022-c847-11e6-8175-8c89a55d403c"].raw_hex is None  # write-only
        dfu = by_uuid["c7e70001-c847-11e6-8175-8c89a55d403c"]
        assert dfu.raw_hex is None and "nie gelesen" in (dfu.error or "")  # even if it said "read"
        assert worker.state.value == "ready"  # the cube kept working
        await finish(worker, task)

    run(scenario())


def test_an_unreadable_characteristic_is_reported_not_fatal(supervisor_env: Env) -> None:
    async def scenario() -> None:
        fac = factory(2, services=vendor_services())  # most readable ones have no value in the fake
        worker, task = await start_ready(supervisor_env, fac)
        readings = await worker.read_out("datasheet")
        broken = [x for x in readings if x.error and "nie gelesen" not in x.error]
        assert broken  # the fake refuses unknown characteristics: reported per characteristic
        assert any(x.raw_hex for x in readings)
        await finish(worker, task)

    run(scenario())


def test_the_accelerometer_recording_collects_raw_samples(supervisor_env: Env) -> None:
    async def scenario() -> None:
        fac = FakeTransportFactory(
            services=vendor_services(), values={ORIENT: bytes([4]), ACCELEROMETER: bytes(6)}
        )
        worker, task = await start_ready(supervisor_env, fac)
        samples = await worker.read_out("accelerometer", seconds=0.3, interval_ms=50)
        assert 3 <= len(samples) <= 8 and {x.uuid for x in samples} == {ACCELEROMETER}
        assert all(x.length == 6 for x in samples)
        await finish(worker, task)

    run(scenario())


def test_a_cube_without_a_readable_accelerometer_says_so(supervisor_env: Env) -> None:
    async def scenario() -> None:
        worker, task = await start_ready(supervisor_env, factory(1))
        with pytest.raises(BleConnectionError) as caught:
            await worker.read_out("accelerometer", seconds=0.1, interval_ms=50)
        assert "Beschleunigungssensor" in caught.value.user_message
        await finish(worker, task)

    run(scenario())


def test_a_read_out_needs_a_ready_cube(supervisor_env: Env) -> None:
    async def scenario() -> None:
        worker = supervisor_env.worker(factory(1))
        with pytest.raises(BleConnectionError):
            await worker.read_out("datasheet")

    run(scenario())


def test_the_transport_has_no_write_method() -> None:
    from octaledger.infrastructure.ble.transport import DeviceTransport

    assert not any("write" in name for name in dir(DeviceTransport))
    assert asyncio  # (the module is used by the scenarios above)


# ---------------------------------------------------------------------- service and API


def test_the_api_stores_lists_shows_and_deletes_read_outs(api_server: RunningApi) -> None:
    agent = FakeAgent()
    api_server.context.agent = agent
    agent.readings = [
        Reading(ACCEL_SERVICE, ORIENT, ("notify", "read"), "03"),
        Reading(VENDOR, "c7e70022-c847-11e6-8175-8c89a55d403c", ("write",)),
    ]
    cube = api_server.client.register_device("Büro")
    api_server.client.set_device_address(cube["id"], "AA:BB")
    with pytest.raises(BleConnectionError):  # not connected yet
        api_server.client.read_out(cube["id"])
    api_server.client.connect_device(cube["id"])
    sheet = api_server.client.read_out(cube["id"])
    assert sheet["kind"] == "datasheet" and sheet["count"] == 2
    first = sheet["readings"][0]
    assert first["meaning"] == "Seite 3" and first["name"] == "Lage (aktive Seite)"
    assert sheet["readings"][1]["raw_hex"] is None
    listed = api_server.client.snapshots(cube["id"])
    assert [s["id"] for s in listed] == [sheet["id"]] and "readings" not in listed[0]
    assert api_server.client.snapshot(sheet["id"])["count"] == 2
    api_server.client.delete_snapshot(sheet["id"])
    assert api_server.client.snapshots(cube["id"]) == []
    with pytest.raises(NotFoundError):
        api_server.client.snapshot(sheet["id"])


def test_recording_limits_are_enforced(api_server: RunningApi) -> None:
    agent = FakeAgent()
    api_server.context.agent = agent
    cube = api_server.client.register_device("Büro")
    api_server.client.set_device_address(cube["id"], "AA:BB")
    api_server.client.connect_device(cube["id"])
    for seconds, interval in ((4, 500), (31, 500), (10, 100), (10, 2500)):
        with pytest.raises(ValidationError):
            api_server.client.read_out(cube["id"], "accelerometer", seconds, interval)
    assert agent.read_calls == []  # nothing was asked from the cube


def test_only_the_newest_twenty_snapshots_are_kept(api_server: RunningApi, tmp_path: Path) -> None:
    agent = FakeAgent()
    api_server.context.agent = agent
    cube = api_server.client.register_device("Büro")
    api_server.client.set_device_address(cube["id"], "AA:BB")
    api_server.client.connect_device(cube["id"])
    for _ in range(23):
        api_server.client.read_out(cube["id"])
    assert len(api_server.client.snapshots(cube["id"])) == 20


def test_snapshots_belong_to_the_backup(api_server: RunningApi) -> None:
    agent = FakeAgent()
    api_server.context.agent = agent
    agent.readings = [Reading(ACCEL_SERVICE, ORIENT, ("read",), "05")]
    cube = api_server.client.register_device("Büro")
    api_server.client.set_device_address(cube["id"], "AA:BB")
    api_server.client.connect_device(cube["id"])
    taken = api_server.client.read_out(cube["id"])
    text = api_server.context.exports.create_backup_text()
    api_server.context.exports.restore_backup_text(text)
    again = api_server.client.snapshot(taken["id"])
    assert again["readings"][0]["raw_hex"] == "05"
