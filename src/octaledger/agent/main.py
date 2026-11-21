"""Agent entry point: wires storage, services, the BLE event loop and the local API together.

Process layout (``docs/ARCHITEKTUR.md``)
----------------------------------------
* **Main thread** - waits for Ctrl+C / a stop request and then shuts everything down in order.
* **BLE thread** - runs the *one* asyncio event loop that owns every tracker connection (Bleak
  requires the related calls to share a running loop). The :class:`AgentSupervisor` lives there.
* **API thread** - uvicorn serving the loopback API; its handlers run in a worker thread pool.

The API talks to the BLE side only through the :class:`AgentControl` methods of
:class:`AgentRuntime`, which hand coroutines to the BLE loop thread-safely
(``run_coroutine_threadsafe``). Closing or reloading the dashboard never touches this process,
so tracking continues (acceptance A-05).

Start-up rules
--------------
* Only the **active tracker** is connected automatically, and only if it has a stored address.
  Registered devices do not imply two reliable simultaneous connections on one adapter
  (Pflichtenheft section 1); other trackers are connected explicitly by the user.
* The API port is checked first, so a second agent fails with a clear message instead of two
  writers racing for the database.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from collections.abc import Coroutine, Mapping
from pathlib import Path
from typing import Any, TypeVar

import uvicorn

from octaledger.agent.dispatcher import ActionDispatcher
from octaledger.agent.housekeeper import Housekeeper
from octaledger.agent.supervisor import AgentSupervisor, DeviceStatus, SupervisorTuning
from octaledger.agent.tray import PystrayTray, TrayModel, tray_available
from octaledger.api.app import create_app
from octaledger.api.context import AppContext
from octaledger.api.security import TOKEN_FILE_NAME, load_or_create_token
from octaledger.application.battery_watch import BatteryWatch
from octaledger.application.catalog_service import CatalogService
from octaledger.application.device_service import DeviceService
from octaledger.application.export_service import ExportService
from octaledger.application.integration_service import IntegrationService
from octaledger.application.notifier import NotificationRelay
from octaledger.application.reporting_service import ReportService
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import (
    ApiUnavailableError,
    BleConnectionError,
    ConfigurationError,
    OctaLedgerError,
)
from octaledger.core.logging import configure_logging, recent_log_lines, shutdown_logging
from octaledger.core.secrets import SECRETS_FILE_NAME, SecretStore
from octaledger.core.settings import (
    AppPaths,
    Settings,
    SettingsStore,
    ensure_directories,
    load_settings,
    resolve_paths,
)
from octaledger.domain.models import DeviceMode
from octaledger.infrastructure.ble.client import BleakTransportFactory
from octaledger.infrastructure.ble.scanner import DiscoverFn, ScanResult, scan
from octaledger.infrastructure.ble.transport import TransportFactory
from octaledger.infrastructure.integrations.base import Adapter
from octaledger.infrastructure.integrations.registry import default_adapters
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from octaledger.infrastructure.system.idle import WindowsInputProbe
from octaledger.infrastructure.system.toast import WinToastNotifier

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Seconds to wait for the API server to come up / the BLE loop to answer a command.
START_TIMEOUT = 10.0
COMMAND_TIMEOUT = 30.0


def check_port_free(host: str, port: int) -> None:
    """Fail early and clearly if something already listens on ``host:port``.

    Raises:
        ConfigurationError: If the port is taken (typically: the agent already runs).
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError as exc:
            raise ConfigurationError(
                f"Port {port} on {host} is not available: {exc}",
                user_message=(
                    f"Der Port {port} ist bereits belegt. Läuft der OctaLedger-Agent schon? "
                    "Sonst einen anderen Port in settings.toml oder mit OCTALEDGER_PORT wählen."
                ),
                details={"host": host, "port": port},
            ) from exc


async def _start_worker(owner: AgentSupervisor, device_id: str, address: str) -> None:
    """Create a worker task; must run on the BLE loop, hence the coroutine."""
    owner.start_device(device_id, address)


