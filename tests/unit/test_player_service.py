"""The player as seen from the app: direct play, control, stop, API and file dialog (AP-61/62)."""

import io
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from octaledger.application.integration_service import IntegrationService
from octaledger.application.player_service import PlayerService
from octaledger.core.errors import IntegrationError, InvalidStateError, ValidationError
from octaledger.core.secrets import SecretStore
from octaledger.infrastructure.audio.worker import AudioWorker
from octaledger.infrastructure.integrations.browser import BrowserAdapter
from octaledger.infrastructure.integrations.player import PlayerAdapter
from octaledger.infrastructure.integrations.spotify import SpotifyAdapter
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from octaledger.infrastructure.system.file_dialog import pick_path
from tests.conftest import RunningApi
from tests.unit.test_local_player import QueueEngine, make_album, wait_for


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.engine = QueueEngine()
        self.local = PlayerAdapter(
            AudioWorker(lambda: self.engine, ffmpeg_finder=lambda: None),
            ffmpeg_finder=lambda: None,
        )
        self.browser = BrowserAdapter()
        self.spotify = SpotifyAdapter()
        self.sent: list[dict[str, Any]] = []

        def record(config: Any, secrets: Any, params: Any, *, timeout: float) -> str:
            self.sent.append(dict(params))
            return "Spotify ok"

        self.spotify.execute = record  # type: ignore[method-assign]
        self.service = IntegrationService(
            self.storage,
            SecretStore(tmp_path / "s.json"),
            {"player": self.local, "browser": self.browser, "spotify": self.spotify},
        )
        self.players = PlayerService(self.storage, self.service)

    def add_spotify(self) -> str:
        info = self.service.create(
            "spotify", "Konto", {"client_id": "client-123", "refresh_token": "r"}
        )
        return str(info.integration.id)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_status_lists_every_player(env: Env) -> None:
    status = env.players.status()
    assert status["local"]["state"] == "stopped" and status["browser"]["playing"] is False
    assert status["spotify"] == {"connection_id": None}
    env.add_spotify()
    assert env.players.status()["spotify"]["connection_id"]


def test_a_folder_plays_on_the_local_player_with_repeat(env: Env, tmp_path: Path) -> None:
    album = make_album(tmp_path)
    result = env.players.play(str(album), repeat="all", shuffle=False, volume=35)
    assert result["player"] == "local" and result["tracks"] == 4
    wait_for(lambda: env.players.status()["local"]["state"] == "playing")
    local = env.players.status()["local"]
    assert local["repeat"] == "all" and local["volume"] == 35 and local["total"] == 4
    env.players.control("local", "next")
    wait_for(lambda: env.players.status()["local"]["position"] == 2)
    env.players.control("local", "stop")
    wait_for(lambda: env.players.status()["local"]["state"] == "stopped")


def test_a_youtube_link_goes_to_the_player_in_the_app(env: Env) -> None:
    result = env.players.play("https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabcdefghijk1")
    assert result["player"] == "browser"
    state = env.browser.state()
    assert state["playing"] and state["video_id"] == "dQw4w9WgXcQ" and state["list_id"]
    env.players.control("browser", "stop")
    assert env.browser.state()["playing"] is False


def test_spotify_needs_a_connection_and_then_sends_volume_and_title(env: Env) -> None:
    link = "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3"
    with pytest.raises(InvalidStateError):
        env.players.play(link)
    env.add_spotify()
    assert env.players.play(link, volume=40)["player"] == "spotify"
    assert [p["action"] for p in env.sent] == ["spotify_volume", "spotify_play"]
    env.players.control("spotify", "stop")
    assert env.sent[-1] == {"action": "spotify_pause"}


def test_a_stream_address_plays_locally(env: Env) -> None:
    env.local._worker._opener = lambda url, **kw: io.BytesIO(b"abcdef")  # type: ignore[union-attr]
    result = env.players.play("https://93.184.216.34/radio.mp3", volume=20)
    assert result["player"] == "local"
    wait_for(lambda: env.engine.events)
    assert env.engine.events[0] == ("play", ("stream", 0.2))


