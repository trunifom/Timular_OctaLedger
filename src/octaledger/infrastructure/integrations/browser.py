"""Browser player adapter: the "player in the app" for YouTube and YouTube Music links.

Responsibility
--------------
The agent cannot remote control a web browser, and YouTube Music has no official interface. What is
allowed and common is to **embed** the YouTube player (IFrame API) in a web page. This adapter
therefore has **no network target**: it only keeps the *wanted state* (what should play, how loud,
or stopped) in memory. The dashboard page "Musik-Player" polls that state and draws the embedded
player - **so music plays only while that page is open in a browser**.

Rules
-----
* ``execute`` only changes the in-memory state (thread-safe); it never touches the network.
* Only YouTube video and playlist ids of the exact shape ``[A-Za-z0-9_-]`` are accepted, so they can
  be embedded safely.
* Every change increases ``nonce`` so the page can tell a repeated play of the same title from no
  change.

Honest limits: whether the browser allows autoplay, whether a video may be embedded and how the
page behaves in a real browser are **not verified** here (``[HW]``). The state is lost when the
agent restarts (nothing keeps playing then anyway).
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Final

from octaledger.core.errors import ValidationError
from octaledger.domain.music_source import MusicSource, SourceKind
from octaledger.domain.playlist import REPEAT_TEXT, Repeat, parse_repeat
from octaledger.infrastructure.integrations.base import (
    ActionSpec,
    Adapter,
    AdapterSpec,
    FieldSpec,
)

logger = logging.getLogger(__name__)

VIDEO_ID: Final = re.compile(r"^[A-Za-z0-9_-]{11}$")
LIST_ID: Final = re.compile(r"^[A-Za-z0-9_-]{10,60}$")

SETUP_GUIDE: Final = """\
**Wofür:** Spielt YouTube- und YouTube-Music-Links in einem **Player im Dashboard** ab (YouTube Music hat keine offizielle Schnittstelle).

**Wichtig – bitte vorher lesen:**
- Die Musik spielt **nur, solange die Seite „Musik-Player“ in einem Browser geöffnet ist.** Schließen Sie die Seite, ist die Musik weg.
- Der Player lädt Inhalte von **youtube.com** (Google erhält dabei Anfragen). Deshalb wird er erst geladen, wenn Sie auf der Seite „Musik-Player“ ausdrücklich zustimmen.
- Nicht jedes Video darf eingebettet werden; dann zeigt die Seite „nicht einbettbar“.
- Browser blockieren Autoplay manchmal. Drücken Sie einmal „Wiedergabe freischalten“ auf der Seite.

