"""The audio worker: a daemon thread that plays what the player adapter asks for.

Playing sound must never block the Bluetooth loop or the action dispatcher, and an internet radio
connection can take seconds. So the adapter only **puts a command into a queue**
(:meth:`AudioWorker.submit`, ``put_nowait``); this thread opens the stream or file and drives the
:class:`~octaledger.infrastructure.audio.engine.AudioEngine`.

What the worker does (AP-61):

* **A play queue.** A folder, an album or a playlist becomes a queue of tracks played in order
  (:mod:`octaledger.domain.playlist`): once, the whole queue again and again, or one track
  endlessly; optionally shuffled. *Next*, *previous*, *pause*, *resume* and *stop* work at any
  time; the end of a track is reported by the engine and moves on to the next one.
* **Many formats.** MP3, FLAC, WAV and Ogg play natively; with FFmpeg installed also AAC/M4A, WMA,
  Opus, AIFF, ... and the sound of video files (the decoder is chosen per file).
* **One sound at a time:** a new playback replaces the old one; ``stop`` ends it.
* **Never dies:** an error is logged and kept as :attr:`last_error` for the interface; a track
  that cannot be played is skipped (when other tracks remain) and the thread continues.
* **Status for the interface:** :meth:`AudioWorker.status` returns an immutable snapshot (state,
  title, position in the queue, repeat, shuffle, volume, error) that the page *Musik-Player*
  shows; it is the truth about what plays, not a guess.
* **Safe sources only:** a web address is opened with :func:`open_stream`, which checks every
  redirect hop again (:mod:`~octaledger.infrastructure.integrations.urlcheck`), accepts only
  ``audio/*`` answers and bounds the connection time and the amount of data read. Files come from
  :func:`resolve_file` (released folders) or
  :func:`octaledger.infrastructure.audio.paths.resolve_media` (free local paths).
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, BinaryIO, Final

import requests

from octaledger.core.errors import IntegrationError, ValidationError
from octaledger.domain.media_formats import FFMPEG, NATIVE, NATIVE_AUDIO, decoder_for
from octaledger.domain.playlist import Repeat, following, play_order, preceding
from octaledger.infrastructure.audio.engine import AudioEngine
from octaledger.infrastructure.audio.ffmpeg import FfmpegPcm, find_ffmpeg
from octaledger.infrastructure.audio.paths import Track
from octaledger.infrastructure.integrations.urlcheck import (
    MAX_REDIRECTS,
    check_media_url,
)

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT: Final = 5.0
READ_TIMEOUT: Final = 15.0
#: A stream is cut off after this many bytes (about 12 hours of 128 kbit/s audio).
MAX_STREAM_BYTES: Final = 700 * 1024 * 1024
MAX_FILE_BYTES: Final = 500 * 1024 * 1024
AUDIO_EXTENSIONS: Final = NATIVE_AUDIO
QUEUE_SIZE: Final = 10
ALLOWED_TYPES: Final = ("audio/", "application/ogg")
#: Content types the built-in decoder reads; any other audio type goes through FFmpeg if present.
NATIVE_TYPES: Final = frozenset(
    {
        "audio/mpeg", "audio/mp3", "audio/ogg", "application/ogg", "audio/flac",
        "audio/x-flac", "audio/wav", "audio/x-wav", "audio/wave", "audio/vorbis",
    }
)  # fmt: skip
#: How many titles of the queue the status carries (the interface shows them as a list).
STATUS_TITLES: Final = 200

STOPPED: Final = "stopped"
PLAYING: Final = "playing"
PAUSED: Final = "paused"


@dataclass(frozen=True, slots=True)
class Command:
    """One request to the worker.

    Attributes:
        kind: ``play_url``, ``play_file``, ``play_queue``, ``stop``, ``volume``, ``pause``,
            ``resume``, ``next``, ``previous``, ``jump``, ``set_repeat``, ``set_shuffle`` or the
            internal ``ended``.
        value: Address, path, volume, index, repeat mode ... depending on ``kind``.
        volume: Volume (``0.0..1.0``) a new playback starts with.
        allow_lan: Whether a stream address in the home network is allowed.
        tracks: The tracks of ``play_queue``.
        repeat: Repeat mode of ``play_queue``.
        shuffle: Whether ``play_queue`` is shuffled.
        start: The track of ``play_queue`` that is played first (an index into ``tracks``).
    """

    kind: str
    value: str | float | Path | None = None
    volume: float | None = None
    allow_lan: bool = False
    tracks: tuple[Track, ...] = ()
    repeat: Repeat = Repeat.OFF
    shuffle: bool = False
    start: int = 0


@dataclass(frozen=True, slots=True)
class PlayerStatus:
    """What the player does right now (an immutable snapshot for the interface).

    Attributes:
        state: ``stopped``, ``playing`` or ``paused``.
        title: The current title (file name or stream address), empty when stopped.
        position: 1-based number of the current track in the queue (0 when stopped).
        total: Number of tracks in the queue.
        repeat: ``off``, ``all`` or ``one``.
        shuffle: Whether the queue is shuffled.
        volume: Volume in percent.
        source: ``file`` or ``stream`` (empty when stopped).
        error: The last problem in plain German, or ``None``.
        queue: The titles of the queue in play order (at most :data:`STATUS_TITLES`).
        ffmpeg: Whether FFmpeg is available for more formats.
        since: Seconds since the epoch when the current track started (0 when stopped).
    """

    state: str = STOPPED
    title: str = ""
    position: int = 0
    total: int = 0
    repeat: str = Repeat.OFF.value
    shuffle: bool = False
    volume: int = 50
    source: str = ""
    error: str | None = None
    queue: tuple[str, ...] = ()
    ffmpeg: bool = False
    since: float = 0.0


@dataclass(frozen=True, slots=True)
class _Item:
    """One thing to play: a file or a web stream."""

    kind: str  # file | stream
    ref: str | Path
    title: str


class _LimitedStream:
    """A byte stream that ends after ``limit`` bytes and closes its response."""

    def __init__(self, response: requests.Response, limit: int, content_type: str = "") -> None:
        self._response = response
        self._raw = response.raw
        self._left = limit
        self.content_type = content_type

    def read(self, size: int = -1) -> bytes:
        """Read at most ``size`` bytes, never more than the overall limit."""
        if self._left <= 0:
            return b""
        size = self._left if size is None or size < 0 else min(size, self._left)
        data: bytes = self._raw.read(size)
        self._left -= len(data)
        return data

    def close(self) -> None:
        """Close the connection."""
        self._response.close()


def open_stream(
    url: str,
    *,
    allow_lan: bool = False,
    session: requests.Session | None = None,
) -> BinaryIO:
    """Open an audio stream safely (see the module docstring).

    Raises:
        ValidationError: If an address (also after a redirect) is refused.
        IntegrationError: If the server does not answer, answers an error or sends no audio.
    """
    http = session or requests.Session()
    http.trust_env = False  # a request to a device must not travel through a proxy
    current = check_media_url(url, allow_lan=allow_lan)
    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = http.get(
                current,
                stream=True,
                allow_redirects=False,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                headers={"User-Agent": "OctaLedger", "Icy-MetaData": "0"},
            )
        except requests.RequestException as exc:
            raise IntegrationError(
                f"Stream not reachable: {type(exc).__name__}",
                user_message="Der Stream ist nicht erreichbar. Bitte die Adresse prüfen.",
            ) from exc
        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise IntegrationError(
                    "Redirect without target", user_message="Ungültige Weiterleitung."
                )
            current = check_media_url(
                requests.compat.urljoin(current, location), allow_lan=allow_lan
            )
            continue
        break
    else:
        raise ValidationError(
            "Too many redirects",
            user_message="Die Adresse leitet zu oft weiter und wird abgelehnt.",
        )
    if response.status_code != 200:
        status = response.status_code
        response.close()
        raise IntegrationError(
            f"Stream answered HTTP {status}",
            user_message=f"Der Server hat den Stream abgelehnt (HTTP {status}).",
        )
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if not content_type.startswith(ALLOWED_TYPES):
        response.close()
        raise IntegrationError(
            f"Not audio: {content_type!r}",
            user_message="Unter dieser Adresse liegt keine Audiodatei oder kein Audiostream.",
        )
    return _LimitedStream(response, MAX_STREAM_BYTES, content_type)  # type: ignore[return-value]


def resolve_file(folders: list[Path], choice: str) -> Path:
    """Turn ``"<folder number>:<relative path>"`` into a real file inside an allowed folder.

    Free paths are never accepted here (the free-path rules live in
    :func:`octaledger.infrastructure.audio.paths.resolve_media`). The resolved path must lie below
    the folder (so ``..`` and links pointing outside are refused), have an audio extension and a
    sane size.

    Raises:
        ValidationError: For anything outside the allowed folders or not an audio file.
    """
    number, _, relative = choice.partition(":")
    if not number.isdigit() or int(number) >= len(folders) or not relative:
        raise ValidationError(
            f"Invalid file choice {choice!r}", user_message="Bitte eine Datei aus der Liste wählen."
        )
    base = folders[int(number)].resolve()
    try:
        path = (base / relative).resolve(strict=True)
        path.relative_to(base)
    except (OSError, ValueError):
        raise ValidationError(
            "File outside the allowed folders or missing",
            user_message="Die Datei liegt nicht in einem freigegebenen Ordner oder fehlt.",
        ) from None
    if path.suffix.lower() not in AUDIO_EXTENSIONS or not path.is_file():
        raise ValidationError(
            "Not an audio file",
            user_message="Erlaubt sind nur MP3-, FLAC-, WAV- und OGG-Dateien.",
        )
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValidationError("File too large", user_message="Die Datei ist zu groß.")
    return path


@dataclass(slots=True)
class _Playback:
    """The state of the current queue; touched only by the worker thread."""

    items: list[_Item] = field(default_factory=list)
    order: list[int] = field(default_factory=list)
    position: int = 0
    repeat: Repeat = Repeat.OFF
    shuffle: bool = False
    seed: int = 0
    failures: int = 0


class AudioWorker:
    """Runs the commands one after another in a background thread."""

    def __init__(
        self,
        engine_factory: Callable[[], AudioEngine],
        *,
        opener: Callable[..., BinaryIO] = open_stream,
        ffmpeg_finder: Callable[[], str | None] = find_ffmpeg,
        ffmpeg_factory: Callable[..., Any] = FfmpegPcm,
    ) -> None:
        """Create the worker (the thread starts with the first command).

        Args:
            engine_factory: Creates the audio engine (called once, in the worker thread).
            opener: Opens a safe stream for an address (replaceable for tests).
            ffmpeg_finder: Returns the path of ``ffmpeg`` or ``None`` (replaceable for tests).
            ffmpeg_factory: Starts a decoding stream (replaceable for tests).
        """
        self._factory = engine_factory
        self._opener = opener
        self._find_ffmpeg = ffmpeg_finder
        self._make_ffmpeg = ffmpeg_factory
        self._queue: queue.Queue[Command | None] = queue.Queue(maxsize=QUEUE_SIZE)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._status = PlayerStatus()
        self._play = _Playback()
        self._volume = 0.5
        self._engine: Any = None
        self._allow_lan = False
        self.last_error: str | None = None
        self.playing: str | None = None

    # ---------------------------------------------------------------- public API

    def submit(self, command: Command) -> None:
        """Queue a command without blocking.

        Raises:
            IntegrationError: If too many commands are waiting.
        """
        self._ensure_thread()
        try:
            self._queue.put_nowait(command)
        except queue.Full:
            raise IntegrationError(
                "Audio queue full", user_message="Der Player ist beschäftigt; bitte kurz warten."
            ) from None

    def status(self) -> PlayerStatus:
        """The current state of the player (a snapshot, safe to call from any thread)."""
        with self._status_lock:
            return replace(self._status, ffmpeg=self._find_ffmpeg() is not None)

    def stop_thread(self, timeout: float = 5.0) -> None:
        """Stop the thread (and the sound)."""
        thread = self._thread
        if thread is None:
            return
        with contextlib.suppress(queue.Full):  # a full queue means the thread is busy anyway
            self._queue.put(None, timeout=1)
        thread.join(timeout)

    # -------------------------------------------------------------------- thread

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="octaledger-audio", daemon=True)
            self._thread.start()

    def _set_status(self, **changes: Any) -> None:
        with self._status_lock:
            self._status = replace(self._status, **changes)

    def _on_ended(self, generation: int) -> None:
        """Called from the audio thread when a track ended: only queue a message."""
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(Command("ended", float(generation)))

    def _run(self) -> None:
        engine: Any = None
        while True:
            command = self._queue.get()
            if command is None:
                break
            try:
                if engine is None:
                    engine = self._factory()
                    self._engine = engine
                    setter = getattr(engine, "set_end_callback", None)
                    if setter is not None:
                        setter(self._on_ended)
                self._handle(engine, command)
                if command.kind != "ended":
                    self.last_error = None
            except (IntegrationError, ValidationError) as exc:
                self._fail(exc.user_message, f"Audio command {command.kind} failed: {exc}")
            except Exception:
                self._fail("Unerwarteter Fehler beim Abspielen.", None)
                logger.exception("Audio worker hit an unexpected error")
        if engine is not None:
            engine.stop()

    def _fail(self, message: str, log: str | None) -> None:
        """Remember an error for the interface; the queue keeps going if it can."""
        self.last_error = message
        if log:
            logger.warning(log)
        play = self._play
        title = play.items[play.order[play.position]].title if play.items and play.order else ""
        # With several tracks the user also learns *which* one was skipped.
        shown = f"„{title}“ übersprungen: {message}" if title and len(play.items) > 1 else message
        self._set_status(error=shown)
        if not self._skip_failed():
            self.playing = None
            if self._engine is not None:  # a track that was playing before must not play on
                with contextlib.suppress(Exception):
                    self._engine.stop()
            self._set_status(
                state=STOPPED, title="", position=0, source="", since=0.0, queue=(), total=0
            )

    def _skip_failed(self) -> bool:
        """After a track failed: try the next one (only while other tracks remain)."""
        play = self._play
        if len(play.items) < 2 or not play.order:
            return False
        play.failures += 1
        if play.failures >= len(play.items):
            return False
        nxt = following(play.position, len(play.order), play.repeat, by_user=True)
        if nxt is None:
            return False
        play.position = nxt
        try:
            self._start_current(self._engine)
        except (IntegrationError, ValidationError) as exc:
            self.last_error = exc.user_message
            self._set_status(error=exc.user_message)
            return self._skip_failed()
        return True

    # ---------------------------------------------------------------- the commands

    def _handle(self, engine: Any, command: Command) -> None:
        kind = command.kind
        if command.volume is not None:
            self._volume = command.volume
        if kind == "stop":
            self._stop(engine)
        elif kind == "volume":
            self._volume = float(str(command.value or 0))
            engine.set_volume(self._volume)
            self._set_status(volume=round(self._volume * 100))
        elif kind == "play_url":
            self._begin(
                engine,
                [_Item("stream", str(command.value), _stream_title(str(command.value)))],
                command,
                allow_lan=command.allow_lan,
            )
        elif kind == "play_file":
            path = Path(str(command.value))
            self._begin(engine, [_Item("file", path, path.stem)], command)
        elif kind == "play_queue":
            items = [_Item("file", t.path, t.title) for t in command.tracks]
            self._begin(engine, items, command, start=command.start)
        elif kind == "pause":
            self._pause(engine, True)
        elif kind == "resume":
            self._pause(engine, False)
        elif kind in ("next", "previous", "jump"):
            self._move(engine, command)
        elif kind == "set_repeat":
            self._play.repeat = Repeat(str(command.value))
            self._set_status(repeat=self._play.repeat.value)
        elif kind == "set_shuffle":
            self._reshuffle(bool(command.value))
        elif kind == "ended":
            self._ended(engine, int(float(str(command.value))))
        else:  # pragma: no cover - the adapter only sends the kinds above
            raise IntegrationError(f"Unknown audio command {kind!r}")

    def _stop(self, engine: Any) -> None:
        engine.stop()
        self._play = _Playback()
        self.playing = None
        self._set_status(
            state=STOPPED, title="", position=0, total=0, source="", since=0.0, queue=()
        )

    def _pause(self, engine: Any, held: bool) -> None:
        if self.playing is None:
            return
        action = getattr(engine, "pause" if held else "resume", None)
        if action is None:
            raise IntegrationError(
                "Engine cannot pause", user_message="Dieser Player kann nicht pausieren."
            )
        action()
        self._set_status(state=PAUSED if held else PLAYING)

    def _begin(
        self,
        engine: Any,
        items: list[_Item],
        command: Command,
        *,
        start: int = 0,
        allow_lan: bool = False,
    ) -> None:
        """Replace what plays by a new queue and start its first track."""
        if not items:
            raise ValidationError("Empty queue", user_message="Es gibt nichts abzuspielen.")
        seed = int(time.time() * 1000) & 0x7FFFFFFF
        first = min(max(start, 0), len(items) - 1)
        order = play_order(len(items), shuffle=command.shuffle, seed=seed, first=first)
        position = order.index(first)
        self._play = _Playback(items, order, position, command.repeat, command.shuffle, seed)
        self._allow_lan = allow_lan
        self._set_status(
            repeat=command.repeat.value,
            shuffle=command.shuffle,
            volume=round(self._volume * 100),
            total=len(items),
            error=None,
        )
        self._start_current(engine)

    def _reshuffle(self, shuffle: bool) -> None:
        """Turn the shuffle on or off without interrupting the current track."""
        play = self._play
        if not play.items:
            self._set_status(shuffle=shuffle)
            return
        current = play.order[play.position]
        play.shuffle = shuffle
        play.order = play_order(len(play.items), shuffle=shuffle, seed=play.seed, first=current)
        play.position = play.order.index(current)
        self._set_status(shuffle=shuffle, queue=self._titles())

    def _move(self, engine: Any, command: Command) -> None:
        play = self._play
        if not play.items:
            return
        count = len(play.order)
        if command.kind == "jump":
            wanted = int(float(str(command.value)))
            if not 0 <= wanted < count:
                raise ValidationError("No such track", user_message="Diesen Titel gibt es nicht.")
            play.position = wanted
        elif command.kind == "next":
            nxt = following(play.position, count, play.repeat, by_user=True)
            if nxt is None:
                self._stop(engine)
                return
            play.position = nxt
        else:
            play.position = preceding(play.position, count, play.repeat)
        play.failures = 0
        self._start_current(engine)

    def _ended(self, engine: Any, generation: int) -> None:
        """A track played to its end: continue by the repeat rules."""
        current = getattr(engine, "generation", generation)
        if generation != current or self.playing is None:
            return  # a message of a track that was replaced or stopped meanwhile
        play = self._play
        nxt = following(play.position, len(play.order), play.repeat)
        if nxt is None:
            logger.info("Playback finished (%d tracks)", len(play.items))
            self._stop(engine)
            return
        play.position = nxt
        play.failures = 0
        self._start_current(engine)

    def _titles(self) -> tuple[str, ...]:
        play = self._play
        return tuple(play.items[i].title for i in play.order[:STATUS_TITLES])

    def _start_current(self, engine: Any) -> None:
        """Open the current track with the right decoder and hand it to the engine."""
        play = self._play
        item = play.items[play.order[play.position]]
        source = self._open(item)
        try:
            engine.play(source, self._volume)
        except BaseException:
            with contextlib.suppress(OSError):
                source.close()
            raise
        self.playing = item.kind
        self._set_status(
            state=PLAYING,
            title=item.title,
            position=play.position + 1,
            total=len(play.items),
            source=item.kind,
            queue=self._titles(),
            since=time.time(),
        )
        logger.info("Playing %s (%d of %d)", item.kind, play.position + 1, len(play.items))

    def _open(self, item: _Item) -> Any:
        """The byte source of an item: a file, a checked stream, or an FFmpeg decoder."""
        ffmpeg = self._find_ffmpeg()
        if item.kind == "file":
            path = Path(str(item.ref))
            decoder = decoder_for(path, ffmpeg=ffmpeg is not None)
            if decoder == FFMPEG and ffmpeg is not None:
                return self._make_ffmpeg(ffmpeg, source=path)
            if decoder == NATIVE:
                return path.open("rb")
            raise ValidationError(
                f"No decoder for {path.suffix}",
                user_message="Dieses Dateiformat kann nicht abgespielt werden (FFmpeg fehlt?).",
            )
        stream = self._opener(str(item.ref), allow_lan=self._allow_lan)
        content_type = str(getattr(stream, "content_type", ""))
        if ffmpeg is not None and content_type and content_type not in NATIVE_TYPES:
            return self._make_ffmpeg(ffmpeg, source=None, feed=stream)
        return stream


def _stream_title(url: str) -> str:
    """A short title for a stream: its host name."""
    rest = url.split("://", 1)[-1]
    return rest.split("/", 1)[0] or url
