"""FFmpeg as an optional decoder for formats the built-in engine cannot play (AP-61).

If ``ffmpeg`` is installed (found on ``PATH``), :class:`FfmpegPcm` starts it as a child process
that decodes a file - or bytes fed through its input - to raw 16-bit stereo PCM, which the audio
engine plays like any other source. Video files give their **sound track** only (``-vn``).

Safety: the command is built as a **list** (no shell), the file path comes from
:mod:`octaledger.infrastructure.audio.paths` (checked), a web stream is never handed to FFmpeg by
address - OctaLedger opens it itself (with all address checks) and pipes the bytes in - and the
child process is always terminated when playback ends.

Honest limit: not tested against a real FFmpeg in this repository (the tests check the command
and the stream wrapper with a fake process).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any, BinaryIO, Final

from octaledger.core.errors import IntegrationError
from octaledger.infrastructure.audio.engine import CHANNELS, SAMPLE_RATE

logger = logging.getLogger(__name__)

CHUNK: Final = 64 * 1024


def find_ffmpeg() -> str | None:
    """The full path of ``ffmpeg`` if it is installed, else ``None``."""
    return shutil.which("ffmpeg")


def ffmpeg_command(executable: str, source: Path | None) -> list[str]:
    """The command line that decodes ``source`` (a file, or ``None`` = standard input) to PCM."""
    return [
        executable,
        "-v",
        "error",
        "-nostdin" if source is not None else "-hide_banner",
        "-i",
        str(source) if source is not None else "pipe:0",
        "-vn",
        "-f",
        "s16le",
        "-ac",
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
        "pipe:1",
    ]


class FfmpegPcm:
    """A readable stream of raw PCM produced by an FFmpeg child process."""

    #: The audio engine plays this as raw PCM instead of detecting a file format.
    is_pcm = True

    def __init__(
        self,
        executable: str,
        source: Path | None = None,
        feed: BinaryIO | None = None,
        *,
        popen: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        """Start FFmpeg.

        Args:
            executable: Path of ``ffmpeg``.
            source: A file to decode, or ``None`` to decode the bytes of ``feed``.
            feed: The byte stream piped into FFmpeg (only with ``source=None``).
            popen: Replaceable for tests.

        Raises:
            IntegrationError: If the process cannot be started.
        """
        command = ffmpeg_command(executable, source)
        try:
            self._process = popen(
                command,
                stdin=subprocess.PIPE if source is None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise IntegrationError(
                f"Cannot start ffmpeg: {exc}",
                user_message="FFmpeg konnte nicht gestartet werden. Ist es installiert?",
            ) from exc
        self._feeder: threading.Thread | None = None
        if source is None and feed is not None:
            self._feeder = threading.Thread(
                target=self._pump, args=(feed,), name="octaledger-ffmpeg-feed", daemon=True
            )
            self._feeder.start()

    def _pump(self, feed: BinaryIO) -> None:
        """Copy the web stream into FFmpeg's input until either side ends."""
        stdin: IO[bytes] | None = self._process.stdin
        try:
            while stdin is not None:
                data = feed.read(CHUNK)
                if not data:
                    break
                stdin.write(data)
        except (OSError, ValueError):
            logger.debug("FFmpeg feed ended", exc_info=True)
        finally:
            for stream in (stdin, feed):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    logger.debug("Stream already closed", exc_info=True)

    def read(self, size: int = CHUNK) -> bytes:
        """Decoded PCM (an empty result means the end of the track)."""
        out = self._process.stdout
        return b"" if out is None else bytes(out.read(size))

    def close(self) -> None:
        """End the child process."""
        process = self._process
        try:
            process.terminate()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
        for stream in (process.stdout, process.stdin):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                logger.debug("FFmpeg pipe already closed", exc_info=True)
