"""End-to-end: fake tracker -> supervisor -> services -> SQLite -> API -> dashboard client.

This is the whole agent process (BLE loop thread + API thread) with a synthetic tracker
instead of Bluetooth hardware. It does NOT prove behaviour with real trackers.
"""

import socket
import threading
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octaledger.agent.main import AgentRuntime, check_port_free
from octaledger.agent.supervisor import SupervisorTuning
from octaledger.application.device_service import DeviceService
from octaledger.core.errors import ConfigurationError, ValidationError
from octaledger.core.settings import AgentSettings, AppPaths, Settings, TrackingSettings
from octaledger.dashboard_client.client import ApiClient
from octaledger.infrastructure.ble.fake import FakeTransportFactory
from octaledger.infrastructure.ble.protocol import (
    ORIENTATION_CHARACTERISTIC_UUID,
    ORIENTATION_SERVICE_UUID,
)
from octaledger.infrastructure.integrations.base import Adapter
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from tests.conftest import API_TOKEN, free_port
from tests.fake_adapter import FakeAdapter

ORIENT = ORIENTATION_CHARACTERISTIC_UUID
FAST = SupervisorTuning(
    debounce_ms=30,
    connect_timeout=1.0,
    backoff_base=0.02,
    backoff_cap=0.05,
    baseline_timeout=0.5,
    shutdown_grace=2.0,
)


def wait_for(predicate: Callable[[], Any], timeout: float = 8.0) -> Any:
    """Poll until ``predicate`` returns something truthy (returned) or fail."""
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return value
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.02)


async def fake_discover(**_kwargs: Any) -> dict[str, tuple[Any, Any]]:
    device = SimpleNamespace(name="ZEI")
    advertisement = SimpleNamespace(
        local_name="ZEI", rssi=-55, service_uuids=[ORIENTATION_SERVICE_UUID]
    )
    return {"AA:BB:CC:DD:EE:FF": (device, advertisement)}


class Agent:
    def __init__(
        self,
        tmp_path: Path,
        factory: FakeTransportFactory,
        *,
        autostart: bool = False,
        adapters: dict[str, Adapter] | None = None,
    ) -> None:
        self.port = free_port()
        self.paths = AppPaths(root=tmp_path / "data")
        self.settings = Settings(
            agent=AgentSettings(port=self.port), tracking=TrackingSettings(debounce_ms=30)
        )
        self.factory = factory
        self.runtime = AgentRuntime(
            self.paths,
            self.settings,
            transport_factory=factory,
            discover=fake_discover,
            tuning=FAST,
            autostart=autostart,
            token=API_TOKEN,
            adapters=adapters,
        )
        self.client = ApiClient(f"http://127.0.0.1:{self.port}", API_TOKEN)

    def live_state(self, device_id: str) -> str | None:
        for device in self.client.devices():
            if device["id"] == device_id and device["status"]:
                return str(device["status"]["state"])
        return None


@pytest.fixture
def agent(tmp_path: Path) -> Iterator[Agent]:
    instance = Agent(tmp_path, FakeTransportFactory(values={ORIENT: b"\x01"}))
    instance.runtime.start()
    try:
        yield instance
    finally:
        instance.runtime.shutdown()


def setup_device(agent: Agent) -> dict[str, str]:
    client = agent.client
    device = client.register_device("Büro")
    meeting = client.create_item("activities", "Meeting")
    code = client.create_item("activities", "Code")
    client.assign_face(device["id"], 1, meeting["id"])
    client.assign_face(device["id"], 2, code["id"])
    client.set_device_address(device["id"], "AA:BB:CC:DD:EE:FF")
    return {"device": device["id"], "meeting": meeting["id"], "code": code["id"]}


# ----------------------------------------------------------------------------- full flow


def test_whole_chain_from_tracker_to_dashboard_client(agent: Agent) -> None:
    ids = setup_device(agent)
    agent.client.connect_device(ids["device"])
    wait_for(lambda: agent.live_state(ids["device"]) == "ready")
    device = agent.client.devices()[0]
    assert device["status"]["battery_percent"] == 87
    wait_for(lambda: agent.client.devices()[0]["model"] == "FAKE-1")  # hardware info stored

    assert agent.client.status()["tracking"]["running"] is None  # baseline starts nothing
    agent.factory.last.push(b"\x02")  # the user turns the cube to face 2 (Code)
    running = wait_for(lambda: agent.client.status()["tracking"]["running"])
    assert running["source"] == "device" and running["device_id"] == ids["device"]
    assert agent.client.status()["tracking"]["activity"]["name"] == "Code"

    agent.factory.last.push(b"\x01")  # then to face 1 (Meeting)
    wait_for(lambda: agent.client.status()["tracking"]["activity"]["name"] == "Meeting")
    now = datetime.now(timezone.utc)
    entries = agent.client.journal(now - timedelta(days=1), now + timedelta(days=1))
    assert [e["activity_name"] for e in entries] == ["Meeting", "Code"]


