"""Dashboard pages: one module per area, each exposing ``render(client, timezone_name)``.

The navigation order below is the order in the sidebar. Every page follows the same rules
(``CLAUDE.md`` section 6): a short "ℹ️ So funktioniert diese Seite" explanation, a help tooltip
on every input and understandable German error messages.
"""

from __future__ import annotations

from collections.abc import Callable

from octaledger.dashboard.pages import (
    catalog,
    data,
    devices,
    diagnostics,
    journal,
    overview,
    settings,
    statistics,
)
from octaledger.dashboard_client.client import ApiClient

#: ``label -> render function``; the dict order is the navigation order.
PAGES: dict[str, Callable[[ApiClient, str], None]] = {
    "🏠 Übersicht": overview.render,
    "🔌 Geräte": devices.render,
    "🗂 Verwaltung": catalog.render,
    "📒 Zeitjournal": journal.render,
    "📊 Statistik": statistics.render,
    "💾 Daten": data.render,
    "⚙️ Einstellungen": settings.render,
    "🩺 Diagnose": diagnostics.render,
}
