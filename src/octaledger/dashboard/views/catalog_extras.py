"""Tags, note templates and project billing on the "Tätigkeiten & Projekte" page.

* **Tags** are free labels on entries; an activity can give new entries default tags.
* A **note template** is a text that pre-fills the note when an entry of the activity is started
  by hand.
* **Budget, hourly rate and billable** belong to a project; amounts are *computed* in reports
  from the rate and rounded there, stored entries are never changed.
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from octaledger.dashboard.ui import call
from octaledger.dashboard_client.client import ApiClient


def tags_tab(client: ApiClient) -> None:
    """Create, rename, recolour and delete tags."""
    st.markdown(
        "Tags sind freie Etiketten für Einträge (z. B. „Kunde A“, „Remote“). Eine Tätigkeit kann "
        "ihren neuen Einträgen automatisch Tags geben; im Zeitjournal lassen sie sich je Eintrag "
        "ändern und als Filter nutzen."
    )
    with st.form("create_tag", clear_on_submit=True):
        name = st.text_input(
            "Name des neuen Tags",
            key="new_tag_name",
            max_chars=50,
            help="Der Name muss eindeutig sein (Groß-/Kleinschreibung zählt nicht).",
        )
        color = st.color_picker(
            "Farbe", "#7F7F7F", key="new_tag_color", help="Farbe des Tags (Voreinstellung: grau)."
        )
        if st.form_submit_button("➕ Tag anlegen", type="primary", help="Legt den Tag an."):
            created, tag = call(client.create_tag, name, color)
            if created and tag:
                st.success(f"Tag „{tag['name']}“ wurde angelegt.")
    ok, tags = call(client.tags)
    if not ok or tags is None:
        return
    if not tags:
        st.info("Noch keine Tags. Legen Sie oben den ersten an.")
    for tag in tags:
        with st.expander(tag["name"], key=f"tag_{tag['id']}"):
            st.markdown(
                f'<span class="ol-dot" style="background:{html.escape(tag["color"])}"></span>'
                f"{html.escape(tag['name'])}",
                unsafe_allow_html=True,
            )
            new_name = st.text_input(
                "Name",
                value=tag["name"],
                key=f"tag_name_{tag['id']}",
                max_chars=50,
                help="Ändert den Namen auch bei allen Einträgen mit diesem Tag.",
            )
            new_color = st.color_picker(
                "Farbe", tag["color"], key=f"tag_color_{tag['id']}", help="Farbe des Tags."
            )
            save, delete = st.columns(2)
            if save.button(
                "💾 Speichern",
                key=f"tag_save_{tag['id']}",
                width="stretch",
                help="Speichert Name und Farbe.",
            ):
                if call(client.update_tag, tag["id"], new_name, new_color)[0]:
                    st.rerun()
            sure = st.checkbox(
                "Löschen bestätigen",
                key=f"tag_confirm_{tag['id']}",
                help="Der Tag verschwindet von allen Einträgen und Tätigkeiten. Die Einträge "
                "selbst bleiben unverändert.",
            )
            if delete.button(
                "🗑 Löschen",
                key=f"tag_delete_{tag['id']}",
                disabled=not sure,
                width="stretch",
                help="Entfernt den Tag überall (die Zeiten bleiben).",
            ):
                if call(client.delete_tag, tag["id"])[0]:
                    st.rerun()


def activity_defaults(client: ApiClient, activity: dict[str, Any]) -> None:
    """Default tags and the note template of one activity."""
    aid = activity["id"]
    ok, tags = call(client.tags)
    ok_d, defaults = call(client.activity_defaults, aid)
    if not (ok and ok_d) or tags is None or defaults is None:
        return
    st.markdown("**Standard-Tags und Notizvorlage**")
    names = {t["id"]: t["name"] for t in tags}
    chosen = st.multiselect(
        "Standard-Tags",
        list(names),
        default=[t["id"] for t in defaults["tags"] if t["id"] in names],
        format_func=names.__getitem__,
        key=f"act_tags_{aid}",
        help="Neue Einträge dieser Tätigkeit bekommen diese Tags automatisch (auch per Würfel). "
        "Voreinstellung: keine.",
    )
    template = st.text_area(
        "Notizvorlage",
        value=defaults["note_template"] or "",
        key=f"act_tpl_{aid}",
        max_chars=500,
        height=80,
        help="Wird beim manuellen Start dieser Tätigkeit als Notiz vorbelegt, z. B. "
        "„Kunde: \\nZiel: “. Leer = keine Vorlage.",
    )
    if st.button(
        "💾 Tags und Vorlage speichern",
        key=f"act_defaults_save_{aid}",
        help="Speichert Standard-Tags und Notizvorlage dieser Tätigkeit.",
    ):
        if call(client.set_activity_defaults, aid, chosen, template or None)[0]:
            st.rerun()


def project_billing(client: ApiClient, project: dict[str, Any]) -> None:
    """Budget, hourly rate and billable flag of one project."""
    pid = project["id"]
    ok, billing = call(client.project_billing, pid)
    if not ok or billing is None:
        return
    st.markdown("**Budget und Stundensatz**")
    budget_hours = st.number_input(
        "Budget (Stunden, 0 = kein Budget)",
        min_value=0.0,
        max_value=100000.0,
        value=(billing["budget_minutes"] or 0) / 60,
        step=1.0,
        key=f"proj_budget_{pid}",
        help="Geplante Zeit für das Projekt. Bei 80 % und 100 % gibt es einmal einen Hinweis. "
        "Voreinstellung: 0 (kein Budget).",
    )
    rate = st.number_input(
        "Stundensatz (0 = keiner)",
        min_value=0.0,
        max_value=1000000.0,
        value=(billing["hourly_rate_cents"] or 0) / 100,
        step=5.0,
        key=f"proj_rate_{pid}",
        help="Betrag pro Stunde in Ihrer Währung. Beträge werden nur in Berichten berechnet und "
        "gerundet, nie in den Rohdaten gespeichert. Voreinstellung: 0.",
    )
    billable = st.checkbox(
        "Abrechenbar",
        value=billing["billable"],
        key=f"proj_billable_{pid}",
        help="Markiert die Zeit dieses Projekts als abrechenbar (Export-Spalte „billable“). "
        "Voreinstellung: nein.",
    )
    if st.button(
        "💾 Budget und Satz speichern",
        key=f"proj_billing_save_{pid}",
        help="Speichert Budget, Stundensatz und Abrechenbarkeit des Projekts.",
    ):
        minutes = round(budget_hours * 60) if budget_hours > 0 else None
        cents = round(rate * 100) if rate > 0 else None
        if call(client.set_project_billing, pid, minutes, cents, billable)[0]:
            st.rerun()
