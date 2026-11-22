"""GUI tests of the page "Musik-Player": playing, controlling, YouTube consent, help texts."""

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from octaledger.dashboard.views.player import player_document
from octaledger.infrastructure.audio.worker import AudioWorker
from octaledger.infrastructure.integrations.browser import BrowserAdapter
from octaledger.infrastructure.integrations.player import PlayerAdapter
from tests.conftest import RunningApi
from tests.gui.test_gui_core import texts
from tests.gui.test_gui_devices_catalog import open_page
from tests.unit.test_local_player import QueueEngine, make_album, wait_for


class Players:
    """The real adapters with a fake sound engine, registered in the test server."""

    def __init__(self, api: RunningApi) -> None:
        self.api = api
        self.engine = QueueEngine()
        self.local = PlayerAdapter(
            AudioWorker(lambda: self.engine, ffmpeg_finder=lambda: None),
            ffmpeg_finder=lambda: None,
        )
        self.browser = BrowserAdapter()
        adapters = api.context.integrations._adapters  # type: ignore[union-attr]
        adapters["player"] = self.local
        adapters["browser"] = self.browser

    def status(self) -> dict[str, Any]:
        return self.api.client.player_status()["local"]


@pytest.fixture
def players(api_server: RunningApi) -> Players:
    return Players(api_server)


def click(at: AppTest, key: str) -> None:
    next(b for b in at.button if b.key == key).click().run()


def test_the_page_starts_empty_with_help_and_three_sources(
    api_server: RunningApi, players: Players
) -> None:
    at = open_page(api_server, "player")
    assert at.header[0].value == "Musik-Player"
    assert any("So funktioniert der Musik-Player" in e.label for e in at.expander)
    assert any("Es spielt nichts" in c.value for c in at.caption)
    assert [t.label for t in at.tabs] == [
        ":material/computer: Dieser PC",
        ":material/smart_display: YouTube & YouTube Music",
        ":material/music_note: Spotify",
    ]
    assert next(b for b in at.button if b.key == "player_play_local").disabled  # no path yet
    assert next(b for b in at.button if b.key == "player_pick_file").help


def test_a_folder_plays_and_the_card_shows_title_position_and_controls(
    api_server: RunningApi, players: Players, tmp_path: Path
) -> None:
    album = make_album(tmp_path)
    at = open_page(api_server, "player")
    at.text_input(key="player_path").set_value(str(album))
    at.segmented_control(key="player_new_repeat").set_value("all")
    at.toggle(key="player_new_shuffle").set_value(False)
    at.slider(key="player_new_volume").set_value(35).run()
    click(at, "player_play_local")
    assert not at.exception
    assert any("4 Titel werden abgespielt" in s.value for s in at.success)
    wait_for(lambda: players.status()["state"] == "playing")
    at.run()
    assert any("1 one" in m.value for m in at.markdown)
    assert any("Titel 1 von 4" in c.value and "Alles wiederholen" in c.value for c in at.caption)
    for key in ("player_prev", "player_pause", "player_next", "player_stop", "player_stop_all"):
        assert next(b for b in at.button if b.key == key).help


def test_the_controls_pause_skip_repeat_volume_jump_and_stop(
    api_server: RunningApi, players: Players, tmp_path: Path
) -> None:
    players.local.play(str(make_album(tmp_path)), repeat="off", volume=40)
    wait_for(lambda: players.status()["state"] == "playing")
    at = open_page(api_server, "player")
    click(at, "player_pause")
    wait_for(lambda: players.status()["state"] == "paused")
    at.run()
    assert any("pausiert" in c.value for c in at.caption)
    click(at, "player_pause")  # now "Fortsetzen"
    wait_for(lambda: players.status()["state"] == "playing")
    click(at, "player_next")
    wait_for(lambda: players.status()["position"] == 2)
    at.segmented_control(key="player_repeat").set_value("one").run()
    wait_for(lambda: players.status()["repeat"] == "one")
    at.toggle(key="player_shuffle").set_value(True).run()
    wait_for(lambda: players.status()["shuffle"] is True)
    at.slider(key="player_volume").set_value(75).run()
    wait_for(lambda: players.status()["volume"] == 75)
    at.selectbox(key="player_jump_pick").set_value(3)
    click(at, "player_jump")
    wait_for(lambda: players.status()["title"] == players.status()["queue"][3])
    click(at, "player_stop")
    wait_for(lambda: players.status()["state"] == "stopped")
    assert not at.exception


