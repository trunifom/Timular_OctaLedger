"""The always-visible status bar at the top of every page.

Research finding (Timeular reviews): the most common problem is a Bluetooth connection that
drops **without the user noticing**, so recording silently stops. Therefore every page starts
with the same compact bar that answers three questions at a glance:

1. *What is running?* (activity, elapsed time, stop button)
2. *Is the tracker connected?* (state as text + icon, never colour alone)
3. *Is there anything I must do?* (disconnected tracker, entries waiting for confirmation)

The bar refreshes itself every 5 seconds and fails silently (the page itself shows API errors).
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import STATE_LABELS, STATE_LEVEL, format_hms
from octaledger.dashboard_client.client import ApiClient

#: Connection states in which recording from the tracker is **not** happening.
NOT_RECORDING = {"disconnected", "reconnect_wait", "stopped", "idle"}
LEVEL_ICON = {"ok": "✔", "warn": "▲", "bad": "✖"}


def tracker_summary(status: dict[str, Any]) -> tuple[str, str, bool]:
    """Describe the active tracker for the bar.

    Returns:
        ``(text, level, needs_attention)`` where ``level`` is ``ok``/``warn``/``bad`` and
        ``needs_attention`` is true when a registered tracker is not delivering values.
    """
    devices = status["devices"]
    if not devices:
        return "Kein Tracker eingerichtet", "warn", False
    active = next((d for d in devices if d["is_active"]), devices[0])
    mark = {"control": " (Steuerung)", "music": " (Musik)"}.get(active.get("mode", ""), "")
    live = active["live"]
    if live is None:
        return f"{active['alias']}{mark}: nicht verbunden", "bad", True
    state = live["state"]
    text = f"{active['alias']}{mark}: {STATE_LABELS.get(state, state)}"
    level = STATE_LEVEL.get(state, "warn")
    return text, level, state in NOT_RECORDING


@st.fragment(run_every="5s")
def status_bar(client: ApiClient) -> None:
    """Render the status bar (auto-refreshing)."""
    try:
        status = client.status()
    except OctaLedgerError:
        return
    tracking = status["tracking"]
    running = tracking["running"]
    text, level, attention = tracker_summary(status)

    with st.container(border=True, key="statusbar"):
        left, middle, right = st.columns([5, 4, 2], vertical_alignment="center")
        if running:
            activity = tracking["activity"] or {"name": "Unbekannt", "color": "#808080"}
            left.markdown(
                f'<span class="ol-dot" style="background:{html.escape(activity["color"])}"></span>'
                f"<b>{html.escape(activity['name'])}</b> "
                f'<span class="ol-num">{format_hms(tracking["elapsed_seconds"])}</span>',
                unsafe_allow_html=True,
            )
        elif tracking["paused"]:
            left.markdown("**Pausiert**")
        else:
            left.markdown(
                '<span class="ol-muted">Keine Zeiterfassung läuft</span>', unsafe_allow_html=True
            )
        css_class = {"ok": "ol-ok", "warn": "ol-warn", "bad": "ol-bad"}[level]
        middle.markdown(
            f'<span class="{css_class}">{LEVEL_ICON[level]}</span> {html.escape(text)}',
            unsafe_allow_html=True,
        )
        if running and right.button(
            "Stopp",
            key="bar_stop",
            icon=":material/stop:",
            width="stretch",
            help="Beendet die laufende Zeit.",
        ):
            try:
                client.stop_tracking()
            except OctaLedgerError:
                st.error("Die Zeiterfassung konnte nicht gestoppt werden.")
            else:
                st.rerun(scope="app")

    if attention and status["devices"]:
        st.warning(
            "**Der Tracker liefert gerade keine Werte.** Würfelbewegungen werden nicht erfasst, "
            "bis die Verbindung wieder steht (Bereich *Würfel verwalten*).",
            icon=":material/bluetooth_disabled:",
        )
    if tracking["uncertain_count"]:
        message, action = st.columns([6, 2], vertical_alignment="center")
        message.warning(
            f"**{tracking['uncertain_count']} Eintrag/Einträge sind unsicher** und warten auf Ihre "
            "Bestätigung.",
            icon=":material/help:",
        )
        action.button(
            "Jetzt prüfen",
            key="bar_review",
            on_click=go,
            args=("journal",),
            width="stretch",
            help="Öffnet das Zeitjournal, wo Sie unsichere Einträge bestätigen oder korrigieren.",
        )
