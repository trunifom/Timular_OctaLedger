"""Appearance page: light or dark, text size. Nothing else - this page is only about looks.

The four kinds of settings of OctaLedger live on four pages so that nobody has to hunt:
*Würfel verwalten* (the cubes), *App* (how time is recorded), **Darstellung** (this page: how the
program looks) and *Smarthome & Verbindungen* (complex functions).

Changes here apply **immediately** (no save button): they are harmless, reversible and the user
sees the result at once - the pattern of the operating systems' appearance settings. Both
choices are stored with the other settings, so they are also kept for the next start.
"""

from __future__ import annotations

import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.core.settings import DisplaySettings, FontSize, Theme
from octaledger.dashboard.ui import call, page_help
from octaledger.dashboard_client.client import ApiClient

THEME_TITLES = {Theme.LIGHT.value: "Hell", Theme.DARK.value: "Dunkel"}
FONT_TITLES = {FontSize.NORMAL.value: "Normal", FontSize.LARGE.value: "Groß"}
DEFAULTS = DisplaySettings()


def render(client: ApiClient, tz: str) -> None:
    """Render the appearance page."""
    st.header("Darstellung")
    page_help(
        "So funktioniert die Darstellung",
        "Hier stellen Sie ein, **wie OctaLedger aussieht**: helles oder dunkles "
        "Erscheinungsbild und die Schriftgröße. Änderungen gelten **sofort** und werden "
        "gespeichert. Mit **Auf Voreinstellung zurücksetzen** kehren Sie zum Ursprung zurück.\n\n"
        "Dieselben zwei Umschalter finden Sie als Kurzbefehle unten in der Seitenleiste. "
        "Wie die Zeit erfasst wird, stellen Sie auf der Seite **App** ein.",
    )
    display = st.session_state.setdefault(
        "_display",
        {
            "theme": DEFAULTS.theme.value,
            "font_size": DEFAULTS.font_size.value,
            "timezone": tz,
        },
    )
    theme = st.radio(
        "Erscheinungsbild",
        list(THEME_TITLES),
        index=list(THEME_TITLES).index(display["theme"]),
        key=f"display_theme_{display['theme']}",  # new key when the sidebar toggled it
        format_func=THEME_TITLES.__getitem__,
        horizontal=True,
        help="Hell passt zu hellen Räumen, Dunkel schont die Augen bei wenig Licht. Beides "
        "erfüllt die Kontrastvorgaben (WCAG AA). Voreinstellung: Hell.",
    )
    font = st.radio(
        "Schriftgröße",
        list(FONT_TITLES),
        index=list(FONT_TITLES).index(display["font_size"]),
        key=f"display_font_{display['font_size']}",
        format_func=FONT_TITLES.__getitem__,
        horizontal=True,
        help="„Groß“ vergrößert Texte und Eingabefelder in der ganzen Oberfläche. "
        "Voreinstellung: Normal.",
    )
    if theme != display["theme"] or font != display["font_size"]:
        display["theme"], display["font_size"] = theme, font
        try:
            client.update_settings({"display": {"theme": theme, "font_size": font}})
        except OctaLedgerError:
            st.session_state["_persist_failed"] = True
        st.rerun()  # the new look takes effect on the next run
    st.markdown("**Vorschau**")
    with st.container(border=True):
        st.markdown("Dies ist ein Beispieltext in der gewählten Größe.")
        st.caption("So sehen Hinweise und Erklärungen aus.")
        st.button(
            "Beispiel-Schaltfläche",
            key="display_sample",
            disabled=True,
            help="Nur zur Ansicht; ohne Funktion.",
        )
    if st.button(
        "Auf Voreinstellung zurücksetzen",
        key="display_reset",
        icon=":material/restart_alt:",
        disabled=(theme, font) == (DEFAULTS.theme.value, DEFAULTS.font_size.value),
        help="Stellt Hell und Normal wieder her.",
    ):
        display["theme"], display["font_size"] = DEFAULTS.theme.value, DEFAULTS.font_size.value
        ok, _ = call(
            client.update_settings,
            {"display": {"theme": display["theme"], "font_size": display["font_size"]}},
        )
        if ok:
            st.rerun()
