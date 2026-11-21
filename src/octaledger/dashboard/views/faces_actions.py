"""Control mode in the setup assistant: give a face an action instead of an activity.

When a cube is in *control* mode, "Seiten zuordnen" shows this editor for the selected face:

1. pick the **connection** the action goes to (or be pointed to the connections page),
2. pick **what to do** (the actions come from the connection's self-description),
3. fill in the action's fields - from a pick list of the target's own lights/scenes/devices where it
   can list them,
4. give the face a **name** ("Schreibtischlampe"), **try it right now**, and save.

Like the time editor it lives outside the auto-refreshing fragment (typing must not be thrown
away) and, after saving, the assistant moves to the next free face. No adapter-specific code: the
forms come from :mod:`octaledger.dashboard.forms`.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from octaledger.dashboard.forms import render_fields
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import call
from octaledger.dashboard_client.client import ApiClient

FLASH_KEY = "faces_flash"
PENDING_KEY = "faces_pending_target"


def render_action_editor(client: ApiClient, device: dict[str, Any], face: int) -> None:
    """Draw the action editor of ``face`` and handle probing, saving and clearing."""
    ok_c, connections = call(client.integrations)
    ok_s, specs = call(client.adapters)
    if not (ok_c and ok_s) or connections is None or specs is None:
        return
    by_kind = {spec["kind"]: spec for spec in specs}
    usable = [c for c in connections if c["enabled"] and c["kind"] in by_kind]
    current = device["actions"].get(str(face))
    st.markdown(f"**Seite {face}**" + (" – hat schon eine Aktion" if current else " – noch frei"))
    if not usable:
        st.info(
            "Es gibt noch keine eingeschaltete Verbindung. Legen Sie zuerst auf der Seite "
            "**Smarthome & Verbindungen** an, womit der Würfel sprechen soll (Home Assistant, Hue, "
            "MQTT …)."
        )
        st.button(
            "Zu den Verbindungen",
            key="faces_to_connections",
            on_click=go,
            args=("connections",),
            type="primary",
            help="Öffnet die Seite, auf der Sie Verbindungen anlegen und testen.",
        )
        _clear_button(client, device, face, current)
        return

    prefix = f"faces_ac_{device['id']}_{face}"
    connection = st.selectbox(
        "Verbindung",
        usable,
        index=_index_of(usable, current["integration_id"]) if current else 0,
        key=f"{prefix}_conn",
        format_func=lambda c: f"{c['name']} ({by_kind[c['kind']]['title']})",
        help="Wohin die Aktion gesendet wird.",
    )
    spec = by_kind[connection["kind"]]
    discovered_key = f"faces_discovered_{connection['id']}"
    if spec["can_discover"] and st.button(
        "Geräte der Verbindung auflisten",
        key=f"{prefix}_discover",
        icon=":material/search:",
        help="Fragt das Ziel nach Lampen, Szenen und Ähnlichem, damit Sie auswählen statt "
        "Kennungen abzutippen.",
    ):
        ok, items = call(client.discover_integration, connection["id"])
        if ok:
            st.session_state[discovered_key] = items
    actions = spec["actions"]
    wanted = current["params"].get("action") if current else None
    action = st.selectbox(
        "Was soll geschehen?",
        actions,
        index=_index_of(actions, wanted, "id") if wanted else 0,
        key=f"{prefix}_{connection['id']}_action",
        format_func=lambda a: a["label"],
        help="Die Aktion, die beim Drehen auf diese Seite ausgelöst wird.",
    )
    st.caption(action["description"])
    if not action["idempotent"]:
        st.warning(
            "Diese Aktion wirkt bei **jedem** Auslösen erneut (zum Beispiel Umschalten). Besser "
            "ist oft ein eindeutiges Ein oder Aus.",
            icon="⚠️",
        )
    reuse = (
        current["params"] if current and current["params"].get("action") == action["id"] else None
    )
    params = render_fields(
        action["fields"],
        key_prefix=f"{prefix}_{connection['id']}_{action['id']}",
        values=reuse,
        discovered=st.session_state.get(discovered_key),
    )
    label = st.text_input(
        f"Name der Seite {face}",
        value=current["label"] if current else "",
        key=f"{prefix}_label",
        max_chars=100,
        placeholder="z. B. Schreibtischlampe",
        help="Wie diese Seite heißt. Der Name erscheint im Bild und in der Live-Ansicht.",
    ).strip()
    payload = {"action": action["id"], **params}
    left, middle, right = st.columns([3, 3, 2])
    if left.button(
        f"Seite {face} speichern",
        key=f"{prefix}_save",
        type="primary",
        width="stretch",
        disabled=not label,
        icon=":material/save:",
        help="Speichert die Aktion und springt zur nächsten freien Seite.",
    ):
        _save(client, device, face, connection["id"], label, payload)
    if middle.button(
        "Jetzt ausprobieren",
        key=f"{prefix}_probe",
        width="stretch",
        icon=":material/play_arrow:",
        help="Führt die Aktion sofort aus, damit Sie sehen, ob sie funktioniert. Es wird nichts "
        "gespeichert.",
    ):
        ok, message = call(client.probe_integration, connection["id"], payload)
        if ok:
            st.success(message)
    _clear_button(client, device, face, current, column=right)


def _index_of(items: list[dict[str, Any]], wanted: str | None, key: str = "id") -> int:
    return next((i for i, item in enumerate(items) if item[key] == wanted), 0)


def _clear_button(
    client: ApiClient,
    device: dict[str, Any],
    face: int,
    current: dict[str, Any] | None,
    column: Any = None,
) -> None:
    holder = column if column is not None else st
    if holder.button(
        "Entfernen",
        key=f"faces_ac_{device['id']}_{face}_clear",
        width="stretch",
        disabled=current is None,
        icon=":material/delete:",
        help="Löst die Aktion von dieser Seite. Die Verbindung selbst bleibt erhalten.",
    ):
        if call(client.clear_action, device["id"], face)[0]:
            st.session_state[FLASH_KEY] = f"Seite {face} ist wieder frei."
            st.rerun()


def _save(
    client: ApiClient,
    device: dict[str, Any],
    face: int,
    integration_id: str,
    label: str,
    payload: dict[str, Any],
) -> None:
    done, _ = call(client.assign_action, device["id"], face, integration_id, label, payload)
    if not done:
        return
    taken = {int(f) for f in device["actions"]} | {face}
    following = next(
        (n for step in range(1, 9) if (n := (face - 1 + step) % 8 + 1) not in taken), None
    )
    message = f"Seite {face} heißt jetzt „{label}“."
    if following is not None:
        st.session_state[PENDING_KEY] = (device["id"], following)
        message += f" Weiter mit Seite {following}: Drehen Sie den Würfel darauf."
    st.session_state[FLASH_KEY] = message
    st.rerun()
