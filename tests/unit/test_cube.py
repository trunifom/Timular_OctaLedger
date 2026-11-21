"""Tests for the schematic cube picture (pure SVG generation, no Streamlit)."""

import re

import pytest

from octaledger.core.settings import Theme
from octaledger.dashboard.cube import FaceLabel, cube_svg, readable_on
from octaledger.dashboard.theme import contrast_ratio
from octaledger.domain.models import DEFAULT_COLOR

PALETTE_COLOURS = ("#2A9D8F", "#E76F51", "#264653", "#F4A261", "#FFFFFF", "#000000", DEFAULT_COLOR)


def polygons(svg: str) -> list[str]:
    return re.findall(r"<polygon [^>]*>", svg)


@pytest.mark.parametrize("theme", list(Theme))
def test_eight_faces_numbered_and_unassigned_faces_are_marked_free(theme: Theme) -> None:
    svg = cube_svg(theme, {})
    assert len(polygons(svg)) == 8
    for number in range(1, 9):
        assert f">{number}</text>" in svg
    assert svg.count(">frei</text>") == 8


def test_names_and_colours_of_assigned_faces_are_shown() -> None:
    svg = cube_svg(Theme.LIGHT, {2: FaceLabel("Meeting", "#2A9D8F")})
    assert "Meeting" in svg and 'fill="#2A9D8F"' in svg
    assert svg.count(">frei</text>") == 7


def test_the_face_that_is_up_has_a_marker_and_a_thick_outline_not_only_a_colour() -> None:
    svg = cube_svg(Theme.LIGHT, {}, up=3)
    assert svg.count("▲") == 1
    assert sum('stroke-width="7"' in p for p in polygons(svg)) == 1
    assert "–" not in svg  # the centre shows the face number, not the "unknown" dash
    assert cube_svg(Theme.LIGHT, {}).count("▲") == 0


def test_a_pending_face_is_dashed_and_differs_from_the_accepted_one() -> None:
    svg = cube_svg(Theme.DARK, {}, up=1, pending=4)
    dashed = [p for p in polygons(svg) if "stroke-dasharray" in p]
    assert len(dashed) == 1 and 'stroke-width="5"' in dashed[0]


def test_a_selected_face_gets_the_accent_ring() -> None:
    svg = cube_svg(Theme.LIGHT, {}, selected=5)
    accent = [p for p in polygons(svg) if 'stroke-width="7"' in p]
    assert len(accent) == 1


def test_user_text_is_escaped_so_it_cannot_inject_markup() -> None:
    svg = cube_svg(Theme.LIGHT, {1: FaceLabel('<script>alert("x")</script>', "#2A9D8F")})
    assert "<script>" not in svg and "&lt;script&gt;" in svg
    assert 'aria-label="a &quot;b&quot;"' in cube_svg(Theme.LIGHT, {}, caption='a "b"')


def test_long_names_are_shortened() -> None:
    svg = cube_svg(Theme.LIGHT, {1: FaceLabel("Ein sehr langer Name der nicht passt", None)})
    assert "…" in svg and "nicht passt" not in svg


@pytest.mark.parametrize("colour", PALETTE_COLOURS)
def test_label_text_is_readable_on_every_activity_colour(colour: str) -> None:
    """Large bold numbers need 3:1 (WCAG); the outline in the opposite colour covers the rest."""
    assert contrast_ratio(readable_on(colour), colour) >= 3.0
    svg = cube_svg(Theme.LIGHT, {1: FaceLabel("Name", colour)})
    assert svg.count('paint-order="stroke"') >= 3  # number, name and centre labels are outlined
