"""Overview page: what runs now, start/stop/pause, the active tracker and data quality."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from octaledger.dashboard.ui import (
    STATE_LABELS,
    STATE_LEVEL,
    call,
    format_hms,
    format_local,
    page_help,
    status_dot,
)
from octaledger.dashboard_client.client import ApiClient

NO_PROJECT = "– kein Projekt –"


def render(client: ApiClient, tz: str) -> None:
    """Render the overview page."""
    st.header("Übersicht")
    page_help(
        "So funktioniert die Übersicht",
        "Hier sehen Sie auf einen Blick, **was gerade läuft**, ob Ihr **Tracker verbunden** ist "
        "und ob Zeiten **noch geprüft** werden müssen.\n\n"
        "- **Automatisch:** Drehen Sie den Würfel auf die Seite einer Tätigkeit, die Zeit startet "
        "von selbst.\n"
        "- **Von Hand:** Mit *Start*, *Pause* und *Stopp* steuern Sie die Zeiterfassung auch ohne "
        "Würfel.\n"
        "- Die Anzeige aktualisiert sich alle 5 Sekunden; mit *Neu laden* sofort.",
    )
    _live_status(client, tz)
    st.divider()
    _start_form(client)


@st.fragment(run_every="5s")
def _live_status(client: ApiClient, tz: str) -> None:
    """The auto-refreshing part: running session, buttons, tracker and quality."""
    ok, status = call(client.status)
    if not ok or status is None:
        return
    tracking: dict[str, Any] = status["tracking"]
    running = tracking["running"]

    with st.container(border=True):
        if running:
            activity = tracking["activity"] or {"name": "Unbekannt", "color": "#808080"}
            project = tracking["project"]
            st.markdown(
                f'<div class="ol-big"><span class="ol-dot" style="background:'
                f'{html.escape(activity["color"])}"></span>{html.escape(activity["name"])}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**{format_hms(tracking['elapsed_seconds'])}** · gestartet "
                f"{format_local(running['started_at'], tz)}"
                + (f" · Projekt: {project['name']}" if project else "")
                + (" · Quelle: Tracker" if running["source"] == "device" else " · Quelle: von Hand")
            )
            if running["quality"] == "uncertain":
                st.warning(
                    "Diese Zeit ist als **unsicher** markiert (Verbindung war unterbrochen). "
                    "Bitte unter *Zeitjournal → Zu prüfen* bestätigen oder korrigieren.",
                    icon="⚠️",
                )
            pause_col, stop_col = st.columns(2)
            if pause_col.button(
                "⏸ Pause",
                key="btn_pause",
                width="stretch",
                help="Beendet die laufende Zeit und merkt sich die Tätigkeit. Mit „Fortsetzen“ "
                "geht es dort weiter.",
            ):
                if call(client.pause_tracking)[0]:
                    st.rerun(scope="app")
            if stop_col.button(
                "⏹ Stopp",
                key="btn_stop",
                type="primary",
                width="stretch",
                help="Beendet die laufende Zeit.",
            ):
                if call(client.stop_tracking)[0]:
                    st.rerun(scope="app")
        elif tracking["paused"]:
            st.markdown('<div class="ol-big">⏸ Pausiert</div>', unsafe_allow_html=True)
            if st.button(
                "▶ Fortsetzen",
                key="btn_resume",
                type="primary",
                help="Startet die zuletzt pausierte Tätigkeit erneut.",
            ):
                if call(client.resume_tracking)[0]:
                    st.rerun(scope="app")
        else:
            st.markdown(
                '<div class="ol-big">Keine Zeiterfassung läuft</div>', unsafe_allow_html=True
            )
            st.caption("Drehen Sie den Würfel oder starten Sie unten eine Tätigkeit von Hand.")

    _tracker_box(status)

    if tracking["uncertain_count"]:
        st.warning(
            f"**{tracking['uncertain_count']} Sitzung(en) sind unsicher** und warten auf Ihre "
            "Bestätigung (Zeitjournal → *Zu prüfen*). Bis dahin gelten Auswertungen nur "
            "mit Vorbehalt.",
            icon="⚠️",
        )
    if st.button("🔄 Neu laden", key="btn_reload", help="Aktualisiert die Anzeige sofort."):
        st.rerun(scope="app")


def _tracker_box(status: dict[str, Any]) -> None:
    """Show the active tracker and its connection state."""
    devices = status["devices"]
    with st.container(border=True):
        st.markdown("**Tracker**")
        if not devices:
            st.info(
                "Es ist noch kein Tracker registriert. Öffnen Sie den Bereich **Geräte**, um "
                "einen Würfel einzurichten."
            )
            return
        for device in devices:
            live = device["live"]
            label = STATE_LABELS.get(live["state"], live["state"]) if live else "Nicht verbunden"
            level = STATE_LEVEL.get(live["state"], "warn") if live else "bad"
            star = " ⭐ aktiv" if device["is_active"] else ""
            st.markdown(
                status_dot(level, f"**{html.escape(device['alias'])}**{star} – {label}"),
                unsafe_allow_html=True,
            )
            if live and live.get("battery_percent") is not None:
                st.caption(f"Batterie: {live['battery_percent']} %")
            if live and live.get("last_error"):
                st.caption(f"Letzte Meldung: {live['last_error']}")
        if not status["agent_running"]:
            st.caption("Die Bluetooth-Verbindung ist in diesem Prozess nicht aktiv.")


def _start_form(client: ApiClient) -> None:
    """Form to start a session manually."""
    st.subheader("Von Hand starten")
    ok, activities = call(client.list_items, "activities")
    ok_p, projects = call(client.list_items, "projects")
    if not ok or not ok_p or activities is None or projects is None:
        return
    if not activities:
        st.info("Legen Sie zuerst im Bereich **Verwaltung** eine Tätigkeit an.")
        return
    with st.form("start_form"):
        activity = st.selectbox(
            "Tätigkeit",
            activities,
            format_func=lambda a: a["name"],
            key="start_activity",
            help="Was Sie jetzt tun. Eine laufende Zeit wird dabei automatisch beendet.",
        )
        project = st.selectbox(
            "Projekt (optional)",
            [None, *projects],
            format_func=lambda p: NO_PROJECT if p is None else p["name"],
            key="start_project",
            help="Wofür die Zeit gebucht wird. Kann leer bleiben.",
        )
        note = st.text_input(
            "Notiz (optional)",
            key="start_note",
            max_chars=500,
            help="Freier Text, z. B. „Angebot Müller“. Erscheint im Zeitjournal und im Export.",
        )
        if st.form_submit_button("▶ Start", type="primary"):
            started, _ = call(
                client.start_tracking,
                activity["id"],
                project["id"] if project else None,
                note.strip() or None,
            )
            if started:
                st.rerun()
