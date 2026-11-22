"""Shared fixtures: a real API server on a free loopback port for integration and GUI tests."""

import os
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
import uvicorn

from octaledger.agent.supervisor import DeviceStatus, LiveEvent
from octaledger.api.app import create_app
from octaledger.api.context import AppContext
from octaledger.application.catalog_service import CatalogService
from octaledger.application.device_service import DeviceService
from octaledger.application.export_service import ExportService
from octaledger.application.integration_service import IntegrationService
from octaledger.application.reporting_service import ReportService
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import BleConnectionError
from octaledger.core.secrets import SecretStore
from octaledger.core.settings import ENV_DATA_DIR, Settings, SettingsStore
from octaledger.dashboard_client.client import ApiClient
from octaledger.domain.readout import Reading
from octaledger.domain.state_machine import ConnectionState
from octaledger.infrastructure.ble.scanner import ScanResult
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from tests.fake_adapter import FakeAdapter

API_TOKEN = "i" * 43


@pytest.fixture(scope="session", autouse=True)
def isolated_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Keep every test away from the real user profile.

    Code that resolves the default data folder (the dashboard's logging setup, for example) would
    otherwise write into the OctaLedger folder in ``%LOCALAPPDATA%``: it pollutes the user's real
    log and fails with a locked-file error when the real agent has that log open.
    """
    folder = tmp_path_factory.mktemp("octaledger-profile")
    previous = os.environ.get(ENV_DATA_DIR)
    os.environ[ENV_DATA_DIR] = str(folder)
    try:
        yield folder
    finally:
        if previous is None:
            os.environ.pop(ENV_DATA_DIR, None)
        else:
            os.environ[ENV_DATA_DIR] = previous


class FakeAgent:
    """Stands in for the BLE agent: records calls instead of touching Bluetooth."""

    def __init__(self) -> None:
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.fail_scan = False
        self.readings: list[Reading] = []
        self.read_calls: list[tuple[str, str, float, int]] = []
        self.scan_results = [ScanResult("AA:BB", "ZEI", -60, ("c7e70010",), True)]

    def start_device(self, device_id: str) -> None:
        self.started.append(device_id)

    def stop_device(self, device_id: str) -> None:
        self.stopped.append(device_id)

    def device_statuses(self) -> list[DeviceStatus]:
        now = datetime.now(UTC)
        return [
            DeviceStatus(
                d,
                ConnectionState.READY,
                "c1",
                0,
                None,
                3,
                now,
                87,
                0,
                2,
                raw_value=3,
                raw_at=now,
                debounce_ms=300,
                recent=(LiveEvent(now, "raw", 3), LiveEvent(now, "face_change", 3)),
            )
            for d in self.started
            if d not in self.stopped
        ]

    def read_out(
        self, device_id: str, kind: str, seconds: float = 0.0, interval_ms: int = 500
    ) -> list[Reading]:
        self.read_calls.append((device_id, kind, seconds, interval_ms))
        if device_id not in self.started:
            raise BleConnectionError("off", user_message="Der Würfel ist nicht verbunden.")
        return list(self.readings)

    def scan(self, seconds: float) -> list[ScanResult]:
        if self.fail_scan:
            raise BleConnectionError("off", user_message="Bluetooth ist aus.")
        return list(self.scan_results)


def free_port() -> int:
    """Return a currently unused loopback TCP port."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass
class RunningApi:
    """A started API server with its client and the objects behind it."""

    client: ApiClient
    port: int
    context: AppContext
    storage: Storage
    tmp_path: Path


@pytest.fixture
def api_server(tmp_path: Path) -> Iterator[RunningApi]:
    """Start the real API (real services, temporary database) in a background thread."""
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    port = free_port()
    context = AppContext(
        storage=storage,
        tracking=TrackingService(storage),
        devices=DeviceService(storage),
        catalog=CatalogService(storage),
        reports=ReportService(storage),
        exports=ExportService(storage, exports_dir=tmp_path / "ex", backup_dir=tmp_path / "bk2"),
        settings=SettingsStore(tmp_path / "settings.toml", Settings()),
        token=API_TOKEN,
        port=port,
        integrations=IntegrationService(
            storage, SecretStore(tmp_path / "secrets.json"), {"fake": FakeAdapter()}
        ),
    )
    config = uvicorn.Config(create_app(context), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "API server did not start"
        time.sleep(0.02)
    try:
        yield RunningApi(
            ApiClient(f"http://127.0.0.1:{port}", API_TOKEN), port, context, storage, tmp_path
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
