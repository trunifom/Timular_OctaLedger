"""Music sources: recognise and normalise what the user pastes (pure, no network).

The user pastes a **link**; this module decides what it is and returns a normalised form:

=========================================================  ==========================
pasted                                                     normalised
=========================================================  ==========================
``https://open.spotify.com/track|album|playlist|artist/ID``  ``spotify:<type>:<id>``
``spotify:<type>:<id>``                                      unchanged
``https://music.youtube.com/watch?v=ID`` / ``www.youtube``   ``youtube:ID``
``https://youtu.be/ID`` (``list=`` is kept)                  ``youtube:ID`` (+ list)
any other ``http(s)://`` address (a stream)                  ``url:<address>``
=========================================================  ==========================

Anything else is **rejected with an explanation**; nothing is guessed. Addresses of streams go
through the same safety check as every other media address
(:func:`octaledger.infrastructure.integrations.urlcheck.check_media_url` is applied by the
caller that opens them); this module only checks the *shape*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qs, urlsplit

from octaledger.core.errors import ValidationError

SPOTIFY_TYPES = ("track", "album", "playlist", "artist", "episode", "show")
_SPOTIFY_ID = re.compile(r"^[A-Za-z0-9]{10,40}$")
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_LIST = re.compile(r"^[A-Za-z0-9_-]{10,60}$")
MAX_LENGTH = 2000


class SourceKind(StrEnum):
    """What kind of source a pasted link is."""

    SPOTIFY = "spotify"
    YOUTUBE = "youtube"
    URL = "url"


@dataclass(frozen=True, slots=True)
class MusicSource:
    """A recognised source.

    Attributes:
        kind: Spotify, YouTube or a plain stream address.
        ref: For Spotify ``<type>:<id>``, for YouTube the video id, for a stream the address.
        playlist: Optional YouTube playlist id (``list=``).
        original: What the user pasted (for display only).
    """

    kind: SourceKind
    ref: str
    playlist: str | None = None
    original: str = ""

    @property
    def uri(self) -> str:
        """The normalised text form (``spotify:track:ID``, ``youtube:ID``, ``url:...``)."""
        if self.kind is SourceKind.SPOTIFY:
            return f"spotify:{self.ref}"
        if self.kind is SourceKind.YOUTUBE:
            return f"youtube:{self.ref}" + (f"?list={self.playlist}" if self.playlist else "")
        return f"url:{self.ref}"

    @property
    def description(self) -> str:
        """A short German description for the interface."""
        if self.kind is SourceKind.SPOTIFY:
            labels = {
                "track": "Spotify-Titel",
                "album": "Spotify-Album",
                "playlist": "Spotify-Playlist",
                "artist": "Spotify-Künstler",
                "episode": "Spotify-Folge",
                "show": "Spotify-Podcast",
            }
            return labels.get(self.ref.split(":")[0], "Spotify")
        if self.kind is SourceKind.YOUTUBE:
            return "YouTube-Video" + (" mit Playlist" if self.playlist else "")
        return "Stream-Adresse"

    @property
    def youtube_url(self) -> str:
        """The canonical YouTube address (only for ``kind == YOUTUBE``)."""
        suffix = f"&list={self.playlist}" if self.playlist else ""
        return f"https://www.youtube.com/watch?v={self.ref}{suffix}"


def _reject(reason: str) -> ValidationError:
    return ValidationError(
        f"Unrecognised music source: {reason}",
        user_message=(
            f"{reason} Erkannt werden Spotify-Links (open.spotify.com/track/…), YouTube- und "
            "YouTube-Music-Links (…/watch?v=…) und Stream-Adressen (https://…)."
        ),
    )


def parse_source(text: str) -> MusicSource:
    """Recognise a pasted link.

    Raises:
        ValidationError: With a German explanation if the text is not a recognised source.
    """
    if not isinstance(text, str) or not text.strip():
        raise _reject("Bitte fügen Sie einen Link ein.")
    raw = text.strip()
    if len(raw) > MAX_LENGTH or any(c.isspace() or ord(c) < 32 for c in raw):
        raise _reject("Der Link enthält Leerzeichen oder Sonderzeichen oder ist zu lang.")
    if raw.startswith("spotify:"):
        return _spotify_uri(raw, raw)
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
    except ValueError:
        raise _reject("Der Link ist ungültig.") from None
    if parts.scheme not in ("http", "https") or not host:
        raise _reject("Das ist kein Link (er muss mit https:// beginnen).")
    if parts.username is not None or parts.password is not None:
        raise _reject("Benutzername und Passwort gehören nicht in einen Link.")
    if host == "open.spotify.com":
        segments = [s for s in parts.path.split("/") if s]
        if segments and segments[0].startswith("intl-"):  # open.spotify.com/intl-de/track/ID
            segments = segments[1:]
        if len(segments) >= 2 and segments[0] in SPOTIFY_TYPES:
            return _spotify_uri(f"spotify:{segments[0]}:{segments[1]}", raw)
        raise _reject("Dieser Spotify-Link zeigt auf keinen Titel, kein Album und keine Playlist.")
    if host in ("music.youtube.com", "www.youtube.com", "youtube.com", "m.youtube.com"):
        return _youtube(parse_qs(parts.query), raw)
    if host == "youtu.be":
        video = parts.path.strip("/")
        return _youtube({"v": [video], **parse_qs(parts.query)}, raw)
    return MusicSource(SourceKind.URL, raw, original=raw)


def _spotify_uri(uri: str, original: str) -> MusicSource:
    pieces = uri.split(":")
    if len(pieces) != 3 or pieces[1] not in SPOTIFY_TYPES or not _SPOTIFY_ID.match(pieces[2]):
        raise _reject("Dieser Spotify-Verweis ist ungültig.")
    return MusicSource(SourceKind.SPOTIFY, f"{pieces[1]}:{pieces[2]}", original=original)


def _youtube(query: dict[str, list[str]], original: str) -> MusicSource:
    video = (query.get("v") or [""])[0]
    if not _YOUTUBE_ID.match(video):
        raise _reject("In diesem YouTube-Link fehlt ein gültiges Video (v=…).")
    playlist = (query.get("list") or [""])[0] or None
    if playlist is not None and not _YOUTUBE_LIST.match(playlist):
        playlist = None  # a malformed list is ignored, the video itself is still valid
    return MusicSource(SourceKind.YOUTUBE, video, playlist, original)
