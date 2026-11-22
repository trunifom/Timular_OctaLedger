"""Audio engines: the part that really makes sound (replaceable, optional).

:class:`AudioEngine` is the small interface the worker uses. :class:`MiniaudioEngine` implements
it with the optional ``miniaudio`` package (MIT, extra ``audio``; MP3, FLAC, WAV and Vorbis, **no
AAC**, so internet radio streams in AAC cannot be played). Without the package
:class:`UnavailableEngine` answers every request with an explanation instead of crashing.

The engines only play bytes that the caller hands over; they never open an address or a file
themselves, so every safety check (:mod:`~octaledger.infrastructure.integrations.urlcheck`, folder
rules) happens before. Not exercised against real sound hardware in this repository.
"""

from __future__ import annotations

import importlib.util
import logging
import threading
from array import array
from typing import Any, BinaryIO, Protocol

from octaledger.core.errors import IntegrationError

logger = logging.getLogger(__name__)

SAMPLE_RATE = 44100
CHANNELS = 2


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
    """Adapts a byte stream to the ``read`` interface of ``miniaudio.StreamableSource``."""

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def read(self, num_bytes: int) -> bytes:
        """Read up to ``num_bytes`` (an empty result ends the stream)."""
        return self._stream.read(num_bytes)

    def seek(self, offset: int, origin: Any) -> bool:
        """Streams cannot seek."""
        return False


class MiniaudioEngine:
    """Plays MP3, FLAC, WAV and Vorbis through ``miniaudio`` (optional extra ``audio``)."""

    def __init__(self) -> None:
        """Create the engine; the audio device is opened on the first playback."""
        self._lock = threading.Lock()
        self._device: Any = None
        self._source: BinaryIO | None = None
        self._volume = 0.5

    def play(self, source: BinaryIO, volume: float) -> None:
        """Start playing ``source`` after stopping the previous one."""
        import miniaudio

        self.stop()
        with self._lock:
            self._volume = max(0.0, min(1.0, volume))
            try:
                stream = miniaudio.stream_any(
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
                generator = self._generator(stream)
                next(generator)
                device.start(generator)
            except (miniaudio.MiniaudioError, OSError) as exc:
                source.close()
                raise IntegrationError(
                    f"Cannot play: {exc}",
                    user_message="Das Format wird nicht unterstützt oder das Audiogerät ist nicht "
                    "verfügbar (AAC-Streams werden nicht abgespielt).",
                ) from exc
            self._device, self._source = device, source

    def stop(self) -> None:
        """Stop and release the audio device and the source."""
        with self._lock:
            device, self._device = self._device, None
            source, self._source = self._source, None
        if device is not None:
            try:
                device.stop()
                device.close()
            except Exception:
                logger.debug("Ignoring error while stopping the audio device", exc_info=True)
        if source is not None:
            try:
                source.close()
            except OSError:
                logger.debug("Ignoring error while closing the audio source", exc_info=True)

    def set_volume(self, volume: float) -> None:
        """Change the volume (takes effect with the next audio block)."""
        self._volume = max(0.0, min(1.0, volume))

    def _generator(self, stream: Any) -> Any:
        """Feed the device with decoded samples, scaled by the current volume."""
        required = yield b""
        while True:
            try:
                samples = stream.send(required)
            except StopIteration:
                return
            if self._volume < 0.999:
                factor = self._volume
                samples = array("h", (int(s * factor) for s in samples))
            required = yield samples
