"""From a path the user typed or picked to the list of tracks to play (AP-61).

The user may name a **file**, a **folder** (an album or a whole collection) or a **playlist file**
(``.m3u``/``.m3u8``). This module turns that into an ordered list of :class:`Track`.

Safety rules (the path comes from the interface, so it is checked):

* the path must be **absolute** and refer to a **local** drive: network paths (UNC, ``\\\\server``)
  and Windows device paths (``\\\\?\\``, ``\\\\.\\``) are refused, because opening them would make
  Windows talk to a remote machine;
* only files with a **playable extension** are taken; everything else in a folder is skipped;
* a folder is scanned to a limited **depth** and **count** and never through links that point
  elsewhere (``os.walk`` without ``followlinks``);
* nothing is copied, read into memory or uploaded: the player opens the file when it plays it.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from octaledger.core.errors import ValidationError
from octaledger.domain.media_formats import decoder_for, is_playlist, support_text

logger = logging.getLogger(__name__)

MAX_PATH_LENGTH: Final = 1000
MAX_TRACKS: Final = 2000
MAX_DEPTH: Final = 6
_DIGITS: Final = re.compile(r"(\d+)")


@dataclass(frozen=True, slots=True)
class Track:
    """One playable file.

    Attributes:
        path: The file.
        title: What the interface shows (the file name without the extension).
    """

    path: Path
    title: str


def natural_key(text: str) -> list[object]:
    """Sort key that orders ``track2`` before ``track10`` (album order by file name)."""
    return [int(part) if part.isdigit() else part.lower() for part in _DIGITS.split(text)]


def clean_path_text(text: object) -> str:
    """Trim a typed path: spaces and the quotes Explorer adds with "Als Pfad kopieren".

    Raises:
        ValidationError: If the text is empty, too long or contains control characters.
    """
    raw = str(text or "").strip().strip('"').strip("'").strip()
    if not raw:
        raise ValidationError("Empty path", user_message="Bitte einen Pfad eingeben.")
    if len(raw) > MAX_PATH_LENGTH or any(ord(c) < 32 for c in raw):
        raise ValidationError(
            "Invalid path text",
            user_message="Der Pfad ist zu lang oder enthält Steuerzeichen.",
        )
    return raw


def reject_unsafe(raw: str) -> Path:
    """Return the path if it is a local absolute path, else raise.

    Raises:
        ValidationError: For network paths, device paths and relative paths.
    """
    normalised = raw.replace("/", "\\")
    if normalised.startswith("\\\\"):
        raise ValidationError(
            "Network or device path refused",
            user_message="Netzwerkpfade (\\\\Server\\Freigabe) sind nicht erlaubt. Nehmen Sie "
            "einen Pfad auf einem lokalen Laufwerk (z. B. C:\\Musik).",
        )
    path = Path(raw)
    if not path.is_absolute():
        raise ValidationError(
            "Relative path refused",
            user_message="Bitte den vollständigen Pfad angeben (z. B. C:\\Musik\\lied.mp3).",
        )
    return path


def _track(path: Path) -> Track:
    return Track(path, path.stem)


def _playable(path: Path, ffmpeg: bool) -> bool:
    return path.is_file() and decoder_for(path, ffmpeg=ffmpeg) is not None


def _scan_folder(folder: Path, ffmpeg: bool) -> list[Track]:
    """All playable files below ``folder`` in natural order (folder by folder)."""
    found: list[Path] = []
    for current, dirs, names in os.walk(folder):
        depth = len(Path(current).relative_to(folder).parts)
        if depth >= MAX_DEPTH:
            dirs.clear()
        dirs.sort(key=natural_key)
        for name in sorted(names, key=natural_key):
            candidate = Path(current) / name
            if decoder_for(candidate, ffmpeg=ffmpeg) is not None:
                found.append(candidate)
                if len(found) >= MAX_TRACKS:
                    logger.warning("Folder scan stopped at %d tracks: %s", MAX_TRACKS, folder)
                    return [_track(p) for p in found]
    return [_track(p) for p in found]


def _read_m3u(playlist: Path, ffmpeg: bool) -> list[Track]:
    """The local, playable entries of an m3u file (web addresses and comments are skipped)."""
    try:
        text = playlist.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise ValidationError(
            f"Cannot read playlist: {exc}",
            user_message="Die Playlist-Datei kann nicht gelesen werden.",
        ) from exc
    tracks: list[Track] = []
    for line in text.splitlines():
        entry = line.strip().strip('"')
        if not entry or entry.startswith("#") or "://" in entry:
            continue
        if entry.replace("/", "\\").startswith("\\\\"):
            continue  # network entries are skipped like network paths
        path = Path(entry)
        path = path if path.is_absolute() else playlist.parent / path
        if _playable(path, ffmpeg):
            tracks.append(_track(path))
            if len(tracks) >= MAX_TRACKS:
                break
    return tracks


def resolve_media(text: object, *, ffmpeg: bool) -> list[Track]:
    """Turn what the user gave (file, folder or playlist file) into tracks.

    Args:
        text: The typed or picked path.
        ffmpeg: Whether FFmpeg is installed (more formats are playable then).

    Returns:
        At least one track.

    Raises:
        ValidationError: With a German explanation if the path is unsafe, missing, not playable
            or leads to no playable file.
    """
    path = reject_unsafe(clean_path_text(text))
    try:
        path = path.resolve(strict=True)
    except OSError:
        raise ValidationError(
            f"Path does not exist: {path}",
            user_message=f"Den Pfad „{path}“ gibt es nicht (oder der Zugriff ist nicht erlaubt).",
        ) from None
    if path.is_dir():
        tracks = _scan_folder(path, ffmpeg)
        empty = "In diesem Ordner liegt keine abspielbare Datei. " + support_text(ffmpeg=ffmpeg)
    elif is_playlist(path):
        tracks = _read_m3u(path, ffmpeg)
        empty = "In dieser Playlist steht keine abspielbare lokale Datei."
    elif _playable(path, ffmpeg):
        tracks = [_track(path)]
        empty = ""
    else:
        tracks = []
        empty = "Dieses Dateiformat kann nicht abgespielt werden. " + support_text(ffmpeg=ffmpeg)
    if not tracks:
        raise ValidationError(f"Nothing playable at {path}", user_message=empty)
    return tracks


def titles(tracks: Iterable[Track]) -> list[str]:
    """The titles of a track list (for the interface)."""
    return [t.title for t in tracks]
