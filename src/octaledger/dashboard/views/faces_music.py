"""Music mode in the setup assistant: give a face a title instead of an activity or action.

For a cube in *music* mode each face plays one title. The user pastes a **link** (Spotify,
YouTube, an internet radio stream); OctaLedger shows what it recognised, the user picks the
**target** that plays it (the local player or a media player of Home Assistant), the volume and a
name, and saves. A face **without** a title is a "silence face": turning the cube onto it stops
the music like the holder does.

The behaviour of the cube (what the holder does, a delay, the default volume) is set in the
fold-out below the face editor. All texts explain what happens; nothing is invented.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import call
from octaledger.dashboard_client.client import ApiClient

FLASH_KEY = "faces_flash"
HOLDER_ACTIONS = {
    "stop": "Musik ganz beenden (Voreinstellung)",
    "pause": "Musik pausieren (wenn das Ziel es kann)",
}


def render_music_editor(client: ApiClient, device: dict[str, Any], face: int) -> None:
    """Draw the title editor of ``face`` and the settings of the cube."""
    ok_c, connections = call(client.integrations)
    ok_s, specs = call(client.adapters)
    if not (ok_c and ok_s) or connections is None or specs is None:
        return
    capable = {s["kind"]: s for s in specs if s.get("music_capable")}
    usable = [c for c in connections if c["enabled"] and c["kind"] in capable]
    current = device["actions"].get(str(face))
    st.markdown(
        f"**Seite {face}**" + (" – hat einen Titel" if current else " – ohne Titel (Stille)")
    )
    if not current:
        st.caption(
            "Eine Seite ohne Titel ist eine **Stille-Seite**: Dreht man den Würfel darauf, "
            "wird die Musik beendet."
        )
    prefix = f"faces_music_{device['id']}_{face}"
    if not usable:
        st.info(
            "Es gibt noch keine Verbindung, die Musik abspielen kann. Legen Sie auf der Seite "
            "**Smarthome & Verbindungen** einen **Lokalen Player** oder **Home Assistant** an."
        )
        st.button(
            "Zu den Verbindungen",
            key="faces_music_to_connections",
            on_click=go,
            args=("connections",),
            type="primary",
            help="Öffnet die Seite, auf der Sie Verbindungen anlegen und testen.",
        )
        _clear(client, device, face, current)
        _settings(client, device)
        return

    target = st.selectbox(
        "Wo soll die Musik spielen?",
        usable,
        index=_index(usable, current["integration_id"]) if current else 0,
        key=f"{prefix}_target",
        format_func=lambda c: f"{c['name']} ({capable[c['kind']]['title']})",
        help="Das Ziel der Wiedergabe: dieser PC (Lokaler Player) oder ein Lautsprecher/Display "
        "über Home Assistant.",
    )
    link = st.text_input(
        "Link oder Stream-Adresse",
        key=f"{prefix}_link",
        max_chars=2000,
        placeholder="https://open.spotify.com/playlist/… oder https://radio.example/live.mp3",
        help="Fügen Sie einen Spotify-, YouTube- oder YouTube-Music-Link oder die Adresse eines "
        "Internetradio-Streams ein. Was erkannt wird, steht darunter.",
    ).strip()
    recognised = None
    if link:
        ok, recognised = call(client.parse_music, link)
        if ok and recognised:
            st.success(f"Erkannt: {recognised['description']} (`{recognised['uri']}`)")
    options: dict[str, str] = {}
    if target["kind"] == "homeassistant":
        options["entity_id"] = _media_player(client, prefix, target)
    volume = st.slider(
        "Lautstärke in %",
        0,
        100,
        50,
        key=f"{prefix}_volume",
        help="Die Lautstärke, mit der dieser Titel startet. Voreinstellung: die des Würfels "
        "(unten einstellbar).",
    )
    label = st.text_input(
        f"Name der Seite {face}",
        value=current["label"] if current else "",
        key=f"{prefix}_label",
        max_chars=100,
        placeholder="z. B. Lofi Radio",
        help="Wie dieser Titel heißt. Er erscheint im Bild und in der Live-Ansicht.",
    ).strip()
    left, right = st.columns([3, 2])
    if left.button(
        f"Titel für Seite {face} speichern",
        key=f"{prefix}_save",
        type="primary",
        width="stretch",
        disabled=not (link and label and recognised),
        icon=":material/save:",
        help="Speichert den Titel dieser Seite. Er startet, sobald Sie den Würfel auf diese "
        "Seite stellen.",
    ):
        done, _ = call(
            client.set_music_title,
            device["id"],
            face,
            target["id"],
            link,
            label,
            volume,
            options,
        )
        if done:
            st.session_state[FLASH_KEY] = f"Seite {face} spielt jetzt „{label}“."
            st.rerun()
    _clear(client, device, face, current, column=right)
    _settings(client, device)


def _media_player(client: ApiClient, prefix: str, target: dict[str, Any]) -> str:
    """Choose the Home Assistant media player (listed from Home Assistant on request)."""
    found_key = f"faces_music_players_{target['id']}"
    if st.button(
        "Mediengeräte auflisten",
        key=f"{prefix}_discover",
        icon=":material/search:",
        help="Fragt Home Assistant nach Lautsprechern und Displays.",
    ):
        ok, items = call(client.discover_integration, target["id"])
        if ok:
            st.session_state[found_key] = (items or {}).get("media_player", [])
    players = st.session_state.get(found_key) or []
    if players:
        names = {p["id"]: p["name"] for p in players}
        return str(
            st.selectbox(
                "Mediengerät",
                list(names),
                format_func=names.__getitem__,
                key=f"{prefix}_player",
                help="Der Lautsprecher oder das Display, das die Musik spielen soll.",
            )
        )
    return st.text_input(
        "Mediengerät (entity_id)",
        key=f"{prefix}_player_text",
        placeholder="media_player.wohnzimmer",
        help="Der Name des Geräts in Home Assistant („media_player.…“). „Mediengeräte auflisten“ "
        "zeigt Ihre Geräte zum Auswählen.",
    ).strip()


def _settings(client: ApiClient, device: dict[str, Any]) -> None:
    """What the holder does, how long it waits, and the default volume of this cube."""
    ok, current = call(client.music_settings, device["id"])
    if not ok or current is None:
        return
    did = device["id"]
    with st.expander("Verhalten dieses Würfels (Halterung)", key=f"music_settings_{did}"):
        st.caption(
            "In der **Halterung** (der Würfel steht auf keiner Seite) hält die Musik an. Hier "
            "legen Sie fest, ob sie ganz endet oder nur pausiert und ob es kurz dauern darf."
        )
        action = st.selectbox(
            "In der Halterung",
            list(HOLDER_ACTIONS),
            index=list(HOLDER_ACTIONS).index(current["base_action"]),
            format_func=HOLDER_ACTIONS.__getitem__,
            key=f"music_base_{did}",
            help="Was passiert, wenn der Würfel in der Halterung steht. Voreinstellung: beenden. "
            "Der lokale Player kennt keine Pause und beendet immer.",
        )
        delay = st.number_input(
            "Wartezeit vor dem Anhalten (Sekunden)",
            min_value=0.0,
            max_value=60.0,
            value=current["stop_delay_ms"] / 1000,
            step=0.5,
            key=f"music_delay_{did}",
            help="So lange wartet OctaLedger, bevor die Musik in der Halterung angehalten wird. "
            "Voreinstellung: 0 (sofort).",
        )
        volume = st.slider(
            "Standard-Lautstärke in %",
            0,
            100,
            int(current["default_volume"]),
            key=f"music_volume_{did}",
            help="Mit dieser Lautstärke beginnt ein neuer Titel, wenn Sie nichts anderes wählen. "
            "Voreinstellung: 50.",
        )
        if st.button(
            "Speichern",
            key=f"music_settings_save_{did}",
            icon=":material/save:",
            help="Speichert das Verhalten dieses Würfels.",
        ):
            if call(client.set_music_settings, did, action, round(delay * 1000), volume)[0]:
                st.rerun()


def _clear(
    client: ApiClient,
    device: dict[str, Any],
    face: int,
    current: dict[str, Any] | None,
    column: Any = None,
) -> None:
    holder = column if column is not None else st
    if holder.button(
        "Titel entfernen",
        key=f"faces_music_{device['id']}_{face}_clear",
        width="stretch",
        disabled=current is None,
        icon=":material/delete:",
        help="Entfernt den Titel; die Seite wird zur Stille-Seite. Die Verbindung bleibt.",
    ):
        if call(client.clear_action, device["id"], face)[0]:
            st.session_state[FLASH_KEY] = f"Seite {face} ist jetzt eine Stille-Seite."
            st.rerun()


def _index(items: list[dict[str, Any]], wanted: str | None) -> int:
    return next((i for i, item in enumerate(items) if item["id"] == wanted), 0)
