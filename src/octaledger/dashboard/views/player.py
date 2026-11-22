"""Page "Musik-Player": one place for local music, YouTube, YouTube Music and Spotify (AP-62).

* **Jetzt läuft** (:mod:`octaledger.dashboard.views.player_now`): what plays and the controls,
  refreshed every second from the truth the players report.
* **Abspielen:** three tabs start something right away, without the cube:
  *Dieser PC* (a file, a folder/album, a playlist file or a radio stream - the path can be typed
  or picked in the normal file dialog), *YouTube & YouTube Music* and *Spotify*.
* **Player in der App:** YouTube cannot be remote controlled, so this page *is* its player: it
  reads the wanted state from ``GET /music/browser-state`` and draws the embedded player. **That
  music plays only while this page is open.** Nothing is loaded from youtube.com until the user
  agrees; the agreement lasts for the browser session only.

The HTML of the embedded player is built by :func:`player_document` from a few validated values
(a video id, an optional playlist id, volume, repeat, shuffle); the same state yields the **same**
text, so the browser keeps the running player instead of reloading it on every refresh.

Honest limits: what YouTube shows (advertising, "not embeddable") is decided by YouTube, not by
this program, and OctaLedger neither removes advertising nor downloads videos; whether a
signed-in YouTube account removes advertising in the embedded player is **not verified**.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any, Final
from urllib.parse import urlencode

import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import call, page_help
from octaledger.dashboard.views.player_now import REPEAT_SHORT, now_playing
from octaledger.dashboard_client.client import ApiClient

CONSENT_KEY: Final = "player_consent"
FLASH_KEY: Final = "player_flash"
_VIDEO = re.compile(r"^[A-Za-z0-9_-]{11}$")
_LIST = re.compile(r"^[A-Za-z0-9_-]{10,60}$")
HEIGHT = 420
ORIGIN = "https://www.youtube-nocookie.com"
ACCOUNT_ORIGIN = "https://www.youtube.com"
EMBED = ORIGIN + "/embed"


def _json_for_script(value: dict[str, Any]) -> str:
    """JSON that is safe inside a ``<script>`` element (no ``</script>``, no HTML comment)."""
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def player_document(state: dict[str, Any], *, account: bool = False) -> str:
    """The HTML page of the embedded player for ``state`` (pure; the ids are validated again).

    A stopped state, or ids of the wrong shape, give a page without any external content.

    The player is a plain cross-origin ``<iframe>``; **no third-party script runs in this page**
    (volume, loop, shuffle and play are sent with ``postMessage``). The only script here is ours
    and contains nothing but validated values.

    Args:
        state: The wanted state of the browser player (``GET /music/browser-state``).
        account: Use ``youtube.com`` instead of ``youtube-nocookie.com``, so that a YouTube
            account signed in in this browser is recognised (Google then sets cookies).
    """
    video = str(state.get("video_id") or "")
    playlist = str(state.get("list_id") or "")
    if not state.get("playing") or not _VIDEO.match(video):
        return "<p style='font-family:sans-serif'>Es spielt nichts.</p>"
    origin = ACCOUNT_ORIGIN if account else ORIGIN
    repeat = str(state.get("repeat") or "off")
    config = {
        "video": video,
        "list": playlist if _LIST.match(playlist) else "",
        "volume": max(0, min(100, int(state.get("volume", 50)))),
        "loop": repeat in ("all", "one"),
        "shuffle": bool(state.get("shuffle")),
    }
    query = {"autoplay": "1", "playsinline": "1", "enablejsapi": "1", "rel": "0", "fs": "1"}
    if config["list"]:
        query.update({"list": str(config["list"]), "listType": "playlist"})
    elif config["loop"]:
        query.update({"loop": "1", "playlist": video})  # a single video loops via its own list
    source = f"{origin}/embed/{video}?{urlencode(query)}"
    watch = f"https://www.youtube.com/watch?v={video}"
    return f"""<!doctype html><meta charset="utf-8">
<style>body{{margin:0;font-family:sans-serif}}iframe{{border:0;width:100%;height:330px}}
button{{margin:8px 8px 8px 0;padding:6px 12px}}a{{margin-left:8px}}</style>
<iframe id="yt" src="{html.escape(source, quote=True)}" title="YouTube"
  allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
  referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
<button id="unlock" type="button">Wiedergabe freischalten</button>
<a id="open" href="{html.escape(watch, quote=True)}" target="_blank"
  rel="noopener noreferrer">Auf YouTube öffnen</a>
