"""Command-line interface: start the agent and dashboard, diagnose and back up.

Commands
--------
``octaledger agent``      run the background agent (BLE, database, local API)
``octaledger dashboard``  start the Streamlit dashboard (loopback only, no telemetry)
``octaledger status``     is the agent running, which trackers are connected
``octaledger scan``       list Bluetooth devices nearby (explicit; never connects)
``octaledger paths``      show where data, logs, backups and exports live
``octaledger backup``     write a JSON backup (works while the agent runs)
``octaledger restore``    preview or restore a backup (only while the agent is stopped)

Exit codes: ``0`` success, ``1`` negative status (e.g. agent not running), ``2`` error (printed
with its stable code), ``3`` needs confirmation, ``130`` interrupted. Errors are shown as one
readable line ``Fehler [OL-...-nnn]: <message>`` - never as a stack trace.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from octaledger import __version__
from octaledger.application.export_service import ExportService
from octaledger.core.errors import OctaLedgerError
from octaledger.core.fileio import atomic_write_text
from octaledger.core.settings import (
    AppPaths,
    Settings,
    ensure_directories,
    load_settings,
    resolve_paths,
)
from octaledger.domain.orientation import decode_orientation
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

EXIT_OK, EXIT_NEGATIVE, EXIT_ERROR, EXIT_CONFIRM, EXIT_INTERRUPTED = 0, 1, 2, 3, 130


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="octaledger",
        description="OctaLedger - lokale Zeiterfassung für Timeular-/ZEI-Tracker",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--decode-test",
        type=int,
        choices=range(9),
        metavar="0..8",
        help="Nur Test: dekodiert einen Wert ohne Hardware",
    )
    commands = parser.add_subparsers(dest="command", metavar="<befehl>")

    def with_data_dir(command: argparse.ArgumentParser) -> argparse.ArgumentParser:
        """Add the shared ``--data-dir`` option to a sub-command."""
        command.add_argument(
            "--data-dir", type=Path, help="Datenordner (Standard: Benutzerprofil/OctaLedger)"
        )
        return command

    agent = with_data_dir(commands.add_parser("agent", help="Agent starten (Hintergrunderfassung)"))
    agent.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Protokollstufe"
    )
    with_data_dir(commands.add_parser("dashboard", help="Dashboard im Browser starten"))
    with_data_dir(commands.add_parser("status", help="Agentenstatus anzeigen"))
    scan = commands.add_parser("scan", help="Bluetooth-Geräte in der Nähe suchen (verbindet nie)")
    scan.add_argument("--seconds", type=float, default=5.0, help="Suchdauer (1-30 s)")
    with_data_dir(commands.add_parser("paths", help="Speicherorte anzeigen"))
    backup = with_data_dir(commands.add_parser("backup", help="JSON-Sicherung erstellen"))
    backup.add_argument("--output", type=Path, help="Zieldatei (Standard: Backup-Ordner)")
    restore = with_data_dir(
        commands.add_parser("restore", help="Sicherung prüfen/wiederherstellen")
    )
    restore.add_argument("file", type=Path, help="Sicherungsdatei (.json)")
    restore.add_argument(
        "--yes", action="store_true", help="Wiederherstellung ausdrücklich bestätigen"
    )
    return parser


# ------------------------------------------------------------------------------ commands


def _paths(data_dir: Path | None) -> tuple[AppPaths, Settings]:
    paths = resolve_paths(data_dir)
    return paths, load_settings(paths.settings_file)


def _cmd_agent(args: argparse.Namespace) -> int:
    from octaledger.agent.main import run_agent

    run_agent(args.data_dir, args.log_level)
    return EXIT_OK


def _cmd_dashboard(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.data_dir)
    entry = Path(__file__).parent / "dashboard" / "streamlit_app.py"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(entry),
        "--server.address",
        "127.0.0.1",  # the dashboard itself is local-only as well
        "--browser.gatherUsageStats",
        "false",  # no hidden telemetry (Pflichtenheft section 8)
        "--server.enableStaticServing",
        "true",  # serves the self-hosted Inter font from dashboard/static
    ]
    print(f"Dashboard startet auf http://127.0.0.1:8501 (Datenordner: {paths.root})")
    return subprocess.call(command)


def _cmd_status(args: argparse.Namespace) -> int:
    from octaledger.dashboard_client.client import ApiClient

    paths, settings = _paths(args.data_dir)
    client = ApiClient.from_settings(settings.agent, paths.root)
    if not client.is_agent_running():
        print("Der Agent läuft nicht (oder ist nicht erreichbar). Start: octaledger agent")
        return EXIT_NEGATIVE
    status = client.status()
    tracking = status["tracking"]
    running = tracking["running"]
    print("Agent: läuft")
    print(
        "Zeiterfassung:",
        tracking["activity"]["name"]
        if running and tracking["activity"]
        else ("pausiert" if tracking["paused"] else "keine"),
    )
    print(f"Unsichere Sitzungen: {tracking['uncertain_count']}")
    for device in status["devices"]:
        live = device["live"]
        print(
            f"Tracker {device['alias']}{' (aktiv)' if device['is_active'] else ''}: "
            f"{live['state'] if live else 'nicht verbunden'}"
        )
    return EXIT_OK


def _cmd_scan(args: argparse.Namespace) -> int:
    from octaledger.infrastructure.ble.scanner import scan

    results = asyncio.run(scan(args.seconds))
    if not results:
        print(
            "Keine Bluetooth-Geräte gefunden. Ist Bluetooth an und der Würfel wach (einmal drehen)?"
        )
        return EXIT_NEGATIVE
    for result in results:
        mark = (
            "passend"
            if result.is_candidate
            else "vermutet"
            if result.looks_like_tracker
            else " " * 8
        )
        print(f"[{mark}] {result.label}")
    print("Es wurde nichts verbunden. Zuordnung im Dashboard (Bereich Geräte).")
    return EXIT_OK


def _cmd_paths(args: argparse.Namespace) -> int:
    paths = resolve_paths(args.data_dir)
    for label, location in (
        ("Datenordner", paths.root),
        ("Datenbank", paths.database_file),
        ("Einstellungen", paths.settings_file),
        ("Protokolle", paths.logs_dir),
        ("Sicherungen", paths.backups_dir),
        ("Exporte", paths.exports_dir),
    ):
        print(f"{label:14}{location}")
    return EXIT_OK


def _export_service(data_dir: Path | None) -> tuple[AppPaths, ExportService]:
    """Open the database offline (no agent needed) and return its export service."""
    paths = resolve_paths(data_dir)
    ensure_directories(paths)
    database = Database(paths.database_file, backup_dir=paths.backups_dir)
    database.initialize()
    return paths, ExportService(
        Storage(database), exports_dir=paths.exports_dir, backup_dir=paths.backups_dir
    )


def _cmd_backup(args: argparse.Namespace) -> int:
    _, service = _export_service(args.data_dir)
    if args.output is not None:
        atomic_write_text(args.output, service.create_backup_text())
        print(f"Sicherung geschrieben: {args.output}")
    else:
        result = service.export_backup()
        print(f"Sicherung geschrieben: {result.path} ({result.rows} Datensätze)")
    return EXIT_OK


def _cmd_restore(args: argparse.Namespace) -> int:
    from octaledger.dashboard_client.client import ApiClient

    paths, settings = _paths(args.data_dir)
    try:
        running = ApiClient.from_settings(settings.agent, paths.root).is_agent_running()
    except OctaLedgerError:
        running = False  # no token yet means the agent never ran
    if running:
        print("Der Agent läuft. Bitte zuerst beenden, dann wiederherstellen.", file=sys.stderr)
        return EXIT_ERROR
    _, service = _export_service(args.data_dir)
    summary = service.inspect_backup(args.file)
    print(
        f"Die Datei ist gültig (Version {summary.schema_version}, erstellt {summary.exported_at})."
    )
    for name, count in summary.counts.items():
        print(f"  {name}: {count}")
    if not args.yes:
        print(
            "Es wurde NICHTS verändert. Zum Wiederherstellen erneut mit --yes aufrufen "
            "(alle aktuellen Daten werden ersetzt; vorher entsteht eine automatische Kopie)."
        )
        return EXIT_CONFIRM
    result = service.restore_backup(args.file)
    print(f"Wiederhergestellt. Vorheriger Stand: {result.pre_restore_backup}")
    return EXIT_OK


_COMMANDS = {
    "agent": _cmd_agent,
    "dashboard": _cmd_dashboard,
    "status": _cmd_status,
    "scan": _cmd_scan,
    "paths": _cmd_paths,
    "backup": _cmd_backup,
    "restore": _cmd_restore,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the exit code (never raises for OctaLedger errors)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.decode_test is not None:
            print(f"Test input, not hardware: {decode_orientation(bytes([args.decode_test]))}")
            return EXIT_OK
        if args.command is None:
            parser.print_help()
            return EXIT_OK
        return _COMMANDS[args.command](args)
    except OctaLedgerError as exc:
        print(f"Fehler [{exc.error_code}]: {exc.user_message}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("Abgebrochen.", file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
