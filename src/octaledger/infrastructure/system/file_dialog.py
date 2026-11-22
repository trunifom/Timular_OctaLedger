"""Pick a file or a folder in the normal Windows dialog (AP-61).

The user may type a path, or click "Durchsuchen" and choose in the familiar file dialog. The
dialog is shown by the **computer the agent runs on** (OctaLedger is local-first, so that is the
computer in front of the user). It runs in a **child process** (``python -c`` with ``tkinter``)
because a dialog needs its own event loop and must never block or crash the agent: if tkinter is
missing, the dialog fails or the user cancels, the caller gets ``None`` or a clear error, never a
hang (a timeout ends a dialog nobody answers).

The script is a fixed text: no user input is part of it. The only argument is the kind
(``file`` or ``folder``), checked against a fixed list.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any, Final

from octaledger.core.errors import IntegrationError, ValidationError
from octaledger.domain.media_formats import known_extensions

logger = logging.getLogger(__name__)

KINDS: Final = ("file", "folder")
TIMEOUT_SECONDS: Final = 600.0

_SCRIPT: Final = """
import sys
import tkinter
from tkinter import filedialog

kind = sys.argv[1]
types = sys.argv[2].split(",")
root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
if kind == "folder":
    chosen = filedialog.askdirectory(title="Ordner oder Album wählen", mustexist=True)
else:
    chosen = filedialog.askopenfilename(
        title="Musik- oder Videodatei wählen",
        filetypes=[("Audio, Video und Playlists", " ".join("*" + t for t in types)),
                   ("Alle Dateien", "*.*")],
    )
sys.stdout.buffer.write((chosen or "").encode("utf-8"))
"""


def dialog_available() -> bool:
    """Whether ``tkinter`` (the dialog toolkit that ships with Python) can be imported."""
    return importlib.util.find_spec("tkinter") is not None


def pick_path(
    kind: str,
    *,
    run: Callable[..., Any] = subprocess.run,
    timeout: float = TIMEOUT_SECONDS,
) -> str | None:
    """Show the dialog and return the chosen path (``None`` if the user cancelled).

    Args:
        kind: ``file`` or ``folder``.
        run: Replaceable for tests.
        timeout: Seconds after which an unanswered dialog is closed.

    Raises:
        ValidationError: For an unknown ``kind``.
        IntegrationError: If the dialog cannot be shown.
    """
    if kind not in KINDS:
        raise ValidationError(
            f"Unknown dialog kind {kind!r}", user_message="Es gibt nur Datei- und Ordnerauswahl."
        )
    if not dialog_available():
        raise IntegrationError(
            "tkinter is not installed",
            user_message="Der Auswahldialog ist auf diesem Computer nicht verfügbar. Tippen Sie "
            "den Pfad ein.",
        )
    extensions = ",".join(sorted([*known_extensions(), ".m3u", ".m3u8"]))
    try:
        result = run(
            [sys.executable, "-I", "-c", _SCRIPT, kind, extensions],
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("File dialog failed: %s", type(exc).__name__)
        raise IntegrationError(
            f"File dialog failed: {type(exc).__name__}",
            user_message="Der Auswahldialog konnte nicht geöffnet werden. Tippen Sie den Pfad ein.",
        ) from exc
    if result.returncode != 0:
        logger.warning("File dialog exited with code %s", result.returncode)
        raise IntegrationError(
            "File dialog crashed",
            user_message="Der Auswahldialog ist abgestürzt. Tippen Sie den Pfad ein.",
        )
    chosen = bytes(result.stdout).decode("utf-8", errors="replace").strip()
    return chosen or None
