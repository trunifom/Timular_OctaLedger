"""Which files the local player can play (pure: judged by the file extension only).

Two decoders exist:

* the **built-in** one (``miniaudio``): MP3, FLAC, WAV and Ogg Vorbis;
* **FFmpeg**, if it is installed on the computer: everything else - AAC/M4A, WMA, Opus, AIFF and
  more, and the **sound track of video files** (MP4, MKV, WebM, MOV, AVI ...). OctaLedger plays
  the sound only, never the picture.

The extension is only a first filter. The decoders decide on the real content; a file with a
wrong extension fails with an explanation instead of crashing.
"""

from __future__ import annotations

from pathlib import PurePath
from typing import Final

NATIVE_AUDIO: Final = frozenset({".mp3", ".flac", ".wav", ".ogg", ".oga"})
FFMPEG_AUDIO: Final = frozenset(
    {
        ".m4a", ".aac", ".wma", ".opus", ".aiff", ".aif", ".aifc", ".ape", ".wv", ".mka",
        ".amr", ".mp2", ".ac3", ".dts", ".caf", ".mpc", ".weba", ".spx", ".m4b", ".tta",
    }
)  # fmt: skip
VIDEO: Final = frozenset(
    {
        ".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".flv", ".3gp", ".ts",
        ".mts", ".m2ts", ".mpg", ".mpeg", ".ogv",
    }
)  # fmt: skip
PLAYLISTS: Final = frozenset({".m3u", ".m3u8"})

NATIVE: Final = "native"
FFMPEG: Final = "ffmpeg"


def suffix(path: str | PurePath) -> str:
    """The lower-case extension (``".mp3"``), empty if there is none."""
    return PurePath(path).suffix.lower()


def decoder_for(path: str | PurePath, *, ffmpeg: bool) -> str | None:
    """Which decoder plays the file: ``native``, ``ffmpeg`` or ``None`` (cannot be played)."""
    ext = suffix(path)
    if ext in NATIVE_AUDIO:
        return NATIVE
    if ffmpeg and (ext in FFMPEG_AUDIO or ext in VIDEO):
        return FFMPEG
    return None


def is_playlist(path: str | PurePath) -> bool:
    """Whether the file is an ``.m3u``/``.m3u8`` list of other files."""
    return suffix(path) in PLAYLISTS


def known_extensions() -> frozenset[str]:
    """Every extension OctaLedger knows (with FFmpeg)."""
    return NATIVE_AUDIO | FFMPEG_AUDIO | VIDEO


def playable_extensions(*, ffmpeg: bool) -> frozenset[str]:
    """The extensions that can be played right now."""
    return known_extensions() if ffmpeg else NATIVE_AUDIO


def support_text(*, ffmpeg: bool) -> str:
    """One German sentence for the interface: what can be played and what is missing."""
    if ffmpeg:
        return (
            "Abspielbar: MP3, FLAC, WAV, OGG sowie (über FFmpeg) AAC/M4A, WMA, Opus, AIFF und "
            "weitere Audioformate und der Ton von Videodateien (MP4, MKV, WebM, MOV, AVI …)."
        )
    return (
        "Abspielbar: MP3, FLAC, WAV und OGG. Für AAC/M4A, WMA, Opus und den Ton von Videodateien "
        "(MP4, MKV, WebM …) muss FFmpeg auf diesem Computer installiert sein (winget install "
        "ffmpeg)."
    )
