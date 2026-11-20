"""Dashboard entry point: page setup, theme, navigation and the agent connection.

Responsibility
--------------
``run()`` is executed by Streamlit on **every interaction** (a "rerun"). It therefore does no
slow work, never starts BLE or loops, and keeps everything it needs between reruns in
``st.session_state``:

``_client``   the :class:`ApiClient` (tests inject their own before the first run)
``_display``  theme, font size and timezone of this session (persisted via the API settings)
``nav``       the selected page

Closing or reloading the browser tab never stops the tracking: the agent is a separate process.
"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from octaledger import __version__
from octaledger.core.errors import ConfigurationError, OctaLedgerError
from octaledger.core.logging import configure_logging
from octaledger.core.settings import FontSize, Theme, load_settings, resolve_paths
from octaledger.dashboard.nav import DEFAULT_PAGE, GROUPS, NAV_STATE_KEY, go
from octaledger.dashboard.pages import PAGES
from octaledger.dashboard.shell import status_bar
from octaledger.dashboard.theme import css
from octaledger.dashboard.ui import display_settings, page_help, show_error
from octaledger.dashboard_client.client import ApiClient

logger = logging.getLogger(__name__)

_logging_ready = False


def _ensure_logging() -> None:
    """Configure logging once per process (not on every rerun)."""
    global _logging_ready
    if _logging_ready:
        return
    try:
        paths = resolve_paths()
        settings = load_settings(paths.settings_file)
        configure_logging(
            level=settings.logging.level,
            log_dir=paths.logs_dir,
            console=False,
            max_bytes=settings.logging.max_bytes,
            backup_count=settings.logging.backup_count,
        )
    except OctaLedgerError:
        configure_logging(console=False)  # never fail the page because of the log setup
    _logging_ready = True


def get_client() -> ApiClient | None:
    """Return the API client, creating it from the settings and the token file on first use.

    Shows a setup explanation and returns ``None`` if that is not possible (for example the
    agent never ran, so there is no token yet).
    """
    existing = st.session_state.get("_client")
    if existing is not None:
        return existing  # type: ignore[no-any-return]
    try:
        paths = resolve_paths()
        settings = load_settings(paths.settings_file)
        client = ApiClient.from_settings(settings.agent, paths.root)
    except ConfigurationError as exc:
        st.title("OctaLedger")
        show_error(exc)
        page_help(
            "Einrichtung",
            "Starten Sie den Agenten (`octaledger agent`). Beim ersten Start erzeugt er das "
            "API-Token, danach finden Dashboard und Agent einander automatisch.",
        )
        return None
    st.session_state["_client"] = client
    return client


def _load_display(client: ApiClient) -> dict[str, str]:
    """Load (once per session) theme/font/timezone from the agent's settings."""
    if "_display" not in st.session_state:
        try:
            settings = client.get_settings()
        except OctaLedgerError:
            settings = None  # agent down: defaults now, real values after "Neu laden"
        shown = display_settings(settings)
        if settings is None:
            return {
                "theme": shown.theme.value,
                "font_size": shown.font_size.value,
                "timezone": shown.timezone,
            }
        st.session_state["_display"] = {
            "theme": shown.theme.value,
            "font_size": shown.font_size.value,
            "timezone": shown.timezone,
        }
    display: dict[str, str] = st.session_state["_display"]
    return display


def _persist(client: ApiClient, **values: str) -> None:
    """Save a display preference through the API; remember a failure for the sidebar."""
    try:
        client.update_settings({"display": values})
        st.session_state["_persist_failed"] = False
    except OctaLedgerError:
        logger.warning("Could not save display settings", exc_info=True)
        st.session_state["_persist_failed"] = True


def _toggle_theme(client: ApiClient) -> None:
    display = st.session_state["_display"]
    display["theme"] = (
        Theme.DARK.value if display["theme"] == Theme.LIGHT.value else Theme.LIGHT.value
    )
    _persist(client, theme=display["theme"])