class AgentRuntime:
    """The running agent: services, BLE loop thread and API server thread."""

    def __init__(
        self,
        paths: AppPaths,
        settings: Settings,
        *,
        transport_factory: TransportFactory,
        discover: DiscoverFn | None = None,
        tuning: SupervisorTuning | None = None,
        autostart: bool = True,
        token: str | None = None,
        adapters: Mapping[str, Adapter] | None = None,
    ) -> None:
        """Build all services (nothing runs until :meth:`start`).

        Args:
            paths: Per-user data locations.
            settings: Validated settings.
            transport_factory: Creates the BLE transports (Bleak in production, a fake in tests).
            discover: Replacement for ``BleakScanner.discover`` (tests).
            tuning: Supervisor timing; default derived from the settings.
            autostart: Connect the active tracker automatically after start.
            token: API token; default is loaded/created in the data folder.
            adapters: Integration adapters by kind; default are the shipped ones.
        """
        ensure_directories(paths)
        self._settings = settings
        self._factory = transport_factory
        self._discover = discover
        self._autostart = autostart
        self._tuning = tuning or SupervisorTuning(debounce_ms=settings.tracking.debounce_ms)
        self._adapters = adapters

        database = Database(paths.database_file, backup_dir=paths.backups_dir)
        database.initialize()
        storage = Storage(database)
        integrations = IntegrationService(
            storage,
            SecretStore(paths.root / SECRETS_FILE_NAME),
            default_adapters() if adapters is None else adapters,
        )
        self._dispatcher = ActionDispatcher(integrations)
        self.context = AppContext(
            storage=storage,
            tracking=TrackingService(storage, settings.tracking),
            devices=DeviceService(storage),
            catalog=CatalogService(storage),
            reports=ReportService(storage),
            exports=ExportService(
                storage, exports_dir=paths.exports_dir, backup_dir=paths.backups_dir
            ),
            settings=SettingsStore(paths.settings_file, settings),
            token=token or load_or_create_token(paths.root / TOKEN_FILE_NAME),
            port=settings.agent.port,
            log_lines=recent_log_lines,
            agent=self,
            integrations=integrations,
            probe=WindowsInputProbe(),
        )
        self._battery_watch = BatteryWatch(
            storage,
            self.device_statuses,
            lambda: self.context.settings.settings.notifications,
            lambda device_id: self._device_name(device_id),
        )
        self._relay = NotificationRelay(
            storage,
            [WinToastNotifier()],
            lambda: self.context.settings.settings.notifications,
            lambda: self.context.settings.settings.display.timezone,
        )
        self._tray: PystrayTray | None = None
        self._housekeeper = Housekeeper(
            [
                self.context.tracking.watchdog,
                self.context.attention.expire_old,
                self.context.workday.tick,
                self._battery_watch.check,
                self._relay.check,
                self._refresh_tray,
            ]
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ble_thread: threading.Thread | None = None
        self._supervisor: AgentSupervisor | None = None
        self._server: uvicorn.Server | None = None
        self._api_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._shutdown_done = False

    # --------------------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Start the BLE loop and the API server (non-blocking).

        Raises:
            ConfigurationError: If the API port is taken or the server does not start.
        """
        check_port_free(self._settings.agent.host, self._settings.agent.port)
        self._start_ble_loop()
        self._dispatcher.start()
        self._start_tray()
        self._housekeeper.start()
        config = uvicorn.Config(
            create_app(self.context),
            host=self._settings.agent.host,
            port=self._settings.agent.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._api_thread = threading.Thread(
            target=self._server.run, name="octaledger-api", daemon=True
        )
        self._api_thread.start()
        deadline = time.monotonic() + START_TIMEOUT
        while not self._server.started:
            if not self._api_thread.is_alive() or time.monotonic() > deadline:
                self.shutdown()
                raise ConfigurationError(
                    "The API server did not start",
                    user_message="Die lokale Schnittstelle konnte nicht gestartet werden.",
                )
            time.sleep(0.02)
        logger.info(
            "Agent API listening on %s:%d", self._settings.agent.host, self._settings.agent.port
        )
        if self._autostart:
            self._autostart_devices()

    def wait(self) -> None:
        """Block the calling thread until :meth:`request_stop` or Ctrl+C."""
        try:
            while not self._stop.wait(0.25):
                if self._api_thread is not None and not self._api_thread.is_alive():
                    logger.error("The API server stopped unexpectedly")
                    break
        except KeyboardInterrupt:
            logger.info("Interrupted by user")

    def request_stop(self) -> None:
        """Ask :meth:`wait` to return (e.g. from a signal handler)."""
        self._stop.set()

    def shutdown(self) -> None:
        """Stop everything in order: API, trackers (final events), BLE loop. Idempotent."""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        logger.info("Agent shutting down")
        if self._server is not None:
            self._server.should_exit = True
        if self._api_thread is not None:
            self._api_thread.join(timeout=10)
        self._dispatcher.stop()
        self._housekeeper.stop()
        if self._tray is not None:
            self._tray.stop()
        loop, supervisor = self._loop, self._supervisor
        if loop is not None and supervisor is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(supervisor.shutdown(), loop).result(
                    timeout=self._tuning.shutdown_grace + 5
                )
            except Exception:  # noqa: BLE001 - shutting down must always finish
                logger.exception("Error while stopping the trackers")
            loop.call_soon_threadsafe(loop.stop)
        if self._ble_thread is not None:
            self._ble_thread.join(timeout=10)
        self._stop.set()
        logger.info("Agent stopped")

    # ---------------------------------------------------------------------- BLE loop

    def _start_ble_loop(self) -> None:
        ready = threading.Event()

        def run() -> None:
            """Thread body: own the event loop, create the supervisor and run until stopped."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._supervisor = AgentSupervisor(
                self._factory,
                self.context.tracking,
                tuning=self._tuning,
                on_hardware_info=self._store_hardware_info,
            )
            ready.set()
            try:
                loop.run_forever()
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        self._ble_thread = threading.Thread(target=run, name="octaledger-ble", daemon=True)
        self._ble_thread.start()
        if not ready.wait(START_TIMEOUT):
            raise ConfigurationError("The BLE loop did not start")

    def _store_hardware_info(self, device_id: str, model: str | None, firmware: str | None) -> None:
        self.context.devices.update_hardware_info(device_id, model=model, firmware=firmware)

    def _call(self, coroutine: Coroutine[Any, Any, T], timeout: float = COMMAND_TIMEOUT) -> T:
        """Run ``coroutine`` on the BLE loop from any thread and return its result."""
        loop = self._loop
        if loop is None or not loop.is_running():
            coroutine.close()
            raise ApiUnavailableError("The BLE loop is not running")
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout)
        except TimeoutError as exc:
            future.cancel()
            raise BleConnectionError(
                "The BLE command timed out",
                user_message="Der Bluetooth-Vorgang hat zu lange gedauert.",
            ) from exc

    def _autostart_devices(self) -> None:
        """Connect the active tracker and every tracker in control mode that has an address.

        Control trackers are never "the active tracker", yet they must work right after the start.
        One tracker failing to start never prevents the others or the agent from starting.
        """
        try:
            candidates = [
                info
                for info in self.context.devices.list_devices()
                if info.is_active or info.device.mode is DeviceMode.CONTROL
            ]
        except OctaLedgerError as exc:
            logger.warning("Automatic connect skipped: %s", exc)
            return
        for info in candidates:
            if info.device.platform_address is None:
                logger.info(
                    "Tracker %s has no Bluetooth address yet; not connecting", info.device.alias
                )
                continue
            try:
                self.start_device(info.device.id)
            except OctaLedgerError as exc:
                logger.warning("Automatic connect of %s skipped: %s", info.device.alias, exc)

    # -------------------------------------------------------------- AgentControl (API)

    def start_device(self, device_id: str) -> None:
        """Start the connection of a registered device (needs a stored address)."""
        address = self.context.devices.get(device_id).device.platform_address
        supervisor = self._supervisor
        if supervisor is None:
            raise ApiUnavailableError("The BLE loop is not running")

        self._call(_start_worker(supervisor, device_id, address or ""))

    def stop_device(self, device_id: str) -> None:
        """Stop a device on purpose (no further reconnects)."""
        supervisor = self._supervisor
        if supervisor is None:
            raise ApiUnavailableError("The BLE loop is not running")
        self._call(supervisor.stop_device(device_id))

    def _start_tray(self) -> None:
        """Show the tray icon when it is enabled and the optional package is installed."""
        if not self._settings.tray.enabled or not tray_available():
            return
        model = TrayModel(
            self.context.tracking,
            self.context.attention,
            self.device_statuses,
            self.request_stop,
        )
        tray = PystrayTray(model)
        if tray.start():
            self._tray = tray

    def _refresh_tray(self) -> None:
        """Housekeeper task: keep the icon colour and tooltip current."""
        if self._tray is not None:
            self._tray.refresh()

    def _device_name(self, device_id: str) -> str:
        """Alias of a device for messages (empty if it no longer exists)."""
        with self.context.storage.read() as repos:
            device = repos.devices.get(device_id)
        return device.alias if device else ""

    def device_statuses(self) -> list[DeviceStatus]:
        """Live status of all started devices (immutable snapshots)."""
        return [] if self._supervisor is None else self._supervisor.statuses()

    def scan(self, seconds: float) -> list[ScanResult]:
        """Scan for BLE devices on the BLE loop (never connects)."""
        return self._call(scan(seconds, discover=self._discover), timeout=seconds + 20)


