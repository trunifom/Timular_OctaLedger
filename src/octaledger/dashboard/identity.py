"""Which cube am I looking at, and what is it for? One answer for every page.

With several cubes the most important questions of the interface are "which cube is this?" and
"what does it do?". This module answers them the same way everywhere:

* a **cube label** ``● ② Regenbogen``: colour dot, number badge and name (never colour alone);
* an **area pill** ``🎵 Musik``: every cube has exactly one functional area - *Zeit* (time
  recording), *Smarthome* (control) or *Musik* - always shown as symbol **and** text;
* **one selection** for the whole session (``st.session_state["cube_selected"]``): the selector in
  the sidebar, the pages "Seiten zuordnen", "Würfel live" and the banner all use it, so the cube
  chosen on one page is still the one on the next;
* an **area filter** in the sidebar (Alle · Zeit · Smarthome · Musik): it narrows the cube selector
  and hides menu entries that only matter for other areas;
* a **banner** at the top of every cube-related page: "Sie bearbeiten: ● ② Regenbogen · 🎵 Musik",
  with a button to change the area.

Not to be confused with the *active time cube* (⭐): that is the cube that records time (a setting
of the app), while the selection only says which cube the interface shows right now.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from typing import Any, Final

import streamlit as st

from octaledger.dashboard.nav import go

SELECTED_KEY: Final = "cube_selected"
AREA_KEY: Final = "area_filter"
ALL: Final = "all"

#: ``mode -> (symbol, German name)``; the key is the cube mode of the API.
AREAS: Final = {
    "time": ("⏱", "Zeit"),
    "control": ("🎛", "Smarthome"),
    "music": ("🎵", "Musik"),
}
AREA_FILTER_LABELS: Final = {
    ALL: "Alle Bereiche",
    **{key: f"{icon} {name}" for key, (icon, name) in AREAS.items()},
}

DEFAULT_COLOR: Final = "#808080"


def mode_text(device: dict[str, Any]) -> str:
    """The German name of the area of a cube (``Zeit``, ``Smarthome`` or ``Musik``)."""
    return AREAS.get(str(device.get("mode", "time")), AREAS["time"])[1]


def area_pill(device: dict[str, Any]) -> str:
    """HTML pill with the area of a cube: symbol and text, framed in the area's own colour."""
    mode = str(device.get("mode", "time"))
    icon, name = AREAS.get(mode, AREAS["time"])
    return f'<span class="ol-area ol-area-{html.escape(mode)}">{icon} {name}</span>'


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


def area_filter() -> str:
    """The area chosen in the sidebar (``all`` or a mode)."""
    chosen = st.session_state.get(AREA_KEY, ALL)
    return str(chosen) if chosen in AREA_FILTER_LABELS else ALL


def in_area(devices: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """The cubes of the chosen area; all cubes when the filter is off or hides every cube."""
    area = area_filter()
    if area == ALL:
        return list(devices)
    matching = [d for d in devices if d.get("mode") == area]
    return matching or list(devices)


def selected_cube(devices: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The cube chosen for this session (falls back to the active time cube, else the first).

    The choice is kept in the session; a cube that no longer exists - or that the area filter
    hides - is replaced by one of the visible cubes.
    """
    visible = in_area(devices)
    if not visible:
        st.session_state.pop(SELECTED_KEY, None)
        return None
    chosen = next((d for d in visible if d["id"] == st.session_state.get(SELECTED_KEY)), None)
    if chosen is None:
        chosen = next((d for d in visible if d["is_active"]), visible[0])
        st.session_state[SELECTED_KEY] = chosen["id"]
    return dict(chosen)


def sidebar_area_filter(devices: Sequence[dict[str, Any]]) -> None:
    """Draw the area filter (inside ``with st.sidebar``); shown once there are cubes."""
    if not devices:
        return
    st.markdown('<div class="ol-nav-group">Bereich</div>', unsafe_allow_html=True)
    st.radio(
        "Bereich",
        list(AREA_FILTER_LABELS),
        key=AREA_KEY,
        format_func=AREA_FILTER_LABELS.__getitem__,
        label_visibility="collapsed",
        help="Zeigt nur Würfel und Menüpunkte eines Bereichs: Zeit (Zeiterfassung), Smarthome "
        "(Lampen, Szenen, Nachrichten) oder Musik. „Alle Bereiche“ zeigt alles.",
    )
    area = area_filter()
    if area != ALL and not any(d.get("mode") == area for d in devices):
        st.caption(f"Kein Würfel im Bereich {AREAS[area][1]}: Es werden alle gezeigt.")


def sidebar_selector(devices: Sequence[dict[str, Any]]) -> None:
    """Draw the cube selector (call inside ``with st.sidebar``).

    One cube: only its label is shown. Several: a selector, so switching is one click everywhere.
    """
    cube = selected_cube(devices)
    if cube is None:
        return
    st.markdown('<div class="ol-nav-group">Ausgewählter Würfel</div>', unsafe_allow_html=True)
    visible = in_area(devices)
    if len(visible) == 1:
        st.markdown(f"{cube_html(cube)} · {area_pill(cube)}", unsafe_allow_html=True)
        return
    by_id = {d["id"]: d for d in visible}
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
    st.markdown(f"{cube_html(cube)} · {area_pill(cube)}", unsafe_allow_html=True)


def banner(
    device: dict[str, Any], *, key: str, action: str = "bearbeiten", change_area: bool = True
) -> None:
    """The line at the top of a cube page: whose settings or data are shown, and its area.

    Args:
        device: The selected cube.
        key: Unique widget key of the container.
        action: The verb of the sentence ("bearbeiten", "beobachten" ...).
        change_area: Offer a button that opens the place where the area is switched (not needed
            on that page itself).
    """
    color = html.escape(str(device.get("color") or DEFAULT_COLOR), quote=True)
    star = " · ⭐ erfasst die Zeit" if device.get("is_active") else ""
    with st.container(key=key):
        text, button = st.columns([6, 2], vertical_alignment="center")
        text.markdown(
            f'<div style="border-left:6px solid {color};padding:2px 0 2px 10px;">'
            f"Sie {action}: {cube_html(device)} · {area_pill(device)}{star}</div>",
            unsafe_allow_html=True,
        )
        if change_area:
            button.button(
                "Bereich ändern",
                key=f"{key}_change_area",
                on_click=go,
                args=("faces",),
                icon=":material/swap_horiz:",
                width="stretch",
                help="Öffnet „Seiten zuordnen“, wo Sie diesen Würfel auf Zeit, Smarthome oder "
                "Musik umstellen. Ihre Einstellungen der anderen Bereiche bleiben gespeichert.",
            )
