"""Navigation model: pages, groups and the callback that switches pages.

Menu structure (research: ``docs/GUI_KONZEPT.md``): eight destinations are fine as long as they are
**grouped** by the user's task, most frequent first, configuration and technology last:

* **Start** - Startseite: what the cube is, guided setup, the manual (every new session opens here)
* **Alltag** - Übersicht, Würfel live, Zeitjournal, Statistik (the daily work, one click away)
* **Würfel** - Würfel verwalten, Seiten zuordnen (everything about the cubes themselves)
* **Einstellungen** - App, Tätigkeiten & Projekte, Darstellung, Smarthome & Verbindungen
  (one page per *kind* of setting, so nobody has to hunt)
* **System** - Daten (export, backup, import, deleting), Diagnose (troubleshooting)

Every entry has an icon **and** a text; the active page is filled (not only coloured) and every page
shows a title identical to its menu label.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

from octaledger.dashboard_client.client import ApiClient

#: Group headings in menu order.
GROUPS: tuple[str, ...] = ("Start", "Alltag", "Würfel", "Einstellungen", "System")
DEFAULT_PAGE = "start"
#: The three functional areas of a cube (its mode): time recording, smart home, music.
ALL_AREAS: frozenset[str] = frozenset({"time", "control", "music"})
NAV_STATE_KEY = "nav"


@dataclass(frozen=True, slots=True)
class PageDef:
    """One destination of the menu."""

    slug: str
    title: str
    icon: str  # Material Symbols name, e.g. ``dashboard``
    group: str
    description: str  # tooltip of the menu entry
    render: Callable[[ApiClient, str], None]
    #: The areas this page is about; the sidebar's area filter hides pages that do not apply.
    areas: frozenset[str] = ALL_AREAS

    @property
    def label(self) -> str:
        """Menu label with icon (Streamlit renders ``:material/name:`` as an icon)."""
        return f":material/{self.icon}: {self.title}"


def go(slug: str) -> None:
    """Switch to a page (used as ``on_click`` callback, so it takes effect on the next rerun)."""
    st.session_state[NAV_STATE_KEY] = slug
