"""A simple, schematic picture of the eight-sided tracker (inline SVG, no external assets).

Responsibility
--------------
Turn "which face is up, which one is waiting for confirmation and what is assigned to each face"
into one SVG string that the live view and the setup assistant show. Pure functions only: no
Streamlit, no network, so the output is unit-testable and identical in every page.

The picture is **schematic** on purpose. The tracker is an octahedron; seen from above it is drawn
as an octagon with eight wedges. The numbers are the *technical* face numbers the device reports
(1-8), not a claim about where a number is printed on the hardware - the calibration step is what
ties a number to an activity. Colour is never the only signal: the face that is up gets a thick
outline *and* a marker, the face that is still being confirmed a dashed outline.

Security: every user-provided text (activity names) is escaped before it enters the SVG.
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from octaledger.core.settings import Theme
from octaledger.dashboard.theme import PALETTES, contrast_ratio

#: Face numbers in drawing order: face 1 at the top, then clockwise.
FACE_NUMBERS: Final = tuple(range(1, 9))
_SIZE: Final = 340
_CENTER: Final = _SIZE / 2
_RADIUS: Final = 160.0
_MAX_NAME: Final = 10
#: Public geometry (the clickable picture needs it): side of the drawing, radius of the centre
#: circle and of the faces.
SIZE: Final = _SIZE
INNER_RADIUS: Final = 24.0
OUTER_RADIUS: Final = _RADIUS + 5.0


@dataclass(frozen=True, slots=True)
class FaceLabel:
    """What the picture shows for one face (``name`` is ``None`` for an unassigned face)."""

    name: str | None = None
    color: str | None = None


def _point(angle_deg: float, radius: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    return _CENTER + radius * math.cos(angle), _CENTER + radius * math.sin(angle)


def _shorten(name: str) -> str:
    return name if len(name) <= _MAX_NAME else name[: _MAX_NAME - 1] + "…"


_DARK_TEXT: Final = "#111827"
_LIGHT_TEXT: Final = "#FFFFFF"


def readable_on(background: str) -> str:
    """Pick the text colour (dark or light) with the better contrast on ``background``."""
    dark = contrast_ratio(_DARK_TEXT, background)
    return _DARK_TEXT if dark >= contrast_ratio(_LIGHT_TEXT, background) else _LIGHT_TEXT


def _halo(text_color: str) -> str:
    """SVG attributes that outline text in the opposite colour.

    On a mid-tone fill neither dark nor light text reaches 4.5:1 (the default activity colour
    gives about 4.4:1), so the outline keeps the glyphs legible on *any* colour a user picks.
    """
    halo = _LIGHT_TEXT if text_color == _DARK_TEXT else _DARK_TEXT
    return f'paint-order="stroke" stroke="{halo}" stroke-width="3" stroke-linejoin="round"'


def face_at(dx: float, dy: float) -> int | None:
    """The face under a point, given relative to the centre of the drawing (``None`` = no face).

    Face 1 is at the top, the faces follow clockwise, each is a wedge of 45 degrees. The centre
    circle and everything outside the faces count as "no face". The click handler of
    ``cube_picker.py`` uses the same formula in JavaScript.
    """
    distance = math.hypot(dx, dy)
    if distance < INNER_RADIUS or distance > OUTER_RADIUS:
        return None
    degrees = math.degrees(math.atan2(dy, dx)) + 90 + 22.5
    return int((degrees % 360) // 45) + 1


def cube_svg(
    theme: Theme,
    faces: Mapping[int, FaceLabel],
    *,
    up: int | None = None,
    pending: int | None = None,
    selected: int | None = None,
    caption: str = "Würfel von oben",
) -> str:
    """Return the SVG of the cube.

    Args:
        theme: Light or dark colours.
        faces: Label per face number 1-8 (missing faces count as unassigned).
        up: The face that is up and accepted (thick outline and marker), or ``None``.
        pending: A face seen on the radio but not yet confirmed (dashed outline), or ``None``.
        selected: A face the user picked in the setup assistant (accent ring), or ``None``.
        caption: Accessible description of the picture.
    """
    palette = PALETTES[theme]
    parts: list[str] = [
        f'<svg viewBox="0 0 {_SIZE} {_SIZE}" role="img" aria-label="{html.escape(caption)}" '
        'xmlns="http://www.w3.org/2000/svg" style="max-width:340px;width:100%;height:auto;'
        'display:block;margin:0 auto">',
        f"<title>{html.escape(caption)}</title>",
    ]
    highlighted: list[str] = []  # drawn last so a neighbour never covers their outline
    texts: list[str] = []
    for number in FACE_NUMBERS:
        centre_angle = -90 + 45 * (number - 1)
        corners = [
            (_CENTER, _CENTER),
            _point(centre_angle - 22.5, _RADIUS),
            _point(centre_angle + 22.5, _RADIUS),
        ]
        label = faces.get(number, FaceLabel())
        fill = label.color or palette.surface
        text_color = readable_on(fill)
        stroke, width, dash = palette.border, 2, ""
        special = number in (up, pending, selected)
        if number == up:
            stroke, width = palette.text, 7
        elif number == pending:
            stroke, width, dash = palette.text, 5, ' stroke-dasharray="9 7"'
        if number == selected:
            stroke, width = palette.primary, 7
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in corners)
        polygon = (
            f'<polygon points="{points}" fill="{html.escape(fill)}" stroke="{stroke}" '
            f'stroke-width="{width}" stroke-linejoin="round"{dash}/>'
        )
        (highlighted if special else parts).append(polygon)

        # The number sits inside the wedge; the name goes right below it and the "up" marker
        # right above it. Stacking them (instead of pushing the name to the rim) keeps every
        # label inside its wedge, also on the left and right faces where a rim label is cut off.
        x, y = _point(centre_angle, _RADIUS * (0.68 if number in (1, 5) else 0.6))
        halo = _halo(text_color)
        texts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="central" '
            f'font-size="30" font-weight="700" fill="{text_color}" {halo}>{number}</text>'
        )
        shown = _shorten(label.name) if label.name else "frei"
        faded = "" if label.name else ' opacity="0.75"'
        texts.append(
            f'<text x="{x:.1f}" y="{y + 24:.1f}" text-anchor="middle" dominant-baseline="central" '
            f'font-size="11" font-weight="600" fill="{text_color}" {halo}{faded}>'
            f"{html.escape(shown)}</text>"
        )
        if number == up:  # a marker that does not depend on colour
            texts.append(
                f'<text x="{x:.1f}" y="{y - 26:.1f}" text-anchor="middle" '
                f'dominant-baseline="central" font-size="18" fill="{text_color}" {halo}>▲</text>'
            )
    parts += highlighted
    parts += texts
    parts.append(
        f'<circle cx="{_CENTER}" cy="{_CENTER}" r="24" fill="{palette.background}" '
        f'stroke="{palette.border}" stroke-width="2"/>'
    )
    centre_text = "–" if up is None else str(up)
    parts.append(
        f'<text x="{_CENTER}" y="{_CENTER}" text-anchor="middle" dominant-baseline="central" '
        f'font-size="24" font-weight="700" fill="{palette.text}">{centre_text}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
