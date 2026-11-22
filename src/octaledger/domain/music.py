"""The rules of the music mode: what a turn of the cube does (pure decision).

Music is **state**, not a one-off action: something plays until something else plays or the face
is left. The rules therefore differ from the control mode:

* a face with a title **replaces** whatever plays; if the title needs *another target* than the
  one that plays now, that target is stopped first (otherwise two sources would play at once);
* a face **without** a title stops the music like the holder does (a "silence face");
* the **holder** (no face up, the neutral value) stops the music - or pauses it, as chosen - on
  **every target the cube uses**, but only if something plays;
* a lost connection does nothing at once (the housekeeper stops after the grace period);
* the first value after connecting does nothing, except that a cube resting in its holder while
  music plays stops it.

:func:`decide` knows nothing about databases or adapters; it returns commands that the
application layer turns into queued jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from octaledger.core.errors import ValidationError

BASE_STOP: Final = "stop"
BASE_PAUSE: Final = "pause"
MAX_STOP_DELAY_MS: Final = 60_000


class CommandKind(StrEnum):
    """What a command asks a target to do."""

    PLAY = "play"
    STOP = "stop"
    PAUSE = "pause"


@dataclass(frozen=True, slots=True)
class MusicSettings:
    """Per-cube behaviour of the music mode.

    Attributes:
        base_action: ``stop`` (default) or ``pause`` when the cube rests in its holder.
        stop_delay_ms: Wait before stopping in the holder (0 = at once).
        default_volume: Volume in percent that a new title starts with.
    """

    base_action: str = BASE_STOP
    stop_delay_ms: int = 0
    default_volume: int = 50

    def __post_init__(self) -> None:
        """Validate the three values."""
        if self.base_action not in (BASE_STOP, BASE_PAUSE):
            raise ValidationError(
                f"Invalid base action {self.base_action!r}",
                user_message="In der Halterung kann die Musik nur gestoppt oder pausiert werden.",
            )
        if (
            isinstance(self.stop_delay_ms, bool)
            or not isinstance(self.stop_delay_ms, int)
            or not 0 <= self.stop_delay_ms <= MAX_STOP_DELAY_MS
        ):
            raise ValidationError(
                f"Invalid stop delay {self.stop_delay_ms!r}",
                user_message="Die Verzögerung muss zwischen 0 und 60 Sekunden liegen.",
            )
        if (
            isinstance(self.default_volume, bool)
            or not isinstance(self.default_volume, int)
            or not 0 <= self.default_volume <= 100
        ):
            raise ValidationError(
                f"Invalid volume {self.default_volume!r}",
                user_message="Die Lautstärke muss zwischen 0 und 100 Prozent liegen.",
            )


@dataclass(frozen=True, slots=True)
class NowPlaying:
    """What plays at the moment (the stored "music_now" of a cube)."""

    face: int
    label: str
    integration_id: str
    since: str
    #: The target (connection and, for Home Assistant, the media player); see
    #: ``music_state.music_target``. Empty in states written before AP-55.
    target: str = ""


@dataclass(frozen=True, slots=True)
class MusicCommand:
    """One thing to do: play the title of a face, or stop/pause a target."""

    kind: CommandKind
    #: The connection (target) the command goes to.
    integration_id: str
    #: The face whose title is played (``None`` for stop/pause).
    face: int | None = None
    delay_ms: int = 0


def decide(
    event: str,
    value: int | None,
    playing: NowPlaying | None,
    titles: dict[int, str],
    targets: frozenset[str],
    settings: MusicSettings,
) -> list[MusicCommand]:
    """Decide what an event does (see the module docstring for the rules).

    Args:
        event: ``face_change``, ``neutral`` or ``baseline`` (anything else does nothing).
        value: The face (``1..8``) or ``0`` for the holder.
        playing: What plays now, or ``None``.
        titles: ``face -> integration id`` for the faces that have a title.
        targets: Every connection the cube uses for music (what the holder has to stop).
        settings: The behaviour of this cube.

    Returns:
        The commands in the order they must be sent (stops before the play).
    """
    release = CommandKind.PAUSE if settings.base_action == BASE_PAUSE else CommandKind.STOP
    if event == "neutral" or (event == "baseline" and value == 0):
        return _release(playing, targets, release, settings.stop_delay_ms)
    if event != "face_change" or value is None:
        return []
    target = titles.get(value)
    if target is None:  # a face without a title is a "silence face"
        return _release(playing, targets, CommandKind.STOP, 0)
    commands: list[MusicCommand] = []
    if playing is not None and playing.integration_id != target:
        commands.append(MusicCommand(CommandKind.STOP, playing.integration_id))
    commands.append(MusicCommand(CommandKind.PLAY, target, face=value))
    return commands


def _release(
    playing: NowPlaying | None, targets: frozenset[str], kind: CommandKind, delay_ms: int
) -> list[MusicCommand]:
    """Stop (or pause) every used target, but only if something plays at all."""
    if playing is None:
        return []
    return [MusicCommand(kind, target, delay_ms=delay_ms) for target in sorted(targets)]
