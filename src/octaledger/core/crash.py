"""Crash reporting: leave a trace even when the process dies without a Python error.

Responsibility
--------------
Python exceptions are already written to the log by :mod:`octaledger.core.logging`. Three
kinds of failure never reach it, and they are exactly the ones a user cannot report because the
console window is gone:

* **Native crashes** (access violation, ``abort()`` in a C library such as ``miniaudio`` or
  Bleak's WinRT layer, Windows exit code ``0xC0000409``). Python has no chance to log anything;
  :mod:`faulthandler` is the only thing that can still write the stack of every thread. It
  writes to ``crash-<process>.log`` in the log directory.
* **Exceptions that Python throws away**: errors inside callbacks of C libraries (``Exception
  ignored in ...``, :data:`sys.unraisablehook`) and unreported asyncio task failures. They are
  forwarded to the log.
* **A process that was simply killed** (task manager, closed console window, power loss). A
  small *run marker* file exists while a process runs and is removed at a clean exit; a marker
  left over from a previous run is reported at the next start.

At the next start :func:`install_crash_reporting` evaluates the leftovers: a crash file with a
traceback is logged as ``ERROR`` (the text is also kept as ``crash-<process>-<time>.log``, the
newest :data:`KEEP_REPORTS` are retained), a lone marker is logged as ``WARNING``.

Limits: nothing can be written when the machine loses power or the process is killed before it
starts; the marker then only tells *that* something ended abnormally, not why. Not every native
crash can be caught (for example a corrupted stack), but those that can are shown with the
Python stack of every thread, which is usually enough to find the call that was running.
"""

from __future__ import annotations

import atexit
import faulthandler
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final, TextIO

logger = logging.getLogger(__name__)

#: How many archived crash reports per process are kept (older ones are deleted).
KEEP_REPORTS: Final = 5
#: Text that faulthandler writes when it reports a crash (not part of our own header lines).
_CRASH_MARKERS: Final = ("Fatal Python error", "Windows fatal exception", "Current thread")
#: Longest crash text that is copied into the log (the full text stays in the archive file).
_MAX_LOGGED_CHARS: Final = 6000
_PROCESS_QUERY_LIMITED_INFORMATION: Final = 0x1000
_STILL_ACTIVE: Final = 259


@dataclass(frozen=True, slots=True)
class PreviousRun:
    """What was found about the previous run of a process.

    Attributes:
        kind: ``native_crash`` (a traceback was written) or ``unclean_exit`` (only the run
            marker was left over: killed, console closed, power loss, or a crash without trace).
        report: The crash text for a native crash, otherwise an explanation.
        archive: The kept copy of the crash text, if one was saved.
    """

    kind: str
    report: str
    archive: Path | None = None


@dataclass(slots=True)
class _Installed:
    """What :func:`install_crash_reporting` set up (needed to undo it in tests)."""

    process: str
    stream: TextIO
    marker: Path
    faulthandler_was_enabled: bool
    previous_unraisable: object


# faulthandler, atexit and sys.unraisablehook are process-wide by nature, so this is the one
# place that remembers that they are set up (installing twice must be harmless).
_installed: _Installed | None = None


# ------------------------------------------------------------------------ helpers


