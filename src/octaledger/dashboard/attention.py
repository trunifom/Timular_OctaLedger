"""The attention panel: questions that wait for a decision, shown on every page.

Two things can appear under the status bar:

* **A waiting connection** ("Verbindung zu Büro verloren seit 09:12 – der Eintrag wird um
  09:17 beendet, falls der Würfel nicht zurückkommt"). Nothing to do; it explains why time is
  still running and when it will stop.
* **A gap question** (the grace period was over, the entry was ended at the moment of the
  loss). The user decides what the gap was: keep it, leave it empty, or book it elsewhere.

Nothing here ever changes time data without a click; every answer is audited by the service.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.dashboard.ui import format_local, show_error
from octaledger.dashboard_client.client import ApiClient

#: Session-state key that remembers which question currently shows the "assign" form.
ASSIGN_KEY = "_attention_assign"


def gap_text(payload: dict[str, Any], tz: str) -> str:
    """Describe a gap in words, e.g. ``von 09:12 bis 10:05 (53 min)``."""
    lost = payload["lost_at"]
    returned = payload.get("returned_at")
    start = format_local(lost, tz)
    if not returned:
        return f"seit {start} (der Würfel ist noch nicht zurück)"
    minutes = round(
        (datetime.fromisoformat(returned) - datetime.fromisoformat(lost)).total_seconds() / 60
    )
    return f"von {start} bis {format_local(returned, tz)} ({minutes} min)"


def _answer(client: ApiClient, item_id: str, action: str, **extra: str | None) -> None:
    """Send an answer; on success refresh the whole app so journal and bar update."""
    try:
        client.resolve_attention(item_id, action, **extra)
    except OctaLedgerError as error:
        show_error(error)
        return
    st.session_state.pop(ASSIGN_KEY, None)
    st.toast("Antwort gespeichert.", icon=":material/check:")
    st.rerun(scope="app")


def _assign_form(client: ApiClient, item_id: str) -> None:
    """Choose an activity (and optionally a project) for the gap."""
    try:
        activities = client.list_items("activities")
        projects = client.list_items("projects")
    except OctaLedgerError as error:
        show_error(error)
        return
    if not activities:
        st.info("Legen Sie zuerst eine Tätigkeit an (Seite *Tätigkeiten & Projekte*).")
        return
    names = {a["id"]: a["name"] for a in activities}
    project_names = {"": "Kein Projekt", **{p["id"]: p["name"] for p in projects}}
    activity = st.selectbox(
        "Tätigkeit für die Lücke",
        list(names),
        format_func=names.__getitem__,
        key=f"att_activity_{item_id}",
        help="Auf diese Tätigkeit wird die Lücke gebucht. Die Zeit wird als unsicher markiert.",
    )
    project = st.selectbox(
        "Projekt (optional)",
        list(project_names),
        format_func=project_names.__getitem__,
        key=f"att_project_{item_id}",
        help="Optional: das Projekt, dem die Lücke zugeordnet wird.",
    )
    if st.button(
        "Lücke so buchen",
        key=f"att_assign_go_{item_id}",
        icon=":material/check:",
        help="Bucht die Lücke auf die gewählte Tätigkeit.",
    ):
        _answer(client, item_id, "assign", activity_id=activity, project_id=project or None)


def _gap_question(client: ApiClient, item: dict[str, Any], tz: str) -> None:
    """One gap question with its four possible answers."""
    item_id = item["id"]
    with st.container(border=True, key=f"att_{item_id}"):
        st.markdown(
            f"**Der Würfel war nicht erreichbar** – {html.escape(gap_text(item['payload'], tz))}. "
            "Der Eintrag wurde am Moment des Verlusts beendet. **Was war in dieser Zeit?**",
            unsafe_allow_html=True,
        )
        keep, discard, assign, dismiss = st.columns(4)
        if keep.button(
            "Lücke behalten",
            key=f"att_keep_{item_id}",
            width="stretch",
            icon=":material/add:",
            help="Verlängert den beendeten Eintrag über die Lücke: Sie haben weitergearbeitet.",
        ):
            _answer(client, item_id, "keep")
        if discard.button(
            "Lücke leer lassen",
            key=f"att_discard_{item_id}",
            width="stretch",
            icon=":material/remove:",
            help="Der Eintrag bleibt am Moment des Verlusts beendet; die Lücke zählt nicht.",
        ):
            _answer(client, item_id, "discard")
        if assign.button(
            "Anderer Tätigkeit zuordnen",
            key=f"att_assign_{item_id}",
            width="stretch",
            icon=":material/swap_horiz:",
            help="Bucht die Lücke auf eine andere Tätigkeit (z. B. Besprechung unterwegs).",
        ):
            st.session_state[ASSIGN_KEY] = item_id
        if dismiss.button(
            "Nichts tun",
            key=f"att_dismiss_{item_id}",
            width="stretch",
            icon=":material/close:",
            help="Schließt die Frage, ohne etwas zu ändern. Die Zeit bleibt wie sie ist.",
        ):
            try:
                client.dismiss_attention(item_id)
            except OctaLedgerError as error:
                show_error(error)
            else:
                st.rerun(scope="app")
        if st.session_state.get(ASSIGN_KEY) == item_id:
            _assign_form(client, item_id)


def _reminder(client: ApiClient, item: dict[str, Any]) -> None:
    """A plain notice (for example a low battery) that is closed with one click."""
    payload = item["payload"]
    text = "Erinnerung"
    if payload.get("reason") == "battery":
        text = (
            f"**Batterie von „{payload.get('alias', '')}“ fast leer** "
            f"({payload.get('percent')} %). "
            "Ein leerer Würfel verhält sich wie ein Verbindungsverlust – bitte bald laden."
        )
    message, action = st.columns([6, 2], vertical_alignment="center")
    message.warning(text, icon=":material/battery_alert:")
    if action.button(
        "Verstanden",
        key=f"att_ack_{item['id']}",
        width="stretch",
        help="Schließt den Hinweis. Er kommt erst wieder, wenn der Würfel zwischendurch "
        "geladen wurde.",
    ):
        try:
            client.dismiss_attention(item["id"])
        except OctaLedgerError as error:
            show_error(error)
        else:
            st.rerun(scope="app")


@st.fragment(run_every="10s")
def attention_panel(client: ApiClient, tz: str) -> None:
    """Render the waiting connections and open questions (refreshes itself)."""
    try:
        data = client.attention()
    except OctaLedgerError:
        return  # the status bar and the page report API problems
    for waiting in data["link_lost"]:
        st.warning(
            f"**Verbindung zu „{waiting['alias']}“ verloren** seit "
            f"{format_local(waiting['since'], tz)}. Die Zeit läuft vorerst weiter (als unsicher "
            f"markiert) und wird um {format_local(waiting['stops_at'], tz)} am Moment des "
            "Verlusts beendet, falls der Würfel nicht zurückkommt.",
            icon=":material/bluetooth_disabled:",
        )
    for item in data["items"]:
        if item["kind"] == "gap":
            _gap_question(client, item, tz)
        elif item["kind"] == "reminder":
            _reminder(client, item)
