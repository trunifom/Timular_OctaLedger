"""The tray icon: proof at a glance that recording runs, without opening the dashboard.

Design: :class:`TrayModel` is plain logic (no library): it turns the service state into an icon
colour and a tooltip and offers the menu actions, which call **application services only**.
:class:`PystrayTray` is a thin wrapper around the optional ``pystray`` package (LGPL, extra
``tray``) that runs the icon in its own daemon thread, so a problem in the tray can never stop
the agent. Without the package, :func:`tray_available` is false and nothing happens.

Colours: green = a time entry runs, grey = nothing runs, red = the active cube is not
connected, yellow = a question waits for you (yellow wins over the others).

Not hardware/desktop tested in this repository: the pystray wrapper only ran against its
interface; the model is fully covered by tests.
"""

from __future__ import annotations

import importlib.util
import logging
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from octaledger.agent.supervisor import DeviceStatus
from octaledger.application.attention_service import AttentionService
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import OctaLedgerError
from octaledger.domain.state_machine import ConnectionState

logger = logging.getLogger(__name__)

DASHBOARD_URL: Final = "http://127.0.0.1:8501"
#: Connection states in which the active cube delivers nothing.
NOT_RECORDING: Final = frozenset(
    {
        ConnectionState.DISCONNECTED,
        ConnectionState.RECONNECT_WAIT,
        ConnectionState.STOPPED,
        ConnectionState.IDLE,
    }
)
COLORS: Final = {
    "green": (46, 160, 67),
    "grey": (128, 128, 128),
    "red": (207, 34, 46),
    "yellow": (212, 167, 44),
}


@dataclass(frozen=True, slots=True)
class TrayView:
    """What the icon shows: a colour name and the tooltip text."""

    color: str
    tooltip: str


def format_elapsed(seconds: int) -> str:
    """``5025`` -> ``1:23:45``."""
    hours, rest = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


class TrayModel:
    """State and actions of the tray icon (no GUI library involved)."""

    def __init__(
        self,
        tracking: TrackingService,
        attention: AttentionService,
        statuses: Callable[[], list[DeviceStatus]],
        quit_agent: Callable[[], None],
        *,
        open_url: Callable[[str], object] = webbrowser.open,
    ) -> None:
        """Create the model.

        Args:
            tracking: Source of the running entry; target of stop/pause.
            attention: Source of the number of open questions.
            statuses: Live status of the started cubes.
            quit_agent: Asks the agent to shut down cleanly.
            open_url: Opens the dashboard (replaceable for tests).
        """
        self._tracking = tracking
        self._attention = attention
        self._statuses = statuses
        self._quit = quit_agent
        self._open_url = open_url

    def view(self) -> TrayView:
        """Compute colour and tooltip from the current state."""
        status = self._tracking.status()
        open_items = len(self._attention.list_open())
        active = {s.device_id: s for s in self._statuses()}.get(status.active_device_id or "")
        disconnected = status.active_device_id is not None and (
            active is None or active.state in NOT_RECORDING
        )
        if status.running is not None:
            name = status.activity.name if status.activity else "Zeit"
            text = f"{name} {format_elapsed(int(status.elapsed.total_seconds()))}"
        elif status.paused:
            text = "Pausiert"
        else:
            text = "Keine Zeiterfassung"
        notes = []
        if disconnected:
            notes.append("Würfel getrennt")
        if open_items:
            notes.append(f"{open_items} Rückfrage(n) offen")
        tooltip = " · ".join([text, *notes])[:120]
        if open_items:
            return TrayView("yellow", tooltip)
        if disconnected:
            return TrayView("red", tooltip)
        return TrayView("green" if status.running is not None else "grey", tooltip)

    # ---------------------------------------------------------------- menu actions

    def stop(self) -> None:
        """End the running entry (nothing happens if none runs)."""
        self._safely(self._tracking.stop)

    def pause_resume(self) -> None:
        """Pause the running entry, or continue the paused one."""
        if self._tracking.status().running is not None:
            self._safely(self._tracking.pause)
        else:
            self._safely(self._tracking.resume)

    def open_dashboard(self) -> None:
        """Open the dashboard in the browser."""
        self._open_url(DASHBOARD_URL)

    def quit(self) -> None:
        """Shut the agent down cleanly."""
        self._quit()

    @staticmethod
    def _safely(action: Callable[[], object]) -> None:
        """Run a service call; an expected refusal (nothing running) is not an error."""
        try:
            action()
        except OctaLedgerError as exc:
            logger.info("Tray action not possible: %s", exc)

    def menu(self) -> list[tuple[str, Callable[[], None]]]:
        """The menu entries in order: label and action."""
        return [
            ("Zeit stoppen", self.stop),
            ("Pause / Fortsetzen", self.pause_resume),
            ("Dashboard öffnen", self.open_dashboard),
            ("Rückfragen anzeigen", self.open_dashboard),
            ("OctaLedger beenden", self.quit),
        ]


def tray_available() -> bool:
    """Whether the optional tray packages (pystray and Pillow) are installed."""
    return all(importlib.util.find_spec(name) is not None for name in ("pystray", "PIL"))


class PystrayTray:
    """Runs a :class:`TrayModel` as a real tray icon in a daemon thread (optional extra)."""

    def __init__(self, model: TrayModel) -> None:
        """Remember the model; nothing is created before :meth:`start`."""
        self._model = model
        self._icon: Any = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """Show the icon. Returns ``False`` (and logs why) if it cannot be shown."""
        if not tray_available():
            logger.info("Tray icon not started: the optional package is not installed")
            return False
        try:
            import pystray  # type: ignore[import-not-found,unused-ignore]

            view = self._model.view()
            self._icon = pystray.Icon(
                "octaledger",
                self._image(view.color),
                view.tooltip,
                pystray.Menu(
                    *(
                        pystray.MenuItem(label, self._wrap(action))
                        for label, action in self._model.menu()
                    )
                ),
            )
            self._thread = threading.Thread(
                target=self._icon.run, name="octaledger-tray", daemon=True
            )
            self._thread.start()
        except Exception:  # noqa: BLE001 - the tray must never prevent the agent from running
            logger.warning("The tray icon could not be started", exc_info=True)
            self._icon = None
            return False
        logger.info("Tray icon started")
        return True

    def refresh(self) -> None:
        """Update colour and tooltip (called by the housekeeper)."""
        if self._icon is None:
            return
        view = self._model.view()
        self._icon.icon = self._image(view.color)
        self._icon.title = view.tooltip

    def stop(self) -> None:
        """Remove the icon."""
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:  # noqa: BLE001 - closing must not fail
                logger.debug("Ignoring error while removing the tray icon", exc_info=True)

    @staticmethod
    def _wrap(action: Callable[[], None]) -> Callable[..., None]:
        def run(*_args: object) -> None:
            """Menu callback: pystray passes extra arguments, the action takes none."""
            try:
                action()
            except Exception:  # noqa: BLE001 - a menu action must not kill the tray thread
                logger.exception("A tray menu action failed")

        return run

    @staticmethod
    def _image(color: str) -> Any:
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((8, 8, 56, 56), fill=(*COLORS[color], 255))
        return image
