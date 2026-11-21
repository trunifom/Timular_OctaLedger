"""Overview page: what runs now, quick start, today's entries and a first-steps guide.

Layout (top to bottom, see ``docs/GUI_KONZEPT.md``):

1. *Erste Schritte* checklist - only while the setup is incomplete, dismissible.
2. The big **running timer** block with pause/stop (auto-refreshing).
3. **Schnellstart** tiles for the most used activities - one click to start.
4. **Heute** - total of today and this week plus today's entries.
5. The manual start form for any other activity, folded away (progressive disclosure).
"""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import (
    STATE_LABELS,
    STATE_LEVEL,
    call,
    format_hm,
    format_hms,
    format_local,
    from_local,
    page_help,
    status_dot,
)
from octaledger.dashboard_client.client import ApiClient

NO_PROJECT = "– kein Projekt –"
QUICK_TILES = 4
HIDE_STEPS_KEY = "hide_first_steps"


def render(client: ApiClient, tz: str) -> None:
    """Render the overview page."""
    st.header("Übersicht")
    page_help(
        "So funktioniert die Übersicht",
        "Hier sehen Sie auf einen Blick, **was gerade läuft**, und starten mit einem Klick die "
        "nächste Tätigkeit.\n\n"
        "- **Automatisch:** Drehen Sie den Würfel auf die Seite einer Tätigkeit, die Zeit startet "
        "von selbst.\n"
        "- **Von Hand:** *Schnellstart*, *Pause* und *Stopp* steuern die Zeiterfassung auch ohne "
        "Würfel.\n"
        "- **Heute:** Ihre Summen und die Einträge des Tages. Korrigieren geht im *Zeitjournal*.\n"
        "- Die Anzeige aktualisiert sich alle 5 Sekunden; mit *Neu laden* sofort.",
    )
    _first_steps(client)
    _live_status(client, tz)
    ok_a, activities = call(client.list_items, "activities")
    ok_p, projects = call(client.list_items, "projects")
    if not ok_a or not ok_p or activities is None or projects is None:
        return
    _quick_start(client, activities)
    _today(client, tz)
    _start_form(client, activities, projects)


# ------------------------------------------------------------------------- first steps


def _first_steps(client: ApiClient) -> None:
    """Checklist guiding a new user through the setup; hidden when done or dismissed."""
    if st.session_state.get(HIDE_STEPS_KEY):
        return
    try:
        activities = client.list_items("activities")
        devices = client.devices()
        now = datetime.now(timezone.utc)
        entries = client.journal(now - timedelta(days=365), now + timedelta(days=1))
    except OctaLedgerError:
        return  # the checklist is a convenience; real errors are shown by the page itself
    steps = [
        ("Tätigkeiten anlegen", bool(activities), "catalog", "Zu Tätigkeiten & Projekten"),
        ("Tracker registrieren", bool(devices), "start", "Zur Einrichtung"),
        (
            "Bluetooth-Gerät zuordnen",
            any(d["has_address"] for d in devices),
            "start",
            "Zur Einrichtung",
        ),
        (
            "Würfelseiten Tätigkeiten zuordnen",
            any(d["configured_faces"] for d in devices),
            "faces",
            "Seiten zuordnen",
        ),
        ("Ersten Eintrag erfassen", bool(entries), "overview", "Jetzt starten"),
    ]
    done = sum(1 for _, finished, _, _ in steps if finished)
    if done == len(steps):
        return
    with st.container(border=True, key="first_steps"):
        st.markdown(f"**Erste Schritte** · {done} von {len(steps)} erledigt")
        st.progress(done / len(steps))
        next_open = next((i for i, (_, finished, _, _) in enumerate(steps) if not finished), None)
        for index, (title, finished, slug, action) in enumerate(steps):
            text_col, button_col = st.columns([5, 2], vertical_alignment="center")
            text_col.markdown(
                ("✔ " if finished else "○ ") + (f"~~{title}~~" if finished else title)
            )
            if not finished and index == next_open and slug != "overview":
                button_col.button(
                    action,
                    key=f"step_{index}",
                    on_click=go,
                    args=(slug,),
                    type="primary",
                    width="stretch",
                    help=f"Öffnet den Bereich für den Schritt „{title}“.",
                )
        st.button(
            "Ausblenden",
            key="hide_steps",
            type="tertiary",
            on_click=lambda: st.session_state.update({HIDE_STEPS_KEY: True}),
            help="Blendet diese Liste aus. Sie erscheint erst in einer neuen Sitzung wieder.",
        )


# ------------------------------------------------------------------------ running block


