"""Actions on the chosen entries: assign, tag, note, quality, move in time, delete (AP-58).

Every action is its own small form with a **mandatory reason** and goes to the API as **one**
request that is applied all-or-nothing (see :mod:`octaledger.application.entry_service`). The
result line says how many entries really changed, how many already had the wanted values and how
many running entries were left out. Deleting needs the number of entries typed in as a
confirmation; an automatic safety backup is written first.
"""

from __future__ import annotations

from typing import Any, Final
from zoneinfo import ZoneInfo

import streamlit as st

from octaledger.dashboard import entry_filter as ef
from octaledger.dashboard.ui import call, format_hm
from octaledger.dashboard.views.journal import _correct_form, _split_form
from octaledger.dashboard_client.client import ApiClient

KEEP: Final = "__keep__"
NO_PROJECT: Final = "__none__"
TAG_ACTIONS: Final = {
    "keep": "Tags nicht ändern",
    "add": "Tags hinzufügen",
    "remove": "Tags entfernen",
    "replace": "Alle Tags ersetzen durch …",
    "clear": "Alle Tags entfernen",
}
NOTE_ACTIONS: Final = {
    "keep": "Notiz nicht ändern",
    "set": "Notiz ersetzen durch …",
    "append": "Text hinten anhängen",
    "clear": "Notiz leeren",
}
UNITS: Final = {"minutes": ("Minuten", 60), "hours": ("Stunden", 3600), "days": ("Tage", 86400)}
QUALITY_CHOICES: Final = {
    KEEP: "unverändert",
    "confirmed": "bestätigt",
    "uncertain": "unsicher (zu prüfen)",
}


def _flash(result: dict[str, Any], what: str) -> None:
    """Remember the result line for the next run and redraw."""
    parts = [f"{result['changed']} Eintrag/Einträge {what}"]
    if result.get("unchanged"):
        parts.append(f"{result['unchanged']} hatten die Werte schon")
    if result.get("skipped_running"):
        parts.append(f"{result['skipped_running']} laufende ausgelassen")
    if result.get("safety_backup"):
        parts.append(f"Sicherung: {result['safety_backup']}")
    st.session_state["ent_flash"] = " · ".join(parts) + "."
    st.rerun()


def _reason(key: str) -> str:
    """The mandatory reason field of a form."""
    return st.text_input(
        "Grund (Pflicht)",
        key=key,
        max_chars=500,
        help="Warum ändern Sie das? Der Grund steht im Änderungsprotokoll.",
    )


def render(
    client: ApiClient,
    tz: str,
    target: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    tags: list[dict[str, Any]],
) -> None:
    """Render the action area for the chosen entries."""
    st.subheader("Auswahl bearbeiten")
    if not target:
        st.info(
            "Noch nichts ausgewählt. Klicken Sie links in der Tabelle auf eine oder mehrere "
            "Zeilen – oder stellen Sie oben **alle Treffer** ein."
        )
        return
    info = ef.selection_summary(target, ZoneInfo(tz))
    span = (
        f", von {info['first']:%d.%m.%Y %H:%M} bis {info['last']:%d.%m.%Y %H:%M}"
        if info["first"] and info["last"]
        else ""
    )
    running = f" ({info['running']} laufend: werden nicht verschoben oder gelöscht)"
    st.markdown(
        f"**{info['count']} Einträge** ausgewählt, zusammen **{format_hm(info['seconds'])}**{span}"
        f"{running if info['running'] else ''}."
    )
    ids = [e["id"] for e in target]
    open_items = [a for a in activities if not a["archived"]]
    open_projects = [p for p in projects if not p["archived"]]
    if len(target) == 1:
        with st.expander("Diesen einen Eintrag genau bearbeiten (Beginn, Ende, Teilen)"):
            correct, split = st.tabs(["Korrigieren", "Teilen"])
            with correct:
                _correct_form(client, tz, target[0], open_items, open_projects)
            with split:
                _split_form(client, tz, target[0])
    assign, note, move, delete = st.tabs(
        ["Zuordnen & Tags", "Notiz & Qualität", "Zeit verschieben", "Löschen"]
    )
    with assign:
        _assign(client, ids, open_items, open_projects, tags)
    with note:
        _note(client, ids)
    with move:
        _move(client, ids)
    with delete:
        _delete(client, ids)


