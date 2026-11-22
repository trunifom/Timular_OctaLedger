"""The rules of a play queue: order, shuffle and repeat (pure, no audio, no files).

A *queue* is a list of tracks played in an *order* (a permutation of their positions). Three
questions are answered here, so the audio worker only has to ask:

* in which order are the tracks played (:func:`play_order`, with an optional shuffle that is
  reproducible because the caller passes the seed);
* which position follows when a track **ends** or the user presses **next** (:func:`following`);
* which position the **previous** button goes to (:func:`preceding`).

Repeat modes: ``off`` plays the queue once and stops, ``all`` starts over after the last track,
``one`` repeats the current track (an endless loop until somebody stops it). The user's own
*next* and *previous* buttons always move on, also in ``one`` mode (the repeat then applies to
the new track), because a button that does nothing would look broken.
"""

from __future__ import annotations

import random
from enum import StrEnum

from octaledger.core.errors import ValidationError


class Repeat(StrEnum):
    """What happens at the end of a track or of the whole queue."""

    OFF = "off"
    ALL = "all"
    ONE = "one"


REPEAT_TEXT: dict[str, str] = {
    Repeat.OFF.value: "einmal abspielen",
    Repeat.ALL.value: "alles wiederholen",
    Repeat.ONE.value: "einen Titel endlos wiederholen",
}


def parse_repeat(value: object) -> Repeat:
    """Turn text into a :class:`Repeat`.

    Raises:
        ValidationError: For anything but ``off``, ``all`` or ``one``.
    """
    try:
        return Repeat(str(value))
    except ValueError:
        raise ValidationError(
            f"Unknown repeat mode {value!r}",
            user_message="Wiederholen ist „einmal“, „alles“ oder „einen Titel“.",
        ) from None


def play_order(count: int, *, shuffle: bool, seed: int = 0, first: int | None = None) -> list[int]:
    """The order in which the tracks ``0..count-1`` are played.

    Args:
        count: Number of tracks.
        shuffle: Mix the order.
        seed: Seed of the mix (the same seed gives the same order).
        first: With a shuffle, this track is moved to the front (the one the user picked).

    Returns:
        A permutation of ``range(count)`` (empty for ``count <= 0``).
    """
    order = list(range(max(count, 0)))
    if shuffle and len(order) > 1:
        random.Random(seed).shuffle(order)  # noqa: S311 - a play order, not a secret
        if first is not None and first in order:
            order.remove(first)
            order.insert(0, first)
    return order


def following(position: int, count: int, repeat: Repeat, *, by_user: bool = False) -> int | None:
    """The position after ``position``, or ``None`` when playback is over.

    Args:
        position: Current position in the order.
        count: Length of the order.
        repeat: The repeat mode.
        by_user: ``True`` for the *next* button, ``False`` when the track ended by itself.
    """
    if count <= 0:
        return None
    if repeat is Repeat.ONE and not by_user:
        return position
    if position + 1 < count:
        return position + 1
    return 0 if repeat is not Repeat.OFF else None


def preceding(position: int, count: int, repeat: Repeat) -> int:
    """The position the *previous* button goes to (the first track starts over)."""
    if count <= 0:
        return 0
    if position > 0:
        return position - 1
    return count - 1 if repeat is Repeat.ALL else 0
