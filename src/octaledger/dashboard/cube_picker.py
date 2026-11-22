"""A clickable cube picture (Streamlit custom component v2, no build step, no external source).

The picture itself comes from :func:`octaledger.dashboard.cube.cube_svg`. This component only puts
that SVG on the page and turns a click into "face N was clicked": the click position is converted
to a face with the same formula as :func:`octaledger.dashboard.cube.face_at` (face 1 at the top,
then clockwise, eight wedges of 45 degrees, the centre circle and the outside do not count).

The component is **an addition, never the only way**: the inspector always shows an equivalent row
of buttons 1 to 8 (keyboard, screen readers, tests, and Streamlit versions without components v2).
If the component cannot be created, :func:`picker_available` is ``False`` and the page simply shows
the plain picture.

Security: the HTML/JS below is fixed text of this module. The only dynamic content is the SVG that
``cube_svg`` builds with every user text escaped; it is set as the component's data.
"""

from __future__ import annotations

import logging
from functools import cache
from typing import Any, Final

import streamlit as st

logger = logging.getLogger(__name__)

NAME: Final = "octaledger_cube_picker"

_HTML: Final = (
    '<div id="cube" role="group" aria-label="Würfelbild: Klicken Sie auf eine Seite"></div>'
)

#: Mirrors ``cube.face_at`` (keep both in step; the Python one is unit-tested).
_JS: Final = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const box = parentElement.querySelector('#cube');
  box.innerHTML = data.svg;
  const svg = box.querySelector('svg');
  if (!svg) { return; }
  svg.style.cursor = 'pointer';
  svg.onclick = (event) => {
    const rect = svg.getBoundingClientRect();
    const size = data.size;
    const x = ((event.clientX - rect.left) / rect.width) * size - size / 2;
    const y = ((event.clientY - rect.top) / rect.height) * size - size / 2;
    const distance = Math.hypot(x, y);
    if (distance < data.inner || distance > data.outer) { return; }
    let degrees = (Math.atan2(y, x) * 180) / Math.PI + 90 + 22.5;
    degrees = ((degrees % 360) + 360) % 360;
    setTriggerValue('face', Math.floor(degrees / 45) + 1);
  };
}
"""


@cache
def _component() -> Any | None:
    """Create the component once (``None`` when this Streamlit has no components v2)."""
    try:
        return st.components.v2.component(NAME, html=_HTML, js=_JS)
    except Exception:  # noqa: BLE001 - any failure means "no clickable picture", not a crash
        logger.warning("Clickable cube picture not available; showing the plain picture")
        return None


def picker_available() -> bool:
    """Whether the clickable picture can be used with the installed Streamlit."""
    return _component() is not None


def cube_picker(svg: str, *, key: str, size: int, inner: float, outer: float) -> int | None:
    """Show the picture and return the face clicked **in this run** (else ``None``).

    Args:
        svg: The picture (from ``cube_svg``).
        key: Unique widget key.
        size: Side of the SVG's coordinate system.
        inner: Radius of the centre circle (clicks inside are ignored).
        outer: Radius of the faces (clicks outside are ignored).
    """
    component = _component()
    if component is None:
        st.markdown(svg, unsafe_allow_html=True)
        return None
    result = component(
        key=key,
        data={"svg": svg, "size": size, "inner": inner, "outer": outer},
        on_face_change=lambda: None,
    )
    face = getattr(result, "face", None)
    return int(face) if isinstance(face, int) and 1 <= face <= 8 else None
