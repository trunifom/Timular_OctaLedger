"""The identity of a cube: number and colour (pure, no I/O).

Several cubes must be told apart at a glance, and **never by colour alone** (colour-blind users,
printed pages, screen readers). Every cube therefore has

* a **number** (``1``, ``2`` ...): the order in which the cubes were registered (stable, because it
  follows the registration time, not the name);
* a **colour** from a fixed palette of eight clearly different tones (the "Okabe-Ito" style
  palette plus two more), assigned automatically so that two cubes never share a colour as long as
  a free one exists; the user can change it.

The interface always shows colour **together with** number and name, for example
``● ② Regenbogen``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

#: ``(colour, German name)``; chosen for contrast on light and dark backgrounds.
PALETTE: Final[tuple[tuple[str, str], ...]] = (
    ("#0072B2", "Blau"),
    ("#D55E00", "Orange-Rot"),
    ("#009E73", "Grün"),
    ("#CC79A7", "Rosa"),
    ("#E69F00", "Gelb-Orange"),
    ("#56B4E9", "Hellblau"),
    ("#7B3294", "Violett"),
    ("#A6192E", "Dunkelrot"),
)

#: Circled digits for numbers 1..20, used as a compact badge next to the colour dot.
_CIRCLED: Final = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def color_name(color: str) -> str:
    """The German name of a palette colour (``"Eigene Farbe"`` for anything else)."""
    wanted = color.upper()
    return next((name for value, name in PALETTE if value == wanted), "Eigene Farbe")


def next_free_color(used: Iterable[str]) -> str:
    """The first palette colour nobody uses yet (starts over when all eight are taken)."""
    taken = {c.upper() for c in used if c}
    for value, _ in PALETTE:
        if value not in taken:
            return value
    return PALETTE[len(taken) % len(PALETTE)][0]


def numbering(created: Sequence[tuple[str, str]]) -> dict[str, int]:
    """Number cubes by registration time: ``{device id: 1, 2, ...}``.

    Args:
        created: ``(device id, registration time as ISO text)`` for every cube; ties are broken by
            the id so the numbering is deterministic.
    """
    ordered = sorted(created, key=lambda item: (item[1], item[0]))
    return {device_id: index for index, (device_id, _) in enumerate(ordered, start=1)}


def badge(number: int) -> str:
    """The compact number badge (``②``); numbers above 20 fall back to ``(21)``."""
    return _CIRCLED[number - 1] if 1 <= number <= len(_CIRCLED) else f"({number})"
