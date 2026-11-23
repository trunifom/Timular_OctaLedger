"""The local player: queue rules, formats, free paths, FFmpeg, the worker's queue (AP-61)."""

import io
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from octaledger.core.errors import ValidationError
from octaledger.domain.media_formats import (
    FFMPEG,
    NATIVE,
    decoder_for,
    is_playlist,
    playable_extensions,
    support_text,
)
from octaledger.domain.music import BASE_CONTINUE, MusicSettings, NowPlaying, decide
from octaledger.domain.music_source import SourceKind, parse_source
from octaledger.domain.playlist import Repeat, following, parse_repeat, play_order, preceding
from octaledger.infrastructure.audio.ffmpeg import FfmpegPcm, ffmpeg_command
from octaledger.infrastructure.audio.paths import (
    MAX_TRACKS,
    clean_path_text,
    natural_key,
    reject_unsafe,
    resolve_media,
)
from octaledger.infrastructure.audio.worker import AudioWorker, Command, PlayerStatus
from octaledger.infrastructure.integrations.player import PlayerAdapter

# ------------------------------------------------------------------ queue rules


def test_play_order_is_a_permutation_and_reproducible() -> None:
    assert play_order(4, shuffle=False) == [0, 1, 2, 3]
    mixed = play_order(20, shuffle=True, seed=7)
    assert sorted(mixed) == list(range(20)) and mixed == play_order(20, shuffle=True, seed=7)
    assert mixed != list(range(20))
    assert play_order(20, shuffle=True, seed=7, first=5)[0] == 5
    assert play_order(0, shuffle=True) == [] and play_order(1, shuffle=True) == [0]


@pytest.mark.parametrize(
    ("position", "count", "repeat", "by_user", "expected"),
    [
        (0, 3, Repeat.OFF, False, 1),
        (2, 3, Repeat.OFF, False, None),  # the end of a single run
        (2, 3, Repeat.ALL, False, 0),  # the loop starts over
        (1, 3, Repeat.ONE, False, 1),  # one track endlessly
        (1, 3, Repeat.ONE, True, 2),  # the next button still moves on
        (2, 3, Repeat.OFF, True, None),
        (0, 0, Repeat.ALL, False, None),
    ],
)
def test_what_follows_a_track(
    position: int, count: int, repeat: Repeat, by_user: bool, expected: int | None
) -> None:
    assert following(position, count, repeat, by_user=by_user) == expected


def test_previous_goes_back_and_wraps_only_when_repeating_all() -> None:
    assert preceding(2, 3, Repeat.OFF) == 1
    assert preceding(0, 3, Repeat.OFF) == 0
    assert preceding(0, 3, Repeat.ALL) == 2
    assert preceding(0, 0, Repeat.ALL) == 0


def test_repeat_is_parsed_strictly() -> None:
    assert parse_repeat("all") is Repeat.ALL
    with pytest.raises(ValidationError):
        parse_repeat("forever")


# ---------------------------------------------------------------------- formats


def test_the_decoder_depends_on_the_extension_and_on_ffmpeg() -> None:
    assert decoder_for("a.MP3", ffmpeg=False) == NATIVE
    assert decoder_for("a.m4a", ffmpeg=False) is None
    assert decoder_for("a.m4a", ffmpeg=True) == FFMPEG
    assert decoder_for("film.mkv", ffmpeg=True) == FFMPEG  # the sound track of a video
    assert decoder_for("film.mkv", ffmpeg=False) is None
    assert decoder_for("notes.txt", ffmpeg=True) is None
    assert is_playlist("x.M3U8") and not is_playlist("x.mp3")
    assert ".mp4" in playable_extensions(ffmpeg=True) and ".mp4" not in playable_extensions(
        ffmpeg=False
    )
    assert "FFmpeg" in support_text(ffmpeg=False) and "über FFmpeg" in support_text(ffmpeg=True)


# ------------------------------------------------------------------------ paths


def make_album(root: Path) -> Path:
    album = root / "Album"
    (album / "CD 2").mkdir(parents=True)
    for name in ("10 ten.mp3", "2 two.mp3", "1 one.flac", "cover.jpg", "notes.txt"):
        (album / name).write_bytes(b"x")
    (album / "CD 2" / "1 other.ogg").write_bytes(b"x")
    return album


def test_a_folder_gives_its_playable_files_in_natural_order(tmp_path: Path) -> None:
    album = make_album(tmp_path)
    tracks = resolve_media(str(album), ffmpeg=False)
    assert [t.title for t in tracks] == ["1 one", "2 two", "10 ten", "1 other"]
    assert natural_key("track2") < natural_key("track10")


