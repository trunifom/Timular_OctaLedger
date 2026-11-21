"""The cube's button and the low-battery warning (AP-37), all with synthetic data."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from octaledger.agent.supervisor import DeviceStatus
from octaledger.application.battery_watch import BatteryWatch
from octaledger.application.device_service import DeviceService
from octaledger.application.tracking_service import Outcome, TrackingService
from octaledger.core.errors import ConfigurationError, NotFoundError, ProtocolError, ValidationError
from octaledger.core.settings import NotificationSettings
from octaledger.domain.attention import AttentionStatus
from octaledger.domain.models import ButtonPress, Device, EventKind, RawEvent
from octaledger.domain.state_machine import ConnectionState
from octaledger.infrastructure.ble.fake import FakeTransportFactory, default_services
from octaledger.infrastructure.ble.protocol import (
    BUTTON_CHARACTERISTIC_UUID,
    ORIENTATION_CHARACTERISTIC_UUID,
    GattCharacteristic,
    GattService,
    decode_button_payload,
    discover_capabilities,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from tests.unit.test_supervisor import Env, env, finish, run, start_ready, wait_until  # noqa: F401

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
M = timedelta(minutes=1)


# ---------------------------------------------------------------------- protocol


def test_button_payload_decodes_short_and_long() -> None:
    assert decode_button_payload(b"\x00").value == "short"
    assert decode_button_payload(b"\x01").value == "long"


@pytest.mark.parametrize("payload", [b"", b"\x02", b"\x00\x00", b"\xff"])
def test_button_payload_rejects_anything_else_with_the_raw_bytes(payload: bytes) -> None:
    with pytest.raises(ProtocolError, match="raw=0x"):
        decode_button_payload(payload)


def test_capability_detection_finds_the_button_in_any_service() -> None:
    assert not discover_capabilities(default_services()).has_button
    assert discover_capabilities(default_services(with_button=True)).has_button
    only_read = default_services()
    only_read.append(
        GattService("1234", (GattCharacteristic(BUTTON_CHARACTERISTIC_UUID, frozenset({"read"})),))
    )
    assert not discover_capabilities(only_read).has_button  # nothing to subscribe to


def test_a_button_event_needs_a_valid_detail() -> None:
    kwargs: dict[str, Any] = {"device_id": "d" * 32, "sequence": 0, "connection_id": "c" * 32}
    assert RawEvent(kind=EventKind.BUTTON, detail="long", **kwargs).detail == "long"
    with pytest.raises(ValidationError):
        RawEvent(kind=EventKind.BUTTON, detail="double", **kwargs)
    with pytest.raises(ValidationError):
        RawEvent(kind=EventKind.BUTTON, **kwargs)


# --------------------------------------------------------------- agent (simulator)


def button_factory() -> FakeTransportFactory:
    return FakeTransportFactory(
        services=default_services(with_button=True),
        values={ORIENTATION_CHARACTERISTIC_UUID: b"\x01"},
    )


def test_a_press_in_the_simulator_becomes_a_stored_event(env: Env) -> None:  # noqa: F811
    async def scenario() -> None:
        fac = button_factory()
        worker, task = await start_ready(env, fac)
        fac.last.press_button(b"\x00")
        await wait_until(lambda: EventKind.BUTTON in env.kinds())
        await finish(worker, task)

    run(scenario())
    (event,) = [e for e in env.events() if e.kind is EventKind.BUTTON]
    assert event.detail == "short" and event.raw_value is None


def test_a_bouncing_press_counts_once_but_short_and_long_are_separate(env: Env) -> None:  # noqa: F811
    async def scenario() -> None:
        fac = button_factory()
        worker, task = await start_ready(env, fac)
        for payload in (b"\x00", b"\x00", b"\x01"):
            fac.last.press_button(payload)
        await wait_until(lambda: env.kinds().count(EventKind.BUTTON) == 2)
        await asyncio.sleep(0.05)
        await finish(worker, task)

    run(scenario())
    pressed = sorted(
        (e for e in env.events() if e.kind is EventKind.BUTTON), key=lambda e: e.sequence
    )
    assert [e.detail for e in pressed] == ["short", "long"]  # equal timestamps: use the sequence


def test_an_unknown_button_packet_is_a_diagnostic_event(env: Env) -> None:  # noqa: F811
    async def scenario() -> None:
        fac = button_factory()
        worker, task = await start_ready(env, fac)
        fac.last.press_button(b"\x07")
        await wait_until(lambda: EventKind.INVALID in env.kinds())
        await finish(worker, task)

    run(scenario())
    assert any("raw=0x07" in str(e.detail) for e in env.events())


def test_a_cube_without_a_button_works_as_before(env: Env) -> None:  # noqa: F811
    async def scenario() -> None:
        fac = FakeTransportFactory(values={ORIENTATION_CHARACTERISTIC_UUID: b"\x01"})
        worker, task = await start_ready(env, fac)
        with pytest.raises(Exception, match="button"):
            fac.last.press_button(b"\x00")
        await finish(worker, task)

    run(scenario())


# ------------------------------------------------------------------ the actions


def button(env: Env, press: str, minutes: float) -> RawEvent:  # noqa: F811
    return RawEvent(
        device_id=env.device_id,
        kind=EventKind.BUTTON,
        sequence=0,
        connection_id="c1",
        detail=press,
        received_at=T0 + timedelta(minutes=minutes),
    )


def devices(env: Env) -> DeviceService:  # noqa: F811
    return DeviceService(env.storage)


def clocked(env: Env) -> TrackingService:  # noqa: F811
    return TrackingService(env.storage, clock=lambda: T0 + 60 * M)


def start_face(env: Env, svc: TrackingService, face_value: int = 1) -> None:  # noqa: F811
    svc.record_event(
        RawEvent(
            device_id=env.device_id,
            kind=EventKind.FACE_CHANGE,
            sequence=0,
            connection_id="c1",
            raw_value=face_value,
            received_at=T0,
        )
    )


def test_without_an_assignment_a_press_does_nothing(env: Env) -> None:  # noqa: F811
    svc = clocked(env)
    start_face(env, svc)
    assert svc.record_event(button(env, "short", 10)).outcome is Outcome.STORED
    assert env.sessions()[0].is_running


def test_stop_ends_the_running_entry(env: Env) -> None:  # noqa: F811
    svc = clocked(env)
    devices(env).set_button(env.device_id, "long", "stop")
    start_face(env, svc)
    assert svc.record_event(button(env, "long", 10)).outcome is Outcome.ENDED
    assert env.sessions()[0].ended_at == T0 + 10 * M
    assert svc.record_event(button(env, "long", 11)).outcome is Outcome.STORED  # nothing running


def test_pause_and_resume_alternate(env: Env) -> None:  # noqa: F811
    svc = clocked(env)
    devices(env).set_button(env.device_id, "short", "pause_resume")
    start_face(env, svc)
    assert svc.record_event(button(env, "short", 10)).outcome is Outcome.ENDED
    assert svc.status().paused
    assert svc.record_event(button(env, "short", 20)).outcome is Outcome.STARTED
    first, second = env.sessions()
    assert first.ended_at == T0 + 10 * M and second.started_at == T0 + 20 * M
    assert first.activity_id == second.activity_id and not svc.status().paused


def test_pause_resume_with_nothing_to_resume_is_ignored(env: Env) -> None:  # noqa: F811
    svc = clocked(env)
    devices(env).set_button(env.device_id, "short", "pause_resume")
    assert svc.record_event(button(env, "short", 5)).outcome is Outcome.STORED


def test_start_last_restarts_the_latest_activity(env: Env) -> None:  # noqa: F811
    svc = clocked(env)
    devices(env).set_button(env.device_id, "short", "start_last")
    assert svc.record_event(button(env, "short", 1)).outcome is Outcome.STORED  # no history
    start_face(env, svc, 2)
    svc.stop(T0 + 5 * M)
    assert svc.record_event(button(env, "short", 30)).outcome is Outcome.STARTED
    assert env.sessions()[-1].activity_id == env.code
    assert svc.record_event(button(env, "short", 31)).outcome is Outcome.CONTINUED


def test_only_the_active_device_changes_time(env: Env) -> None:  # noqa: F811
    svc = clocked(env)
    devices(env).set_button(env.device_id, "long", "stop")
    start_face(env, svc)
    with env.storage.transaction() as repos:
        repos.state.delete("active_device")
    assert svc.record_event(button(env, "long", 10)).outcome is Outcome.STORED
    assert env.sessions()[0].is_running


def test_assignments_validate_and_can_be_cleared(env: Env) -> None:  # noqa: F811
    service = devices(env)
    assert service.set_button(env.device_id, "short", "stop") == {"short": "stop", "long": None}
    assert service.set_button(env.device_id, "short", "none") == {"short": None, "long": None}
    for press, action in (("double", "stop"), ("short", "explode")):
        with pytest.raises(ValidationError):
            service.set_button(env.device_id, press, action)
    with pytest.raises(NotFoundError):
        service.get_buttons("0" * 32)


def test_the_new_event_kind_is_accepted_by_the_database(tmp_path: Path) -> None:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    with storage.transaction() as repos:
        device = repos.devices.add(Device(alias="A"))
        repos.events.add(
            RawEvent(
                device_id=device.id,
                kind=EventKind.BUTTON,
                sequence=0,
                connection_id="c" * 32,
                detail="short",
            )
        )
        repos.buttons.set(device.id, ButtonPress.LONG, None)  # clearing nothing is fine
        assert repos.events.count(device.id) == 1


# ----------------------------------------------------------------------- battery


def status(device_id: str, battery: int | None) -> DeviceStatus:
    return DeviceStatus(
        device_id=device_id,
        state=ConnectionState.READY,
        connection_id=None,
        attempt=0,
        last_error=None,
        last_value=None,
        last_event_at=None,
        battery_percent=battery,
        dropped_values=0,
        duplicates_ignored=0,
    )


class BatteryEnv:
    def __init__(self, env: Env, limit: int = 20) -> None:  # noqa: F811
        self.env = env
        self.level: int | None = 80
        self.limit = limit
        self.watch = BatteryWatch(
            env.storage,
            lambda: [status(env.device_id, self.level)],
            lambda: NotificationSettings(battery_warning_percent=self.limit),
            lambda _id: "Büro",
            clock=lambda: T0,
        )

    def open_items(self) -> list[Any]:
        with self.env.storage.read() as repos:
            return repos.attention.list_open()


def test_a_low_battery_is_reported_once(env: Env) -> None:  # noqa: F811
    b = BatteryEnv(env)
    assert b.watch.check() == []
    b.level = 15
    (item,) = b.watch.check()
    assert item.kind.value == "reminder" and item.payload["percent"] == 15
    assert b.watch.check() == [] and len(b.open_items()) == 1


def test_it_warns_again_only_after_a_charge(env: Env) -> None:  # noqa: F811
    b = BatteryEnv(env)
    b.level = 10
    assert len(b.watch.check()) == 1
    with env.storage.transaction() as repos:  # the user acknowledged the first warning
        for item in repos.attention.list_open():
            repos.attention.close(item.id, AttentionStatus.DISMISSED, "dismissed", T0)
    b.level = 22  # inside the hysteresis band: still the same discharge cycle
    assert b.watch.check() == []
    b.level = 60  # charged
    b.watch.check()
    b.level = 10
    assert len(b.watch.check()) == 1  # a new cycle warns again


def test_zero_switches_the_warning_off_and_unknown_levels_are_ignored(env: Env) -> None:  # noqa: F811
    b = BatteryEnv(env, limit=0)
    b.level = 1
    assert b.watch.check() == []
    b.limit = 20
    b.level = None
    assert b.watch.check() == []


def test_battery_setting_is_validated() -> None:
    assert NotificationSettings().battery_warning_percent == 20
    with pytest.raises(ConfigurationError):
        NotificationSettings(battery_warning_percent=95)
