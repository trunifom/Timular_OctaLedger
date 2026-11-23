"""Audio engines: the part that really makes sound (replaceable, optional).

:class:`AudioEngine` is the small interface the worker uses. :class:`MiniaudioEngine` implements
it with the optional ``miniaudio`` package (MIT, extra ``audio``): MP3, FLAC, WAV and Vorbis
natively, and **raw PCM** for everything FFmpeg decodes (see
:mod:`octaledger.infrastructure.audio.ffmpeg`). Without the package :class:`UnavailableEngine`
answers every request with an explanation instead of crashing.

What the engine offers beyond play/stop/volume (AP-61):

* **pause and resume** (the source keeps its position; the device plays silence meanwhile);
* an **end callback**: when a track has been played to its end the engine calls
  ``callback(generation)`` from its audio thread. The callback must not block; the worker only
  puts a message into its queue. ``generation`` identifies the playback, so a message of a track
  that was already replaced is recognised and ignored.

The engines only play bytes that the caller hands over; they never open an address or a file
themselves, so every safety check (:mod:`~octaledger.infrastructure.integrations.urlcheck`, path
rules) happens before. Not exercised against real sound hardware in this repository.
"""

from __future__ import annotations

import importlib.util
import logging
import threading
from array import array
from collections.abc import Callable
from typing import Any, BinaryIO, Protocol

from octaledger.core.errors import IntegrationError

logger = logging.getLogger(__name__)

SAMPLE_RATE = 44100
CHANNELS = 2
PCM_BLOCK = 8192


def audio_available() -> bool:
    """Whether the optional ``miniaudio`` package is installed."""
    return importlib.util.find_spec("miniaudio") is not None


class AudioEngine(Protocol):
    """What the worker needs from an audio backend."""

    def play(self, source: BinaryIO, volume: float) -> None:
        """Stop what plays and start playing ``source`` (a readable byte stream)."""
        ...

    def stop(self) -> None:
        """Stop playing (no error if nothing plays)."""
        ...

    def set_volume(self, volume: float) -> None:
        """Change the volume of the current and later playback (``0.0..1.0``)."""
        ...


class UnavailableEngine:
    """Used when no audio package is installed: every request explains what to do."""

    def play(self, source: BinaryIO, volume: float) -> None:
        """Always fails with the installation hint."""
        raise IntegrationError(
            "No audio engine installed",
            user_message='Zum Abspielen fehlt das Zusatzpaket „audio“: pip install -e ".[audio]".',
        )

    def stop(self) -> None:
        """Nothing plays, so there is nothing to stop."""

    def set_volume(self, volume: float) -> None:
        """Nothing plays, so there is nothing to change."""


class _ReaderSource:
    """Adapts a byte stream to the ``read`` interface of ``miniaudio.StreamableSource``.

    ``miniaudio`` is an optional dependency, so this class duck-types ``StreamableSource``
    instead of inheriting from it. The decoder's C read callback, however, reads and writes
    ``error_in_readcallback`` on the source and ``stream_any`` sets ``ffi_handle``; without
    these attributes every read raised ``AttributeError`` inside the callback and nothing
    was decoded. They are declared here with the same defaults as the library's base class.
    """

    # Set by miniaudio's read callback when ``read`` raised; ``None`` means "no error".
    error_in_readcallback: Exception | None = None
    # Assigned by miniaudio (``ffi.new_handle``) while the decoder runs.
    ffi_handle: Any = None

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def read(self, num_bytes: int) -> bytes:
        """Read up to ``num_bytes`` (an empty result ends the stream)."""
        return self._stream.read(num_bytes)

    def seek(self, offset: int, origin: Any) -> bool:
        """Streams cannot seek."""
        return False

    def close(self) -> None:
        """Called by miniaudio when decoding ends; the engine closes the stream itself."""


