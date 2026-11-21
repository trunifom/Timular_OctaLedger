"""Shared state of the API: the services, the token and the agent control interface.

Kept in its own module so that ``app`` (middleware, error mapping) and ``routes`` (endpoints)
can both depend on it without importing each other.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from octaledger.agent.supervisor import DeviceStatus
from octaledger.application.attention_service import AttentionService
from octaledger.application.catalog_service import CatalogService
from octaledger.application.data_service import DataService
from octaledger.application.device_service import DeviceService
from octaledger.application.export_service import ExportService
from octaledger.application.integration_service import IntegrationService
from octaledger.application.reporting_service import ReportService
from octaledger.application.tracking_service import TrackingService
from octaledger.application.workday_service import WorkdayService
from octaledger.core.settings import SettingsStore
from octaledger.infrastructure.ble.scanner import ScanResult
from octaledger.infrastructure.storage.repositories import Storage
from octaledger.infrastructure.system.idle import FixedInputProbe, InputProbe


class AgentControl(Protocol):
    """What the API needs from the running agent (thread-safe wrappers around the BLE loop)."""

    def start_device(self, device_id: str) -> None:
        """Start the connection of a registered device."""
        ...

    def stop_device(self, device_id: str) -> None:
        """Stop a device on purpose (no further reconnects)."""
        ...

    def device_statuses(self) -> list[DeviceStatus]:
        """Return the live status of all started devices."""
        ...

    def scan(self, seconds: float) -> list[ScanResult]:
        """Scan for BLE devices (explicitly requested by the user)."""
        ...


def _no_logs() -> list[str]:
    return []


@dataclass(slots=True)
class AppContext:
    """Everything the routes need (one instance per running agent).

    Attributes:
        token: The API token every protected route requires.
        port: The API port (the ``Host`` header must name it).
        log_lines: Returns the recent, already redacted log lines for the diagnostics page.
        agent: Control of the BLE side; ``None`` when the API runs without an agent (tests).
        integrations: Control mode (connections, face actions); ``None`` if not available.
        data: Data management (deleting entries, removing cubes, reset); built automatically.
    """

    storage: Storage
    tracking: TrackingService
    devices: DeviceService
    catalog: CatalogService
    reports: ReportService
    exports: ExportService
    settings: SettingsStore
    token: str
    port: int
    log_lines: Callable[[], list[str]] = field(default=_no_logs)
    agent: AgentControl | None = None
    integrations: IntegrationService | None = None
    data: DataService | None = None
    probe: InputProbe = field(default_factory=FixedInputProbe)
    attention: AttentionService = field(init=False)
    workday: WorkdayService = field(init=False)

    def __post_init__(self) -> None:
        """Build the attention and data-management services from the other services."""
        self.attention = AttentionService(self.storage)
        self.workday = WorkdayService(self.storage, lambda: self.settings.settings, self.probe)
        if self.data is None:
            self.data = DataService(self.storage, self.exports, self.integrations, self.settings)