def test_stop_all_stops_the_local_player_and_the_youtube_player(
    api_server: RunningApi, players: Players, tmp_path: Path
) -> None:
    players.local.play(str(make_album(tmp_path)))
    players.browser.execute(
        {}, {}, {"action": "browser_play", "video_id": "dQw4w9WgXcQ", "volume": 40}, timeout=1
    )
    wait_for(lambda: players.status()["state"] == "playing")
    at = open_page(api_server, "player")
    click(at, "player_stop_all")
    wait_for(
        lambda: players.status()["state"] == "stopped" and not players.browser.state()["playing"]
    )
    assert not at.exception


def test_a_wrong_path_is_explained_and_nothing_plays(
    api_server: RunningApi, players: Players, tmp_path: Path
) -> None:
    at = open_page(api_server, "player")
    at.text_input(key="player_path").set_value(str(tmp_path / "gibt-es-nicht.mp3")).run()
    click(at, "player_play_local")
    assert not at.exception
    assert any("gibt es nicht" in e.value for e in at.error)
    assert players.status()["state"] == "stopped"
    at.text_input(key="player_path").set_value("//server/share/a.mp3").run()
    click(at, "player_play_local")
    assert any("Netzwerkpfade" in e.value for e in at.error)


def test_youtube_asks_for_consent_first_and_a_link_starts_the_player_state(
    api_server: RunningApi, players: Players
) -> None:
    at = open_page(api_server, "player")
    assert "youtube.com" in texts(at)
    assert not any("iframe" in str(e).lower() for e in at.main)  # nothing external yet
    button = next(b for b in at.button if b.key == "player_consent_button")
    assert button.help
    at.text_input(key="player_yt_link").set_value(
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabcdefghijk1"
    )
    at.segmented_control(key="player_yt_repeat").set_value("all")
    at.toggle(key="player_yt_shuffle").set_value(True).run()
    click(at, "player_play_youtube")
    state = players.browser.state()
    assert state["playing"] and state["video_id"] == "dQw4w9WgXcQ" and state["list_id"]
    assert state["repeat"] == "all" and state["shuffle"] is True
    next(b for b in at.button if b.key == "player_consent_button").click().run()
    assert not at.exception
    assert any("Dieser Titel läuft hier" in c.value for c in at.caption)
    assert at.toggle(key="player_account").value is False  # the account is opt-in
    assert any("YouTube-Video" in m.value for m in at.markdown)  # shown in "Jetzt läuft"


def test_spotify_without_a_connection_explains_what_to_do(
    api_server: RunningApi, players: Players
) -> None:
    at = open_page(api_server, "player")
    assert any("Verbindung" in i.value and "Spotify" in i.value for i in at.info)
    assert next(b for b in at.button if b.key == "player_to_connections").help


def test_every_input_has_a_help_text(api_server: RunningApi, players: Players) -> None:
    at = open_page(api_server, "player")
    widgets = [*at.text_input, *at.slider, *at.toggle, *at.segmented_control]
    widgets += [b for b in at.button if not getattr(b, "form_id", "")]
    assert [getattr(w, "key", w.label) for w in widgets if not w.help] == []


# ------------------------------------------------------------------ the embedded page


STATE = {"playing": True, "video_id": "dQw4w9WgXcQ", "list_id": "", "volume": 40}


def test_a_single_video_loops_through_its_own_playlist() -> None:
    page = player_document({**STATE, "repeat": "one"})
    assert "loop=1" in page and "playlist=dQw4w9WgXcQ" in page and "youtube-nocookie.com" in page
    assert "loop=1" not in player_document({**STATE, "repeat": "off"})


def test_a_playlist_loops_and_shuffles_through_the_api_commands() -> None:
    page = player_document({**STATE, "list_id": "PLabcdefghijk1", "repeat": "all", "shuffle": True})
    assert "listType=playlist" in page and "loop=1" not in page
    assert '"loop": true' in page and '"shuffle": true' in page and "setShuffle" in page


def test_the_account_option_switches_the_domain_and_errors_get_a_way_out() -> None:
    page = player_document(STATE, account=True)
    assert "https://www.youtube.com/embed/" in page and "nocookie" not in page.split("<script>")[0]
    assert "Auf YouTube öffnen" in page and "watch?v=dQw4w9WgXcQ" in page
    assert "Der Besitzer erlaubt keine Einbettung" in page and "Wiedergabe beendet" in page


def test_nothing_external_is_in_the_page_without_a_playing_state() -> None:
    for state in (
        {"playing": False, "video_id": "dQw4w9WgXcQ"},
        {"playing": True, "video_id": 'bad id"><script>'},
    ):
        assert "iframe" not in player_document(state)