class MiniaudioEngine:
    """Plays MP3, FLAC, WAV, Vorbis and raw PCM through ``miniaudio`` (extra ``audio``)."""

    def __init__(self) -> None:
        """Create the engine; the audio device is opened on the first playback."""
        self._lock = threading.Lock()
        self._device: Any = None
        self._source: BinaryIO | None = None
        self._volume = 0.5
        self._paused = False
        self._generation = 0
        self._on_end: Callable[[int], None] | None = None

    # ------------------------------------------------------------------ interface

    def set_end_callback(self, callback: Callable[[int], None] | None) -> None:
        """Register what is called (from the audio thread) when a track ended by itself."""
        self._on_end = callback

    @property
    def generation(self) -> int:
        """The number of the current playback (it grows with every :meth:`play`)."""
        return self._generation

    def play(self, source: BinaryIO, volume: float) -> None:
        """Start playing ``source`` after stopping the previous one.

        A source with ``is_pcm = True`` is played as raw 16-bit stereo PCM (FFmpeg output);
        anything else is detected by ``miniaudio`` (MP3, FLAC, WAV, Vorbis).
        """
        import miniaudio

        self.stop()
        with self._lock:
            self._volume = max(0.0, min(1.0, volume))
            self._paused = False
            self._generation += 1
            generation = self._generation
            try:
                if getattr(source, "is_pcm", False):
                    samples = self._pcm_blocks(source)
                else:
                    samples = miniaudio.stream_any(
                        _ReaderSource(source),
                        output_format=miniaudio.SampleFormat.SIGNED16,
                        nchannels=CHANNELS,
                        sample_rate=SAMPLE_RATE,
                    )
                device = miniaudio.PlaybackDevice(
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=CHANNELS,
                    sample_rate=SAMPLE_RATE,
                )
                generator = self._generator(samples, generation)
                next(generator)
                device.start(generator)
            except (miniaudio.MiniaudioError, OSError) as exc:
                self._close(source)
                raise IntegrationError(
                    f"Cannot play: {exc}",
                    user_message="Das Format wird nicht unterstützt oder das Audiogerät ist nicht "
                    "verfügbar.",
                ) from exc
            self._device, self._source = device, source

    def stop(self) -> None:
        """Stop and release the audio device and the source."""
        with self._lock:
            device, self._device = self._device, None
            source, self._source = self._source, None
            self._generation += 1  # a late "ended" message of this track is now stale
            self._paused = False
        if device is not None:
            try:
                device.stop()
                device.close()
            except Exception:
                logger.debug("Ignoring error while stopping the audio device", exc_info=True)
        if source is not None:
            self._close(source)

    def pause(self) -> None:
        """Hold playback (silence is played; the track keeps its position)."""
        self._paused = True

    def resume(self) -> None:
        """Continue after :meth:`pause`."""
        self._paused = False

    @property
    def paused(self) -> bool:
        """Whether playback is held."""
        return self._paused

    def set_volume(self, volume: float) -> None:
        """Change the volume (takes effect with the next audio block)."""
        self._volume = max(0.0, min(1.0, volume))

    # ------------------------------------------------------------------- internals

    @staticmethod
    def _close(source: Any) -> None:
        try:
            source.close()
        except OSError:
            logger.debug("Ignoring error while closing the audio source", exc_info=True)

    @staticmethod
    def _pcm_blocks(source: Any) -> Any:
        """A generator of sample blocks from a raw PCM stream (same protocol as stream_any)."""
        frame_bytes = CHANNELS * 2
        required = yield b""
        while True:
            wanted = max(int(required or PCM_BLOCK) * frame_bytes, frame_bytes)
            data = source.read(wanted)
            if not data:
                return
            data = data[: len(data) - len(data) % 2]
            block = array("h")
            block.frombytes(data)
            required = yield block

    def _generator(self, stream: Any, generation: int) -> Any:
        """Feed the device with decoded samples, scaled by volume, silent while paused."""
        required = yield b""
        while True:
            if self._paused:
                required = yield array("h", bytes(int(required or PCM_BLOCK) * CHANNELS * 2))
                continue
            try:
                samples = stream.send(required)  # the first send(None) primes the stream
            except StopIteration:
                self._finished(generation)
                return
            if self._volume < 0.999:
                factor = self._volume
                samples = array("h", (int(s * factor) for s in samples))
            required = yield samples

    def _finished(self, generation: int) -> None:
        """A track played to its end: tell the worker (never raises into the audio thread)."""
        callback = self._on_end
        if callback is None or generation != self._generation:
            return
        try:
            callback(generation)
        except Exception:
            logger.exception("The end-of-track callback failed")