@st.fragment(run_every="5s")
def _live_status(client: ApiClient, tz: str) -> None:
    """The auto-refreshing part: running entry, buttons, tracker."""
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
                f'**<span class="ol-num">{format_hms(tracking["elapsed_seconds"])}</span>** · '
                f"gestartet {format_local(running['started_at'], tz)}"
                + (f" · Projekt: {project['name']}" if project else "")
                + (
                    " · Quelle: Tracker" if running["source"] == "device" else " · Quelle: von Hand"
                ),
                unsafe_allow_html=True,
            )
            if running["quality"] == "uncertain":
                st.warning(
                    "Diese Zeit ist als **unsicher** markiert (Verbindung war unterbrochen). "
                    "Bitte unter *Zeitjournal → Zu prüfen* bestätigen oder korrigieren.",
                    icon="⚠️",
                )
            pause_col, stop_col = st.columns(2)
            if pause_col.button(
                "Pause",
                key="btn_pause",
                icon=":material/pause:",
                width="stretch",
                help="Beendet die laufende Zeit und merkt sich die Tätigkeit. Mit „Fortsetzen“ "
                "geht es dort weiter.",
            ):
                if call(client.pause_tracking)[0]:
                    st.rerun(scope="app")
            if stop_col.button(
                "Stopp",
                key="btn_stop",
                icon=":material/stop:",
                type="primary",
                width="stretch",
                help="Beendet die laufende Zeit.",
            ):
                if call(client.stop_tracking)[0]:
                    st.rerun(scope="app")
        elif tracking["paused"]:
            st.markdown('<div class="ol-big">Pausiert</div>', unsafe_allow_html=True)
            if st.button(
                "Fortsetzen",
                key="btn_resume",
                icon=":material/play_arrow:",
                type="primary",
                help="Startet die zuletzt pausierte Tätigkeit erneut.",
            ):
                if call(client.resume_tracking)[0]:
                    st.rerun(scope="app")
        else:
            st.markdown(
                '<div class="ol-big">Keine Zeiterfassung läuft</div>', unsafe_allow_html=True
            )
            st.caption(
                "Drehen Sie den Würfel oder starten Sie unten eine Tätigkeit mit einem Klick."
            )

    _tracker_box(status)
    if st.button(
        "Neu laden",
        key="btn_reload",
        icon=":material/refresh:",
        type="tertiary",
        help="Aktualisiert die Anzeige sofort.",
    ):
        st.rerun(scope="app")


def _tracker_box(status: dict[str, Any]) -> None:
    """Show the trackers and their connection state (details: battery, last message)."""
    devices = status["devices"]
    with st.container(border=True):
        st.markdown("**Tracker**")
        if not devices:
            st.info(
                "Es ist noch kein Tracker registriert. Öffnen Sie den Bereich "
                "**Würfel verwalten**, um einen Würfel einzurichten."
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


# ------------------------------------------------------------------------- quick start


def _quick_start(client: ApiClient, activities: list[dict[str, Any]]) -> None:
    """One-click tiles for the most used activities of the last 30 days."""
    if not activities:
        st.info("Legen Sie zuerst im Bereich **Tätigkeiten & Projekte** eine Tätigkeit an.")
        return
    now = datetime.now(timezone.utc)
    _, entries = call(client.journal, now - timedelta(days=30), now + timedelta(days=1))
    usage = Counter(e["activity_id"] for e in (entries or []))
    ranked = sorted(activities, key=lambda a: (-usage[a["id"]], a["name"].lower()))[:QUICK_TILES]
    st.subheader("Schnellstart")
    columns = st.columns(len(ranked))
    for column, activity in zip(columns, ranked, strict=False):
        if column.button(
            activity["name"],
            key=f"quick_{activity['id']}",
            icon=":material/play_arrow:",
            width="stretch",
            help=f"Startet „{activity['name']}“ sofort. Eine laufende Zeit wird dabei beendet.",
        ):
            if call(client.start_tracking, activity["id"])[0]:
                st.rerun()


# ----------------------------------------------------------------------------- today


def _today(client: ApiClient, tz: str) -> None:
    """Totals for today and this week plus the entries of today."""
    today = datetime.now(ZoneInfo(tz)).date()
    ok_d, day = call(client.day_report, today, tz=tz)
    ok_w, week = call(client.week_report, today, tz=tz)
    if not (ok_d and ok_w) or day is None or week is None:
        return
    st.subheader("Heute")
    a, b, c = st.columns(3)
    a.metric(
        "Heute",
        format_hm(day["personal_seconds"]),
        help="Ihre Arbeitszeit heute (ohne Doppelzählung).",
    )
    b.metric(
        "Diese Woche",
        format_hm(week["personal_seconds"]),
        help="Ihre Arbeitszeit seit Montag (ohne Doppelzählung).",
    )
    c.metric(
        "Davon unsicher heute",
        format_hm(day["uncertain_seconds"]),
        help="Noch nicht bestätigte Zeit von heute. Bestätigen Sie sie im Zeitjournal.",
    )
    ok, entries = call(
        client.journal,
        from_local(today, time(0, 0), tz),
        from_local(today + timedelta(days=1), time(0, 0), tz),
    )
    if not ok or entries is None:
        return
    if not entries:
        st.caption("Heute gibt es noch keine Einträge.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Beginn": format_local(e["started_at"], tz)[-5:],
                    "Ende": "läuft" if e["running"] else format_local(e["ended_at"], tz)[-5:],
                    "Dauer": format_hm(e["duration_seconds"]),
                    "Tätigkeit": e["activity_name"],
                    "Projekt": e["project_name"] or "–",
                    "Qualität": "unsicher" if e["quality"] == "uncertain" else "bestätigt",
                }
                for e in entries
            ]
        ),
        hide_index=True,
        width="stretch",
        key="today_table",
    )


# --------------------------------------------------------------------------- manual form


def _start_form(
    client: ApiClient, activities: list[dict[str, Any]], projects: list[dict[str, Any]]
) -> None:
    """Form to start any activity with project and note (folded away by default)."""
    if not activities:
        return
    with st.expander("Mit Projekt oder Notiz starten"):
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
            if st.form_submit_button(
                "Start",
                icon=":material/play_arrow:",
                type="primary",
                help="Startet jetzt einen Eintrag mit der gewählten Tätigkeit.",
            ):
                started, _ = call(
                    client.start_tracking,
                    activity["id"],
                    project["id"] if project else None,
                    note.strip() or None,
                )
                if started:
                    st.rerun()
