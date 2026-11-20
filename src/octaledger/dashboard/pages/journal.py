"""Time journal: filter, review uncertain sessions, correct, split, delete, add past time."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from octaledger.dashboard.ui import (
    call,
    format_hm,
    format_local,
    from_local,
    page_help,
    to_local,
)
from octaledger.dashboard_client.client import ApiClient

ALL = "Alle"
QUALITY_LABELS = {"confirmed": "bestätigt", "uncertain": "unsicher"}


def render(client: ApiClient, tz: str) -> None:
    """Render the journal page."""
    st.header("Zeitjournal")
    page_help(
        "So funktioniert das Zeitjournal",
        "Hier sehen und korrigieren Sie Ihre erfassten Zeiten.\n\n"
        "- **Journal:** Filtern Sie nach Zeitraum, Tätigkeit, Projekt oder Gerät, wählen Sie eine "
        "Sitzung und **korrigieren**, **teilen** oder **löschen** Sie sie.\n"
        "- **Zu prüfen:** Zeiten mit *unsicherer* Qualität (z. B. nach einem "
        "Verbindungsabbruch). Bestätigen Sie sie, wenn der Zeitraum stimmt.\n"
        "- **Nachtragen:** Eine vergangene Zeit von Hand eintragen.\n\n"
        "**Nichts geht verloren:** Jede Korrektur und jedes Löschen verlangt einen **Grund** "
        "und wird nachvollziehbar protokolliert.",
    )
    ok_a, activities = call(client.list_items, "activities", True)
    ok_p, projects = call(client.list_items, "projects", True)
    ok_d, devices = call(client.devices)
    if not (ok_a and ok_p and ok_d) or activities is None or projects is None or devices is None:
        return
    journal_tab, review_tab, add_tab = st.tabs(["Journal", "Zu prüfen", "Nachtragen"])
    with journal_tab:
        _journal(client, tz, activities, projects, devices)
    with review_tab:
        _review(client, tz)
    with add_tab:
        _add(
            client,
            tz,
            [a for a in activities if not a["archived"]],
            [p for p in projects if not p["archived"]],
        )


def _filters(
    activities: list[dict[str, Any]], projects: list[dict[str, Any]], devices: list[dict[str, Any]]
) -> tuple[date, date, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    today = date.today()
    first, second = st.columns(2)
    start = first.date_input(
        "Von",
        today - timedelta(days=6),
        key="journal_from",
        format="DD.MM.YYYY",
        help="Erster Tag des Zeitraums (Ihre Zeitzone).",
    )
    end = second.date_input(
        "Bis (einschließlich)",
        today,
        key="journal_to",
        format="DD.MM.YYYY",
        help="Letzter Tag des Zeitraums, einschließlich.",
    )
    a_col, p_col, d_col = st.columns(3)
    activity = a_col.selectbox(
        "Tätigkeit",
        [None, *activities],
        key="journal_activity",
        format_func=lambda a: ALL if a is None else a["name"],
        help="Nur Zeiten dieser Tätigkeit anzeigen.",
    )
    project = p_col.selectbox(
        "Projekt",
        [None, *projects],
        key="journal_project",
        format_func=lambda p: ALL if p is None else p["name"],
        help="Nur Zeiten dieses Projekts anzeigen.",
    )
    device = d_col.selectbox(
        "Gerät",
        [None, *devices],
        key="journal_device",
        format_func=lambda d: ALL if d is None else d["alias"],
        help="Nur Zeiten, die dieser Tracker erzeugt hat.",
    )
    return start, end, activity, project, device


def _journal(
    client: ApiClient,
    tz: str,
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    devices: list[dict[str, Any]],
) -> None:
    start, end, activity, project, device = _filters(activities, projects, devices)
    if end < start:
        st.error("Das Ende liegt vor dem Beginn. Bitte den Zeitraum korrigieren.")
        return
    ok, entries = call(
        client.journal,
        from_local(start, time(0, 0), tz),
        from_local(end + timedelta(days=1), time(0, 0), tz),
        device_id=device["id"] if device else None,
        activity_id=activity["id"] if activity else None,
        project_id=project["id"] if project else None,
    )
    if not ok or entries is None:
        return
    if not entries:
        st.info("Im gewählten Zeitraum gibt es keine Zeiten.")
        return
    total = sum(e["duration_seconds"] for e in entries)
    st.caption(f"{len(entries)} Sitzung(en), zusammen {format_hm(total)} (Gerätezeit)")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Beginn": format_local(e["started_at"], tz),
                    "Ende": "läuft" if e["running"] else format_local(e["ended_at"], tz),
                    "Dauer": format_hm(e["duration_seconds"]),
                    "Tätigkeit": e["activity_name"],
                    "Projekt": e["project_name"] or "–",
                    "Gerät": e["device_alias"] or "von Hand",
                    "Qualität": QUALITY_LABELS.get(e["quality"], e["quality"]),
                    "Rev.": e["revision"],
                    "Notiz": e["note"] or "",
                }
                for e in entries
            ]
        ),
        hide_index=True,
        width="stretch",
        key="journal_table",
    )
    _edit(
        client,
        tz,
        entries,
        [a for a in activities if not a["archived"]],
        [p for p in projects if not p["archived"]],
    )


def _label(entry: dict[str, Any], tz: str) -> str:
    end = "läuft" if entry["running"] else format_local(entry["ended_at"], tz)[-5:]
    return f"{format_local(entry['started_at'], tz)} – {end} · {entry['activity_name']}"


def _edit(
    client: ApiClient,
    tz: str,
    entries: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
) -> None:
    st.subheader("Sitzung bearbeiten")
    entry = st.selectbox(
        "Sitzung wählen",
        entries,
        key="edit_pick",
        format_func=lambda e: _label(e, tz),
        help="Die Sitzung, die Sie korrigieren, teilen oder löschen möchten.",
    )
    if entry is None:
        return
    sid = entry["id"]
    correct_tab, split_tab, delete_tab = st.tabs(["Korrigieren", "Teilen", "Löschen"])
    with correct_tab:
        _correct_form(client, tz, entry, activities, projects)
        if entry["quality"] == "uncertain" and st.button(
            "✅ Als bestätigt markieren",
            key=f"confirm_{sid}",
            help="Der Zeitraum stimmt. Entfernt die Markierung „unsicher“.",
        ):
            if call(client.confirm_session, sid)[0]:
                st.rerun()
    with split_tab:
        _split_form(client, tz, entry)
    with delete_tab:
        reason = st.text_input(
            "Grund für das Löschen",
            key=f"del_reason_{sid}",
            max_chars=500,
            help="Pflichtangabe. Wird im Protokoll festgehalten.",
        )
        sure = st.checkbox(
            "Ja, diese Sitzung löschen",
            key=f"del_confirm_{sid}",
            help="Das Löschen kann nicht rückgängig gemacht werden.",
        )
        if st.button(
            "🗑 Löschen",
            key=f"del_{sid}",
            disabled=not sure,
            help="Löscht die Sitzung endgültig (mit Protokolleintrag).",
        ):
            if call(client.delete_session, sid, reason)[0]:
                st.rerun()


def _datetime_inputs(prefix: str, tz: str, iso_value: str | None, label: str) -> tuple[date, time]:
    moment = to_local(iso_value, tz) or datetime.now(timezone.utc).astimezone(ZoneInfo(tz))
    day_col, time_col = st.columns(2)
    day = day_col.date_input(
        f"{label} (Datum)",
        moment.date(),
        key=f"{prefix}_date",
        format="DD.MM.YYYY",
        help=f"{label}: Datum in Ihrer Zeitzone.",
    )
    clock = time_col.time_input(
        f"{label} (Uhrzeit)",
        moment.time().replace(second=0, microsecond=0),
        key=f"{prefix}_time",
        step=60,
        help=f"{label}: Uhrzeit in Ihrer Zeitzone.",
    )
    return day, clock


def _correct_form(
    client: ApiClient,
    tz: str,
    entry: dict[str, Any],
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
) -> None:
    sid = entry["id"]
    activity_options: list[dict[str, Any]] = list(activities)
    if not any(a["id"] == entry["activity_id"] for a in activity_options):
        activity_options.append({"id": entry["activity_id"], "name": entry["activity_name"]})
    project_options: list[dict[str, Any] | None] = [None, *projects]
    with st.form(f"correct_{sid}"):
        activity = st.selectbox(
            "Tätigkeit",
            activity_options,
            key=f"c_act_{sid}",
            format_func=lambda a: a["name"],
            index=next(
                i for i, a in enumerate(activity_options) if a["id"] == entry["activity_id"]
            ),
            help="Die richtige Tätigkeit für diesen Zeitraum.",
        )
        project = st.selectbox(
            "Projekt",
            project_options,
            key=f"c_proj_{sid}",
            format_func=lambda p: "– kein Projekt –" if p is None else p["name"],
            index=next(
                (i for i, p in enumerate(project_options) if p and p["id"] == entry["project_id"]),
                0,
            ),
            help="Optionales Projekt.",
        )
        start_day, start_time = _datetime_inputs(
            f"c_start_{sid}", tz, entry["started_at"], "Beginn"
        )
        end_day, end_time = _datetime_inputs(f"c_end_{sid}", tz, entry["ended_at"], "Ende")
        if entry["running"]:
            st.caption("Die Sitzung läuft noch; das Ende wird nicht geändert.")
        note = st.text_input(
            "Notiz",
            value=entry["note"] or "",
            key=f"c_note_{sid}",
            max_chars=500,
            help="Freier Text; leer lassen, um die Notiz zu entfernen.",
        )
        reason = st.text_input(
            "Grund der Korrektur (Pflicht)",
            key=f"c_reason_{sid}",
            max_chars=500,
            help="Warum ändern Sie diese Zeit? Wird im Protokoll festgehalten.",
        )
        if st.form_submit_button("💾 Korrektur speichern", type="primary"):
            changes: dict[str, Any] = {
                "activity_id": activity["id"],
                "project_id": project["id"] if project else None,
                "started_at": from_local(start_day, start_time, tz),
                "note": note.strip() or None,
            }
            if not entry["running"]:
                changes["ended_at"] = from_local(end_day, end_time, tz)
            if call(client.correct_session, sid, changes, reason)[0]:
                st.rerun()


def _split_form(client: ApiClient, tz: str, entry: dict[str, Any]) -> None:
    sid = entry["id"]
    with st.form(f"split_{sid}"):
        st.caption("Teilt die Sitzung in zwei Teile (z. B. eine vergessene Pause).")
        day, clock = _datetime_inputs(f"s_at_{sid}", tz, entry["started_at"], "Teilen um")
        reason = st.text_input(
            "Grund (Pflicht)",
            key=f"s_reason_{sid}",
            max_chars=500,
            help="Warum wird die Sitzung geteilt?",
        )
        if st.form_submit_button("✂️ Teilen"):
            if call(client.split_session, sid, from_local(day, clock, tz), reason)[0]:
                st.rerun()


def _review(client: ApiClient, tz: str) -> None:
    ok, uncertain = call(client.uncertain_sessions)
    if not ok or uncertain is None:
        return
    if not uncertain:
        st.success("Alles bestätigt – es gibt nichts zu prüfen. 🎉")
        return
    st.warning(
        f"{len(uncertain)} Sitzung(en) sind **unsicher** (z. B. Verbindungsabbruch). Prüfen Sie "
        "den Zeitraum und bestätigen Sie ihn; falls er nicht stimmt, korrigieren Sie ihn im Reiter "
        "*Journal*."
    )
    for session in uncertain:
        end = "läuft" if session["running"] else format_local(session["ended_at"], tz)
        col_text, col_button = st.columns([4, 1])
        col_text.markdown(
            f"**{format_local(session['started_at'], tz)} – {end}** · "
            f"{format_hm(session['duration_seconds'])}"
        )
        if col_button.button(
            "✅ Bestätigen",
            key=f"review_confirm_{session['id']}",
            help="Der Zeitraum stimmt; die Markierung „unsicher“ entfällt.",
        ):
            if call(client.confirm_session, session["id"])[0]:
                st.rerun()


def _add(
    client: ApiClient, tz: str, activities: list[dict[str, Any]], projects: list[dict[str, Any]]
) -> None:
    if not activities:
        st.info("Legen Sie zuerst im Bereich **Verwaltung** eine Tätigkeit an.")
        return
    with st.form("add_form", clear_on_submit=False):
        activity = st.selectbox(
            "Tätigkeit",
            activities,
            key="add_activity",
            format_func=lambda a: a["name"],
            help="Was Sie getan haben.",
        )
        project = st.selectbox(
            "Projekt (optional)",
            [None, *projects],
            key="add_project",
            format_func=lambda p: "– kein Projekt –" if p is None else p["name"],
            help="Optionales Projekt.",
        )
        now = datetime.now(timezone.utc).isoformat()
        start_day, start_time = _datetime_inputs("add_start", tz, now, "Beginn")
        end_day, end_time = _datetime_inputs("add_end", tz, now, "Ende")
        note = st.text_input("Notiz (optional)", key="add_note", max_chars=500, help="Freier Text.")
        if st.form_submit_button("➕ Nachtragen", type="primary"):
            added, _ = call(
                client.add_session,
                activity["id"],
                from_local(start_day, start_time, tz),
                from_local(end_day, end_time, tz),
                project["id"] if project else None,
                note.strip() or None,
            )
            if added:
                st.success("Die Zeit wurde nachgetragen.")
