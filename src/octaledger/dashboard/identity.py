"""Which cube am I looking at? One selection for every page, always shown with colour **and** text.

With several cubes the most important question of the interface is "which cube is this?". This
module answers it the same way everywhere:

* a **cube label** ``● ② Regenbogen``: colour dot, number badge and name (never colour alone);
* **one selection** for the whole session (``st.session_state["cube_selected"]``): the selector in
  the sidebar, the pages "Seiten zuordnen", "Würfel live", "Würfel-Inspektor" and the banner all
  use it, so the cube chosen on one page is still the one on the next;
* a **banner** at the top of every cube-related page: "Sie bearbeiten: ● ② Regenbogen · Musik".

Not to be confused with the *active time cube* (⭐): that is the cube that records time (a setting
of the app), while the selection only says which cube the interface shows right now.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from typing import Any, Final

import streamlit as st

SELECTED_KEY: Final = "cube_selected"
MODE_TEXT: Final = {"time": "Zeit", "control": "Smarthome", "music": "Musik"}
MODE_ICON: Final = {"time": "⏱", "control": "🎛", "music": "🎵"}

DEFAULT_COLOR: Final = "#808080"


def mode_text(device: dict[str, Any]) -> str:
    """The German name of the area of a cube (``Zeit``, ``Smarthome`` or ``Musik``)."""
    return MODE_TEXT.get(str(device.get("mode", "time")), "Zeit")


def cube_label(device: dict[str, Any]) -> str:
    """Plain text label with number badge and name (for lists), e.g. ``② Regenbogen``."""
    return f"{device.get('badge', '')} {device['alias']}".strip()


def cube_html(device: dict[str, Any]) -> str:
    """HTML of the label: colour dot, number badge and name (all escaped)."""
    color = html.escape(str(device.get("color") or DEFAULT_COLOR), quote=True)
    return (
        f'<span class="ol-dot" style="background:{color}"></span>'
        f"<b>{html.escape(str(device.get('badge', '')))} {html.escape(device['alias'])}</b>"
    )


def selected_cube(devices: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The cube chosen for this session (falls back to the active time cube, else the first).

    The choice is kept in the session; a cube that no longer exists is replaced.
    """
    if not devices:
        st.session_state.pop(SELECTED_KEY, None)
        return None
    chosen = next((d for d in devices if d["id"] == st.session_state.get(SELECTED_KEY)), None)
    if chosen is None:
        chosen = next((d for d in devices if d["is_active"]), devices[0])
        st.session_state[SELECTED_KEY] = chosen["id"]
    return dict(chosen)


def sidebar_selector(devices: Sequence[dict[str, Any]]) -> None:
    """Draw the cube selector (call inside ``with st.sidebar``).

    One cube: only its label is shown. Several: a selector, so switching is one click everywhere.
    """
    cube = selected_cube(devices)
    if cube is None:
        return
    st.markdown('<div class="ol-nav-group">Ausgewählter Würfel</div>', unsafe_allow_html=True)
    if len(devices) == 1:
        st.markdown(
            f"{cube_html(cube)} · {mode_text(cube)}",
            unsafe_allow_html=True,
        )
        return
    by_id = {d["id"]: d for d in devices}
    st.selectbox(
        "Ausgewählter Würfel",
        list(by_id),
        key=SELECTED_KEY,
        format_func=lambda i: f"{cube_label(by_id[i])} · {mode_text(by_id[i])}",
        label_visibility="collapsed",
        help="Welchen Würfel Sie gerade ansehen und bearbeiten. Die Auswahl gilt auf allen "
        "Seiten. Der Stern ⭐ in der Übersicht markiert dagegen den Würfel, der die Zeit "
        "erfasst.",
    )
    st.markdown(
        f"{cube_html(cube)} · {mode_text(cube)}",
        unsafe_allow_html=True,
    )


def banner(device: dict[str, Any], *, key: str, action: str = "bearbeiten") -> None:
    """The line at the top of a cube page: whose settings or data are shown."""
    color = html.escape(str(device.get("color") or DEFAULT_COLOR), quote=True)
    star = " · ⭐ erfasst die Zeit" if device.get("is_active") else ""
    with st.container(key=key):
        st.markdown(
            f'<div style="border-left:6px solid {color};padding:2px 0 2px 10px;">'
            f"Sie {action}: {cube_html(device)} · "
            f"{html.escape(MODE_ICON.get(device.get('mode', 'time'), ''))} "
            f"{html.escape(mode_text(device))}{star}</div>",
            unsafe_allow_html=True,
        )
