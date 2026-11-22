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
from octaledger.application.battery_service import BatteryService
from octaledger.application.catalog_service import CatalogService
from octaledger.application.data_service import DataService
from octaledger.application.device_service import DeviceService
from octaledger.application.entry_service import EntryService
from octaledger.application.export_service import ExportService
from octaledger.application.ics_import import IcsService
from octaledger.application.integration_service import IntegrationService
from octaledger.application.music_service import MusicService
from octaledger.application.readout_service import ReadoutService
from octaledger.application.reporting_service import ReportService
from octaledger.application.tag_service import TagService
from octaledger.application.tracking_service import TrackingService
from octaledger.application.work_time_service import WorkTimeService
from octaledger.application.workday_service import WorkdayService
from octaledger.core.settings import SettingsStore
from octaledger.domain.readout import Reading
from octaledger.infrastructure.ble.scanner import ScanResult
from octaledger.infrastructure.storage.repositories import Storage
from octaledger.infrastructure.system.autostart import Autostart
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

    def read_out(
        self, device_id: str, kind: str, seconds: float = 0.0, interval_ms: int = 500
    ) -> list[Reading]:
        """Read out a connected cube: ``datasheet`` or ``accelerometer`` (read only)."""
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
    autostart: Autostart = field(default_factory=Autostart)
    attention: AttentionService = field(init=False)
    workday: WorkdayService = field(init=False)
    worktime: WorkTimeService = field(init=False)
    tag_service: TagService = field(init=False)
    ics: IcsService = field(init=False)
    battery: BatteryService = field(init=False)
    readout: ReadoutService = field(init=False)
    entries: EntryService = field(init=False)
    music: MusicService | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Build the attention and data-management services from the other services."""
        self.attention = AttentionService(self.storage)
        self.worktime = WorkTimeService(self.storage)
        self.tag_service = TagService(self.storage)
        self.ics = IcsService(self.storage)
        self.battery = BatteryService(self.storage)
        self.readout = ReadoutService(self.storage, lambda: self.agent)
        self.entries = EntryService(self.storage, self.exports)
        if self.integrations is not None:
            self.music = MusicService(
                self.storage, self.integrations, lambda: self.settings.settings
            )
        self.workday = WorkdayService(self.storage, lambda: self.settings.settings, self.probe)
        if self.data is None:
            self.data = DataService(self.storage, self.exports, self.integrations, self.settings)