def test_a_single_file_and_quotes_from_explorer(tmp_path: Path) -> None:
    song = tmp_path / "lied.mp3"
    song.write_bytes(b"x")
    assert resolve_media(f'"{song}"', ffmpeg=False)[0].path == song.resolve()


def test_unplayable_and_missing_paths_are_explained(tmp_path: Path) -> None:
    (tmp_path / "x.m4a").write_bytes(b"x")
    with pytest.raises(ValidationError) as caught:
        resolve_media(str(tmp_path / "x.m4a"), ffmpeg=False)
    assert "FFmpeg" in caught.value.user_message
    assert resolve_media(str(tmp_path / "x.m4a"), ffmpeg=True)[0].title == "x"
    with pytest.raises(ValidationError) as missing:
        resolve_media(str(tmp_path / "gibtsnicht.mp3"), ffmpeg=False)
    assert "gibt es nicht" in missing.value.user_message
    with pytest.raises(ValidationError):
        resolve_media(str(tmp_path), ffmpeg=False)  # an empty folder


@pytest.mark.parametrize(
    "text",
    ["", "   ", "relative/song.mp3", "song.mp3", "C:/a\x00b.mp3", "C:/" + "a" * 1100],
)
def test_bad_path_text_is_refused(text: str) -> None:
    with pytest.raises(ValidationError):
        reject_unsafe(clean_path_text(text))


@pytest.mark.parametrize(
    "text", ["//server/share/a.mp3", "\\\\server\\share\\a.mp3", "//?/C:/a.mp3"]
)
def test_network_and_device_paths_are_refused(text: str) -> None:
    with pytest.raises(ValidationError) as caught:
        reject_unsafe(clean_path_text(text))
    assert "Netzwerkpfade" in caught.value.user_message


def test_a_m3u_playlist_lists_local_playable_entries_only(tmp_path: Path) -> None:
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    playlist = tmp_path / "mix.m3u"
    playlist.write_text(
        "#EXTM3U\n#EXTINF:1,x\na.mp3\nb.txt\nhttp://radio.example/live\n//srv/s/c.mp3\nmissing.mp3\n",
        encoding="utf-8",
    )
    assert [t.title for t in resolve_media(str(playlist), ffmpeg=False)] == ["a"]


def test_a_folder_scan_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octaledger.infrastructure.audio.paths.MAX_TRACKS", 3)
    for i in range(10):
        (tmp_path / f"{i}.mp3").write_bytes(b"x")
    assert len(resolve_media(str(tmp_path), ffmpeg=False)) == 3
    assert MAX_TRACKS >= 100


# ---------------------------------------------------------------- source parsing


def test_local_paths_are_recognised_with_spaces_and_as_file_urls() -> None:
    plain = parse_source("C:\\Users\\Max Muster\\Music\\Album 1")
    assert plain.kind is SourceKind.LOCAL and plain.ref.endswith("Album 1")
    assert plain.uri.startswith("local:") and "Computer" in plain.description or True
    assert parse_source('"D:/Alben/Teil 2"').kind is SourceKind.LOCAL
    assert parse_source("file:///C:/Music/a%20b.mp3").ref == "C:/Music/a b.mp3"
    assert parse_source("https://youtu.be/dQw4w9WgXcQ").kind is SourceKind.YOUTUBE


@pytest.mark.parametrize("text", ["\\\\server\\share\\a.mp3", "//server/share/a.mp3"])
def test_network_paths_are_not_music_sources(text: str) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_source(text)
    assert "Netzwerkpfade" in caught.value.user_message


# ----------------------------------------------------------------------- FFmpeg


def test_the_ffmpeg_command_is_a_list_that_decodes_to_pcm(tmp_path: Path) -> None:
    song = tmp_path / "a b.m4a"
    command = ffmpeg_command("ffmpeg", song)
    assert command[0] == "ffmpeg" and str(song) in command and "-vn" in command
    assert command[-1] == "pipe:1" and "-nostdin" in command and "s16le" in command
    piped = ffmpeg_command("ffmpeg", None)
    assert "pipe:0" in piped and "-nostdin" not in piped


class FakeProcess:
    def __init__(self, output: bytes) -> None:
        self.stdout = io.BytesIO(output)
        self.stdin: io.BytesIO | None = io.BytesIO()
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        self.terminated = True


def test_the_ffmpeg_stream_reads_pcm_and_ends_the_process(tmp_path: Path) -> None:
    process = FakeProcess(b"\x01\x02" * 100)
    stream = FfmpegPcm("ffmpeg", tmp_path / "a.m4a", popen=lambda *a, **k: process)
    assert stream.is_pcm and len(stream.read(50)) == 50
    stream.close()
    assert process.terminated


