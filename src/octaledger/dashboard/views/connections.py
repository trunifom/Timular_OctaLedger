"""Connections page: link the cube to things it can control (smart home, MQTT, web addresses).

A *connection* says **where** actions go (an MQTT broker, Home Assistant, a Hue bridge, a web
address). *What* a cube face does is chosen later per face in the setup assistant. This page:

* lists the connections with their state, and lets the user **test** one (no side effects), **pair**
  it (Hue), **try an action right now**, switch it on/off, change or delete it,
* creates a new one from a form that the *kind of connection describes itself* (see
  :mod:`octaledger.dashboard.forms`; a new adapter needs no change here),
* shows the **history** of sent actions with the result of each, so a light that did not switch
  is never a mystery.

Passwords and tokens are never shown; an empty field keeps a stored one.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from octaledger.dashboard.forms import render_fields
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import call, format_local, page_help
from octaledger.dashboard_client.client import ApiClient

STATUS_TEXT = {
    "pending": "⏳ wartet",
    "done": "✅ gesendet",
    "failed": "❌ fehlgeschlagen",
    "expired": "⌛ verfallen",
}
FLASH_KEY = "connections_flash"


def render(client: ApiClient, tz: str) -> None:
    """Render the connections page."""
    st.header("Verbindungen")
    page_help(
        "So funktioniert die Seite „Verbindungen“",
        "Hier verbinden Sie OctaLedger mit Dingen, die der Würfel **steuern** soll, zum Beispiel "
        "Licht über **Home Assistant**, **Philips Hue**, einen **MQTT-Broker** oder eine beliebige "
        "**Web-Adresse**. Matter-Geräte und Google Home erreichen Sie über Home Assistant.\n\n"
        "1. **Verbindung anlegen** (unten): Art wählen, Angaben eintragen.\n"
        "2. **Testen**: prüft die Verbindung, ohne etwas zu schalten.\n"
        "3. **Seiten zuordnen**: dort stellen Sie den Würfel auf *Steuerung* und geben jeder Seite "
        "eine Aktion.\n\n"
        "Passwörter und Tokens werden nie angezeigt und nie in Sicherungen gespeichert.",
    )
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)
    ok, specs = call(client.adapters)
    ok_i, connections = call(client.integrations)
    if not (ok and ok_i) or specs is None or connections is None:
        return
    by_kind = {spec["kind"]: spec for spec in specs}
    if not connections:
        st.info("Noch keine Verbindung angelegt. Wählen Sie unten, womit der Würfel sprechen soll.")
    for connection in connections:
        spec = by_kind.get(connection["kind"])
        if spec is None:
            st.warning(
                f"„{connection['name']}“ gehört zu einer Art, die diese Version nicht kennt "
                f"({connection['kind']})."
            )
            continue
        _connection_panel(client, connection, spec)
    _new_connection(client, specs)
    _history(client, tz)


def _summary(connection: dict[str, Any], spec: dict[str, Any]) -> str:
    """One line with the settings (no secrets) and which secrets are stored."""
    shown = []
    for field in spec["config_fields"]:
        if field["kind"] == "password":
            if field["name"] in connection["secrets_set"]:
                shown.append(f"{field['label']}: gespeichert ✔")
        elif connection["config"].get(field["name"]) not in (None, ""):
            value = connection["config"][field["name"]]
            text = "ja" if value is True else "nein" if value is False else str(value)
            shown.append(f"{field['label']}: {text}")
    return " · ".join(shown)


def _connection_panel(client: ApiClient, connection: dict[str, Any], spec: dict[str, Any]) -> None:
    cid = connection["id"]
    state = "✅" if connection["enabled"] else "⏸"
    with st.container(border=True, key=f"conn_{cid}"):
        st.markdown(f"**{state} {connection['name']}** · {spec['title']}")
        st.caption(_summary(connection, spec) or "Keine Angaben.")
        if not connection["enabled"]:
            st.caption("Ausgeschaltet: es werden keine Aktionen gesendet.")
        overview, trial, settings = st.tabs(["Prüfen", "Ausprobieren", "Einstellungen"])
        with overview:
            _check_and_pair(client, connection, spec)
        with trial:
            _try_action(client, connection, spec)
        with settings:
            _settings(client, connection, spec)


def _check_and_pair(client: ApiClient, connection: dict[str, Any], spec: dict[str, Any]) -> None:
    cid = connection["id"]
    columns = st.columns(2 if spec["can_pair"] else 1)
    if columns[0].button(
        "Verbindung testen",
        key=f"conn_check_{cid}",
        icon=":material/network_check:",
        width="stretch",
        help="Prüft, ob das Ziel erreichbar ist und die Zugangsdaten stimmen. Es wird nichts "
        "geschaltet.",
    ):
        ok, message = call(client.check_integration, cid)
        if ok:
            st.success(message)
    if spec["can_pair"] and columns[1].button(
        "Koppeln",
        key=f"conn_pair_{cid}",
        icon=":material/link:",
        width="stretch",
        help=spec["pair_help"] or "Koppelt OctaLedger einmalig mit dem Ziel.",
    ):
        ok, message = call(client.pair_integration, cid)
        if ok:
            st.session_state[FLASH_KEY] = message
            st.rerun()
    if spec["can_pair"] and spec["pair_help"]:
        st.caption(spec["pair_help"])


def _try_action(client: ApiClient, connection: dict[str, Any], spec: dict[str, Any]) -> None:
    cid = connection["id"]
    st.caption("Führt eine Aktion **jetzt sofort** aus, damit Sie sehen, ob sie funktioniert.")
    discovered_key = f"conn_discovered_{cid}"
    if spec["can_discover"] and st.button(
        "Geräte der Verbindung auflisten",
        key=f"conn_discover_{cid}",
        icon=":material/search:",
        help="Fragt das Ziel nach Lampen, Szenen und Ähnlichem, damit Sie auswählen statt tippen "
        "können.",
    ):
        ok, items = call(client.discover_integration, cid)
        if ok:
            st.session_state[discovered_key] = items
    actions = spec["actions"]
    action = st.selectbox(
        "Aktion",
        actions,
        key=f"conn_action_{cid}",
        format_func=lambda a: a["label"],
        help="Was gesendet werden soll.",
    )
    st.caption(action["description"])
    if not action["idempotent"]:
        st.warning(
            "Diese Aktion wirkt bei **jedem** Senden erneut (zum Beispiel Umschalten).", icon="⚠️"
        )
    params = render_fields(
        action["fields"],
        key_prefix=f"conn_try_{cid}_{action['id']}",
        discovered=st.session_state.get(discovered_key),
    )
    if st.button(
        "Jetzt senden",
        key=f"conn_probe_{cid}",
        type="primary",
        icon=":material/play_arrow:",
        help="Sendet die Aktion sofort an das Ziel.",
    ):
        ok, message = call(client.probe_integration, cid, {"action": action["id"], **params})
        if ok:
            st.success(message)


def _settings(client: ApiClient, connection: dict[str, Any], spec: dict[str, Any]) -> None:
    cid = connection["id"]
    name = st.text_input(
        "Name",
        value=connection["name"],
        key=f"conn_name_{cid}",
        max_chars=100,
        help="Frei wählbar, nur zur Anzeige. Jeder Name darf nur einmal vorkommen.",
    )
    values = render_fields(
        spec["config_fields"],
        key_prefix=f"conn_edit_{cid}",
        values=connection["config"],
        secrets_set=connection["secrets_set"],
    )
    left, middle, right = st.columns(3)
    if left.button(
        "Speichern",
        key=f"conn_save_{cid}",
        type="primary",
        icon=":material/save:",
        width="stretch",
        help="Speichert Name und Angaben. Leere Passwortfelder behalten den gespeicherten Wert.",
    ):
        ok, _ = call(client.update_integration, cid, name=name, values=values)
        if ok:
            st.session_state[FLASH_KEY] = f"„{name}“ wurde gespeichert."
            st.rerun()
    enabled = connection["enabled"]
    if middle.button(
        "Ausschalten" if enabled else "Einschalten",
        key=f"conn_toggle_{cid}",
        icon=":material/power_settings_new:",
        width="stretch",
        help="Eine ausgeschaltete Verbindung behält ihre Angaben, sendet aber nichts.",
    ):
        ok, _ = call(client.update_integration, cid, enabled=not enabled)
        if ok:
            st.rerun()
    confirm = st.checkbox(
        f"Ja, „{connection['name']}“ löschen",
        key=f"conn_confirm_{cid}",
        help="Löschen ist nur möglich, solange keine Würfelseite diese Verbindung nutzt.",
    )
    if right.button(
        "Löschen",
        key=f"conn_delete_{cid}",
        icon=":material/delete:",
        width="stretch",
        disabled=not confirm,
        help="Entfernt die Verbindung samt gespeicherten Zugangsdaten.",
    ):
        ok, _ = call(client.delete_integration, cid)
        if ok:
            st.session_state[FLASH_KEY] = f"„{connection['name']}“ wurde gelöscht."
            st.rerun()


def _new_connection(client: ApiClient, specs: list[dict[str, Any]]) -> None:
    st.subheader("Neue Verbindung")
    if not specs:
        st.info("In dieser Version sind keine Arten von Verbindungen verfügbar.")
        return
    spec = st.selectbox(
        "Art der Verbindung",
        specs,
        key="new_conn_kind",
        format_func=lambda s: s["title"],
        help="Womit der Würfel sprechen soll. Alle Arten lassen sich später einzeln testen.",
    )
    st.caption(spec["description"])
    name = st.text_input(
        "Name der Verbindung",
        key=f"new_conn_name_{spec['kind']}",
        max_chars=100,
        placeholder="z. B. Wohnzimmer",
        help="Frei wählbar, nur zur Anzeige. Jeder Name darf nur einmal vorkommen.",
    )
    values = render_fields(spec["config_fields"], key_prefix=f"new_conn_{spec['kind']}")
    if st.button(
        "Verbindung anlegen",
        key="new_conn_create",
        type="primary",
        icon=":material/add:",
        help="Legt die Verbindung an. Danach können Sie sie testen.",
    ):
        ok, created = call(client.create_integration, spec["kind"], name, values)
        if ok and created:
            message = f"„{created['name']}“ wurde angelegt."
            if spec["can_pair"]:
                message += " Nächster Schritt: **Koppeln** (Tab „Prüfen“)."
            st.session_state[FLASH_KEY] = message
            _clear_new_form()  # a typed password must not linger in the form
            st.rerun()
    st.button(
        "Würfel-Seiten zuordnen",
        key="conn_to_faces",
        on_click=go,
        args=("faces",),
        help="Öffnet den Assistenten, in dem Sie dem Würfel den Steuerungsmodus und jeder Seite "
        "eine Aktion geben.",
    )


def _clear_new_form() -> None:
    """Forget what was typed into the "new connection" form (secrets included)."""
    for key in [k for k in st.session_state if str(k).startswith("new_conn_")]:
        if key not in ("new_conn_kind", "new_conn_create"):
            del st.session_state[key]


def _history(client: ApiClient, tz: str) -> None:
    st.subheader("Letzte Aktionen")
    ok, jobs = call(client.jobs, 30)
    if not ok or jobs is None:
        return
    if not jobs:
        st.caption(
            "Noch wurde keine Aktion gesendet. Sobald der Würfel im Steuerungsmodus eine Seite "
            "meldet, erscheint sie hier mit dem Ergebnis."
        )
        return
    rows = [
        {
            "Zeit": format_local(job["created_at"], tz, with_seconds=True),
            "Verbindung": job["integration"],
            "Aktion": job["label"],
            "Seite": job["face"] if job["face"] is not None else "–",
            "Ergebnis": STATUS_TEXT.get(job["status"], job["status"]),
            "Hinweis": job["error"] or "",
        }
        for job in jobs
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
