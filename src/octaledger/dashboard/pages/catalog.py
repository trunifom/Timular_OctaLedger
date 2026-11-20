"""Management page: activities and projects (create, rename, recolour, archive, delete)."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from octaledger.dashboard.ui import call, page_help
from octaledger.dashboard_client.client import ApiClient


def render(client: ApiClient, tz: str) -> None:
    """Render the management page."""
    st.header("Verwaltung")
    page_help(
        "So funktioniert die Verwaltung",
        "**Tätigkeiten** sagen, *was* Sie tun (z. B. Meeting, Entwicklung). Jede Würfelseite "
        "bekommt eine Tätigkeit. **Projekte** sagen, *wofür* die Zeit gebucht wird (optional).\n\n"
        "- **Farbe:** Ohne eigene Wahl vergibt OctaLedger gut unterscheidbare Farben für die "
        "Diagramme.\n"
        "- **Archivieren statt Löschen:** Wird ein Eintrag schon verwendet, lässt er sich nicht "
        "löschen. Archivieren blendet ihn aus den Auswahllisten aus; alte Zeiten und Auswertungen "
        "bleiben korrekt. Sie können ihn jederzeit wiederherstellen.",
    )
    activities_tab, projects_tab = st.tabs(["Tätigkeiten", "Projekte"])
    with activities_tab:
        _catalog(client, "activities", "Tätigkeit", "Tätigkeiten")
    with projects_tab:
        _catalog(client, "projects", "Projekt", "Projekte")


def _catalog(client: ApiClient, kind: str, singular: str, plural: str) -> None:
    with st.form(f"create_{kind}", clear_on_submit=True):
        name = st.text_input(
            f"Name der neuen {singular}",
            key=f"new_name_{kind}",
            max_chars=100,
            help="Der Name muss eindeutig sein (Groß-/Kleinschreibung zählt nicht).",
        )
        custom = st.checkbox(
            "Eigene Farbe wählen",
            key=f"new_custom_{kind}",
            help="Ohne Haken wählt OctaLedger automatisch eine gut unterscheidbare Farbe.",
        )
        color = st.color_picker(
            "Farbe",
            "#0072B2",
            key=f"new_color_{kind}",
            help="Wird nur verwendet, wenn „Eigene Farbe wählen“ aktiv ist.",
        )
        if st.form_submit_button(f"➕ {singular} anlegen", type="primary"):
            created, item = call(client.create_item, kind, name, color if custom else None)
            if created and item:
                st.success(f"„{item['name']}“ wurde angelegt.")

    show_archived = st.toggle(
        "Archivierte anzeigen",
        key=f"show_archived_{kind}",
        help="Zeigt auch archivierte Einträge, damit Sie sie wiederherstellen können.",
    )
    ok, items = call(client.list_items, kind, show_archived)
    if not ok or items is None:
        return
    if not items:
        st.info(f"Noch keine {plural}. Legen Sie oben die erste an.")
    for item in items:
        _item_panel(client, kind, singular, item)


def _item_panel(client: ApiClient, kind: str, singular: str, item: dict[str, Any]) -> None:
    iid = item["id"]
    archived = item["archived"]
    title = f"{item['name']}" + (" (archiviert)" if archived else "")
    with st.expander(title):
        st.markdown(
            f'<span class="ol-dot" style="background:{html.escape(item["color"])}"></span>'
            f"{html.escape(item['name'])}",
            unsafe_allow_html=True,
        )
        new_name = st.text_input(
            "Name",
            value=item["name"],
            key=f"name_{kind}_{iid}",
            max_chars=100,
            help="Ändert den Namen auch in alten Auswertungen.",
        )
        new_color = st.color_picker(
            "Farbe",
            item["color"],
            key=f"color_{kind}_{iid}",
            help="Farbe in Diagrammen und der Übersicht.",
        )
        save, archive, delete = st.columns(3)
        if save.button(
            "💾 Speichern",
            key=f"save_{kind}_{iid}",
            use_container_width=True,
            help="Speichert Name und Farbe.",
        ):
            if call(client.update_item, kind, iid, new_name, new_color)[0]:
                st.rerun()
        if archive.button(
            "♻️ Wiederherstellen" if archived else "📦 Archivieren",
            key=f"archive_{kind}_{iid}",
            use_container_width=True,
            help="Archivierte Einträge verschwinden aus den Auswahllisten, bleiben aber in "
            "Auswertungen erhalten.",
        ):
            if call(client.archive_item, kind, iid, not archived)[0]:
                st.rerun()
        confirm = st.checkbox(
            "Löschen bestätigen",
            key=f"confirm_{kind}_{iid}",
            help=f"Löschen geht nur, wenn die {singular} noch nirgends verwendet wird. "
            "Sonst bitte archivieren.",
        )
        if delete.button(
            "🗑 Löschen",
            key=f"delete_{kind}_{iid}",
            disabled=not confirm,
            use_container_width=True,
            help="Entfernt den Eintrag endgültig.",
        ):
            if call(client.delete_item, kind, iid)[0]:
                st.rerun()