def run_agent(
    data_dir: Path | None = None,
    log_level: str | None = None,
    factory: TransportFactory | None = None,
) -> None:
    """Run the agent until Ctrl+C (used by ``octaledger agent``).

    Args:
        data_dir: Alternative data folder (default: per-user folder / OCTALEDGER_DATA_DIR).
        log_level: Override of the configured log level.
        factory: Transport factory (default: Bleak).

    Raises:
        OctaLedgerError: For configuration, port or storage problems (the CLI prints them).
    """
    paths = resolve_paths(data_dir)
    ensure_directories(paths)
    settings = load_settings(paths.settings_file)
    configure_logging(
        level=log_level or settings.logging.level,
        log_dir=paths.logs_dir,
        max_bytes=settings.logging.max_bytes,
        backup_count=settings.logging.backup_count,
    )
    logger.info("OctaLedger agent starting (data folder %s)", paths.root)
    scan_seconds = (
        float(settings.agent.scan_timeout_seconds) if settings.agent.scan_before_connect else 0.0
    )
    runtime = AgentRuntime(
        paths,
        settings,
        transport_factory=factory or BleakTransportFactory(scan_timeout=scan_seconds),
    )
    try:
        runtime.start()
        logger.info("Agent running. Press Ctrl+C to stop.")
        runtime.wait()
    finally:
        runtime.shutdown()
        shutdown_logging()
