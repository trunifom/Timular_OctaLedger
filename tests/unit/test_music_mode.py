"""The music mode: link recognition, rules, queuing, state and the watchdog (AP-48)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from octaledger.application.device_service import DeviceService
from octaledger.application.integration_service import IntegrationService
from octaledger.application.music_service import MusicService
from octaledger.application.tracking_service import Outcome, TrackingService
from octaledger.core.errors import InvalidStateError, ValidationError
from octaledger.core.secrets import SecretStore
from octaledger.core.settings import Settings
from octaledger.domain.models import DeviceMode, EventKind, JobStatus, RawEvent
from octaledger.domain.music import (
    CommandKind,
    MusicCommand,
    MusicSettings,
    NowPlaying,
    decide,
)
from octaledger.domain.music_source import SourceKind, parse_source
from octaledger.infrastructure.integrations.homeassistant import HomeAssistantAdapter
from octaledger.infrastructure.integrations.player import PlayerAdapter
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

UTC = UTC
T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
PUBLIC = "93.184.216.34"

# ----------------------------------------------------------------- link recognition


@pytest.mark.parametrize(
    ("text", "uri", "kind"),
    [
        (
            "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
            "spotify:track:4uLU6hMCjMI75M1A2tKUQC",
            SourceKind.SPOTIFY,
        ),
        (
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc",
            "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
            SourceKind.SPOTIFY,
        ),
        (
            "https://open.spotify.com/intl-de/album/1DFixLWuPkv3KT3TnV35m3",
            "spotify:album:1DFixLWuPkv3KT3TnV35m3",
            SourceKind.SPOTIFY,
        ),
        (
            "spotify:track:4uLU6hMCjMI75M1A2tKUQC",
            "spotify:track:4uLU6hMCjMI75M1A2tKUQC",
            SourceKind.SPOTIFY,
        ),
        (
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "youtube:dQw4w9WgXcQ",
            SourceKind.YOUTUBE,
        ),
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabcdefghijk123",
            "youtube:dQw4w9WgXcQ?list=PLabcdefghijk123",
            SourceKind.YOUTUBE,
        ),
        ("https://youtu.be/dQw4w9WgXcQ?t=5", "youtube:dQw4w9WgXcQ", SourceKind.YOUTUBE),
        (
            "https://stream.example.org/live.mp3",
            "url:https://stream.example.org/live.mp3",
            SourceKind.URL,
        ),
    ],
)
def test_links_are_recognised_and_normalised(text: str, uri: str, kind: SourceKind) -> None:
    source = parse_source(text)
    assert (source.uri, source.kind) == (uri, kind) and source.description


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "irgendwas",
        "ftp://example.org/x",
        "javascript:alert(1)",
        "https://user:pw@example.org/x",
        "https://open.spotify.com/user/xyz",
        "https://open.spotify.com/track/",
        "https://open.spotify.com/track/kurz",
        "spotify:track:bad id",
        "spotify:user:4uLU6hMCjMI75M1A2tKUQC",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=zu-kurz",
        "https://youtu.be/",
        "https://example.org/ a",
        "https://example.org/" + "a" * 2100,
    ],
)
def test_garbage_is_rejected_with_an_explanation(text: str) -> None:
    with pytest.raises(ValidationError) as info:
        parse_source(text)
    assert "Erkannt werden" in info.value.user_message or "Link" in info.value.user_message


def test_a_malformed_playlist_is_ignored_but_the_video_stays() -> None:
    source = parse_source("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=x")
    assert source.playlist is None and source.ref == "dQw4w9WgXcQ"
    assert source.youtube_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


# ----------------------------------------------------------------- the rules (pure)

NOW_SPOTIFY = NowPlaying(2, "Radio", "spotify-id", "2026-01-05T08:00:00+00:00")
TITLES = {1: "player-id", 2: "ha-id", 3: "player-id"}
TARGETS = frozenset({"player-id", "ha-id"})
S = MusicSettings()


def run(event: str, value: int | None, playing: NowPlaying | None, **kw: Any) -> list[MusicCommand]:
    return decide(
        event,
        value,
        playing,
        kw.get("titles", TITLES),
        kw.get("targets", TARGETS),
        kw.get("settings", S),
    )


def test_a_face_with_a_title_just_plays_when_nothing_plays() -> None:
    assert run("face_change", 1, None) == [MusicCommand(CommandKind.PLAY, "player-id", face=1)]


def test_a_face_on_the_same_target_replaces_without_a_stop() -> None:
    playing = NowPlaying(1, "A", "player-id", "x")
    assert run("face_change", 3, playing) == [MusicCommand(CommandKind.PLAY, "player-id", face=3)]


def test_a_face_on_another_target_stops_the_old_one_first() -> None:
    playing = NowPlaying(1, "A", "player-id", "x")
    assert run("face_change", 2, playing) == [
        MusicCommand(CommandKind.STOP, "player-id"),
        MusicCommand(CommandKind.PLAY, "ha-id", face=2),
    ]


def test_a_face_without_a_title_is_a_silence_face() -> None:
    playing = NowPlaying(1, "A", "player-id", "x")
    stops = run(
        "face_change", 7, playing, settings=MusicSettings(base_action="pause", stop_delay_ms=5000)
    )
    assert stops == [  # always a full stop, immediately, on every used target
        MusicCommand(CommandKind.STOP, "ha-id"),
        MusicCommand(CommandKind.STOP, "player-id"),
    ]
    assert run("face_change", 7, None) == []  # nothing plays: nothing to do


def test_the_holder_stops_every_used_target_but_only_if_something_plays() -> None:
    playing = NowPlaying(1, "A", "player-id", "x")
    assert run("neutral", 0, playing) == [
        MusicCommand(CommandKind.STOP, "ha-id"),
        MusicCommand(CommandKind.STOP, "player-id"),
    ]
    assert run("neutral", 0, None) == []


def test_the_holder_can_pause_after_a_delay() -> None:
    playing = NowPlaying(1, "A", "player-id", "x")
    commands = run("neutral", 0, playing, settings=MusicSettings("pause", 3000))
    assert {(c.kind, c.delay_ms) for c in commands} == {(CommandKind.PAUSE, 3000)}


def test_the_baseline_does_nothing_unless_the_cube_rests_in_its_holder() -> None:
    assert run("baseline", 1, None) == [] and run("baseline", 1, NOW_SPOTIFY) == []
    assert run("baseline", 0, NOW_SPOTIFY) != []  # resting in the holder while music plays
    assert run("baseline", 0, None) == []


@pytest.mark.parametrize("event", ["disconnect", "reconnect", "invalid", "button"])
def test_other_events_do_nothing(event: str) -> None:
    assert run(event, None, NOW_SPOTIFY) == []


def test_music_settings_are_validated() -> None:
    for bad in (
        {"base_action": "dance"},
        {"stop_delay_ms": -1},
        {"stop_delay_ms": 70_000},
        {"default_volume": 101},
    ):
        with pytest.raises(ValidationError):
            MusicSettings(**bad)  # type: ignore[arg-type]


# ----------------------------------------------------------------- the whole machine


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.now = T0
        self.player = PlayerAdapter(worker=None)
        self.sent: list[dict[str, Any]] = []
        self.service = IntegrationService(
            self.storage,
            SecretStore(tmp_path / "s.json"),
            {
                "player": self._recording(PlayerAdapter()),
                "homeassistant": self._recording(HomeAssistantAdapter()),
            },
            clock=lambda: self.now,
        )
        self.tracking = TrackingService(self.storage, clock=lambda: self.now)
        self.music = MusicService(
            self.storage, self.service, lambda: Settings(), clock=lambda: self.now
        )
        devices = DeviceService(self.storage)
        self.timer = devices.register("Zeit").id
        self.cube = devices.register("Musik").id
        devices.set_mode(self.cube, DeviceMode.MUSIC)
        self.radio = self.service.create("player", "Radio PC", {}).integration.id
        self.ha = self.service.create(
            "homeassistant", "Sonos", {"base_url": "http://192.168.1.2:8123", "token": "t"}
        ).integration.id
        self.sequence = 0

    def _recording(self, adapter: Any) -> Any:
        sent = self.sent

        def execute(config: Any, secrets: Any, params: Any, *, timeout: float) -> str:
            sent.append({"kind": adapter.spec.kind, **dict(params)})
            return "ok"

        adapter.execute = execute
        return adapter

    def event(self, kind: EventKind, value: int | None) -> RawEvent:
        self.sequence += 1
        return RawEvent(
            device_id=self.cube,
            kind=kind,
            sequence=self.sequence,
            connection_id="c1",
            raw_value=value,
            received_at=self.now,
        )

    def turn(self, face: int) -> Outcome:
        return self.tracking.record_event(self.event(EventKind.FACE_CHANGE, face)).outcome

    def holder(self) -> Outcome:
        return self.tracking.record_event(self.event(EventKind.NEUTRAL, 0)).outcome

    def title(self, face: int, target: str, link: str, label: str, **kw: Any) -> None:
        self.music.set_title(self.cube, face, target, link, label, **kw)

    def send_all(self) -> None:
        while self.service.process_due():
            pass

    def jobs(self) -> list[Any]:
        with self.storage.read() as repos:
            return sorted(repos.jobs.list_recent(100), key=lambda j: (j.created_at, j.step))

    def playing(self) -> Any:
        (state,) = self.music.state()
        return state["playing"]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_a_music_cube_never_creates_time(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/lofi.mp3", "Lofi")
    env.turn(1)
    env.holder()
    with env.storage.read() as repos:
        assert repos.sessions.list_all() == []


def test_the_role_is_stored_safely_and_restored(env: Env, tmp_path: Path) -> None:
    with env.storage.read() as repos:
        assert repos.devices.require(env.cube).mode is DeviceMode.MUSIC
        raw = repos.devices._c.execute(
            "SELECT mode, music FROM devices WHERE id = ?", (env.cube,)
        ).fetchone()
    assert (raw["mode"], raw["music"]) == ("control", 1)  # the old CHECK condition stays valid
    assert DeviceMode.MUSIC.is_controller and not DeviceMode.TIME.is_controller


def test_a_music_cube_cannot_be_the_active_time_tracker(env: Env) -> None:
    from octaledger.core.errors import InvalidStateError as Refused

    with pytest.raises(Refused):
        env.tracking.handover(env.cube)


def test_a_face_plays_and_the_state_follows_the_sent_job(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/lofi.mp3", "Lofi Radio", volume=40)
    assert env.turn(1) is Outcome.MUSIC_COMMANDED
    assert env.playing() is None  # nothing is "playing" before the job was really sent
    env.send_all()
    assert env.sent == [
        {"kind": "player", "action": "play_url", "url": f"https://{PUBLIC}/lofi.mp3", "volume": 40}
    ]
    now = env.playing()
    assert now["face"] == 1 and now["label"] == "Lofi Radio" and now["integration_id"] == env.radio


def test_the_holder_stops_what_plays_and_clears_the_state(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/lofi.mp3", "Lofi")
    env.turn(1)
    env.send_all()
    assert env.holder() is Outcome.MUSIC_STOPPED
    env.send_all()
    assert env.sent[-1] == {"kind": "player", "action": "stop"}
    assert env.playing() is None


def test_the_holder_does_nothing_when_nothing_plays(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/lofi.mp3", "Lofi")
    assert env.holder() is Outcome.STORED
    assert env.jobs() == []


def test_changing_the_target_stops_the_old_target_before_the_new_one_plays(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/lofi.mp3", "Radio")
    env.title(
        2,
        env.ha,
        "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
        "Spotify",
        options={"entity_id": "media_player.wz"},
    )
    env.turn(1)
    env.send_all()
    env.sent.clear()
    env.turn(2)
    env.now = T0 + timedelta(seconds=2)  # the 300 ms step delay has passed
    env.send_all()
    assert [s["action"] for s in env.sent] == ["stop", "media_volume", "media_play"]
    assert (
        env.sent[0]["kind"] == "player"
        and env.sent[2]["media_url"] == "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
    )
    assert env.playing()["face"] == 2


def test_the_holder_stops_every_target_of_the_cube(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/lofi.mp3", "Radio")
    env.title(
        2, env.ha, f"https://{PUBLIC}/hq.mp3", "Sonos", options={"entity_id": "media_player.wz"}
    )
    env.turn(2)
    env.now = T0 + timedelta(seconds=2)  # the title step waits 300 ms after the volume
    env.send_all()
    env.sent.clear()
    env.holder()
    env.send_all()
    assert {(s["kind"], s["action"]) for s in env.sent} == {
        ("player", "stop"),
        ("homeassistant", "media_stop"),
    }
    assert [s for s in env.sent if s["kind"] == "homeassistant"][0][
        "entity_id"
    ] == "media_player.wz"


def test_a_pause_cube_pauses_where_the_target_can(env: Env) -> None:
    env.music.set_settings(env.cube, MusicSettings(base_action="pause"))
    env.title(
        2, env.ha, f"https://{PUBLIC}/hq.mp3", "Sonos", options={"entity_id": "media_player.wz"}
    )
    env.turn(2)
    env.now = T0 + timedelta(seconds=2)
    env.send_all()
    env.holder()
    env.send_all()
    assert env.sent[-1]["action"] == "media_pause" and env.playing() is None


def test_a_new_face_cancels_what_was_not_sent_yet(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/a.mp3", "A")
    env.title(3, env.radio, f"https://{PUBLIC}/b.mp3", "B")
    env.turn(1)  # queued, not sent yet
    env.turn(3)
    env.send_all()
    played = [s["url"] for s in env.sent if s["action"] == "play_url"]
    assert played == [f"https://{PUBLIC}/b.mp3"]  # no half second of the first title
    assert [j.last_error for j in env.jobs() if j.status is JobStatus.EXPIRED] == [
        "Durch eine neue Seite ersetzt."
    ]


def test_a_face_without_a_title_silences_the_music(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/a.mp3", "A")
    env.turn(1)
    env.send_all()
    assert env.turn(5) is Outcome.MUSIC_STOPPED
    env.send_all()
    assert env.sent[-1]["action"] == "stop" and env.playing() is None


def test_a_failed_job_leaves_the_state_unchanged(env: Env) -> None:
    from octaledger.core.errors import IntegrationError

    env.title(1, env.radio, f"https://{PUBLIC}/a.mp3", "A")
    env.turn(1)
    env.send_all()
    assert env.playing()["face"] == 1
    env.title(3, env.radio, f"https://{PUBLIC}/b.mp3", "B")
    adapter = env.service.adapter_for("player")
    adapter.execute = lambda *a, **k: (_ for _ in ()).throw(
        IntegrationError("x", user_message="kaputt")
    )  # type: ignore[method-assign]
    env.turn(3)
    env.send_all()
    assert env.playing()["face"] == 1  # still the old title: the new one never started


def test_the_baseline_in_the_holder_stops_music_that_still_plays(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/a.mp3", "A")
    env.turn(1)
    env.send_all()
    result = env.tracking.record_event(env.event(EventKind.BASELINE, 0))
    assert result.outcome is Outcome.MUSIC_STOPPED
    assert env.tracking.record_event(env.event(EventKind.BASELINE, 1)).outcome is Outcome.STORED


# ------------------------------------------------------------ titles and settings


def test_a_title_must_fit_its_target(env: Env) -> None:
    with pytest.raises(ValidationError):  # the local player cannot play Spotify
        env.title(1, env.radio, "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC", "S")
    with pytest.raises(ValidationError):  # Home Assistant needs a media player
        env.title(1, env.ha, f"https://{PUBLIC}/a.mp3", "S")
    with pytest.raises(ValidationError):  # not a recognised link
        env.title(1, env.radio, "irgendwas", "S")
    with pytest.raises(ValidationError):  # unsafe address
        env.title(1, env.radio, "http://127.0.0.1/x", "S")
    with pytest.raises(ValidationError):
        env.title(1, env.radio, f"https://{PUBLIC}/a.mp3", "S", volume=101)
    assert env.service.get_steps(env.cube, 1) == []  # nothing half-saved


def test_only_a_music_cube_gets_titles(env: Env) -> None:
    other = DeviceService(env.storage).register("Normal").id
    with pytest.raises(InvalidStateError):
        env.music.set_title(other, 1, env.radio, f"https://{PUBLIC}/a.mp3", "x")


def test_youtube_links_go_to_home_assistant_as_a_cast_address(env: Env) -> None:
    env.title(
        1,
        env.ha,
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "YT",
        options={"entity_id": "media_player.tv"},
    )
    play = next(s for s in env.service.get_steps(env.cube, 1) if s.params["action"] == "media_play")
    assert play.params["media_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_the_default_volume_comes_from_the_cube_settings(env: Env) -> None:
    env.music.set_settings(env.cube, MusicSettings(default_volume=25))
    env.title(1, env.radio, f"https://{PUBLIC}/a.mp3", "A")
    assert env.service.get_steps(env.cube, 1)[0].params["volume"] == 25


def test_the_state_lists_only_music_cubes(env: Env) -> None:
    assert [d["alias"] for d in env.music.state()] == ["Musik"]


# ---------------------------------------------------------------------- watchdog


def lose(env: Env) -> None:
    env.title(1, env.radio, f"https://{PUBLIC}/a.mp3", "A")
    env.turn(1)
    env.send_all()
    env.tracking.record_event(env.event(EventKind.DISCONNECT, None))


def test_music_keeps_playing_during_the_grace_period_and_stops_after_it(env: Env) -> None:
    lose(env)
    assert env.music.watchdog(T0 + timedelta(seconds=299)) == 0
    assert env.music.state()[0]["lost_since"] is not None
    assert env.music.watchdog(T0 + timedelta(seconds=300)) == 1
    env.now = T0 + timedelta(seconds=301)
    env.send_all()
    assert env.sent[-1]["action"] == "stop" and env.playing() is None
    assert env.music.watchdog(T0 + timedelta(hours=1)) == 0  # only once


def test_a_return_inside_the_grace_period_cancels_the_stop(env: Env) -> None:
    lose(env)
    env.tracking.record_event(env.event(EventKind.RECONNECT, None))
    assert env.music.watchdog(T0 + timedelta(hours=1)) == 0
    assert env.playing() is not None


def test_no_music_means_nothing_to_stop_after_a_loss(env: Env) -> None:
    env.tracking.record_event(env.event(EventKind.DISCONNECT, None))
    assert env.music.watchdog(T0 + timedelta(hours=1)) == 0
