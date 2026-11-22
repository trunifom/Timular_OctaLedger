"""Start with Windows: one value in the user's ``Run`` registry key (no admin rights needed).

The state is **read** from the registry, never assumed. The registry access sits behind the
small :class:`RunKeyBackend` interface so the logic can be tested without touching a real
registry. Only the current user's key (``HKCU``) is used, and only the single value
``OctaLedger`` is ever written or removed.

Some antivirus programs distrust autostart entries; the value is plain and transparent: the
command that starts the agent (see :func:`build_command`), nothing hidden.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from octaledger.core.errors import ConfigurationError, InvalidStateError

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "OctaLedger"


class RunKeyBackend(Protocol):
    """Reads and writes one value of the ``Run`` key."""

    def read(self, name: str) -> str | None:
        """Return the value or ``None`` if it does not exist."""
        ...

    def write(self, name: str, value: str) -> None:
        """Create or replace the value."""
        ...

    def delete(self, name: str) -> None:
        """Remove the value (no error if it does not exist)."""
        ...


class WinregRunKey:
    """The real registry (Windows only)."""

    def read(self, name: str) -> str | None:
        """Return the value or ``None``."""
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _kind = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ConfigurationError(
                f"Cannot read the Run key: {exc}",
                user_message="Der Autostart-Eintrag von Windows kann nicht gelesen werden.",
            ) from exc
        return str(value)

    def write(self, name: str, value: str) -> None:
        """Create or replace the value."""
        import winreg

        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        except OSError as exc:
            raise ConfigurationError(
                f"Cannot write the Run key: {exc}",
                user_message="Der Autostart-Eintrag konnte nicht gespeichert werden.",
            ) from exc

    def delete(self, name: str) -> None:
        """Remove the value."""
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ConfigurationError(
                f"Cannot delete the Run value: {exc}",
                user_message="Der Autostart-Eintrag konnte nicht entfernt werden.",
            ) from exc


def build_command(python: Path | None = None, windowless: bool = True) -> str:
    """The command Windows runs at logon: the agent without a console window.

    Args:
        python: Interpreter to use (default: the running one).
        windowless: Prefer ``pythonw.exe`` next to the interpreter (no console window).

    Returns:
        A command line with the executable in quotes (paths may contain spaces).
    """
    exe = Path(python) if python is not None else Path(sys.executable)
    if windowless:
        candidate = exe.with_name("pythonw.exe")
        if candidate.exists():
            exe = candidate
    return f'"{exe}" -m octaledger agent'


@dataclass(frozen=True, slots=True)
class AutostartStatus:
    """What the registry says.

    Attributes:
        available: Whether autostart can be used (Windows only).
        enabled: Whether an OctaLedger entry exists.
        command: The stored command, if any.
        current: Whether the stored command equals the one for this installation (a moved
            or re-created virtual environment makes it stale).
    """

    available: bool
    enabled: bool
    command: str | None
    current: bool


class Autostart:
    """Switch "start with Windows" on and off."""

    def __init__(
        self, backend: RunKeyBackend | None = None, *, available: bool | None = None
    ) -> None:
        """Create the switch.

        Args:
            backend: Registry access (default: the real registry on Windows).
            available: Override of the platform check (tests).
        """
        self._available = sys.platform == "win32" if available is None else available
        self._backend: RunKeyBackend | None = backend or (
            WinregRunKey() if self._available else None
        )

    def status(self) -> AutostartStatus:
        """Read the real state."""
        if not self._available or self._backend is None:
            return AutostartStatus(False, False, None, False)
        stored = self._backend.read(VALUE_NAME)
        return AutostartStatus(True, stored is not None, stored, stored == build_command())

    def enable(self) -> AutostartStatus:
        """Write the entry (replacing a stale one).

        Raises:
            InvalidStateError: Outside Windows.
        """
        backend = self._require()
        backend.write(VALUE_NAME, build_command())
        logger.info("Autostart enabled")
        return self.status()

    def disable(self) -> AutostartStatus:
        """Remove the entry.

        Raises:
            InvalidStateError: Outside Windows.
        """
        self._require().delete(VALUE_NAME)
        logger.info("Autostart disabled")
        return self.status()

    def _require(self) -> RunKeyBackend:
        if not self._available or self._backend is None:
            raise InvalidStateError(
                "Autostart is only available on Windows",
                user_message="„Mit Windows starten“ gibt es nur unter Windows.",
            )
        return self._backend