def test_link_loss_marks_uncertain_and_the_agent_reconnects(agent: Agent) -> None:
    ids = setup_device(agent)
    agent.client.connect_device(ids["device"])
    wait_for(lambda: agent.live_state(ids["device"]) == "ready")
    agent.factory.last.push(b"\x02")
    wait_for(lambda: agent.client.status()["tracking"]["running"])
    created = len(agent.factory.created)
    agent.factory.last.drop_link()
    wait_for(lambda: agent.client.status()["tracking"]["uncertain_count"] == 1)
    wait_for(
        lambda: len(agent.factory.created) > created and agent.live_state(ids["device"]) == "ready"
    )
    assert agent.client.status()["tracking"]["running"] is not None  # no new session was invented


def test_disconnect_via_api_stops_without_reconnecting(agent: Agent) -> None:
    ids = setup_device(agent)
    agent.client.connect_device(ids["device"])
    wait_for(lambda: agent.live_state(ids["device"]) == "ready")
    agent.client.disconnect_device(ids["device"])
    wait_for(lambda: agent.live_state(ids["device"]) == "stopped")
    created = len(agent.factory.created)
    time.sleep(0.3)
    assert len(agent.factory.created) == created  # a deliberate stop means no automatic retry


def test_scan_goes_through_the_ble_loop(agent: Agent) -> None:
    results = agent.client.scan(2.0)
    assert [(r["name"], r["is_candidate"]) for r in results] == [("ZEI", True)]


def test_connecting_a_device_without_address_is_refused(agent: Agent) -> None:
    device = agent.client.register_device("Ohne Adresse")
    with pytest.raises(ValidationError):
        agent.client.connect_device(device["id"])


# ------------------------------------------------------------------------- start / stop


def test_active_tracker_with_address_connects_automatically(tmp_path: Path) -> None:
    # Prepare the data BEFORE the agent starts (what a previous run would have left behind).
    paths = AppPaths(root=tmp_path / "data")
    paths.root.mkdir(parents=True)
    database = Database(paths.database_file, backup_dir=paths.backups_dir)
    database.initialize()
    devices = DeviceService(Storage(database))
    device = devices.register("Büro", platform_address="AA:BB")
    other = devices.register("Zuhause", platform_address="CC:DD")
    factory = FakeTransportFactory(values={ORIENT: b"\x01"})
    instance = Agent(tmp_path, factory, autostart=True)
    try:
        instance.runtime.start()
        wait_for(lambda: instance.live_state(device.id) == "ready")
        assert instance.live_state(other.id) is None  # only the ACTIVE tracker is auto-connected
        assert len(factory.created) == 1
    finally:
        instance.runtime.shutdown()


def test_no_autostart_without_stored_address(tmp_path: Path) -> None:
    factory = FakeTransportFactory()
    instance = Agent(tmp_path, factory, autostart=True)
    DeviceService(instance.runtime.context.storage).register("Neu")
    try:
        instance.runtime.start()
        time.sleep(0.2)
        assert factory.created == []
    finally:
        instance.runtime.shutdown()


def test_second_agent_on_the_same_port_fails_with_a_clear_message(
    agent: Agent, tmp_path: Path
) -> None:
    clone_settings = Settings(agent=AgentSettings(port=agent.port))
    second = AgentRuntime(
        AppPaths(root=tmp_path / "second"),
        clone_settings,
        transport_factory=FakeTransportFactory(),
        token=API_TOKEN,
    )
    with pytest.raises(ConfigurationError) as info:
        second.start()
    assert (
        "bereits belegt" in info.value.user_message and str(agent.port) in info.value.user_message
    )


def test_shutdown_is_orderly_idempotent_and_releases_everything(tmp_path: Path) -> None:
    instance = Agent(tmp_path, FakeTransportFactory(values={ORIENT: b"\x01"}))
    instance.runtime.start()
    ids = setup_device(instance)
    instance.client.connect_device(ids["device"])
    wait_for(lambda: instance.live_state(ids["device"]) == "ready")
    instance.runtime.shutdown()
    instance.runtime.shutdown()  # idempotent
    assert not instance.factory.last.is_connected  # the tracker was disconnected
    assert instance.runtime._ble_thread is not None and not instance.runtime._ble_thread.is_alive()
    check_port_free("127.0.0.1", instance.port)  # the API port is free again
    assert not instance.client.is_agent_running()


