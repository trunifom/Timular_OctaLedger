"""Control mode in the setup assistant: give a face an action chain instead of an activity.

When a cube is in *control* mode, "Seiten zuordnen" shows this editor for the selected face. A
face has one or more **steps**; each step is

1. a **connection** (or a pointer to the connections page),
2. **what to do** (the actions come from the connection's self-description),
3. the action's fields - from a pick list of the target's own lights/scenes/devices where it can
   list them,
4. optionally a **delay**, "continue if this step fails" and a **time window**.

Step 1 keeps the widget keys of the earlier single-action editor. The name of the face is the name
of step 1. Like the time editor it lives outside the auto-refreshing fragment (typing must not be
thrown away) and, after saving, the assistant moves to the next free face. No adapter-specific code:
the forms come from :mod:`octaledger.dashboard.forms`.
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
WEEKDAYS = {
    "1": "Mo",
    "2": "Di",
    "3": "Mi",
    "4": "Do",
    "5": "Fr",
    "6": "Sa",
    "7": "So",
}
MAX_STEPS = 10


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
    chains_ok, chains = call(client.action_chains, device["id"])
    saved = (chains or {}).get(str(face), []) if chains_ok else []
    count_key = f"{prefix}_count"
    if count_key not in st.session_state:
        st.session_state[count_key] = max(1, len(saved))
    count = int(st.session_state[count_key])

    first = _step_editor(client, prefix, usable, by_kind, saved[0] if saved else None, current, 0)
    label = st.text_input(
        f"Name der Seite {face}",
        value=current["label"] if current else "",
        key=f"{prefix}_label",
        max_chars=100,
        placeholder="z. B. Schreibtischlampe",
        help="Wie diese Seite heißt. Der Name erscheint im Bild und in der Live-Ansicht.",
    ).strip()
    steps: list[dict[str, Any]] = []
    if first is not None:
        steps.append({**first, "label": label})
    for index in range(1, count):
        st.divider()
        st.markdown(f"**Schritt {index + 1}**")
        extra = _step_editor(
            client,
            f"{prefix}_s{index}",
            usable,
            by_kind,
            saved[index] if index < len(saved) else None,
            None,
            index,
        )
        step_label = st.text_input(
            f"Name von Schritt {index + 1}",
            value=saved[index]["label"] if index < len(saved) else "",
            key=f"{prefix}_s{index}_label",
            max_chars=100,
            placeholder=f"z. B. {label or 'Seite'} – Musik",
            help="Wie dieser Schritt im Verlauf heißt.",
        ).strip()
        if extra is not None:
            steps.append({**extra, "label": step_label or f"{label} ({index + 1})"})
        _move_buttons(client, device, face, prefix, index, steps, saved)

    add, drop = st.columns(2)
    if add.button(
        "Schritt hinzufügen",
        key=f"{prefix}_add",
        disabled=count >= MAX_STEPS,
        icon=":material/add:",
        width="stretch",
        help="Fügt der Seite einen weiteren Schritt an (z. B. Musik nach 10 Sekunden). Alle "
        "Schritte starten, sobald Sie den Würfel drehen.",
    ):
        st.session_state[count_key] = count + 1
        st.rerun()
    if drop.button(
        "Letzten Schritt entfernen",
        key=f"{prefix}_drop",
        disabled=count <= 1,
        icon=":material/remove:",
        width="stretch",
        help="Entfernt den letzten Schritt aus dem Formular (gespeichert wird erst mit „Seite "
        "speichern“).",
    ):
        st.session_state[count_key] = count - 1
        st.rerun()

    complete = bool(label) and len(steps) == count
    left, middle, right = st.columns([3, 3, 2])
    if left.button(
        f"Seite {face} speichern",
        key=f"{prefix}_save",
        type="primary",
        width="stretch",
        disabled=not label,
        icon=":material/save:",
        help="Speichert die Aktion (alle Schritte) und springt zur nächsten freien Seite.",
    ):
        if complete:
            _save(client, device, face, label, steps)
        else:
            st.error("Bitte jeden Schritt vollständig ausfüllen (Verbindung und Aktion).")
    if middle.button(
        "Schritt 1 ausprobieren",
        key=f"{prefix}_probe",
        width="stretch",
        icon=":material/play_arrow:",
        help="Führt den ersten Schritt sofort aus, damit Sie sehen, ob er funktioniert. Es wird "
        "nichts gespeichert.",
    ):
        if first is not None:
            ok, message = call(client.probe_integration, first["integration_id"], first["params"])
            if ok:
                st.success(message)
    _clear_button(client, device, face, current, column=right)


def _step_editor(
    client: ApiClient,
    prefix: str,
    usable: list[dict[str, Any]],
    by_kind: dict[str, dict[str, Any]],
    saved: dict[str, Any] | None,
    legacy: dict[str, Any] | None,
    index: int,
) -> dict[str, Any] | None:
    """Draw one step; return it as an API step (without label) or ``None`` if incomplete.

    ``saved`` is the stored step (any index); ``legacy`` is the face's old single action, used
    only to pre-fill step 1 when no chain was stored yet.
    """
    source = saved or (
        {"integration_id": legacy["integration_id"], "params": legacy["params"]} if legacy else None
    )
    connection = st.selectbox(
        "Verbindung",
        usable,
        index=_index_of(usable, source["integration_id"]) if source else 0,
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
    wanted = source["params"].get("action") if source else None
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
    reuse = source["params"] if source and source["params"].get("action") == action["id"] else None
    params = render_fields(
        action["fields"],
        key_prefix=f"{prefix}_{connection['id']}_{action['id']}",
        values=reuse,
        discovered=st.session_state.get(discovered_key),
    )
    delay, goon, active = st.columns(3)
    seconds = delay.number_input(
        "Verzögerung (Sekunden)",
        min_value=0.0,
        max_value=300.0,
        value=(saved["delay_ms"] / 1000) if saved else 0.0,
        step=0.5,
        key=f"{prefix}_delay",
        help="So lange nach dem Drehen wartet dieser Schritt. 0 = sofort. Alle Verzögerungen "
        "zusammen dürfen höchstens 5 Minuten betragen. Voreinstellung: 0.",
    )
    keep_going = goon.checkbox(
        "Bei Fehler weitermachen",
        value=bool(saved["continue_on_error"]) if saved else False,
        key=f"{prefix}_goon",
        help="Ohne Haken werden die folgenden Schritte abgebrochen, wenn dieser Schritt "
        "fehlschlägt. Voreinstellung: aus.",
    )
    enabled = active.checkbox(
        "Schritt aktiv",
        value=bool(saved["enabled"]) if saved else True,
        key=f"{prefix}_enabled",
        help="Inaktive Schritte bleiben gespeichert, werden aber übersprungen.",
    )
    condition = _condition(prefix, saved["condition"] if saved else None)
    return {
        "integration_id": connection["id"],
        "params": {"action": action["id"], **params},
        "delay_ms": round(seconds * 1000),
        "continue_on_error": keep_going,
        "enabled": enabled,
        "condition": condition,
    }


def _condition(prefix: str, saved: dict[str, str] | None) -> dict[str, str] | None:
    """The optional "only at certain times" part of a step."""
    saved = saved or {}
    with st.expander("Nur zu bestimmten Zeiten", key=f"{prefix}_when"):
        st.caption(
            "Der Schritt läuft nur, wenn die Bedingung **beim Drehen** erfüllt ist; sonst wird er "
            "übersprungen. Leer lassen = immer."
        )
        start, end = st.columns(2)
        begin = start.text_input(
            "Von (HH:MM)",
            value=saved.get("start", ""),
            key=f"{prefix}_from",
            max_chars=5,
            placeholder="08:00",
            help="Beginn des Zeitfensters in Ihrer Zeitzone. Leer = kein Zeitfenster.",
        )
        finish = end.text_input(
            "Bis (HH:MM)",
            value=saved.get("end", ""),
            key=f"{prefix}_to",
            max_chars=5,
            placeholder="18:00",
            help="Ende des Zeitfensters; es darf über Mitternacht gehen (22:00 bis 06:00).",
        )
        days = st.multiselect(
            "Wochentage",
            list(WEEKDAYS),
            default=[d for d in saved.get("weekdays", "").split(",") if d in WEEKDAYS],
            format_func=WEEKDAYS.__getitem__,
            key=f"{prefix}_days",
            help="An welchen Wochentagen der Schritt läuft. Leer = an allen.",
        )
    if not (begin or finish or days):
        return None
    return {"start": begin, "end": finish, "weekdays": ",".join(days)}


def _move_buttons(
    client: ApiClient,
    device: dict[str, Any],
    face: int,
    prefix: str,
    index: int,
    steps: list[dict[str, Any]],
    saved: list[dict[str, Any]],
) -> None:
    """Move a *saved* step one place up (swaps it with the one before)."""
    if index >= len(saved):
        return
    if st.button(
        "↑ Nach oben",
        key=f"{prefix}_s{index}_up",
        help="Tauscht diesen gespeicherten Schritt mit dem davor und speichert die Reihenfolge.",
    ):
        order = [{k: v for k, v in step.items() if k != "position"} for step in saved]
        order[index - 1], order[index] = order[index], order[index - 1]
        if call(client.assign_steps, device["id"], face, order)[0]:
            for key in [k for k in st.session_state if str(k).startswith(prefix)]:
                if "_count" not in str(key):
                    del st.session_state[key]
            st.rerun()


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
        help="Löst die Aktion (alle Schritte) von dieser Seite. Die Verbindung selbst bleibt "
        "erhalten.",
    ):
        if call(client.clear_action, device["id"], face)[0]:
            st.session_state[FLASH_KEY] = f"Seite {face} ist wieder frei."
            st.rerun()


def _save(
    client: ApiClient,
    device: dict[str, Any],
    face: int,
    label: str,
    steps: list[dict[str, Any]],
) -> None:
    done, _ = call(client.assign_steps, device["id"], face, steps)
    if not done:
        return
    taken = {int(f) for f in device["actions"]} | {face}
    following = next(
        (n for step in range(1, 9) if (n := (face - 1 + step) % 8 + 1) not in taken), None
    )
    message = f"Seite {face} heißt jetzt „{label}“."
    if len(steps) > 1:
        message += f" Sie hat {len(steps)} Schritte."
    if following is not None:
        st.session_state[PENDING_KEY] = (device["id"], following)
        message += f" Weiter mit Seite {following}: Drehen Sie den Würfel darauf."
    st.session_state[FLASH_KEY] = message
    st.rerun()