def test_unsafe_or_wrong_input_is_refused(env: Env, tmp_path: Path) -> None:
    for bad in ("", "relative.mp3", "//server/share/a.mp3", "https://127.0.0.1/stream"):
        with pytest.raises(ValidationError):
            env.players.play(bad)
    with pytest.raises(ValidationError):
        env.players.play(str(tmp_path / "missing.mp3"))
    with pytest.raises(ValidationError):
        env.players.play("https://youtu.be/dQw4w9WgXcQ", volume=101)
    for target, action in (("local", "dance"), ("browser", "next"), ("tv", "stop")):
        with pytest.raises(ValidationError):
            env.players.control(target, action)
    with pytest.raises(InvalidStateError):
        env.players.control("spotify", "stop")


def test_stop_all_stops_everything_and_clears_the_remembered_titles(
    env: Env, tmp_path: Path
) -> None:
    with env.storage.transaction() as repos:
        repos.state.set("music_now:cube", "{}")
        repos.state.set("music_owner:target", "{}")
        repos.state.set("music:cube", "keep")  # the settings of a cube stay
    env.players.play("https://youtu.be/dQw4w9WgXcQ")
    env.players.play(str(make_album(tmp_path)))
    wait_for(lambda: env.players.status()["local"]["state"] == "playing")
    env.add_spotify()
    assert env.players.stop_all() == []
    wait_for(lambda: env.players.status()["local"]["state"] == "stopped")
    assert env.browser.state()["playing"] is False
    assert env.sent[-1] == {"action": "spotify_pause"}
    with env.storage.read() as repos:
        keys = set(repos.state.items())
    assert "music_now:cube" not in keys and "music_owner:target" not in keys
    assert "music:cube" in keys


def test_stop_all_reports_a_player_that_cannot_be_stopped(env: Env) -> None:
    env.add_spotify()

    def broken(*_a: Any, **_k: Any) -> str:
        raise IntegrationError("down", user_message="Spotify antwortet nicht.")

    env.spotify.execute = broken  # type: ignore[method-assign]
    problems = env.players.stop_all()
    assert problems == ["spotify: Spotify antwortet nicht."]
    assert env.browser.state()["playing"] is False  # the others were still stopped


# --------------------------------------------------------------------- file dialog


class Done:
    def __init__(self, code: int, out: bytes) -> None:
        self.returncode = code
        self.stdout = out


def test_the_dialog_returns_the_chosen_path_or_none() -> None:
    seen: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> Done:
        seen.append(command)
        return Done(0, "C:/Musik/Schöne Lieder\n".encode())

    assert pick_path("folder", run=run) == "C:/Musik/Schöne Lieder"
    assert seen[0][0] == sys.executable and seen[0][-2] == "folder" and ".mp3" in seen[0][-1]
    assert pick_path("file", run=lambda *a, **k: Done(0, b"")) is None  # cancelled


def test_dialog_problems_are_explained_not_raised_raw() -> None:
    with pytest.raises(ValidationError):
        pick_path("everything")
    with pytest.raises(IntegrationError) as crashed:
        pick_path("file", run=lambda *a, **k: Done(1, b""))
    assert "abgestürzt" in crashed.value.user_message

    def slow(*_a: Any, **_k: Any) -> Done:
        raise subprocess.TimeoutExpired("x", 1)

    with pytest.raises(IntegrationError) as timeout:
        pick_path("file", run=slow)
    assert "Pfad ein" in timeout.value.user_message


# ---------------------------------------------------------------------------- API


def test_the_api_exposes_status_play_control_stop_and_the_dialog(
    api_server: RunningApi, tmp_path: Path
) -> None:
    env = Env(tmp_path)
    api_server.context.player = env.players
    client = api_server.client
    status = client.player_status()
    assert status["local"]["state"] == "stopped" and "FFmpeg" in status["formats"]
    assert "dialog" in status
    album = make_album(tmp_path)
    played = client.player_play(str(album), repeat="one", shuffle=True, volume=25)
    assert played["player"] == "local" and played["tracks"] == 4
    deadline = time.monotonic() + 5
    while client.player_status()["local"]["state"] != "playing":
        assert time.monotonic() < deadline
        time.sleep(0.02)
    client.player_control("local", "volume", 60)
    client.player_control("local", "pause")
    with pytest.raises(ValidationError):
        client.player_control("local", "dance")
    with pytest.raises(ValidationError):
        client.player_play("relative.mp3")
    assert client.player_stop() == []
    deadline = time.monotonic() + 5
    while client.player_status()["local"]["state"] != "stopped":
        assert time.monotonic() < deadline
        time.sleep(0.02)
