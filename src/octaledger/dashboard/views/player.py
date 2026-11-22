"""Page "Musik-Player": the built-in player for YouTube and YouTube Music titles.

The agent cannot control a browser, so this page *is* the player: it reads the wanted state from
``GET /music/browser-state`` every second and draws the embedded YouTube player. **Music plays only
while this page is open.** The player loads the video from youtube-nocookie.com (a cross-origin frame; no third-party
script runs in the dashboard), so nothing is loaded until the user agrees on this page (the agreement lasts for the browser session only).

The HTML is built by :func:`player_document` from a few validated values (a video id, an optional
playlist id, a volume); the same state yields the **same** text, so the browser keeps the running
player instead of reloading it on every refresh.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urlencode

import streamlit as st

from octaledger.dashboard.ui import call, page_help
from octaledger.dashboard_client.client import ApiClient

CONSENT_KEY = "player_consent"
_VIDEO = re.compile(r"^[A-Za-z0-9_-]{11}$")
_LIST = re.compile(r"^[A-Za-z0-9_-]{10,60}$")
HEIGHT = 340
ORIGIN = "https://www.youtube-nocookie.com"
EMBED = ORIGIN + "/embed"


def _json_for_script(value: dict[str, Any]) -> str:
    """JSON that is safe inside a ``<script>`` element (no ``</script>``, no HTML comment)."""
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def player_document(state: dict[str, Any]) -> str:
    """The HTML page of the embedded player for ``state`` (pure; the ids are validated again).

    A stopped state, or ids of the wrong shape, give a page without any external content.

    The player is a plain cross-origin ``<iframe>`` of youtube-nocookie.com; **no third-party
    script runs in this page** (volume and play are sent with ``postMessage``). The only script
    here is ours and contains nothing but validated values.
    """
    video = str(state.get("video_id") or "")
    playlist = str(state.get("list_id") or "")
    if not state.get("playing") or not _VIDEO.match(video):
        return "<p style='font-family:sans-serif'>Es spielt nichts.</p>"
    config = {
        "video": video,
        "list": playlist if _LIST.match(playlist) else "",
        "volume": max(0, min(100, int(state.get("volume", 50)))),
    }
    query = {"autoplay": "1", "playsinline": "1", "enablejsapi": "1", "rel": "0"}
    if config["list"]:
        query.update({"list": str(config["list"]), "listType": "playlist"})
    source = f"{EMBED}/{video}?{urlencode(query)}"
    return f"""<!doctype html><meta charset="utf-8">
<style>body{{margin:0;font-family:sans-serif}}iframe{{border:0;width:100%;height:240px}}
button{{margin:8px 0;padding:6px 12px}}</style>
<iframe id="yt" src="{html.escape(source, quote=True)}" title="YouTube"
  allow="autoplay; encrypted-media; picture-in-picture"
  referrerpolicy="strict-origin-when-cross-origin"></iframe>
<button id="unlock" type="button">Wiedergabe freischalten</button>
<p id="msg"></p>
<script>
const CFG = {_json_for_script(config)};
const ORIGIN = {_json_for_script({"o": ORIGIN})}.o;
const frame = document.getElementById('yt');
const msg = (t) => {{ document.getElementById('msg').textContent = t; }};
const send = (func, args) => frame.contentWindow.postMessage(
  JSON.stringify({{event: 'command', func: func, args: args || []}}), ORIGIN);
const start = () => {{ send('setVolume', [CFG.volume]); send('playVideo'); }};
frame.addEventListener('load', () => {{
  frame.contentWindow.postMessage(JSON.stringify({{event: 'listening', id: 1}}), ORIGIN);
  setTimeout(start, 600);
}});
window.addEventListener('message', (e) => {{
  if (e.origin !== ORIGIN || e.source !== frame.contentWindow) return;
  let data = null;
  try {{ data = JSON.parse(e.data); }} catch (err) {{ return; }}
  if (data.event === 'onReady') start();
  if (data.event === 'onError') {{
    msg([101, 150].includes(data.info)
      ? 'Dieses Video darf nicht eingebettet werden.'
      : 'Das Video kann nicht abgespielt werden (Code ' + data.info + ').');
  }}
}});
document.getElementById('unlock').addEventListener('click', () => {{ start(); msg(''); }});
</script>"""


def render(client: ApiClient, tz: str) -> None:
    """Render the page."""
    st.header("Musik-Player")
    page_help(
        "So funktioniert der Musik-Player",
        "Dieser Player spielt **YouTube- und YouTube-Music-Titel**, die ein Würfel im "
        "Musik-Modus auslöst (Ziel „Player in der App“).\n\n"
        "- **Die Musik läuft nur, solange diese Seite in einem Browser geöffnet ist.** "
        "OctaLedger kann keinen Browser fernsteuern.\n"
        "- **Datenschutz:** Der Player lädt Inhalte von youtube.com; Google erhält dabei "
        "Anfragen. Darum wird nichts geladen, bevor Sie unten zustimmen.\n"
        "- **Wiedergabe freischalten:** Browser blockieren Ton ohne Klick. Drücken Sie einmal "
        "den Knopf im Player.\n"
        "- Nicht jedes Video darf eingebettet werden; dann steht das im Player.\n"
        "- **Einrichten:** Verbindung „Player in der App (YouTube)“ anlegen, im Musik-Modus als "
        "Ziel wählen und YouTube-Links als Titel eintragen.",
    )
    if not st.session_state.get(CONSENT_KEY):
        st.info(
            "Der Player ist noch **nicht geladen**. Er holt Skripte und Videos von "
            "**youtube.com**; dabei erfährt Google, dass diese Seite aufgerufen wird."
        )
        if st.button(
            "Player laden (Verbindung zu youtube.com erlauben)",
            key="player_consent_button",
            type="primary",
            icon=":material/play_circle:",
            help="Erlaubt diesem Browser, den YouTube-Player zu laden. Die Zustimmung "
            "gilt, bis Sie die Seite schließen oder neu laden.",
        ):
            st.session_state[CONSENT_KEY] = True
            st.rerun()
        return
    _player(client)


@st.fragment(run_every="1s")
def _player(client: ApiClient) -> None:
    """Redraw the player from the wanted state (same state = same page = running player)."""
    ok, state = call(client.browser_player_state)
    if not ok or state is None:
        return
    if state.get("playing"):
        st.caption("Jetzt läuft der Titel, den der Würfel gewählt hat. Diese Seite offen lassen.")
    else:
        st.caption("Es spielt nichts. Drehen Sie den Würfel auf eine Seite mit einem Titel.")
    # st.iframe replaces the deprecated st.components.v1.html; the page text is built only from
    # validated ids (see player_document), because the frame runs with access to this app.
    st.iframe(player_document(state), height=HEIGHT)
    st.caption("Nicht jedes Video lässt sich einbetten; Fehler zeigt der Player an.")
