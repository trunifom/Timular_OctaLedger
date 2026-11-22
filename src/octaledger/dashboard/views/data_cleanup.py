"""The "Löschen" tab of the data page: delete entries of a period, or start over completely.

Deleting is irreversible, so the page follows the safe pattern researched for this project
(AP-33; see ``docs/BENUTZERHANDBUCH.md`` chapter 13):

1. **See what would happen first:** a live preview names the number of entries, the period and
   how many carry a note. Nothing is deleted by looking.
2. **Ask again with the numbers:** the confirm step repeats the count on its button
   ("12 Einträge endgültig löschen"); the *Behalten* button is the safe default.
3. **Type to confirm only for the most dangerous cases** (all entries, factory reset); routine
   deletions do not get a type-in box, otherwise people click through them blindly.
4. **Safety backup:** the agent writes a complete backup first and the page names the file, which
   is the undo (tab *Wiederherstellen*).

Running entries are never touched by these operations.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

import streamlit as st

from octaledger.dashboard.ui import call, format_local, from_local
from octaledger.dashboard_client.client import ApiClient

#: What must be typed to delete *all* entries / to reset everything.
DELETE_ALL_TEXT = "ALLE LÖSCHEN"
RESET_TEXT = "ALLES LÖSCHEN"
ASK_KEY = "cleanup_ask"
RESULT_KEY = "cleanup_result"

OVERVIEW_LABELS = {
    "sessions": "Einträge (gespeichert)",
    "raw_events": "Rohereignisse (gespeichert)",
    "devices": "Würfel (gespeichert)",
    "activities": "Tätigkeiten (gespeichert)",
    "projects": "Projekte (gespeichert)",
    "integrations": "Verbindungen (gespeichert)",
}


def render(client: ApiClient, tz: str) -> None:
    """Draw the tab."""
    ok, overview = call(client.data_overview)
    if not ok or overview is None:
        return
    result = st.session_state.pop(RESULT_KEY, None)
    if result:
        st.success(result)
    st.markdown(
        "Hier löschen Sie gezielt Daten. Vor **jedem** Löschen legt OctaLedger automatisch eine "
        "vollständige Sicherung an; sie ist Ihr **Rückgängig**."
    )
    columns = st.columns(3)
    for index, (key, label) in enumerate(OVERVIEW_LABELS.items()):
        columns[index % 3].metric(
            label, overview[key], help=f"Anzahl {label}, die gerade gespeichert sind."
        )
    st.subheader("Einträge löschen")
    _entries(client, tz, overview)
    st.subheader("Gefahrenzone")
    _danger(client, overview)


def _entries(client: ApiClient, tz: str, overview: dict[str, Any]) -> None:
    if overview["sessions"] == 0:
        st.info("Es sind keine Einträge gespeichert, die man löschen könnte.")
        return
    scope = st.radio(
        "Was soll gelöscht werden?",
        ["period", "all"],
        key="cleanup_scope",
        format_func={"period": "Einträge eines Zeitraums", "all": "Alle Einträge"}.__getitem__,
        horizontal=True,
        help="Ein Zeitraum ist der sichere Normalfall. „Alle Einträge“ verlangt eine zusätzliche "
        "Bestätigung durch Eintippen.",
    )
    start = end = None
    if scope == "period":
        first_col, last_col = st.columns(2)
        first = first_col.date_input(
            "Von",
            date.today() - timedelta(days=29),
            key="cleanup_from",
            format="DD.MM.YYYY",
            help="Erster Tag, einschließlich.",
        )
        last = last_col.date_input(
            "Bis (einschließlich)",
            date.today(),
            key="cleanup_to",
            format="DD.MM.YYYY",
            help="Letzter Tag, einschließlich.",
        )
        if last < first:
            st.error("„Bis“ darf nicht vor „Von“ liegen.")
            return
        start = from_local(first, time(0, 0), tz).isoformat()
        end = from_local(last + timedelta(days=1), time(0, 0), tz).isoformat()
    ok, preview = call(client.preview_entries, start, end)
    if not ok or preview is None:
        return
    count = preview["count"]
    if count == 0:
        st.info("In diesem Zeitraum gibt es keine abgeschlossenen Einträge.")
        return
    st.markdown(
        f"**{count} Einträge** vom {format_local(preview['first'], tz)} bis "
        f"{format_local(preview['last'], tz)}, davon {preview['with_note']} mit Notiz."
    )
    if preview["running_left_out"]:
        st.caption("Der gerade laufende Eintrag wird nie gelöscht.")
    with_events = st.checkbox(
        "Auch die Rohereignisse dieses Zeitraums löschen",
        key="cleanup_events",
        help="Rohereignisse sind die unveränderten Meldungen des Würfels (Diagnose). Für die "
        "Auswertung werden sie nicht gebraucht; löschen spart Platz.",
    )
    if st.button(
        "Löschen …",
        key="cleanup_ask_btn",
        icon=":material/delete:",
        help="Fragt noch einmal nach. Gelöscht wird erst danach.",
    ):
        st.session_state[ASK_KEY] = (start, end, count)
    ask = st.session_state.get(ASK_KEY)
    if ask != (start, end, count):
        return
    with st.container(border=True, key="cleanup_confirm"):
        st.warning(
            f"{count} Einträge werden gelöscht. Vorher entsteht automatisch eine Sicherung.",
            icon="⚠️",
        )
        allowed = True
        if scope == "all":
            typed = st.text_input(
                f"Zur Bestätigung „{DELETE_ALL_TEXT}“ eintippen",
                key="cleanup_typed",
                help="Schutz davor, versehentlich alles zu löschen.",
            )
            allowed = typed.strip() == DELETE_ALL_TEXT
        yes, no = st.columns(2)
        if yes.button(
            f"{count} Einträge endgültig löschen",
            key="cleanup_do",
            type="primary",
            disabled=not allowed,
            width="stretch",
            help="Löscht die gezeigten Einträge. Die Sicherung vorher ist Ihr Rückgängig.",
        ):
            st.session_state.pop(ASK_KEY, None)
            ok, done = call(client.delete_entries, count, start, end, with_events)
            if ok and done:
                st.session_state[RESULT_KEY] = (
                    f"{done['sessions']} Einträge gelöscht. Rückgängig machen: Reiter "
                    f"„Wiederherstellen“, Sicherung **{done['safety_backup']}** (Ordner „backups“)."
                )
                st.rerun()
        if no.button(
            "Behalten",
            key="cleanup_keep",
            width="stretch",
            help="Bricht ab, es wird nichts gelöscht.",
        ):
            st.session_state.pop(ASK_KEY, None)
            st.rerun()


def _danger(client: ApiClient, overview: dict[str, Any]) -> None:
    with st.expander(
        "Alles zurücksetzen (Werkseinstellungen)", expanded=False, key="cleanup_danger"
    ):
        st.error(
            "Löscht **alles**: "
            + ", ".join(
                f"{overview[k]} {label.removesuffix(' (gespeichert)')}"
                for k, label in OVERVIEW_LABELS.items()
            )
            + ", die gespeicherten Zugangsdaten und das Protokoll der Änderungen.",
            icon="🛑",
        )
        st.caption(
            "Vorher wird eine vollständige Sicherung angelegt (ohne Zugangsdaten). Danach ist "
            "OctaLedger so leer wie nach der Installation."
        )
        reset_settings = st.checkbox(
            "Auch die Einstellungen auf die Voreinstellungen zurücksetzen",
            value=True,
            key="cleanup_reset_settings",
            help="Zeitzone, Erkennung der Würfelbewegung, Darstellung und Protokollstufe gehen "
            "auf ihre Standardwerte zurück.",
        )
        typed = st.text_input(
            f"Zur Bestätigung „{RESET_TEXT}“ eintippen",
            key="cleanup_reset_typed",
            help="Schutz davor, versehentlich alles zu löschen.",
        )
        if st.button(
            "Alles löschen und zurücksetzen",
            key="cleanup_reset_do",
            type="primary",
            disabled=typed.strip() != RESET_TEXT,
            help="Löscht alle Daten endgültig (nach der automatischen Sicherung).",
        ):
            ok, done = call(client.factory_reset, typed.strip(), reset_settings)
            if ok and done:
                st.session_state.pop("_display", None)
                st.session_state[RESULT_KEY] = (
                    f"Alles zurückgesetzt. Die Sicherung vorher heißt **{done['safety_backup']}** "
                    "(Ordner „backups“); mit „Wiederherstellen“ bekommen Sie alles zurück."
                )
                st.rerun()