<p id="msg"></p>
<script>
const CFG = {_json_for_script(config)};
const ORIGIN = {_json_for_script({"o": origin})}.o;
const REASONS = {{
  2: 'Der Link enthält ein ungültiges Video.',
  5: 'Der Browser kann dieses Video nicht abspielen.',
  100: 'Das Video wurde entfernt oder ist privat.',
  101: 'Der Besitzer erlaubt keine Einbettung. Nutzen Sie „Auf YouTube öffnen“.',
  150: 'Der Besitzer erlaubt keine Einbettung. Nutzen Sie „Auf YouTube öffnen“.',
}};
const frame = document.getElementById('yt');
const msg = (t) => {{ document.getElementById('msg').textContent = t; }};
const send = (func, args) => frame.contentWindow.postMessage(
  JSON.stringify({{event: 'command', func: func, args: args || []}}), ORIGIN);
const start = () => {{
  send('setVolume', [CFG.volume]);
  if (CFG.list) {{ send('setLoop', [CFG.loop]); send('setShuffle', [CFG.shuffle]); }}
  send('playVideo');
}};
frame.addEventListener('load', () => {{
  frame.contentWindow.postMessage(JSON.stringify({{event: 'listening', id: 1}}), ORIGIN);
  setTimeout(start, 600);
}});
window.addEventListener('message', (e) => {{
  if (e.origin !== ORIGIN || e.source !== frame.contentWindow) return;
  let data = null;
  try {{ data = JSON.parse(e.data); }} catch (err) {{ return; }}
  if (data.event === 'onReady') start();
  if (data.event === 'onStateChange' && data.info === 0 && !CFG.loop) msg('Wiedergabe beendet.');
  if (data.event === 'onError') {{
    msg(REASONS[data.info] || ('Das Video kann nicht abgespielt werden (Code ' + data.info + ').'));
  }}
}});
document.getElementById('unlock').addEventListener('click', () => {{ start(); msg(''); }});
</script>"""


# ----------------------------------------------------------------------------- the page


def render(client: ApiClient, tz: str) -> None:
    """Render the page."""
    st.header("Musik-Player")
    page_help(
        "So funktioniert der Musik-Player",
        "Hier spielen Sie Musik **direkt** ab und steuern, was läuft – auch das, was der Würfel "
        "gestartet hat.\n\n"
        "- **Jetzt läuft:** zeigt Titel, Position in der Liste, Wiederholen und Lautstärke. "
        "Zurück, Pause, Weiter, Stopp und **Alles stoppen** gehen jederzeit.\n"
        "- **Dieser PC:** eine Datei, einen **Ordner (Album)** oder eine Playlist-Datei (.m3u) "
        "spielen, oder einen Radio-Stream. Den Pfad tippen oder mit **Datei/Ordner wählen** im "
        "Windows-Fenster aussuchen. Wiederholen: einmal, alles oder **einen Titel endlos**; "
        "optional zufällig. Ton und Video-Dateien: MP3, FLAC, WAV, OGG, mit FFmpeg auch AAC/M4A, "
        "WMA, Opus, MP4, MKV, WebM …\n"
        "- **YouTube und YouTube Music:** läuft im Player unten auf dieser Seite – **nur solange "
        "die Seite offen ist**. Nicht jedes Video darf eingebettet werden; dann hilft „Auf "
        "YouTube öffnen“. Werbung und Einschränkungen bestimmt YouTube.\n"
        "- **Spotify:** braucht eine Verbindung und ein aktives Spotify-Gerät.\n"
        "- **Vom Würfel aus:** Jede Würfelseite kann einen Titel starten (Seite *Seiten "
        "zuordnen*). In der Halterung kann die Musik enden, pausieren oder weiterlaufen.",
    )
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash, icon=":material/check_circle:")
    ok, status = call(client.player_status)
    if not ok or status is None:
        return
    now_playing(client)
    st.subheader("Abspielen")
    local_tab, youtube_tab, spotify_tab = st.tabs(
        [
            ":material/computer: Dieser PC",
            ":material/smart_display: YouTube & YouTube Music",
            ":material/music_note: Spotify",
        ]
    )
    with local_tab:
        _local_form(client, status)
    with youtube_tab:
        _youtube_form(client)
    with spotify_tab:
        _spotify_form(client, status)
    _embedded(client)


def _pick(client: ApiClient, kind: str) -> None:
    """Callback of the pick buttons: show the Windows dialog, put the choice into the path field."""
    try:
        chosen = client.pick_path(kind)
    except OctaLedgerError as exc:
        st.session_state["player_error"] = exc.user_message
        return
    if chosen:
        st.session_state["player_path"] = chosen


def _start(client: ApiClient, source: str, repeat: str, shuffle: bool, volume: int) -> bool:
    """Play ``source`` and remember the success message; ``True`` if it started."""
    ok, result = call(client.player_play, source, repeat=repeat, shuffle=shuffle, volume=volume)
    if ok and result is not None:
        st.session_state[FLASH_KEY] = result["message"]
    return bool(ok and result is not None)


def _repeat_and_shuffle(prefix: str, *, allow_one: bool = True) -> tuple[str, bool]:
    """The repeat and shuffle choices of a start form."""
    options = [k for k in REPEAT_SHORT if allow_one or k != "one"]
    repeat = st.segmented_control(
        "Wiederholen",
        options,
        default="off",
        required=True,
        key=f"{prefix}_repeat",
        format_func=lambda k: REPEAT_SHORT[k],
        help="Einmal: die Liste läuft einmal durch und endet. Alles: sie beginnt von vorn. "
        "Ein Titel: ein Titel läuft endlos, bis Sie stoppen oder den Würfel bewegen.",
    )
    shuffle = st.toggle(
        "Zufällige Reihenfolge",
        key=f"{prefix}_shuffle",
        help="Mischt die Titel eines Ordners oder einer Playlist.",
    )
    return str(repeat), shuffle


def _local_form(client: ApiClient, status: dict[str, Any]) -> None:
    """Start a file, a folder, a playlist file or a radio stream of this computer."""
    path = st.text_input(
        "Pfad oder Stream-Adresse",
        key="player_path",
        max_chars=1000,
        placeholder="C:/Musik/Album  oder  C:/Musik/lied.mp3  oder  https://radio.example/live.mp3",
        help="Eine Datei, ein Ordner (alle Titel darin, auch in Unterordnern, in "
        "Dateinamen-Reihenfolge), eine .m3u-Playlist oder die Adresse eines Radio-Streams. "
        "Netzwerkpfade sind nicht erlaubt.",
    ).strip()
    dialog = bool(status.get("dialog"))
    left, right, _ = st.columns([1, 1, 2])
    left.button(
        "Datei wählen …",
        key="player_pick_file",
        icon=":material/audio_file:",
        width="stretch",
        disabled=not dialog,
        on_click=_pick,
        args=(client, "file"),
        help="Öffnet das Windows-Auswahlfenster auf diesem Computer."
        if dialog
        else "Der Auswahldialog ist hier nicht verfügbar; tippen Sie den Pfad ein.",
    )
    right.button(
        "Ordner wählen …",
        key="player_pick_folder",
        icon=":material/folder_open:",
        width="stretch",
        disabled=not dialog,
        on_click=_pick,
        args=(client, "folder"),
        help="Wählt einen ganzen Ordner oder ein Album im Windows-Auswahlfenster."
        if dialog
        else "Der Auswahldialog ist hier nicht verfügbar; tippen Sie den Pfad ein.",
    )
    st.caption(status["formats"])
    if path:
        ok, recognised = call(client.parse_music, path)
        if ok and recognised and recognised["kind"] in ("local", "url"):
            st.caption(f"Erkannt: {recognised['description']}.")
    repeat, shuffle = _repeat_and_shuffle("player_new")
    volume = st.slider(
        "Lautstärke in %",
        0,
        100,
        50,
        key="player_new_volume",
        help="Mit dieser Lautstärke startet die Wiedergabe (nur dieser Player, nicht Windows).",
    )
    if st.button(
        "Abspielen",
        key="player_play_local",
        type="primary",
        icon=":material/play_arrow:",
        disabled=not path,
        help="Startet sofort und ersetzt, was auf diesem PC läuft.",
    ):
        if _start(client, path, repeat, shuffle, volume):
            st.rerun()
    error = st.session_state.pop("player_error", None)
    if error:
        st.error(error, icon=":material/error:")


def _youtube_form(client: ApiClient) -> None:
    """Start a YouTube or YouTube Music link in the player of this page."""
    link = st.text_input(
        "YouTube- oder YouTube-Music-Link",
        key="player_yt_link",
        max_chars=2000,
        placeholder="https://music.youtube.com/watch?v=…  oder  https://www.youtube.com/playlist…",
        help="Ein Link zu einem Video oder (mit list=…) zu einer Playlist. Der Titel spielt im "
        "Player unten auf dieser Seite.",
    ).strip()
    repeat, shuffle = _repeat_and_shuffle("player_yt")
    st.caption(
        "Bei einer Playlist wird immer die ganze Playlist wiederholt; „Ein Titel“ gilt für ein "
        "einzelnes Video."
    )
    volume = st.slider(
        "Lautstärke in %",
        0,
        100,
        50,
        key="player_yt_volume",
        help="Die Lautstärke des YouTube-Players beim Start.",
    )
    if st.button(
        "Abspielen",
        key="player_play_youtube",
        type="primary",
        icon=":material/play_arrow:",
        disabled=not link,
        help="Startet den Titel im Player unten. Dazu muss dort die Verbindung zu youtube.com "
        "erlaubt sein.",
    ):
        if _start(client, link, repeat, shuffle, volume):
            st.session_state.setdefault(CONSENT_KEY, False)
            st.rerun()


def _spotify_form(client: ApiClient, status: dict[str, Any]) -> None:
    """Start a Spotify link on the connected account."""
    if not status["spotify"]["connection_id"]:
        st.info(
            "Für Spotify brauchen Sie eine **Verbindung** zu Ihrem Spotify-Konto. Legen Sie sie "
            "auf der Seite „Smarthome & Verbindungen“ an."
        )
        st.button(
            "Zu den Verbindungen",
            key="player_to_connections",
            on_click=go,
            args=("connections",),
            type="primary",
            help="Öffnet die Seite, auf der Sie Spotify verbinden.",
        )
        return
    link = st.text_input(
        "Spotify-Link",
        key="player_sp_link",
        max_chars=2000,
        placeholder="https://open.spotify.com/playlist/…",
        help="Ein Link zu einem Titel, Album, einer Playlist oder einem Künstler.",
    ).strip()
    volume = st.slider(
        "Lautstärke in %",
        0,
        100,
        50,
        key="player_sp_volume",
        help="Die Lautstärke des Spotify-Geräts beim Start.",
    )
    st.caption(
        "Spotify spielt auf Ihrem aktiven Spotify-Gerät (App oder Lautsprecher). Wiederholen und "
        "Zufall stellen Sie in Spotify selbst ein."
    )
    if st.button(
        "Abspielen",
        key="player_play_spotify",
        type="primary",
        icon=":material/play_arrow:",
        disabled=not link,
        help="Schickt den Titel an Ihr aktives Spotify-Gerät.",
    ):
        if _start(client, link, "off", False, volume):
            st.rerun()


# -------------------------------------------------------------------- embedded YouTube


def _embedded(client: ApiClient) -> None:
    """The player of this page for YouTube (asks for consent before anything is loaded)."""
    ok, state = call(client.browser_player_state)
    if not ok or state is None:
        return
    st.subheader("Player in der App (YouTube)")
    if not st.session_state.get(CONSENT_KEY):
        st.info(
            "Der YouTube-Player ist noch **nicht geladen**. Er holt Skripte und Videos von "
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
    st.toggle(
        "Mit meinem YouTube-Konto abspielen",
        key="player_account",
        help="Nutzt youtube.com statt youtube-nocookie.com, damit ein in diesem Browser "
        "angemeldetes YouTube-Konto (z. B. Premium) erkannt wird. Google setzt dann Cookies. "
        "Ob dadurch Werbung entfällt, bestimmt YouTube; es ist nicht geprüft. Voreinstellung: aus.",
    )
    _frame(client)


@st.fragment(run_every="1s")
def _frame(client: ApiClient) -> None:
    """Redraw the player from the wanted state (same state = same page = running player)."""
    ok, state = call(client.browser_player_state)
    if not ok or state is None:
        return
    if state.get("playing"):
        st.caption("Dieser Titel läuft hier. Lassen Sie diese Seite geöffnet.")
    else:
        st.caption(
            "Es spielt nichts. Starten Sie oben einen YouTube-Link oder drehen Sie den Würfel."
        )
    # st.iframe replaces the deprecated st.components.v1.html; the page text is built only from
    # validated ids (see player_document), because the frame runs with access to this app.
    st.iframe(
        player_document(state, account=bool(st.session_state.get("player_account"))),
        height=HEIGHT,
    )
    st.caption("Nicht jedes Video lässt sich einbetten; Fehler zeigt der Player an.")
