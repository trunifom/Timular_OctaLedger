"""Tests for the command-line interface: commands, exit codes and error presentation."""

import json
from pathlib import Path
from typing import Any

import pytest

import octaledger.cli as cli
from octaledger import __version__
from octaledger.cli import (
    EXIT_CONFIRM,
    EXIT_ERROR,
    EXIT_INTERRUPTED,
    EXIT_NEGATIVE,
    EXIT_OK,
    build_parser,
    main,
)
from octaledger.core.errors import ConfigurationError
from octaledger.infrastructure.ble.protocol import ORIENTATION_SERVICE_UUID
from tests.conftest import API_TOKEN, RunningApi, free_port

# ---------------------------------------------------------------------------- basics


def test_version_and_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0 and __version__ in capsys.readouterr().out
    assert main([]) == EXIT_OK
    help_text = capsys.readouterr().out
    for command in ("agent", "dashboard", "status", "scan", "paths", "backup", "restore"):
        assert command in help_text


def test_decode_test_still_works(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--decode-test", "3"]) == EXIT_OK
    assert "Test input, not hardware: 3" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["--decode-test", "9"])


def test_unknown_command_is_an_argparse_error() -> None:
    with pytest.raises(SystemExit) as info:
        main(["frobnicate"])
    assert info.value.code == 2


def test_parser_has_data_dir_where_documented() -> None:
    parser = build_parser()
    for command in ("agent", "dashboard", "status", "paths", "backup"):
        assert parser.parse_args([command, "--data-dir", "x"]).data_dir == Path("x")
    assert parser.parse_args(["restore", "f.json", "--yes"]).yes is True


# ----------------------------------------------------------------------- error handling


def test_octaledger_errors_become_one_readable_line_and_exit_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(_args: Any) -> int:
        raise ConfigurationError("bad", user_message="Einstellung kaputt.")

    monkeypatch.setitem(cli._COMMANDS, "paths", failing)
    assert main(["paths"]) == EXIT_ERROR
    err = capsys.readouterr().err
    assert err.strip() == "Fehler [OL-CONFIG-001]: Einstellung kaputt."  # no traceback


def test_ctrl_c_returns_130(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupted(_args: Any) -> int:
        raise KeyboardInterrupt

    monkeypatch.setitem(cli._COMMANDS, "paths", interrupted)
    assert main(["paths"]) == EXIT_INTERRUPTED
    assert "Abgebrochen" in capsys.readouterr().err


# ------------------------------------------------------------------------------- paths


def test_paths_command_shows_all_locations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["paths", "--data-dir", str(tmp_path)]) == EXIT_OK
    out = capsys.readouterr().out
    for label in (
        "Datenordner",
        "Datenbank",
        "Einstellungen",
        "Protokolle",
        "Sicherungen",
        "Exporte",
    ):
        assert label in out
    assert str(tmp_path.resolve()) in out and "octaledger.sqlite3" in out


# ---------------------------------------------------------------------- backup / restore


def test_backup_then_restore_roundtrip_with_confirmation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    assert main(["backup", "--data-dir", str(source)]) == EXIT_OK
    created = list((source / "backups").glob("octaledger-backup-*.json"))
    assert len(created) == 1 and "Sicherung geschrieben" in capsys.readouterr().out

    explicit = tmp_path / "chosen.json"
    assert main(["backup", "--data-dir", str(source), "--output", str(explicit)]) == EXIT_OK
    assert json.loads(explicit.read_text(encoding="utf-8"))["format"] == "octaledger-backup"

    # Without --yes only a preview is shown and nothing changes (exit 3).
    assert main(["restore", str(explicit), "--data-dir", str(target)]) == EXIT_CONFIRM
    out = capsys.readouterr().out
    assert "gültig" in out and "NICHTS verändert" in out
    assert not list((target / "backups").glob("*pre-restore*"))

    assert main(["restore", str(explicit), "--data-dir", str(target), "--yes"]) == EXIT_OK
    assert "Wiederhergestellt" in capsys.readouterr().out
    assert list((target / "backups").glob("octaledger-pre-restore-*.sqlite3"))


