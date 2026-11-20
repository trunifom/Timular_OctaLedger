"""Small shared GUI building blocks: formatting, help texts, error display, safe API calls.

Rules for every page (``CLAUDE.md`` section 6)
-----------------------------------------------
* **Every** input has a ``help=`` tooltip and every page an "ℹ️" explanation (:func:`page_help`).
* Errors are shown with the German user message plus the stable error code; technical details
  are folded away and **never** include a stack trace (:func:`show_error`).
* Pages never talk to the network directly; they call the API client through :func:`call`,
  which turns failures into a visible message instead of an exception.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

import streamlit as st

from octaledger.core.errors import ApiUnavailableError, OctaLedgerError
from octaledger.core.settings import DisplaySettings
from octaledger.domain.state_machine import ConnectionState

T = TypeVar("T")

#: German labels for the connection states shown to users.
STATE_LABELS: dict[str, str] = {
    ConnectionState.IDLE.value: "Leerlauf",
    ConnectionState.SCANNING.value: "Suche läuft",
    ConnectionState.CONNECTING.value: "Verbinde …",
    ConnectionState.DISCOVERING.value: "Dienste werden geprüft …",
    ConnectionState.SUBSCRIBING.value: "Abonniere Meldungen …",
    ConnectionState.BASELINE.value: "Ausgangslage wird gelesen …",
    ConnectionState.READY.value: "Bereit",
    ConnectionState.DISCONNECTED.value: "Getrennt",
    ConnectionState.RECONNECT_WAIT.value: "Warte auf neuen Versuch",
    ConnectionState.STOPPED.value: "Gestoppt",
}

#: Visual health of a state (used for the coloured status dot).
STATE_LEVEL: dict[str, str] = {
    ConnectionState.READY.value: "ok",
    ConnectionState.STOPPED.value: "bad",
    ConnectionState.DISCONNECTED.value: "bad",
    ConnectionState.RECONNECT_WAIT.value: "warn",
    ConnectionState.IDLE.value: "warn",
}


def format_hms(total_seconds: int) -> str:
    """``3725`` -> ``1:02:05`` (negative values are shown as 0)."""
    seconds = max(int(total_seconds), 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def format_hm(total_seconds: int) -> str:
    """``5400`` -> ``1 h 30 min`` (compact, for tables and metrics)."""
    minutes_total = max(int(total_seconds), 0) // 60
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def to_local(iso_text: str | None, tz_name: str) -> datetime | None:
    """Convert an API timestamp to the display timezone (``None`` stays ``None``)."""
    if not iso_text:
        return None
    return datetime.fromisoformat(iso_text).astimezone(ZoneInfo(tz_name))


def format_local(iso_text: str | None, tz_name: str, *, with_seconds: bool = False) -> str:
    """``2026-01-05T08:00:00+00:00`` -> ``05.01.2026 09:00`` in the display timezone."""
    moment = to_local(iso_text, tz_name)
    if moment is None:
        return "–"
    return moment.strftime("%d.%m.%Y %H:%M:%S" if with_seconds else "%d.%m.%Y %H:%M")


def display_settings(client_settings: dict[str, dict[str, Any]] | None) -> DisplaySettings:
    """Build validated display settings from the API's settings (defaults on any problem)."""
    try:
        return DisplaySettings(**(client_settings or {}).get("display", {}))
    except (OctaLedgerError, TypeError):
        return DisplaySettings()


def show_error(error: OctaLedgerError) -> None:
    """Show an error as the user message plus code; technical text only inside an expander."""
    st.error(error.user_message, icon="🚫")
    st.caption(f"Fehlercode: {error.error_code}")
    if error.message and error.message != error.user_message:
        with st.expander("Technische Details"):
            st.write(error.message)
            if error.details:
                st.json(error.details)


def call(function: Callable[..., T], *args: Any, **kwargs: Any) -> tuple[bool, T | None]:
    """Run an API call; on failure show the error and return ``(False, None)``.

    Never raises for :class:`OctaLedgerError`, so a failing call cannot blank the page.
    """
    try:
        return True, function(*args, **kwargs)
    except OctaLedgerError as exc:
        show_error(exc)
        if isinstance(exc, ApiUnavailableError):
            st.info("Starten Sie den Agenten und klicken Sie dann auf „Neu laden“.")
        return False, None


def page_help(title: str, text: str) -> None:
    """The "ℹ️ So funktioniert diese Seite" explanation every page starts with."""
    with st.expander(f"ℹ️ {title}"):
        st.markdown(text)


def help_popover(text: str, *, key: str) -> None:
    """A small "ℹ️" button that opens an explanation next to a function."""
    with st.popover("ℹ️", help="Erklärung anzeigen", key=key):
        st.markdown(text)


def status_dot(level: str, label: str) -> str:
    """HTML for a coloured status dot with a text label (colour is never the only signal)."""
    css_class = {"ok": "ol-ok", "warn": "ol-warn", "bad": "ol-bad"}.get(level, "")
    return f'<span class="ol-dot {css_class}" style="background:currentColor"></span>{label}'
