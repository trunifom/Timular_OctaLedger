"""Shared fixtures: a real API server on a free loopback port for integration and GUI tests."""

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn

from octaledger.api.app import create_app
from octaledger.api.context import AppContext
from octaledger.application.catalog_service import CatalogService
from octaledger.application.device_service import DeviceService
from octaledger.application.export_service import ExportService
from octaledger.application.reporting_service import ReportService
from octaledger.application.tracking_service import TrackingService
from octaledger.core.settings import Settings, SettingsStore
from octaledger.dashboard_client.client import ApiClient
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

API_TOKEN = "i" * 43


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
