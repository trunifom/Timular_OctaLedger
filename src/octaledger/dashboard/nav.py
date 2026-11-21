"""Navigation model: pages, groups and the callback that switches pages.

Menu structure (research: ``docs/GUI_KONZEPT.md``): eight destinations are fine as long as they are
**grouped** by the user's task, most frequent first, configuration and technology last:

* **Start** - Startseite: what the cube is, guided setup, the manual (every new session opens here)
* **Alltag** - Übersicht, Würfel live, Zeitjournal, Statistik (the daily work, one click away)
* **Einrichten** - Geräte, Seiten zuordnen, Verwaltung (done once, changed rarely)
* **System** - Daten, Einstellungen, Diagnose (backup, preferences, troubleshooting)

Every entry has an icon **and** a text; the active page is filled (not only coloured) and every page
shows a title identical to its menu label.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

from octaledger.dashboard_client.client import ApiClient

#: Group headings in menu order.
GROUPS: tuple[str, ...] = ("Start", "Alltag", "Einrichten", "System")
DEFAULT_PAGE = "start"
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

    @property
    def label(self) -> str:
        """Menu label with icon (Streamlit renders ``:material/name:`` as an icon)."""
        return f":material/{self.icon}: {self.title}"


def go(slug: str) -> None:
    """Switch to a page (used as ``on_click`` callback, so it takes effect on the next rerun)."""
    st.session_state[NAV_STATE_KEY] = slug
