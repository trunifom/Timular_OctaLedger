"""Tests for the agent supervisor using the synthetic FakeTransport and real asyncio timing.

Timings are tiny (tens of milliseconds) but every wait is a bounded poll, never a fixed sleep
that the assertion depends on.
"""

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, TypeVar

import pytest

from octaledger.agent.supervisor import AgentSupervisor, DeviceWorker, SupervisorTuning
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import StorageError, ValidationError
from octaledger.domain.models import Activity, Device, EventKind, Quality
from octaledger.domain.state_machine import ConnectionState
from octaledger.infrastructure.ble.fake import FakeTransport, FakeTransportFactory, default_services
from octaledger.infrastructure.ble.protocol import (
    ORIENTATION_CHARACTERISTIC_UUID,
    ORIENTATION_SERVICE_UUID,
    GattCharacteristic,
    GattService,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

S = ConnectionState
T = TypeVar("T")
ORIENT = ORIENTATION_CHARACTERISTIC_UUID

FAST = SupervisorTuning(
    debounce_ms=30,
    buffer_size=100,
    connect_timeout=1.0,
    backoff_base=0.02,
    backoff_cap=0.05,
    baseline_timeout=0.4,
    shutdown_grace=1.0,
)


def run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def wait_until(predicate: Callable[[], bool], timeout: float = 3.0) -> None:
    """Poll ``predicate`` until true or fail after ``timeout`` seconds."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.005)


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        with self.storage.transaction() as repos:
            device = repos.devices.add(Device(alias="Büro", platform_address="ADDR"))
            self.meeting = repos.activities.add(Activity(name="Meeting")).id
            self.code = repos.activities.add(Activity(name="Code")).id
            repos.mappings.assign(device.id, 1, self.meeting)
            repos.mappings.assign(device.id, 2, self.code)
            repos.state.set("active_device", device.id)
        self.device_id = device.id
        self.tracking = TrackingService(self.storage)

    def events(self) -> list[Any]:
        with self.storage.read() as repos:
            return list(reversed(repos.events.list_for_device(self.device_id)))

    def kinds(self) -> list[EventKind]:
        return [e.kind for e in self.events()]

    def sessions(self) -> list[Any]:
        with self.storage.read() as repos:
            return repos.sessions.list_all()

    def worker(self, factory: Any, **kwargs: Any) -> DeviceWorker:
        return DeviceWorker(
            self.device_id,
            "ADDR",
            factory,
            self.tracking,
            tuning=kwargs.pop("tuning", FAST),
            **kwargs,
        )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def factory(initial: int = 1, **kwargs: Any) -> FakeTransportFactory:
    return FakeTransportFactory(values={ORIENT: bytes([initial])}, **kwargs)


async def start_ready(
    env: Env, fac: FakeTransportFactory, **kwargs: Any
) -> tuple[DeviceWorker, asyncio.Task[None]]:
    worker = env.worker(fac, **kwargs)
    task = asyncio.create_task(worker.run())
    await wait_until(lambda: worker.state is S.READY)
    return worker, task


async def finish(worker: DeviceWorker, task: asyncio.Task[None]) -> None:
    worker.request_stop()
    await asyncio.wait_for(task, timeout=2.0)


# ------------------------------------------------------------------------------ happy path


def test_reaches_ready_reads_baseline_and_optional_info(env: Env) -> None:
    info: list[tuple[str, str | None, str | None]] = []

    async def scenario() -> None:
        fac = factory(1)
        worker, task = await start_ready(env, fac, on_hardware_info=lambda *a: info.append(a))
        status = worker.status()
        assert status.state is S.READY and status.last_value == 1 and status.battery_percent == 87
        assert status.connection_id is not None and status.last_error is None
        assert EventKind.BASELINE in env.kinds()
        await wait_until(lambda: bool(info))
        await finish(worker, task)

    run(scenario())
    assert info == [(env.device_id, "FAKE-1", "0.0-test")]
    assert env.sessions() == []  # baseline never starts a session by default


def test_face_change_after_debounce_starts_session(env: Env) -> None:
    async def scenario() -> None:
        fac = factory(1)
        worker, task = await start_ready(env, fac)
        fac.last.push(b"\x02")
        await wait_until(lambda: len(env.sessions()) == 1)
        await finish(worker, task)

    run(scenario())
    (session,) = env.sessions()
    assert session.activity_id == env.code and session.device_id == env.device_id


def test_identical_values_and_unstable_faces_create_nothing(env: Env) -> None:
    """Acceptance A-02 and A-03 through the whole pipeline."""

    async def scenario() -> None:
        fac = factory(1)
        worker, task = await start_ready(env, fac)
        for _ in range(20):
            fac.last.push(b"\x01")  # 20 identical values
        fac.last.push(b"\x02")  # passing through face 2 ...
        fac.last.push(b"\x01")  # ... straight back: never stable
        await asyncio.sleep(0.15)  # longer than the debounce time
        assert env.kinds() == [EventKind.BASELINE]
        assert worker.status().duplicates_ignored >= 20
        await finish(worker, task)

    run(scenario())
    assert env.sessions() == []


def test_only_stable_final_face_is_committed(env: Env) -> None:
    async def scenario() -> None:
        fac = factory(0)
        worker, task = await start_ready(env, fac)
        fac.last.push(b"\x01")
        fac.last.push(b"\x02")  # replaces candidate 1 before it was stable
        await wait_until(lambda: EventKind.FACE_CHANGE in env.kinds())
        await finish(worker, task)

    run(scenario())
    changes = [e for e in env.events() if e.kind is EventKind.FACE_CHANGE]
    assert [e.raw_value for e in changes] == [2]


def test_invalid_packet_is_recorded_without_stopping(env: Env) -> None:
    async def scenario() -> None:
        fac = factory(1)
        worker, task = await start_ready(env, fac)
        fac.last.push(b"\x09")
        await wait_until(lambda: EventKind.INVALID in env.kinds())
        assert worker.state is S.READY
        await finish(worker, task)

    run(scenario())
    assert env.sessions() == []


# ------------------------------------------------------------------------ loss / reconnect


def test_link_loss_marks_uncertain_then_reconnect_continues_session(env: Env) -> None:
    """Acceptance A-04: reconnect does not create an unintended new session."""

    async def scenario() -> None:
        fac = factory(2)  # the tracker lies on face 2 when first connected
        worker, task = await start_ready(env, fac)
        fac.last.push(b"")  # user turns to face 1 (Meeting) and the session starts
        await wait_until(lambda: len(env.sessions()) == 1)
        fac.update_defaults(values={ORIENT: b""})  # after the reconnect it still reports 1
        fac.last.drop_link()
        await wait_until(lambda: len(fac.created) >= 2 and worker.state is S.READY)
        await finish(worker, task)

    run(scenario())
    kinds = env.kinds()
    assert EventKind.DISCONNECT in kinds and EventKind.RECONNECT in kinds
    assert kinds.index(EventKind.DISCONNECT) < kinds.index(EventKind.RECONNECT)
    (session,) = env.sessions()  # still exactly one session: it simply continued
    assert session.activity_id == env.meeting and session.quality is Quality.UNCERTAIN


def test_connect_failures_back_off_and_succeed(env: Env) -> None:
    async def scenario() -> None:
        fac = factory(1)
        fac.pending_failures = 2  # only the first transport fails (twice) ...

        original = fac.create

        def create(address: str) -> Any:
            transport = original(address)
            if len(fac.created) <= 2 and isinstance(transport, FakeTransport):
                transport.fail_next_connects(1)  # ... plus the second one once
            return transport

        fac.create = create  # type: ignore[method-assign]
        worker, task = await start_ready(env, fac)
        assert len(fac.created) == 3
        assert worker.status().attempt == 0  # reset after reaching READY
        await finish(worker, task)

    run(scenario())
    # Failed attempts report nothing (never connected); the first success is no reconnect.
    # The only DISCONNECT is the one from the deliberate stop at the end.
    assert env.kinds() == [EventKind.BASELINE, EventKind.DISCONNECT]


def test_each_cycle_gets_new_connection_id_and_sequence_restarts(env: Env) -> None:
    async def scenario() -> None:
        fac = factory(1)
        worker, task = await start_ready(env, fac)
        first_id = worker.status().connection_id
        fac.last.drop_link()
        await wait_until(lambda: len(fac.created) >= 2 and worker.state is S.READY)
        assert worker.status().connection_id != first_id
        await finish(worker, task)

    run(scenario())
    by_connection: dict[str, list[int]] = {}
    for event in env.events():
        by_connection.setdefault(event.connection_id, []).append(event.sequence)
    assert len(by_connection) == 2
    assert all(seq[0] == 0 or seq == sorted(seq) for seq in by_connection.values())


def test_missing_initial_value_times_out_and_retries(env: Env) -> None:
    services = [
        GattService(
            ORIENTATION_SERVICE_UUID,
            (GattCharacteristic(ORIENT, frozenset({"notify"})),),  # not readable, never pushes
        )
    ]

    async def scenario() -> None:
        fac = FakeTransportFactory(services=services)
        worker = env.worker(fac)
        task = asyncio.create_task(worker.run())
        await wait_until(lambda: len(fac.created) >= 2, timeout=3)
        assert "Anfangswert" in (worker.status().last_error or "")
        await finish(worker, task)

    run(scenario())


# ------------------------------------------------------------------------------ unsupported


def test_unsupported_device_stops_without_retry(env: Env) -> None:
    async def scenario() -> None:
        other = GattService("0000aaaa-0000-1000-8000-00805f9b34fb", ())
        fac = FakeTransportFactory(services=[other])
        worker = env.worker(fac)
        await asyncio.wait_for(worker.run(), timeout=2)
        assert worker.state is S.STOPPED
        assert "nicht" in (worker.status().last_error or "")
        assert len(fac.created) == 1  # no reconnect loop for an unusable device

    run(scenario())


# ------------------------------------------------------------------------------- stopping


def test_deliberate_stop_ends_reconnecting_and_reports_gap(env: Env) -> None:
    async def scenario() -> None:
        fac = factory(1)
        worker, task = await start_ready(env, fac)
        worker.request_stop()
        await asyncio.wait_for(task, timeout=2)
        assert worker.state is S.STOPPED and not fac.last.is_connected
        created = len(fac.created)
        await asyncio.sleep(0.15)
        assert len(fac.created) == created  # no reconnect after a deliberate stop

    run(scenario())
    assert env.kinds()[-1] is EventKind.DISCONNECT


def test_stop_during_backoff_is_prompt(env: Env) -> None:
    slow = SupervisorTuning(
        debounce_ms=30,
        connect_timeout=1.0,
        backoff_base=30.0,
        backoff_cap=60.0,
        baseline_timeout=0.4,
    )

    async def scenario() -> None:
        fac = factory(1)
        fac.pending_failures = 1
        worker = env.worker(fac, tuning=slow)
        task = asyncio.create_task(worker.run())
        await wait_until(lambda: worker.state is S.RECONNECT_WAIT)
        loop = asyncio.get_running_loop()
        started = loop.time()
        worker.request_stop()
        await asyncio.wait_for(task, timeout=2)
        assert loop.time() - started < 1.0  # did not wait for the 30 s backoff
        assert worker.state is S.STOPPED

    run(scenario())


def test_connect_timeout_is_treated_as_failure(env: Env) -> None:
    tight = SupervisorTuning(
        debounce_ms=30,
        connect_timeout=0.05,
        backoff_base=0.02,
        backoff_cap=0.05,
        baseline_timeout=0.4,
    )

    async def scenario() -> None:
        fac = FakeTransportFactory(connect_delay=0.5)
        worker = env.worker(fac, tuning=tight)
        task = asyncio.create_task(worker.run())
        await wait_until(lambda: len(fac.created) >= 2)
        assert worker.state in (S.CONNECTING, S.RECONNECT_WAIT, S.DISCONNECTED)
        await finish(worker, task)

    run(scenario())


# ------------------------------------------------------------------- robustness / limits


def test_buffer_overflow_drops_oldest_and_keeps_newest(env: Env) -> None:
    small = SupervisorTuning(
        debounce_ms=30, buffer_size=3, connect_timeout=1.0, backoff_base=0.02, baseline_timeout=0.4
    )

    async def scenario() -> None:
        fac = factory(0)
        worker, task = await start_ready(env, fac, tuning=small)
        for value in (1, 2, 1, 2, 1, 2, 2):  # synchronous burst: the loop cannot drain in between
            fac.last.push(bytes([value]))
        assert worker.status().dropped_values >= 4
        await wait_until(
            lambda: any(e.raw_value == 2 for e in env.events() if e.kind is EventKind.FACE_CHANGE)
        )
        await finish(worker, task)

    run(scenario())


def test_storage_error_does_not_kill_the_connection(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        fac = factory(1)
        worker, task = await start_ready(env, fac)
        original = env.tracking.record_event
        calls = {"n": 0}

        def flaky(event: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                raise StorageError("disk full", user_message="Datenträger voll")
            return original(event)

        monkeypatch.setattr(env.tracking, "record_event", flaky)
        fac.last.push(b"\x02")  # first processing attempt fails ...
        await wait_until(lambda: worker.status().last_error == "Datenträger voll")
        assert worker.state is S.READY  # ... but the link stays up
        fac.last.push(b"\x01")  # later events are processed normally again
        await wait_until(lambda: calls["n"] >= 2)
        await finish(worker, task)

    run(scenario())


def test_tuning_validation() -> None:
    for kwargs in (
        {"buffer_size": 0},
        {"connect_timeout": 0},
        {"baseline_timeout": -1},
        {"backoff_base": 0},
        {"backoff_base": 5, "backoff_cap": 1},
        {"shutdown_grace": -1},
    ):
        with pytest.raises(ValidationError):
            SupervisorTuning(**kwargs)


# ------------------------------------------------------------------------------ supervisor


def test_supervisor_manages_workers_and_shuts_down(env: Env) -> None:
    async def scenario() -> None:
        fac = factory(1)
        supervisor = AgentSupervisor(fac, env.tracking, tuning=FAST)
        worker = supervisor.start_device(env.device_id, "ADDR")
        assert supervisor.start_device(env.device_id, "ADDR") is worker  # idempotent
        await wait_until(lambda: worker.state is S.READY)
        assert [s.state for s in supervisor.statuses()] == [S.READY]
        status = supervisor.status_of(env.device_id)
        assert status is not None and status.last_value == 1
        assert supervisor.status_of("unknown") is None
        await supervisor.shutdown()
        assert worker.state is S.STOPPED and not fac.last.is_connected
        await supervisor.stop_device("unknown")  # no-op

    run(scenario())


def test_supervisor_stop_device_and_restart(env: Env) -> None:
    async def scenario() -> None:
        fac = factory(1)
        supervisor = AgentSupervisor(fac, env.tracking, tuning=FAST)
        first = supervisor.start_device(env.device_id, "ADDR")
        await wait_until(lambda: first.state is S.READY)
        await supervisor.stop_device(env.device_id)
        assert first.state is S.STOPPED
        second = supervisor.start_device(env.device_id, "ADDR")  # finished task -> new worker
        assert second is not first
        await wait_until(lambda: second.state is S.READY)
        await supervisor.shutdown()

    run(scenario())


@pytest.mark.parametrize("address", ["", "   "])
def test_supervisor_requires_address(env: Env, address: str) -> None:
    async def scenario() -> None:
        supervisor = AgentSupervisor(factory(), env.tracking, tuning=FAST)
        with pytest.raises(ValidationError) as info:
            supervisor.start_device(env.device_id, address)
        assert "Adresse" in info.value.user_message

    run(scenario())


def test_two_devices_run_independently(env: Env) -> None:
    with env.storage.transaction() as repos:
        second = repos.devices.add(Device(alias="Zuhause", platform_address="ADDR2"))

    async def scenario() -> None:
        fac = factory(1)
        supervisor = AgentSupervisor(fac, env.tracking, tuning=FAST)
        a = supervisor.start_device(env.device_id, "ADDR")
        b = supervisor.start_device(second.id, "ADDR2")
        await wait_until(lambda: a.state is S.READY and b.state is S.READY)
        fac.created[0].drop_link()  # only the first device loses its link
        await wait_until(lambda: len(fac.created) >= 3 and a.state is S.READY)
        assert b.state is S.READY
        await supervisor.shutdown()

    run(scenario())


def test_default_services_helper_is_compatible() -> None:
    assert default_services()[0].uuid == ORIENTATION_SERVICE_UUID


def test_notifications_and_stop_from_a_foreign_thread_wake_the_worker(env: Env) -> None:
    """Callbacks must not rely on running on the loop thread (found by the end-to-end test)."""
    import threading

    async def scenario() -> None:
        fac = factory(1)
        worker, task = await start_ready(env, fac)
        loop = asyncio.get_running_loop()
        pusher = threading.Thread(target=lambda: fac.last.push(b"\x02"))
        await loop.run_in_executor(None, lambda: (pusher.start(), pusher.join()))
        await wait_until(lambda: len(env.sessions()) == 1)  # the idle worker did wake up
        stopper = threading.Thread(target=worker.request_stop)
        await loop.run_in_executor(None, lambda: (stopper.start(), stopper.join()))
        await asyncio.wait_for(task, timeout=2.0)  # and a stop from another thread works too

    run(scenario())