def test_restore_rejects_invalid_files_with_an_error_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main(["restore", str(bad), "--data-dir", str(tmp_path / "d"), "--yes"]) == EXIT_ERROR
    err = capsys.readouterr().err
    assert err.startswith("Fehler [OL-DATA-002]") and "keine Daten verändert" in err
    assert (
        main(["restore", str(tmp_path / "missing.json"), "--data-dir", str(tmp_path / "d")])
        == EXIT_ERROR
    )


def _configure_data_dir_for(api: RunningApi, data_dir: Path) -> None:
    """Point a data folder at the running test API (settings.toml port + token file)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "settings.toml").write_text(f"[agent]\nport = {api.port}\n", encoding="utf-8")
    (data_dir / "api_token").write_text(API_TOKEN, encoding="utf-8")


def test_restore_is_refused_while_the_agent_runs(
    api_server: RunningApi, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "live"
    _configure_data_dir_for(api_server, data_dir)
    backup = tmp_path / "b.json"
    backup.write_text(api_server.client.create_backup()["content"], encoding="utf-8")
    assert main(["restore", str(backup), "--data-dir", str(data_dir), "--yes"]) == EXIT_ERROR
    assert "Agent läuft" in capsys.readouterr().err


# --------------------------------------------------------------------------------- status


def test_status_reports_a_running_agent(
    api_server: RunningApi, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "live"
    _configure_data_dir_for(api_server, data_dir)
    api_server.client.register_device("Büro")
    activity = api_server.client.create_item("activities", "Meeting")
    api_server.client.start_tracking(activity["id"])
    assert main(["status", "--data-dir", str(data_dir)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Agent: läuft" in out and "Meeting" in out and "Tracker Büro (aktiv)" in out


def test_status_without_agent_exits_1_and_without_token_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A free port: on a machine where the real agent is running, the default port is taken.
    monkeypatch.setenv("OCTALEDGER_PORT", str(free_port()))
    data_dir = tmp_path / "idle"
    assert main(["status", "--data-dir", str(data_dir)]) == EXIT_ERROR  # no token yet
    assert "Fehler [OL-CONFIG-001]" in capsys.readouterr().err
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "api_token").write_text(API_TOKEN, encoding="utf-8")
    assert main(["status", "--data-dir", str(data_dir)]) == EXIT_NEGATIVE
    assert "Agent läuft nicht" in capsys.readouterr().out


# ----------------------------------------------------------------------------------- scan


def test_scan_prints_results_and_never_connects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from octaledger.infrastructure.ble import scanner

    async def fake_scan(timeout: float, **_k: Any) -> list[Any]:
        return [scanner.ScanResult("AA:BB", "ZEI", -50, (ORIENTATION_SERVICE_UUID,), True)]

    monkeypatch.setattr(scanner, "scan", fake_scan)
    assert main(["scan", "--seconds", "2"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "ZEI" in out and "passend" in out and "nichts verbunden" in out
    assert "AA:BB" not in out  # addresses are not printed

    async def nothing(timeout: float, **_k: Any) -> list[Any]:
        return []

    monkeypatch.setattr(scanner, "scan", nothing)
    assert main(["scan"]) == EXIT_NEGATIVE


def test_scan_invalid_duration_is_a_clear_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scan", "--seconds", "99"]) == EXIT_ERROR
    assert "Fehler [OL-VALID-001]" in capsys.readouterr().err


# ------------------------------------------------------------------- agent and dashboard


def test_agent_command_passes_arguments_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[Any, ...]] = []
    from octaledger.agent import main as agent_main

    monkeypatch.setattr(agent_main, "run_agent", lambda *a: calls.append(a))
    assert main(["agent", "--data-dir", str(tmp_path), "--log-level", "DEBUG"]) == EXIT_OK
    assert calls == [(tmp_path, "DEBUG")]


def test_dashboard_command_is_local_only_and_telemetry_free(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "call", lambda cmd: captured.append(cmd) or 0)
    assert main(["dashboard", "--data-dir", str(tmp_path)]) == EXIT_OK
    (command,) = captured
    assert "streamlit" in command and "run" in command
    assert command[command.index("--server.address") + 1] == "127.0.0.1"
    assert command[command.index("--browser.gatherUsageStats") + 1] == "false"
    assert Path(command[command.index("run") + 1]).exists()  # the packaged entry script


def test_package_entry_script_and_streamlit_config_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / ".streamlit" / "config.toml").read_text(encoding="utf-8").count("false") >= 2