def test_wait_returns_after_request_stop(agent: Agent) -> None:
    timer = threading.Timer(0.2, agent.runtime.request_stop)
    timer.start()
    started = time.monotonic()
    agent.runtime.wait()
    assert 0.1 < time.monotonic() - started < 3
    timer.join()


def test_check_port_free_detects_a_taken_port() -> None:
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        with pytest.raises(ConfigurationError) as info:
            check_port_free("127.0.0.1", port)
        assert info.value.details["port"] == port
    check_port_free("127.0.0.1", port)  # free again after closing


# ----------------------------------------------------------------- control mode (AP-26c)


def setup_control_device(agent: Agent) -> dict[str, str]:
    client = agent.client
    device = client.register_device("Steuerung")
    client.set_device_mode(device["id"], "control")
    connection = client.create_integration(
        "fake", "Licht", {"host": "10.0.0.5", "password": "richtig"}
    )
    client.assign_action(
        device["id"], 2, connection["id"], "Schreibtischlampe", {"action": "toggle"}
    )
    client.set_device_address(device["id"], "AA:BB:CC:DD:EE:FF")
    return {"device": device["id"], "connection": connection["id"]}


@pytest.fixture
def control_agent(tmp_path: Path) -> Iterator[tuple[Agent, FakeAdapter]]:
    adapter = FakeAdapter()
    instance = Agent(
        tmp_path,
        FakeTransportFactory(values={ORIENT: b"\x01"}),
        adapters={"fake": adapter},
    )
    instance.runtime.start()
    try:
        yield instance, adapter
    finally:
        instance.runtime.shutdown()


def test_turning_the_cube_in_control_mode_sends_the_action_and_records_no_time(
    control_agent: tuple[Agent, FakeAdapter],
) -> None:
    agent, adapter = control_agent
    ids = setup_control_device(agent)
    agent.client.connect_device(ids["device"])
    wait_for(lambda: agent.live_state(ids["device"]) == "ready")
    time.sleep(0.3)
    assert adapter.calls == []  # the baseline (first value after connecting) switches nothing

    agent.factory.last.push(b"\x02")  # the user turns the cube to face 2
    wait_for(lambda: len(adapter.calls) == 1)
    config, secrets, params = adapter.calls[0]
    assert params == {"action": "toggle"} and secrets == {"password": "richtig"}
    assert config["host"] == "10.0.0.5"
    job = wait_for(lambda: next((j for j in agent.client.jobs() if j["status"] == "done"), None))
    assert job["label"] == "Schreibtischlampe" and job["face"] == 2

    agent.factory.last.push(b"\x05")  # a face without an action does nothing
    time.sleep(0.4)
    assert len(adapter.calls) == 1
    assert agent.client.status()["tracking"]["running"] is None  # no time was recorded
    now = datetime.now(timezone.utc)
    assert agent.client.journal(now - timedelta(days=1), now + timedelta(days=1)) == []
    live = agent.client.live_view(ids["device"])
    assert (
        live["mode"] == "control" and live["faces"]["2"]["action"]["label"] == "Schreibtischlampe"
    )


def test_a_failing_target_is_shown_in_the_history_not_swallowed(
    control_agent: tuple[Agent, FakeAdapter],
) -> None:
    agent, adapter = control_agent
    ids = setup_control_device(agent)
    adapter.script = [RuntimeError("boom")]
    agent.client.connect_device(ids["device"])
    wait_for(lambda: agent.live_state(ids["device"]) == "ready")
    agent.factory.last.push(b"\x02")
    job = wait_for(lambda: next((j for j in agent.client.jobs() if j["status"] == "failed"), None))
    assert job["error"] == "Unerwarteter Fehler in der Verbindung."
    assert "boom" not in str(agent.client.jobs())


def test_control_trackers_connect_on_their_own_when_the_agent_starts(tmp_path: Path) -> None:
    """A control tracker is never the active tracker, yet it must work right after a restart."""
    adapter = FakeAdapter()
    first = Agent(
        tmp_path, FakeTransportFactory(values={ORIENT: b"\x01"}), adapters={"fake": adapter}
    )
    first.runtime.start()
    try:
        ids = setup_control_device(first)
    finally:
        first.runtime.shutdown()
    # a second start on the same data folder, with autostart switched on
    second = Agent(
        tmp_path,
        FakeTransportFactory(values={ORIENT: b"\x01"}),
        autostart=True,
        adapters={"fake": adapter},
    )
    second.runtime.start()
    try:
        wait_for(lambda: second.live_state(ids["device"]) == "ready")
    finally:
        second.runtime.shutdown()