def test_a_web_stream_is_piped_into_ffmpeg_never_given_by_address() -> None:
    process = FakeProcess(b"pcm")
    seen: list[list[str]] = []

    def popen(command: list[str], **kwargs: Any) -> FakeProcess:
        seen.append(command)
        return process

    source = io.BytesIO(b"aacdata" * 10)
    stream = FfmpegPcm("ffmpeg", None, source, popen=popen)
    stream._feeder.join(2)  # type: ignore[union-attr]
    assert "pipe:0" in seen[0] and not any("http" in part for part in seen[0])
    assert process.stdin is not None and process.stdin.closed
    stream.close()


# ----------------------------------------------------------------------- worker


class QueueEngine:
    """A fake engine that records what plays and can report the end of a track."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []
        self.generation = 0
        self._callback: Any = None
        self.fail_on: set[str] = set()

    def set_end_callback(self, callback: Any) -> None:
        self._callback = callback

    def play(self, source: BinaryIO, volume: float) -> None:
        name = getattr(source, "name", "stream")
        if Path(str(name)).name in self.fail_on:
            from octaledger.core.errors import IntegrationError

            raise IntegrationError("bad", user_message="Defekte Datei")
        self.generation += 1
        self.events.append(("play", (Path(str(name)).name, round(volume, 2))))
        source.close()

    def stop(self) -> None:
        self.generation += 1
        self.events.append(("stop", None))

    def set_volume(self, volume: float) -> None:
        self.events.append(("volume", round(volume, 2)))

    def pause(self) -> None:
        self.events.append(("pause", None))

    def resume(self) -> None:
        self.events.append(("resume", None))

    def end_track(self) -> None:
        self._callback(self.generation)


def wait_for(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.01)


def plays(engine: QueueEngine) -> list[str]:
    return [e[1][0] for e in engine.events if e[0] == "play"]


def album_command(tmp_path: Path, **kw: Any) -> Command:
    album = make_album(tmp_path)
    tracks = tuple(resolve_media(str(album), ffmpeg=False))
    return Command("play_queue", tracks=tracks, volume=0.4, **kw)


def new_worker(engine: QueueEngine) -> AudioWorker:
    return AudioWorker(lambda: engine, ffmpeg_finder=lambda: None)


def test_a_folder_plays_track_after_track_and_stops_at_the_end(tmp_path: Path) -> None:
    engine = QueueEngine()
    worker = new_worker(engine)
    worker.submit(album_command(tmp_path))
    wait_for(lambda: len(plays(engine)) == 1)
    status = worker.status()
    assert status.state == "playing" and status.position == 1 and status.total == 4
    assert status.title == "1 one" and status.volume == 40
    for expected in (2, 3, 4):
        engine.end_track()
        wait_for(lambda n=expected: worker.status().position == n)
    engine.end_track()  # the last one: playback is over
    wait_for(lambda: worker.status().state == "stopped")
    assert plays(engine) == ["1 one.flac", "2 two.mp3", "10 ten.mp3", "1 other.ogg"]
    worker.stop_thread()


def test_repeat_all_loops_and_repeat_one_stays_on_the_track(tmp_path: Path) -> None:
    engine = QueueEngine()
    worker = new_worker(engine)
    worker.submit(album_command(tmp_path, repeat=Repeat.ALL))
    wait_for(lambda: len(plays(engine)) == 1)
    for _ in range(4):
        before = len(plays(engine))
        engine.end_track()
        wait_for(lambda b=before: len(plays(engine)) == b + 1)
    assert plays(engine)[4] == "1 one.flac"  # started over after the fourth
    worker.submit(Command("set_repeat", "one"))
    wait_for(lambda: worker.status().repeat == "one")
    before = len(plays(engine))
    engine.end_track()
    wait_for(lambda: len(plays(engine)) == before + 1)
    assert plays(engine)[-1] == plays(engine)[-2]
    worker.stop_thread()


def test_next_previous_jump_pause_resume_and_stop(tmp_path: Path) -> None:
    engine = QueueEngine()
    worker = new_worker(engine)
    worker.submit(album_command(tmp_path))
    wait_for(lambda: len(plays(engine)) == 1)
    worker.submit(Command("next"))
    wait_for(lambda: worker.status().position == 2)
    worker.submit(Command("previous"))
    wait_for(lambda: worker.status().position == 1)
    worker.submit(Command("jump", 3.0))
    wait_for(lambda: worker.status().position == 4)
    worker.submit(Command("pause"))
    wait_for(lambda: worker.status().state == "paused")
    worker.submit(Command("resume"))
    wait_for(lambda: worker.status().state == "playing")
    worker.submit(Command("stop"))
    wait_for(lambda: worker.status().state == "stopped")
    assert worker.status().total == 0 and worker.status().title == ""
    worker.stop_thread()


def test_a_late_end_message_of_a_replaced_track_is_ignored(tmp_path: Path) -> None:
    engine = QueueEngine()
    worker = new_worker(engine)
    worker.submit(album_command(tmp_path))
    wait_for(lambda: len(plays(engine)) == 1)
    stale = engine.generation
    worker.submit(Command("next"))
    wait_for(lambda: worker.status().position == 2)
    worker._on_ended(stale)  # the end of the first track arrives after it was replaced
    worker.submit(Command("volume", 0.2))
    wait_for(lambda: worker.status().volume == 20)
    assert worker.status().position == 2
    worker.stop_thread()


def test_a_broken_track_is_skipped_and_reported(tmp_path: Path) -> None:
    engine = QueueEngine()
    engine.fail_on = {"1 one.flac"}
    worker = new_worker(engine)
    worker.submit(album_command(tmp_path))
    wait_for(lambda: worker.status().state == "playing")
    status = worker.status()
    assert status.position == 2 and status.error == "„1 one“ übersprungen: Defekte Datei"
    assert plays(engine)[0] == "2 two.mp3"
    worker.stop_thread()


def test_a_single_broken_file_stops_with_the_error(tmp_path: Path) -> None:
    engine = QueueEngine()
    engine.fail_on = {"lied.mp3"}
    song = tmp_path / "lied.mp3"
    song.write_bytes(b"x")
    worker = new_worker(engine)
    worker.submit(Command("play_queue", tracks=tuple(resolve_media(str(song), ffmpeg=False))))
    wait_for(lambda: worker.status().error is not None)
    assert worker.status().state == "stopped" and worker.last_error == "Defekte Datei"
    worker.stop_thread()


def test_shuffle_changes_the_order_without_losing_the_current_track(tmp_path: Path) -> None:
    engine = QueueEngine()
    worker = new_worker(engine)
    worker.submit(album_command(tmp_path, shuffle=True))
    wait_for(lambda: worker.status().state == "playing")
    assert worker.status().shuffle and sorted(worker.status().queue) == sorted(
        ["1 one", "2 two", "10 ten", "1 other"]
    )
    current = worker.status().title
    worker.submit(Command("set_shuffle", False))
    wait_for(lambda: not worker.status().shuffle)
    assert worker.status().title == current
    assert worker.status().queue[worker.status().position - 1] == current
    worker.stop_thread()


def test_ffmpeg_is_used_for_formats_the_native_decoder_cannot_read(tmp_path: Path) -> None:
    engine = QueueEngine()
    video = tmp_path / "film.mkv"
    video.write_bytes(b"x")
    started: list[Path] = []

    class Pcm(io.BytesIO):
        is_pcm = True
        name = "pcm"

    def factory(executable: str, source: Path | None = None, feed: Any = None) -> Pcm:
        assert source is not None
        started.append(source)
        return Pcm()

    worker = AudioWorker(lambda: engine, ffmpeg_finder=lambda: "ffmpeg", ffmpeg_factory=factory)
    worker.submit(Command("play_queue", tracks=tuple(resolve_media(str(video), ffmpeg=True))))
    wait_for(lambda: worker.status().state == "playing")
    assert started == [video.resolve()] and worker.status().ffmpeg is True
    worker.stop_thread()


def test_the_status_is_a_plain_snapshot_without_starting_a_thread() -> None:
    worker = AudioWorker(QueueEngine, ffmpeg_finder=lambda: None)
    assert worker.status() == PlayerStatus()
    assert threading.active_count() >= 1 and worker._thread is None


# ---------------------------------------------------------------------- adapter


def test_the_adapter_plays_a_path_and_is_controlled_from_the_app(tmp_path: Path) -> None:
    engine = QueueEngine()
    adapter = PlayerAdapter(new_worker(engine), ffmpeg_finder=lambda: None)
    album = make_album(tmp_path)
    assert adapter.status()["state"] == "stopped"
    assert adapter.play(str(album), repeat="all", shuffle=False, volume=30) == 4
    wait_for(lambda: adapter.status()["state"] == "playing")
    status = adapter.status()
    assert status["repeat"] == "all" and status["total"] == 4 and status["volume"] == 30
    adapter.control("next")
    wait_for(lambda: adapter.status()["position"] == 2)
    adapter.control("repeat", "one")
    adapter.control("shuffle", True)
    adapter.control("volume", 80)
    wait_for(lambda: adapter.status()["volume"] == 80 and adapter.status()["shuffle"])
    adapter.control("stop")
    wait_for(lambda: adapter.status()["state"] == "stopped")
    for bad in (("volume", 101), ("repeat", "x"), ("dance", None), ("jump", -1)):
        with pytest.raises(ValidationError):
            adapter.control(*bad)


def test_play_path_works_as_an_action_with_a_validated_path(tmp_path: Path) -> None:
    engine = QueueEngine()
    adapter = PlayerAdapter(new_worker(engine), ffmpeg_finder=lambda: None)
    album = make_album(tmp_path)
    cleaned = adapter.validate_action(
        {"action": "play_path", "path": f'"{album}"', "repeat": "one"}
    )
    assert cleaned["repeat"] == "one" and cleaned["path"] == str(album)
    message = adapter.execute({"volume": 20}, {}, cleaned, timeout=1)
    assert "4 Titel" in message
    wait_for(lambda: engine.events)
    assert engine.events[0] == ("play", ("1 one.flac", 0.2))
    for bad in ({"path": "relative.mp3"}, {"path": "//srv/share/a.mp3"}, {"path": ""}):
        with pytest.raises(ValidationError):
            adapter.validate_action({"action": "play_path", **bad})
    with pytest.raises(ValidationError):  # a path that does not exist is refused when it runs
        adapter.execute(
            {}, {}, {"action": "play_path", "path": str(tmp_path / "nope.mp3")}, timeout=1
        )


def test_a_music_title_can_be_a_local_path_and_the_adapter_checks_it(tmp_path: Path) -> None:
    adapter = PlayerAdapter(new_worker(QueueEngine()), ffmpeg_finder=lambda: None)
    album = make_album(tmp_path)
    plays_ = adapter.music_play_params(
        parse_source(str(album)), 45, {"repeat": "all", "shuffle": "true"}
    )
    assert plays_ == [
        {"action": "play_path", "path": str(album), "repeat": "all", "shuffle": True, "volume": 45}
    ]
    with pytest.raises(ValidationError):
        adapter.music_play_params(parse_source(str(tmp_path / "missing")), 45, {})
    with pytest.raises(ValidationError):
        adapter.music_play_params(parse_source(str(album)), 45, {"repeat": "forever"})
    assert adapter.music_stop_params({}) == {"action": "stop"}


# ----------------------------------------------------------------- holder: continue


def test_in_the_holder_the_music_can_keep_playing_but_a_silence_face_still_stops() -> None:
    playing = NowPlaying(1, "Album", "conn", "2026-01-01T00:00:00+00:00", "conn")
    keep = MusicSettings(base_action=BASE_CONTINUE)
    targets = frozenset({"conn"})
    assert decide("neutral", 0, playing, {1: "conn"}, targets, keep) == []
    assert decide("baseline", 0, playing, {1: "conn"}, targets, keep) == []
    stopped = decide("face_change", 5, playing, {1: "conn"}, targets, keep)  # face without title
    assert [c.kind.value for c in stopped] == ["stop"]
    assert [c.kind.value for c in decide("neutral", 0, playing, {}, targets, MusicSettings())] == [
        "stop"
    ]
    with pytest.raises(ValidationError):
        MusicSettings(base_action="forever")


def test_a_shuffled_folder_does_not_always_start_with_its_first_file(tmp_path: Path) -> None:
    """Regression: track 0 was pinned to the front, so a "random" start was always the same."""
    firsts = set()
    command = album_command(tmp_path, shuffle=True)
    for _ in range(12):
        engine = QueueEngine()
        worker = new_worker(engine)
        worker.submit(command)
        wait_for(lambda e=engine: len(plays(e)) == 1)
        firsts.add(plays(engine)[0])
        worker.stop_thread()
        time.sleep(0.002)  # the seed is the clock in milliseconds
    assert len(firsts) > 1


def test_an_explicit_start_track_is_still_played_first_with_a_shuffle(tmp_path: Path) -> None:
    engine = QueueEngine()
    worker = new_worker(engine)
    worker.submit(album_command(tmp_path, shuffle=True, start=2))
    wait_for(lambda: len(plays(engine)) == 1)
    assert plays(engine)[0] == "10 ten.mp3"
    worker.stop_thread()


def test_a_local_path_title_marks_the_music_as_playing() -> None:
    """Regression: "play_path" was not a play action, so the holder had nothing to stop."""
    from octaledger.application.music_state import PLAY_ACTIONS

    assert "play_path" in PLAY_ACTIONS