def _pid_alive(pid: int) -> bool:
    """Whether a process with this id exists (never sends a signal on Windows)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # exists but belongs to someone else
    return True


def _crash_file(log_dir: Path, process: str) -> Path:
    return log_dir / f"crash-{process}.log"


def _marker_file(log_dir: Path, process: str) -> Path:
    return log_dir / f"running-{process}.json"


def _read_marker(marker: Path) -> dict[str, object] | None:
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _prune_reports(log_dir: Path, process: str) -> None:
    """Delete archived crash reports beyond :data:`KEEP_REPORTS` (newest are kept)."""
    reports = sorted(log_dir.glob(f"crash-{process}-*.log"))
    for old in reports[:-KEEP_REPORTS]:
        try:
            old.unlink()
        except OSError:
            logger.debug("Could not delete the old crash report %s", old, exc_info=True)


def _inspect_previous(log_dir: Path, process: str) -> PreviousRun | None:
    """Evaluate the crash file and run marker left by the previous run."""
    crash_file = _crash_file(log_dir, process)
    marker = _read_marker(_marker_file(log_dir, process))
    text = ""
    try:
        text = crash_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    body = "\n".join(line for line in text.splitlines() if not line.startswith("==="))
    if any(marker_text in body for marker_text in _CRASH_MARKERS):
        stamp = datetime.fromtimestamp(crash_file.stat().st_mtime, UTC).strftime("%Y%m%d-%H%M%S")
        target = log_dir / f"crash-{process}-{stamp}.log"
        try:
            target.write_text(text, encoding="utf-8")
            _prune_reports(log_dir, process)
        except OSError:
            logger.warning("Could not keep the crash report", exc_info=True)
            return PreviousRun("native_crash", body.strip(), None)
        return PreviousRun("native_crash", body.strip(), target)
    if marker is not None:
        started = marker.get("started", "?")
        return PreviousRun(
            "unclean_exit",
            f"The previous {process} run (started {started}) did not end cleanly and left no "
            "crash trace: it was killed, its console window was closed, the computer lost "
            "power, or it crashed in a way that cannot be traced.",
        )
    return None


def _report_previous(previous: PreviousRun, process: str) -> None:
    """Write the finding of the previous run into the log."""
    if previous.kind == "native_crash":
        shown = previous.report
        if len(shown) > _MAX_LOGGED_CHARS:
            shown = shown[:_MAX_LOGGED_CHARS] + "\n... (cut, see the crash report file)"
        where = f" Full text: {previous.archive}" if previous.archive else ""
        logger.error(
            "The previous %s run CRASHED natively (no Python error).%s\n%s",
            process,
            where,
            shown,
        )
    else:
        logger.warning("%s", previous.report)


def _log_unraisable(unraisable: sys.UnraisableHookArgs) -> None:
    """``sys.unraisablehook``: errors Python would only print and forget go into the log."""
    where = unraisable.err_msg or "Exception ignored"
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None = None
    if unraisable.exc_type is not None and unraisable.exc_value is not None:
        exc_info = (unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback)
    logging.getLogger(f"{__name__}.unraisable").error(
        "%s (object: %r)", where, unraisable.object, exc_info=exc_info
    )


def _clean_exit() -> None:
    """``atexit``: remove the run marker, which proves that this run ended normally."""
    state = _installed
    if state is not None:
        try:
            state.marker.unlink(missing_ok=True)
        except OSError:
            logger.debug("Could not remove the run marker", exc_info=True)


# ----------------------------------------------------------------------- public API


def install_crash_reporting(log_dir: Path, process: str) -> PreviousRun | None:
    """Switch crash reporting on for this process (call once, right after the log setup).

    Args:
        log_dir: The log directory (the files are written next to ``octaledger.log``).
        process: A short name such as ``agent`` or ``dashboard``; every process has its own
            crash file and run marker.

    Returns:
        What was found about the previous run of this process (also written to the log), or
        ``None`` if it ended cleanly or crash reporting could not be started. Never raises: a
        problem here must not stop the application.
    """
    global _installed
    if _installed is not None:
        return None
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        marker_path = _marker_file(log_dir, process)
        old = _read_marker(marker_path)
        old_pid = old.get("pid") if old else None
        if isinstance(old_pid, int) and old_pid != os.getpid() and _pid_alive(old_pid):
            logger.debug(
                "Another %s process (%d) is running; crash reporting not started", process, old_pid
            )
            return None
        previous = _inspect_previous(log_dir, process)
        stream = _crash_file(log_dir, process).open("w", encoding="utf-8")
        now = datetime.now(UTC).isoformat(timespec="seconds")
        stream.write(f"=== {process} pid={os.getpid()} started {now} ===\n")
        stream.flush()
        was_enabled = faulthandler.is_enabled()
        faulthandler.enable(file=stream, all_threads=True)
        marker_path.write_text(
            json.dumps({"pid": os.getpid(), "started": now, "process": process}),
            encoding="utf-8",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Crash reporting could not be started: %s", exc)
        return None
    previous_hook = sys.unraisablehook
    if previous_hook is sys.__unraisablehook__:
        sys.unraisablehook = _log_unraisable
    _installed = _Installed(process, stream, marker_path, was_enabled, previous_hook)
    atexit.register(_clean_exit)
    logger.debug("Crash reporting active (%s)", stream.name)
    if previous is not None:
        _report_previous(previous, process)
    return previous


def uninstall_crash_reporting() -> None:
    """Undo :func:`install_crash_reporting` (for tests; a real process keeps it until exit)."""
    global _installed
    state, _installed = _installed, None
    if state is None:
        return
    faulthandler.disable()
    if state.faulthandler_was_enabled:
        faulthandler.enable()
    if sys.unraisablehook is _log_unraisable:
        sys.unraisablehook = state.previous_unraisable  # type: ignore[assignment]
    atexit.unregister(_clean_exit)
    state.stream.close()
    state.marker.unlink(missing_ok=True)
