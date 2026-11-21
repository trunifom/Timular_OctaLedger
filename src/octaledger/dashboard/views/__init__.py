"""Dashboard pages: one module per area, each exposing ``render(client, timezone_name)``.

``PAGES`` maps a page slug to its :class:`~octaledger.dashboard.nav.PageDef`; the order of the
dict is the order inside each menu group. Every page follows the same rules (``CLAUDE.md``
section 6): a title identical to the menu label, a short "ℹ️ So funktioniert diese Seite"
explanation, a help tooltip on every input and understandable German error messages.
"""

from __future__ import annotations

from octaledger.dashboard.nav import PageDef
from octaledger.dashboard.views import (
    catalog,
    connections,
    data,
    devices,
    diagnostics,
    faces,
    journal,
    live,
    overview,
    settings,
    start,
    statistics,
)

_DEFINITIONS = (
    PageDef(
        "start",
        "Startseite",
        "home",
        "Start",
        "Was ist der Würfel? Einrichten Schritt für Schritt und das Handbuch zum Nachlesen",
        start.render,
    ),
    PageDef(
        "overview",
        "Übersicht",
        "dashboard",
        "Alltag",
        "Was läuft gerade? Start, Pause, Stopp, heutige Einträge",
        overview.render,
    ),
    PageDef(
        "live",
        "Würfel live",
        "view_in_ar",
        "Alltag",
        "Sehen Sie in Echtzeit, wie der Würfel liegt und was die Software daraus macht",
        live.render,
    ),
    PageDef(
        "journal",
        "Zeitjournal",
        "calendar_month",
        "Alltag",
        "Einträge ansehen, korrigieren, teilen, bestätigen, nachtragen",
        journal.render,
    ),
    PageDef(
        "statistics",
        "Statistik",
        "bar_chart",
        "Alltag",
        "Auswertung nach Tag, Woche oder Zeitraum mit Diagrammen",
        statistics.render,
    ),
    PageDef(
        "devices",
        "Geräte",
        "bluetooth",
        "Einrichten",
        "Würfel registrieren, verbinden und die acht Seiten zuordnen",
        devices.render,
    ),
    PageDef(
        "faces",
        "Seiten zuordnen",
        "touch_app",
        "Einrichten",
        "Sehen Sie, welche Seite oben liegt, und geben Sie ihr eine Tätigkeit",
        faces.render,
    ),
    PageDef(
        "connections",
        "Verbindungen",
        "hub",
        "Einrichten",
        "Smarthome, MQTT, Home Assistant, Hue oder Web-Adressen anbinden",
        connections.render,
    ),
    PageDef(
        "catalog",
        "Verwaltung",
        "category",
        "Einrichten",
        "Tätigkeiten und Projekte anlegen und pflegen",
        catalog.render,
    ),
    PageDef(
        "data",
        "Daten",
        "database",
        "System",
        "CSV-Export, Sicherung und Wiederherstellung",
        data.render,
    ),
    PageDef(
        "settings",
        "Einstellungen",
        "settings",
        "System",
        "Zeitzone, Erkennung der Würfelbewegung, Protokoll",
        settings.render,
    ),
    PageDef(
        "diagnostics",
        "Diagnose",
        "monitor_heart",
        "System",
        "Verbindungs- und Datenbankstatus, Protokoll, Diagnosebericht",
        diagnostics.render,
    ),
)

#: ``slug -> page``; the dict order is the menu order.
PAGES: dict[str, PageDef] = {page.slug: page for page in _DEFINITIONS}
