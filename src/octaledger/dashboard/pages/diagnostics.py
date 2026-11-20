"""Diagnostics page: device states, database check, redacted logs and an anonymised report."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from octaledger import __version__
from octaledger.dashboard.ui import STATE_LABELS, call, format_local, page_help
from octaledger.dashboard_client.client import ApiClient


def build_report(
    devices: list[dict[str, Any]], integrity: dict[str, Any], log_lines: list[str]
) -> str:
    """Build a text report that is safe to share (F-19).

    Device **names are replaced** by "Gerät 1, 2 ...", Bluetooth addresses are never part of
    the API data, and the log lines are already redacted by the agent (tokens, passwords and
    address fragments are masked). User-chosen names of activities/projects are not included.
    """
    lines = [
        "OctaLedger Diagnosebericht (anonymisiert)",
        f"Programmversion: {__version__}",
        f"Erstellt: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        f"Datenbank-Integrität: {'in Ordnung' if integrity.get('ok') else 'PROBLEME'}",
    ]
    lines += [f"  - {p}" for p in integrity.get("problems", [])]
    lines += ["", "Geräte:"]
    for index, device in enumerate(devices, start=1):
        live = device["status"] or {}
        lines.append(
            f"  Gerät {index}: aktiv={'ja' if device['is_active'] else 'nein'}, "
            f"Zustand={live.get('state', 'nicht verbunden')}, "
            f"Fehlversuche={live.get('attempt', 0)}, "
            f"Seiten zugeordnet={device['configured_faces']}/8, "
            f"Adresse={'ja' if device['has_address'] else 'nein'}, "
            f"Modell={device['model'] or '?'}, Firmware={device['firmware'] or '?'}"
        )
    lines += ["", "Letzte Protokollzeilen:", *log_lines]
    return "\n".join(lines) + "\n"


def _or(value: Any, fallback: str) -> Any:
    """``value`` unless it is ``None`` (0 is a valid value and must not be replaced)."""
    return fallback if value is None else value


def render(client: ApiClient, tz: str) -> None:
    """Render the diagnostics page."""
    st.header("Diagnose")
    page_help(
        "So nutzen Sie die Diagnose",
        "Hier finden Sie Informationen, wenn etwas nicht wie erwartet funktioniert.\n\n"
        "- **Geräte:** Zustand, Fehlversuche und letzte Meldung je Tracker.\n"
        "- **Datenbank prüfen:** Prüft die Datei auf Beschädigungen.\n"
        "- **Protokoll:** Die letzten Ereignisse des Agenten. Passwörter, Tokens und Teile von "
        "Bluetooth-Adressen sind automatisch unkenntlich gemacht.\n"
        "- **Diagnosebericht:** Eine anonymisierte Textdatei (ohne Gerätenamen, Adressen, "
        "Tätigkeiten) – Sie können sie bei einer Fehlermeldung mitschicken.",
    )
    ok, devices = call(client.devices)
    if not ok or devices is None:
        return

    st.subheader("Geräte")
    if not devices:
        st.info("Noch kein Tracker registriert.")
    for device in devices:
        live = device["status"]
        with st.container(border=True):
            st.markdown(f"**{device['alias']}**" + (" ⭐ aktiv" if device["is_active"] else ""))
            if live is None:
                st.caption("Nicht verbunden – es läuft kein Verbindungsversuch.")
                continue
            st.caption(
                f"Zustand: {STATE_LABELS.get(live['state'], live['state'])} · "
                f"Fehlversuche: {live['attempt']} · letzter Wert: {_or(live['last_value'], '–')}"
                f" · letztes Ereignis: {format_local(live['last_event_at'], tz, with_seconds=True)}"
            )
            st.caption(
                f"Batterie: {_or(live['battery_percent'], 'unbekannt')}"
                f" · verworfene Werte: {live['dropped_values']} · ignorierte Duplikate: "
                f"{live['duplicates_ignored']}"
            )
            if live["last_error"]:
                st.warning(f"Letzte Meldung: {live['last_error']}", icon="⚠️")

    st.subheader("Datenbank")
    integrity: dict[str, Any] = st.session_state.get("_integrity") or {"ok": True, "problems": []}
    if st.button(
        "🔎 Datenbank prüfen",
        key="btn_integrity",
        help="Führt die Integritätsprüfung der SQLite-Datenbank aus (dauert Sekunden).",
    ):
        done, result = call(client.integrity)
        if done and result:
            integrity = st.session_state["_integrity"] = result
    if "_integrity" in st.session_state:
        if integrity["ok"]:
            st.success("Die Datenbank ist in Ordnung.")
        else:
            st.error("Die Datenbank meldet Probleme: " + "; ".join(integrity["problems"]))

    st.subheader("Protokoll")
    limit = st.slider(
        "Anzahl Zeilen",
        10,
        500,
        100,
        step=10,
        key="log_limit",
        help="Wie viele der letzten Protokollzeilen angezeigt werden.",
    )
    ok_logs, lines = call(client.logs, limit)
    if ok_logs and lines is not None:
        st.code("\n".join(lines) if lines else "(noch keine Einträge)", language="text")
        st.download_button(
            "⬇️ Diagnosebericht (anonymisiert)",
            build_report(devices, integrity, lines).encode("utf-8"),
            file_name="octaledger-diagnose.txt",
            mime="text/plain",
            key="download_diag",
            help="Textdatei ohne Gerätenamen, Adressen und Tätigkeiten – geeignet zum Weitergeben.",
        )
