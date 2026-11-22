"""The "Jetzt läuft" card of the page *Musik-Player*: what plays and the controls (AP-62).

It redraws every second (``st.fragment(run_every=...)``) from ``GET /player/status`` and shows the
truth the audio worker reports, not a guess: the title, the position in the queue, repeat and
shuffle, the volume and the last problem in plain German. The controls work at any moment:
previous, pause/resume, next, stop, repeat, shuffle, volume and jumping to a track.

Control callbacks never draw (output of a callback is lost on the next redraw); an error is kept
in ``st.session_state`` and shown by the card on its next redraw.
"""

from __future__ import annotations

from typing import Any, Final

import pandas as pd
import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.dashboard.ui import call
from octaledger.dashboard_client.client import ApiClient
from octaledger.domain.playlist import REPEAT_TEXT

ERROR_KEY: Final = "player_error"
SYNC_KEY: Final = "player_synced_since"
REPEAT_SHORT: Final = {"off": "Einmal", "all": "Alles", "one": "Ein Titel"}
REPEAT_ICON: Final = {
    "off": ":material/trending_flat:",
    "all": ":material/repeat:",
    "one": ":material/repeat_one:",
}


def control(client: ApiClient, target: str, action: str, value: Any = None) -> None:
    """Send a control command; a problem is remembered for the card instead of drawn here."""
    try:
        client.player_control(target, action, value)
    except OctaLedgerError as exc:
        st.session_state[ERROR_KEY] = exc.user_message


def _from_widget(client: ApiClient, action: str, key: str) -> None:
    """Callback of repeat, shuffle and volume: send what the widget now shows."""
    control(client, "local", action, st.session_state.get(key))


def _jump(client: ApiClient) -> None:
    """Callback of "Abspielen" in the list: jump to the track chosen in the select box."""
    control(client, "local", "jump", st.session_state.get("player_jump_pick"))


def stop_everything(client: ApiClient) -> None:
    """Callback of the big stop button: every player, each one tried."""
    try:
        problems = client.player_stop()
    except OctaLedgerError as exc:
        st.session_state[ERROR_KEY] = exc.user_message
        return
    if problems:
        st.session_state[ERROR_KEY] = "Nicht alles ließ sich stoppen: " + "; ".join(problems)


@st.fragment(run_every="1s")
def now_playing(client: ApiClient) -> None:
    """Draw the card (see the module docstring)."""
    ok, status = call(client.player_status)
    if not ok or status is None:
        return
    local, browser = status["local"], status["browser"]
    error = st.session_state.pop(ERROR_KEY, None)
    with st.container(border=True, key="player_now_card"):
        st.subheader("Jetzt läuft", help="Zeigt, was gerade spielt, und steuert es.")
        if error:
            st.error(error, icon=":material/error:")
        if local["state"] != "stopped":
            _local(client, local)
        elif browser.get("playing"):
            _browser(client, browser)
        else:
            st.caption(
                "Es spielt nichts. Starten Sie unten etwas oder drehen Sie den Würfel auf eine "
                "Seite mit einem Titel."
            )
        if local.get("error") and local["state"] == "stopped":
            st.warning(local["error"], icon=":material/warning:")
        st.button(
            "Alles stoppen",
            key="player_stop_all",
            icon=":material/stop_circle:",
            on_click=stop_everything,
            args=(client,),
            help="Beendet die Wiedergabe auf allen Playern (dieser PC, Player in der App, "
            "Spotify). Das geht jederzeit, auch wenn der Würfel noch auf einer Seite liegt.",
        )