def _toggle_font(client: ApiClient) -> None:
    display = st.session_state["_display"]
    display["font_size"] = (
        FontSize.LARGE.value
        if display["font_size"] == FontSize.NORMAL.value
        else FontSize.NORMAL.value
    )
    _persist(client, font_size=display["font_size"])


def _sidebar(client: ApiClient, display: dict[str, str], agent_up: bool) -> str:
    """Draw the grouped sidebar menu and return the slug of the selected page."""
    current = st.session_state.get(NAV_STATE_KEY, DEFAULT_PAGE)
    if current not in PAGES:
        current = DEFAULT_PAGE
    st.session_state[NAV_STATE_KEY] = current
    with st.sidebar:
        st.markdown("### :material/schedule: OctaLedger")
        st.caption("Lokale Zeiterfassung für Ihren Würfel")
        for group in GROUPS:
            st.markdown(f'<div class="ol-nav-group">{group}</div>', unsafe_allow_html=True)
            for page in (p for p in PAGES.values() if p.group == group):
                st.button(
                    page.label,
                    key=f"nav_{page.slug}",
                    type="primary" if page.slug == current else "secondary",
                    on_click=go,
                    args=(page.slug,),
                    width="stretch",
                    help=page.description,
                )
        st.divider()
        dark = display["theme"] == Theme.DARK.value
        large = display["font_size"] == FontSize.LARGE.value
        theme_col, font_col = st.columns(2)
        theme_col.button(
            ("Hell" if dark else "Dunkel"),
            icon=":material/light_mode:" if dark else ":material/dark_mode:",
            key="btn_theme",
            on_click=_toggle_theme,
            args=(client,),
            width="stretch",
            help="Wechselt zwischen heller und dunkler Darstellung.",
        )
        font_col.button(
            "Kleiner" if large else "Größer",
            icon=":material/text_decrease:" if large else ":material/text_increase:",
            key="btn_font",
            on_click=_toggle_font,
            args=(client,),
            width="stretch",
            help="Wechselt zwischen normaler und größerer Schrift.",
        )
        if st.session_state.get("_persist_failed"):
            st.caption("⚠️ Einstellung gilt nur für diese Sitzung (Agent nicht erreichbar).")
        st.caption(
            ("🟢 Agent läuft" if agent_up else "🔴 Agent nicht erreichbar") + f" · v{__version__}"
        )
    return str(current)


def _agent_down(client: ApiClient) -> None:
    """Explain what to do when the agent cannot be reached."""
    st.error("Der OctaLedger-Agent ist nicht erreichbar.", icon="🚫")
    st.caption("Fehlercode: OL-API-002")
    st.markdown(
        "Der Agent erfasst die Zeit im Hintergrund. Das Dashboard ist nur die Anzeige.\n\n"
        "1. Öffnen Sie eine Eingabeaufforderung im Projektordner.\n"
        "2. Starten Sie den Agenten: `octaledger agent`\n"
        "3. Klicken Sie danach auf **Neu laden**."
    )
    if st.button(
        "🔄 Neu laden",
        key="btn_reload_agent",
        type="primary",
        help="Prüft erneut, ob der Agent jetzt läuft.",
    ):
        st.session_state.pop("_display", None)
        st.rerun()


def run() -> None:
    """Render the whole dashboard (called by Streamlit on every rerun)."""
    st.set_page_config(page_title="OctaLedger", page_icon="⏱️", layout="wide")
    _ensure_logging()
    client = get_client()
    if client is None:
        return
    display = _load_display(client)
    st.markdown(
        css(Theme(display["theme"]), FontSize(display["font_size"])), unsafe_allow_html=True
    )
    agent_up = client.is_agent_running()
    page = _sidebar(client, display, agent_up)
    if not agent_up:
        _agent_down(client)
        return
    status_bar(client)
    renderer: Any = PAGES[page].render
    renderer(client, display["timezone"])
