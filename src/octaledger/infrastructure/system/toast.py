"""Windows toast notifications through the optional ``winotify`` package.

``winotify`` (MIT) is an optional extra (``pip install octaledger[toast]``). Without it
:func:`toast_available` is false and the interface greys the switch out with an explanation.
Messages have no action buttons (those need a Start-menu shortcut with an AppUserModelID);
the answer is always given in the dashboard.
"""

from __future__ import annotations

import importlib.util
import logging

logger = logging.getLogger(__name__)

APP_ID = "OctaLedger"


def toast_available() -> bool:
    """Whether the optional toast package is installed."""
    return importlib.util.find_spec("winotify") is not None


class WinToastNotifier:
    """Shows messages as Windows toasts (never raises)."""

    def notify(self, title: str, message: str) -> None:
        """Show a toast; a failure is logged, not raised."""
        try:
            from winotify import Notification  # type: ignore[import-not-found,unused-ignore]

            Notification(app_id=APP_ID, title=title, msg=message).show()
        except Exception:
            logger.warning("The toast could not be shown", exc_info=True)