def _assign(
    client: ApiClient,
    ids: list[str],
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    tags: list[dict[str, Any]],
) -> None:
    """Activity, project and tags of all chosen entries."""
    by_activity = {a["id"]: a["name"] for a in activities}
    by_project = {KEEP: "unverändert", NO_PROJECT: "– kein Projekt –"} | {
        p["id"]: p["name"] for p in projects
    }
    with st.form("ent_form_assign"):
        activity = st.selectbox(
            "Tätigkeit",
            [KEEP, *by_activity],
            key="ent_b_act",
            format_func=lambda i: "unverändert" if i == KEEP else by_activity[i],
            help="Setzt bei allen gewählten Einträgen diese Tätigkeit.",
        )
        project = st.selectbox(
            "Projekt",
            list(by_project),
            key="ent_b_proj",
            format_func=by_project.__getitem__,
            help="Setzt bei allen gewählten Einträgen dieses Projekt oder entfernt es.",
        )
        action = st.radio(
            "Tags",
            list(TAG_ACTIONS),
            key="ent_b_tagmode",
            horizontal=True,
            format_func=TAG_ACTIONS.__getitem__,
            help="Was mit den Tags der gewählten Einträge geschehen soll. „Alle Tags entfernen“ "
            "setzt sie zurück.",
        )
        chosen = st.multiselect(
            "Tags (für hinzufügen, entfernen, ersetzen)",
            [t["name"] for t in tags],
            key="ent_b_tags",
            help="Die Tags, auf die sich die obige Auswahl bezieht. Neue Tags legen Sie unter "
            "„Tätigkeiten & Projekte“ an.",
        )
        reason = _reason("ent_b_reason_assign")
        submitted = st.form_submit_button(
            "Zuordnung anwenden", type="primary", help="Wendet die Änderungen auf alle an."
        )
    if not submitted:
        return
    ids_by_name = {t["name"]: t["id"] for t in tags}
    picked = [ids_by_name[n] for n in chosen]
    change: dict[str, Any] = {}
    if activity != KEEP:
        change["activity_id"] = activity
    if project == NO_PROJECT:
        change["clear_project"] = True
    elif project != KEEP:
        change["project_id"] = project
    if action in ("add", "remove", "replace") and not picked:
        st.warning("Bitte wählen Sie mindestens einen Tag aus.")
        return
    if action == "add":
        change["tags_add"] = picked
    elif action == "remove":
        change["tags_remove"] = picked
    elif action == "replace":
        change["tags_replace"] = picked
    elif action == "clear":
        change["tags_replace"] = []
    ok, result = call(client.bulk_edit, ids, reason, **change)
    if ok and result:
        _flash(result, "zugeordnet")


def _note(client: ApiClient, ids: list[str]) -> None:
    """Note and quality of all chosen entries."""
    with st.form("ent_form_note"):
        mode = st.radio(
            "Notiz",
            list(NOTE_ACTIONS),
            key="ent_b_note_mode",
            horizontal=True,
            format_func=NOTE_ACTIONS.__getitem__,
            help="Wie die Notiz der gewählten Einträge geändert wird.",
        )
        text = st.text_input(
            "Text",
            key="ent_b_note",
            max_chars=500,
            help="Der Text für „ersetzen“ oder „anhängen“.",
        )
        quality = st.selectbox(
            "Qualität",
            list(QUALITY_CHOICES),
            key="ent_b_quality",
            format_func=QUALITY_CHOICES.__getitem__,
            help="„bestätigt“ heißt: Der Zeitraum stimmt. „unsicher“ markiert ihn zur Prüfung.",
        )
        reason = _reason("ent_b_reason_note")
        submitted = st.form_submit_button(
            "Notiz und Qualität anwenden", type="primary", help="Wendet die Änderungen auf alle an."
        )
    if not submitted:
        return
    change: dict[str, Any] = {"note_mode": mode, "note": text}
    if quality != KEEP:
        change["quality"] = quality
    if mode in ("set", "append") and not text.strip():
        st.warning("Bitte einen Text eingeben.")
        return
    ok, result = call(client.bulk_edit, ids, reason, **change)
    if ok and result:
        _flash(result, "geändert")


def _move(client: ApiClient, ids: list[str]) -> None:
    """Move all chosen entries in time (start and end by the same amount)."""
    with st.form("ent_form_move"):
        left, middle, right = st.columns(3)
        amount = left.number_input(
            "Um wie viel",
            1,
            100000,
            1,
            key="ent_b_shift",
            help="Betrag der Verschiebung (Start und Ende wandern gemeinsam, die Dauer bleibt).",
        )
        unit = middle.selectbox(
            "Einheit",
            list(UNITS),
            key="ent_b_unit",
            format_func=lambda u: UNITS[u][0],
            help="Minuten, Stunden oder Tage.",
        )
        direction = right.radio(
            "Richtung",
            ["later", "earlier"],
            key="ent_b_dir",
            format_func=lambda d: "später" if d == "later" else "früher",
            help="Später = in Richtung Gegenwart, früher = in die Vergangenheit.",
        )
        reason = _reason("ent_b_reason_shift")
        submitted = st.form_submit_button(
            "Verschieben", type="primary", help="Verschiebt alle gewählten, beendeten Einträge."
        )
    st.caption(
        "Laufende Einträge werden nicht verschoben. Entsteht dadurch eine Überschneidung mit "
        "einem anderen Eintrag, wird **nichts** verschoben."
    )
    if not submitted:
        return
    seconds = int(amount) * UNITS[unit][1] * (1 if direction == "later" else -1)
    ok, result = call(client.bulk_edit, ids, reason, shift_seconds=seconds)
    if ok and result:
        _flash(result, "verschoben")


def _delete(client: ApiClient, ids: list[str]) -> None:
    """Delete all chosen entries after a typed-in count and a mandatory reason."""
    st.warning(
        f"Gelöscht werden **{len(ids)} Einträge** (laufende bleiben). Vorher wird automatisch eine "
        "Sicherung angelegt; sie lässt sich auf der Seite **Daten** wiederherstellen."
    )
    reason = _reason("ent_b_reason_delete")
    typed = st.number_input(
        f"Zur Bestätigung die Anzahl eintippen ({len(ids)})",
        0,
        1_000_000,
        0,
        key="ent_b_delete_count",
        help="Schutz vor Versehen: Das Löschen ist erst möglich, wenn hier genau die Zahl der "
        "ausgewählten Einträge steht.",
    )
    if st.button(
        f"{len(ids)} Einträge endgültig löschen",
        key="ent_b_delete",
        icon=":material/delete:",
        disabled=int(typed) != len(ids),
        help="Löscht alle gewählten, beendeten Einträge (mit Sicherung und Protokolleintrag).",
    ):
        ok, result = call(client.bulk_delete, ids, reason)
        if ok and result:
            _flash(result, "gelöscht")