**Einrichtung:** Verbindung speichern (keine Angaben nötig), im Musik-Modus als Ziel wählen, Seite **Musik-Player** öffnen und offen lassen.
"""  # noqa: E501


@dataclass(frozen=True, slots=True)
class PlayerState:
    """The wanted state of the browser player."""

    playing: bool = False
    video_id: str = ""
    list_id: str = ""
    volume: int = 50
    nonce: int = 0
    #: ``off``, ``all`` or ``one``. A playlist can only repeat as a whole (``one`` acts like
    #: ``all`` there); a single video repeats itself.
    repeat: str = "off"
    shuffle: bool = False


class BrowserAdapter(Adapter):
    """Keeps the state the "Musik-Player" page draws (see the module docstring)."""

    spec = AdapterSpec(
        kind="browser",
        title="Player in der App (YouTube)",
        description=(
            "Spielt YouTube- und YouTube-Music-Links in einem Player auf der Seite „Musik-Player“. "
            "Die Musik läuft nur, solange diese Seite im Browser offen ist."
        ),
        setup_guide=SETUP_GUIDE,
        config_fields=(),
        actions=(
            ActionSpec(
                "browser_play",
                "Im Player abspielen",
                "Lässt den Player der App ein YouTube-Video oder eine ganze Playlist abspielen.",
                fields=(
                    FieldSpec(
                        "video_id",
                        "YouTube-Video",
                        help="Die 11 Zeichen lange Video-Kennung aus dem Link (…watch?v=KENNUNG). "
                        "Leer lassen, wenn eine ganze Playlist läuft.",
                    ),
                    FieldSpec(
                        "list_id",
                        "Playlist (optional)",
                        help="Die Kennung nach list= im Link. Mit Video: die Playlist beginnt bei "
                        "diesem Video; ohne Video: sie beginnt vorn (oder zufällig).",
                    ),
                    FieldSpec(
                        "volume",
                        "Lautstärke in %",
                        kind="int",
                        default=50,
                        minimum=0,
                        maximum=100,
                        help="0 bis 100 Prozent.",
                    ),
                    FieldSpec(
                        "repeat",
                        "Wiederholen",
                        kind="choice",
                        choices=tuple((key, text) for key, text in REPEAT_TEXT.items()),
                        default=Repeat.OFF.value,
                        help="Einmal abspielen oder wiederholen. Bei einer Playlist wird immer die "
                        "ganze Playlist wiederholt; „einen Titel endlos“ gilt für ein einzelnes "
                        "Video.",
                    ),
                    FieldSpec(
                        "shuffle",
                        "Zufällige Reihenfolge",
                        kind="bool",
                        default=False,
                        help="Mischt die Titel einer Playlist.",
                    ),
                ),
                idempotent=True,
                capability="music",
            ),
            ActionSpec(
                "browser_stop",
                "Player anhalten",
                "Hält den Player der App an.",
                idempotent=True,
                capability="music",
            ),
        ),
    )

    def __init__(self) -> None:
        """Create the adapter with an empty (stopped) state."""
        self._lock = threading.Lock()
        self._state = PlayerState()

    def state(self) -> dict[str, Any]:
        """The current wanted state (a copy)."""
        with self._lock:
            return asdict(self._state)

    # ----------------------------------------------------------------------- music

    def music_play_params(
        self, source: MusicSource, volume: int, options: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        """One play action for a YouTube source (others are refused with an explanation)."""
        if source.kind is not SourceKind.YOUTUBE:
            raise ValidationError(
                "The browser player plays YouTube only",
                user_message="Der Player in der App spielt nur YouTube- und YouTube-Music-Links.",
            )
        params: dict[str, Any] = {
            "action": "browser_play",
            "video_id": source.ref,  # empty for a link to a whole playlist
            "volume": volume,
            "repeat": parse_repeat(options.get("repeat", Repeat.OFF.value)).value,
            "shuffle": str(options.get("shuffle", "")).lower() in ("1", "true", "yes", "ja"),
        }
        if source.playlist:
            params["list_id"] = source.playlist
        return [params]

    def music_stop_params(
        self, play_params: Mapping[str, Any], pause: bool = False
    ) -> dict[str, Any] | None:
        """Stopping and pausing are the same here."""
        return {"action": "browser_stop"}

    # ------------------------------------------------------------------ operations

    def validate_action(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Validate the fields and additionally the shape of the YouTube ids."""
        cleaned = super().validate_action(params)
        video = cleaned.get("video_id") or None
        if cleaned.get("action") == "browser_play" and not video and not cleaned.get("list_id"):
            raise ValidationError(
                "A video or a playlist is needed",
                user_message="Es fehlt ein YouTube-Video oder eine Playlist.",
            )
        if video is not None and not VIDEO_ID.match(str(video)):
            raise ValidationError(
                "Invalid video id", user_message="Die Video-Kennung ist ungültig."
            )
        if "repeat" in cleaned:
            cleaned["repeat"] = parse_repeat(cleaned["repeat"]).value
        playlist = cleaned.get("list_id")
        if playlist is not None and not LIST_ID.match(str(playlist)):
            raise ValidationError(
                "Invalid playlist id", user_message="Die Playlist-Kennung ist ungültig."
            )
        return cleaned

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """Nothing to reach; always succeeds."""
        return (
            "Der Player in der App braucht keine Verbindung. Öffnen Sie die Seite „Musik-Player“ "
            "und lassen Sie sie geöffnet."
        )

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Change the wanted state; the page picks it up within a second."""
        action = str(params.get("action"))
        with self._lock:
            nonce = self._state.nonce + 1
            if action == "browser_play":
                self._state = PlayerState(
                    True,
                    str(params.get("video_id") or ""),
                    str(params.get("list_id") or ""),
                    int(params.get("volume", 50)),
                    nonce,
                    parse_repeat(params.get("repeat", Repeat.OFF.value)).value,
                    bool(params.get("shuffle", False)),
                )
                return "Player in der App gestartet (nur sichtbar, wenn die Seite offen ist)."
            if action == "browser_stop":
                self._state = PlayerState(False, volume=self._state.volume, nonce=nonce)
                return "Player in der App angehalten."
        raise ValidationError(
            f"Unknown browser action {action!r}",
            user_message="Diese Aktion kennt der Player nicht.",
        )
