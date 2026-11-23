"""Tests of the crash reporting (real child processes crash on purpose)."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from octaledger.core import crash
from octaledger.core.crash import install_crash_reporting, uninstall_crash_reporting
from octaledger.core.logging import configure_logging, recent_log_lines

CHILD = textwrap.dedent(
    """
    import faulthandler, sys, threading
    from pathlib import Path
    from octaledger.core.crash import install_crash_reporting
    from octaledger.core.logging import configure_logging

    log_dir = Path(sys.argv[1])
    configure_logging(log_dir=log_dir, console=False)
    install_crash_reporting(log_dir, "agent")
    mode = sys.argv[2]
    if mode == "segfault":
        threading.Thread(target=lambda: None).start()
        faulthandler._sigsegv()
    # mode "clean": just end normally
    """
)


def run_child(log_dir: Path, mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", CHILD, str(log_dir), mode],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.fixture
def clean_state() -> Iterator[None]:
    uninstall_crash_reporting()
    yield
    uninstall_crash_reporting()
    configure_logging(console=False)


def test_a_native_crash_leaves_a_stack_and_is_reported_at_the_next_start(tmp_path: Path) -> None:
    assert run_child(tmp_path, "segfault").returncode != 0
    text = (tmp_path / "crash-agent.log").read_text(encoding="utf-8")
    assert "=== agent pid=" in text
    assert "fatal" in text.lower()  # "Windows fatal exception" / "Fatal Python error"
    assert (tmp_path / "running-agent.json").exists()  # the run never ended cleanly

    second = run_child(tmp_path, "clean")
    assert second.returncode == 0
    log = (tmp_path / "octaledger.log").read_text(encoding="utf-8")
    assert "previous agent run CRASHED natively" in log
    archives = list(tmp_path.glob("crash-agent-*.log"))
    assert len(archives) == 1 and "fatal" in archives[0].read_text(encoding="utf-8").lower()
    assert not (tmp_path / "running-agent.json").exists()  # the clean run removed its marker

    third = run_child(tmp_path, "clean")  # nothing new to report
    assert third.returncode == 0
    assert (tmp_path / "octaledger.log").read_text(encoding="utf-8").count("CRASHED") == 1


def test_a_clean_run_reports_nothing(tmp_path: Path) -> None:
    assert run_child(tmp_path, "clean").returncode == 0
    assert run_child(tmp_path, "clean").returncode == 0
    log = (tmp_path / "octaledger.log").read_text(encoding="utf-8")
    assert "CRASHED" not in log and "did not end cleanly" not in log


def test_a_leftover_marker_without_trace_is_an_unclean_exit(
    tmp_path: Path, clean_state: None
) -> None:
    configure_logging(console=False)
    (tmp_path / "running-agent.json").write_text(
        '{"pid": 0, "started": "2026-01-01T00:00:00+00:00"}', encoding="utf-8"
    )
    found = install_crash_reporting(tmp_path, "agent")
    assert found is not None and found.kind == "unclean_exit"
    assert any("did not end cleanly" in line for line in recent_log_lines())


def test_installing_twice_and_a_live_other_process_are_harmless(
    tmp_path: Path, clean_state: None
) -> None:
    assert install_crash_reporting(tmp_path, "agent") is None
    assert install_crash_reporting(tmp_path, "agent") is None  # second call does nothing
    uninstall_crash_reporting()
    assert not (tmp_path / "running-agent.json").exists()


def test_an_unwritable_log_directory_never_stops_the_application(
    tmp_path: Path, clean_state: None
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert install_crash_reporting(blocker / "logs", "agent") is None


def test_ignored_callback_errors_reach_the_log(clean_state: None) -> None:
    """The hook is called directly: pytest installs its own ``sys.unraisablehook``."""
    configure_logging(console=False)
    error = ValueError("in a callback")
    args = SimpleNamespace(
        exc_type=ValueError,
        exc_value=error,
        exc_traceback=error.__traceback__,
        err_msg="Exception ignored in cffi callback",
        object=None,
    )
    crash._log_unraisable(args)  # type: ignore[arg-type]
    text = "\n".join(recent_log_lines())
    assert "Exception ignored in cffi callback" in text and "ValueError: in a callback" in text


def test_asyncio_and_warning_records_reach_the_log_file(tmp_path: Path, clean_state: None) -> None:
    import logging

    configure_logging(log_dir=tmp_path, console=False)
    logging.getLogger("asyncio").error("Task exception was never retrieved")
    text = "\n".join(recent_log_lines())
    assert "Task exception was never retrieved" in text
    # Python warnings use the "py.warnings" logger; it must reach the same sinks.
    assert logging.getLogger("py.warnings").handlers


def test_old_crash_reports_are_pruned(tmp_path: Path) -> None:
    for number in range(crash.KEEP_REPORTS + 3):
        (tmp_path / f"crash-agent-2026010{number}-000000.log").write_text("x", encoding="utf-8")
    crash._prune_reports(tmp_path, "agent")
    assert len(list(tmp_path.glob("crash-agent-*.log"))) == crash.KEEP_REPORTS