def _local(client: ApiClient, local: dict[str, Any]) -> None:
    """The card of the local player."""
    paused = local["state"] == "paused"
    queue = list(local["queue"])
    kind = "Radio-Stream" if local["source"] == "stream" else "Datei"
    st.markdown(f"### {'⏸' if paused else '▶'} {local['title']}")
    parts = [kind]
    if local["total"] > 1:
        parts.append(f"Titel {local['position']} von {local['total']}")
    parts.append(REPEAT_TEXT[local["repeat"]].capitalize())
    if local["shuffle"]:
        parts.append("zufällige Reihenfolge")
    if paused:
        parts.append("pausiert")
    st.caption(" · ".join(parts))
    if local.get("error"):
        st.warning(local["error"], icon=":material/warning:")
    # When a new track starts, take over repeat, shuffle and volume from the player once, so a
    # change made by the cube is visible without overwriting what the user just moved.
    if st.session_state.get(SYNC_KEY) != local["since"]:
        st.session_state[SYNC_KEY] = local["since"]
        st.session_state["player_repeat"] = local["repeat"]
        st.session_state["player_shuffle"] = local["shuffle"]
        st.session_state["player_volume"] = local["volume"]
    prev, toggle, nxt, stop = st.columns(4)
    prev.button(
        "Zurück",
        key="player_prev",
        icon=":material/skip_previous:",
        width="stretch",
        on_click=control,
        args=(client, "local", "previous"),
        help="Springt zum vorherigen Titel der Liste.",
    )
    toggle.button(
        "Fortsetzen" if paused else "Pause",
        key="player_pause",
        icon=":material/play_arrow:" if paused else ":material/pause:",
        width="stretch",
        type="primary",
        on_click=control,
        args=(client, "local", "resume" if paused else "pause"),
        help="Hält die Wiedergabe an oder setzt sie fort. Bei einem Radio-Stream läuft die "
        "Verbindung weiter.",
    )
    nxt.button(
        "Weiter",
        key="player_next",
        icon=":material/skip_next:",
        width="stretch",
        on_click=control,
        args=(client, "local", "next"),
        help="Springt zum nächsten Titel der Liste.",
    )
    stop.button(
        "Stopp",
        key="player_stop",
        icon=":material/stop:",
        width="stretch",
        on_click=control,
        args=(client, "local", "stop"),
        help="Beendet die Wiedergabe dieses PCs und leert die Liste.",
    )
    left, middle, right = st.columns([3, 2, 4], vertical_alignment="bottom")
    left.segmented_control(
        "Wiederholen",
        list(REPEAT_SHORT),
        key="player_repeat",
        required=True,
        format_func=lambda k: REPEAT_SHORT[k],
        on_change=_from_widget,
        args=(client, "repeat", "player_repeat"),
        help="Einmal: die Liste läuft einmal durch. Alles: sie beginnt von vorn. Ein Titel: der "
        "aktuelle Titel wird endlos wiederholt, bis Sie stoppen.",
    )
    middle.toggle(
        "Zufällig",
        key="player_shuffle",
        on_change=_from_widget,
        args=(client, "shuffle", "player_shuffle"),
        help="Mischt die Reihenfolge der Titel; der laufende Titel bleibt.",
    )
    right.slider(
        "Lautstärke",
        0,
        100,
        key="player_volume",
        format="%d %%",
        on_change=_from_widget,
        args=(client, "volume", "player_volume"),
        help="Lautstärke dieses Players (nicht die von Windows).",
    )
    if len(queue) > 1:
        _queue(client, local, queue)


def _queue(client: ApiClient, local: dict[str, Any], queue: list[str]) -> None:
    """The queue in play order with the current title marked, and a way to jump."""
    current = local["position"] - 1
    with st.expander(f"Liste ({local['total']} Titel)", key="player_queue_box"):
        st.dataframe(
            pd.DataFrame(
                {
                    "": ["▶" if i == current else "" for i in range(len(queue))],
                    "Nr.": range(1, len(queue) + 1),
                    "Titel": queue,
                }
            ),
            hide_index=True,
            width="stretch",
            height=min(35 * len(queue) + 38, 320),
            alt="Die Titel der Wiedergabeliste in Abspielreihenfolge",
        )
        if len(queue) < local["total"]:
            st.caption(f"Gezeigt werden die ersten {len(queue)} von {local['total']} Titeln.")
        pick, go = st.columns([4, 1], vertical_alignment="bottom")
        pick.selectbox(
            "Springen zu",
            range(len(queue)),
            index=current,
            key="player_jump_pick",
            format_func=lambda i: f"{i + 1}. {queue[i]}",
            help="Wählen Sie einen Titel der Liste und springen Sie direkt dorthin.",
        )
        go.button(
            "Abspielen",
            key="player_jump",
            icon=":material/play_arrow:",
            width="stretch",
            on_click=_jump,
            args=(client,),
            help="Spielt den gewählten Titel jetzt.",
        )


def _browser(client: ApiClient, browser: dict[str, Any]) -> None:
    """The card of the player in the app (YouTube): only the state, it plays in the page."""
    link = f"https://www.youtube.com/watch?v={browser['video_id']}"
    st.markdown(f"### ▶ YouTube-Video `{browser['video_id']}`")
    parts = ["Player in der App"]
    if browser.get("list_id"):
        parts.append("mit Playlist")
    parts.append(REPEAT_TEXT.get(browser.get("repeat", "off"), "").capitalize())
    if browser.get("shuffle"):
        parts.append("zufällige Reihenfolge")
    st.caption(" · ".join(p for p in parts if p))
    st.link_button(
        "Auf YouTube öffnen",
        link,
        icon=":material/open_in_new:",
        help="Öffnet das Video auf youtube.com in einem neuen Tab (falls es sich nicht einbetten "
        "lässt).",
    )
    st.button(
        "Anhalten",
        key="player_browser_stop",
        icon=":material/stop:",
        on_click=control,
        args=(client, "browser", "stop"),
        help="Hält den Player in der App an.",
    )
