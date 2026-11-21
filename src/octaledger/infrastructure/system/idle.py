"""Idle-time probes: how long ago was the last keyboard or mouse input?

Privacy rule: **only that duration** is read, never what was typed, clicked or shown.

On Windows the value comes from ``GetLastInputInfo`` (user32). It is only meaningful when the
agent runs in the **user's own session** (not as a service in session 0) and it counts
programmatically generated input too; watching a video or reading counts as idle. Without
Windows, or if the call fails, the probe answers ``None`` ("unknown") and the idle feature
simply does nothing; it never raises.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Protocol

logger = logging.getLogger(__name__)

#: The tick counter of ``GetLastInputInfo`` is 32 bit and wraps after about 49.7 days.
_TICK_MASK = 0xFFFFFFFF


class InputProbe(Protocol):
    """Answers how many seconds ago the last user input happened."""

    def idle_seconds(self) -> float | None:
        """Return the idle time in seconds, or ``None`` if it cannot be determined."""
        ...


class FixedInputProbe:
    """A probe with a settable value (tests and non-Windows systems)."""

    def __init__(self, seconds: float | None = None) -> None:
        """Start with ``seconds`` (``None`` = unknown)."""
        self.seconds = seconds

    def idle_seconds(self) -> float | None:
        """Return the value that was set."""
        return self.seconds


class _LastInputInfo(ctypes.Structure):
    """The ``LASTINPUTINFO`` structure of the Windows API."""

    _fields_ = (("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint))


class WindowsInputProbe:
    """Reads the idle time with ``GetLastInputInfo`` (Windows only)."""

    def __init__(self) -> None:
        """Remember whether the API can be used at all."""
        self._available = sys.platform == "win32"
        self._warned = False

    def idle_seconds(self) -> float | None:
        """Return the idle time, or ``None`` outside Windows or if the call fails."""
        if not self._available:
            return None
        try:
            info = _LastInputInfo()
            info.cbSize = ctypes.sizeof(_LastInputInfo)
            user32 = ctypes.windll.user32  # type: ignore[attr-defined,unused-ignore]
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
            if not user32.GetLastInputInfo(ctypes.byref(info)):
                raise OSError("GetLastInputInfo failed")
            now = int(kernel32.GetTickCount()) & _TICK_MASK
            return float(((now - info.dwTime) & _TICK_MASK) / 1000.0)
        except (OSError, AttributeError) as exc:
            if not self._warned:
                logger.warning("Idle time is not available: %s", exc)
                self._warned = True
            return None
