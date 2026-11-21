"""The audio worker: a daemon thread that plays what the player adapter asks for.

Playing sound must never block the Bluetooth loop or the action dispatcher, and an internet radio
connection can take seconds. So the adapter only **puts a command into a queue**
(:meth:`AudioWorker.submit`, ``put_nowait``); this thread opens the stream or file and drives the
:class:`~octaledger.infrastructure.audio.engine.AudioEngine`.

* **One sound at a time:** a new playback replaces the old one; ``stop`` ends it.
* **Never dies:** an error is logged and kept as :attr:`last_error` for the interface; the thread
  continues with the next command.
* **Safe sources only:** a web address is opened with :func:`open_stream`, which checks every
  redirect hop again (:mod:`~octaledger.infrastructure.integrations.urlcheck`), accepts only
  ``audio/*`` answers and bounds the connection time and the amount of data read. Files come from
  :func:`resolve_file`, which keeps them inside the folders the user allowed.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Final

import requests

from octaledger.core.errors import IntegrationError, ValidationError
from octaledger.infrastructure.audio.engine import AudioEngine
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
AUDIO_EXTENSIONS: Final = frozenset({".mp3", ".flac", ".wav", ".ogg"})
QUEUE_SIZE: Final = 10
ALLOWED_TYPES: Final = ("audio/", "application/ogg")


@dataclass(frozen=True, slots=True)
class Command:
    """One request to the worker."""

    kind: str  # play_url | play_file | stop | volume
    value: str | float | Path | None = None
    volume: float | None = None
    allow_lan: bool = False


class _LimitedStream:
    """A byte stream that ends after ``limit`` bytes and closes its response."""

    def __init__(self, response: requests.Response, limit: int) -> None:
        self._response = response
        self._raw = response.raw
        self._left = limit

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
    return _LimitedStream(response, MAX_STREAM_BYTES)  # type: ignore[return-value]


def resolve_file(folders: list[Path], choice: str) -> Path:
    """Turn ``"<folder number>:<relative path>"`` into a real file inside an allowed folder.

    Free paths are never accepted. The resolved path must lie below the folder (so ``..`` and
    links pointing outside are refused), have an audio extension and a sane size.

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


class AudioWorker:
    """Runs the commands one after another in a background thread."""

    def __init__(
        self,
        engine_factory: Callable[[], AudioEngine],
        *,
        opener: Callable[..., BinaryIO] = open_stream,
    ) -> None:
        """Create the worker (the thread starts with the first command).

        Args:
            engine_factory: Creates the audio engine (called once, in the worker thread).
            opener: Opens a safe stream for an address (replaceable for tests).
        """
        self._factory = engine_factory
        self._opener = opener
        self._queue: queue.Queue[Command | None] = queue.Queue(maxsize=QUEUE_SIZE)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.last_error: str | None = None
        self.playing: str | None = None

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

    def stop_thread(self, timeout: float = 5.0) -> None:
        """Stop the thread (and the sound)."""
        thread = self._thread
        if thread is None:
            return
        try:
            self._queue.put(None, timeout=1)
        except queue.Full:
            pass
        thread.join(timeout)

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="octaledger-audio", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        engine: Any = None
        while True:
            command = self._queue.get()
            if command is None:
                break
            try:
                if engine is None:
                    engine = self._factory()
                self._handle(engine, command)
                self.last_error = None
            except (IntegrationError, ValidationError) as exc:
                self.last_error = exc.user_message
                self.playing = None
                logger.warning("Audio command %s failed: %s", command.kind, exc)
            except Exception:  # noqa: BLE001 - the worker must outlive any engine bug
                self.last_error = "Unerwarteter Fehler beim Abspielen."
                self.playing = None
                logger.exception("Audio worker hit an unexpected error")
        if engine is not None:
            engine.stop()

    def _handle(self, engine: AudioEngine, command: Command) -> None:
        volume = 0.5 if command.volume is None else command.volume
        if command.kind == "stop":
            engine.stop()
            self.playing = None
        elif command.kind == "volume":
            engine.set_volume(float(str(command.value or 0)))
        elif command.kind == "play_url":
            stream = self._opener(str(command.value), allow_lan=command.allow_lan)
            engine.play(stream, volume)
            self.playing = "stream"
        elif command.kind == "play_file":
            engine.play(Path(str(command.value)).open("rb"), volume)
            self.playing = "file"
        else:  # pragma: no cover - the adapter only sends the four kinds above
            raise IntegrationError(f"Unknown audio command {command.kind!r}")
