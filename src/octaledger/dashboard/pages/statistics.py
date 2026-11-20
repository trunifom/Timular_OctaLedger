"""Statistics page: day/week/custom reports with charts, tables and honest uncertainty."""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from octaledger.core.settings import Theme
from octaledger.dashboard.theme import PALETTES
from octaledger.dashboard.ui import call, format_hm, from_local, page_help
from octaledger.dashboard_client.client import ApiClient

ALL = "Alle"
PERIODS = {"day": "Tag", "week": "Woche", "custom": "Eigener Zeitraum"}


def render(client: ApiClient, tz: str) -> None:
    """Render the statistics page."""
    st.header("Statistik")
    page_help(
        "So lesen Sie die Statistik",
        "Wählen Sie **Tag**, **Woche** oder einen **eigenen Zeitraum** (Zeiten in Ihrer "
        "Zeitzone). Mit den Filtern grenzen Sie nach Tätigkeit, Projekt oder Gerät ein.\n\n"
        "- **Persönliche Arbeitszeit:** Zeit, in der Sie gearbeitet haben – ohne Doppelzählung. "
        "Verwenden Sie diese Zahl für Ihre Arbeitszeit.\n"
        "- **Gerätezeit:** Summe der Zeiten aller Tracker. Sie ist größer, wenn sich Tracker "
        "überschneiden (zeigt *Überschneidung*).\n"
        "- **Davon unsicher:** Zeit, die Sie noch nicht bestätigt haben (z. B. nach "
        "Verbindungsabbruch). Auswertungen gelten dafür nur mit Vorbehalt.\n"
        "- Unter jedem Diagramm steht dieselbe Information als **Tabelle**.",
    )
    ok_a, activities = call(client.list_items, "activities", True)
    ok_p, projects = call(client.list_items, "projects", True)
    ok_d, devices = call(client.devices)
    if not (ok_a and ok_p and ok_d) or activities is None or projects is None or devices is None:
        return

    period = st.radio(
        "Zeitraum",
        list(PERIODS),
        key="stat_period",
        horizontal=True,
        format_func=PERIODS.__getitem__,
        help="Tag oder Woche (Montag bis Sonntag) um das gewählte Datum, oder frei wählbar.",
    )
    today = date.today()
    if period == "custom":
        a, b = st.columns(2)
        first = a.date_input(
            "Von",
            today - timedelta(days=29),
            key="stat_from",
            format="DD.MM.YYYY",
            help="Erster Tag.",
        )
        last = b.date_input(
            "Bis (einschließlich)",
            today,
            key="stat_to",
            format="DD.MM.YYYY",
            help="Letzter Tag, einschließlich (höchstens 400 Tage).",
        )
    else:
        day = st.date_input(
            "Datum",
            today,
            key="stat_day",
            format="DD.MM.YYYY",
            help="Der Tag, oder ein beliebiger Tag der gewünschten Woche.",
        )
    with st.expander("Filter (Tätigkeit, Projekt, Gerät)"):
        c1, c2, c3 = st.columns(3)
        activity = c1.selectbox(
            "Tätigkeit",
            [None, *activities],
            key="stat_activity",
            format_func=lambda x: ALL if x is None else x["name"],
            help="Nur diese Tätigkeit auswerten.",
        )
        project = c2.selectbox(
            "Projekt",
            [None, *projects],
            key="stat_project",
            format_func=lambda x: ALL if x is None else x["name"],
            help="Nur dieses Projekt auswerten.",
        )
        device = c3.selectbox(
            "Gerät",
            [None, *devices],
            key="stat_device",
            format_func=lambda x: ALL if x is None else x["alias"],
            help="Nur Zeiten dieses Trackers auswerten.",
        )
    filters = {
        "tz": tz,
        "activity_id": activity["id"] if activity else None,
        "project_id": project["id"] if project else None,
        "device_id": device["id"] if device else None,
    }
    if period == "day":
        ok, report = call(client.day_report, day, **filters)
    elif period == "week":
        ok, report = call(client.week_report, day, **filters)
    else:
        if last < first:
            st.error("Das Ende liegt vor dem Beginn. Bitte den Zeitraum korrigieren.")
            return
        ok, report = call(
            client.report,
            from_local(first, time(0, 0), tz),
            from_local(last + timedelta(days=1), time(0, 0), tz),
            **filters,
        )
    if not ok or report is None:
        return
    _show(report)


def _show(report: dict[str, Any]) -> None:
    theme = Theme(st.session_state.get("_display", {}).get("theme", Theme.LIGHT.value))
    template = PALETTES[theme].plotly_template

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "Persönliche Arbeitszeit",
        format_hm(report["personal_seconds"]),
        help="Zeit, in der Sie gearbeitet haben, ohne Doppelzählung.",
    )
    m2.metric(
        "Gerätezeit",
        format_hm(report["device_seconds"]),
        help="Summe aller Tracker-Zeiten (kann bei Überschneidung größer sein).",
    )
    m3.metric(
        "Davon unsicher",
        format_hm(report["uncertain_seconds"]),
        help="Noch nicht bestätigte Zeit (z. B. nach Verbindungsabbruch).",
    )
    m4.metric(
        "Überschneidung",
        format_hm(report["overlap_seconds"]),
        help="Zeit, die mehrere Tracker gleichzeitig gezählt haben.",
    )
    if report["includes_running"]:
        st.caption("Ein laufender Eintrag ist bis zum aktuellen Moment eingerechnet.")
    if report["uncertain_seconds"]:
        st.warning(
            f"{format_hm(report['uncertain_seconds'])} sind **unsicher** und noch nicht bestätigt. "
            "Bestätigen Sie sie im Zeitjournal (Reiter *Zu prüfen*).",
            icon="⚠️",
        )
    if not report["session_count"]:
        st.info("Im gewählten Zeitraum gibt es keine Zeiten.")
        return

    daily = pd.DataFrame(
        [
            {
                "Tag": d["day"],
                "Persönliche Zeit (h)": round(d["personal_seconds"] / 3600, 2),
                "Gerätezeit (h)": round(d["device_seconds"] / 3600, 2),
                "Davon unsicher (h)": round(d["uncertain_seconds"] / 3600, 2),
            }
            for d in report["daily"]
        ]
    )
    if len(daily) > 1:
        st.subheader("Verlauf pro Tag")
        figure = go.Figure(
            go.Bar(x=daily["Tag"], y=daily["Persönliche Zeit (h)"], name="Persönliche Zeit")
        )
        figure.update_layout(template=template, yaxis_title="Stunden", margin={"t": 10})
        st.plotly_chart(figure, width="stretch", key="chart_daily")
        st.dataframe(daily, hide_index=True, width="stretch", key="table_daily")

    for title, rows, key in (
        ("Nach Tätigkeit", report["by_activity"], "activity"),
        ("Nach Projekt", report["by_project"], "project"),
    ):
        st.subheader(title)
        table = pd.DataFrame(
            [
                {
                    "Name": r["name"],
                    "Zeit": format_hm(r["seconds"]),
                    "Anteil": f"{r['fraction']:.0%}",
                    "davon unsicher": format_hm(r["uncertain_seconds"]),
                    "Stunden": r["seconds"] / 3600,
                }
                for r in rows
            ]
        )
        figure = go.Figure(
            go.Pie(
                labels=[r["name"] for r in rows],
                values=[r["seconds"] for r in rows],
                marker={"colors": [r["color"] for r in rows]},
                hole=0.45,
                sort=False,
            )
        )
        figure.update_layout(template=template, margin={"t": 10})
        st.plotly_chart(figure, width="stretch", key=f"chart_{key}")
        st.dataframe(
            table.drop(columns="Stunden"),
            hide_index=True,
            width="stretch",
            key=f"table_{key}",
        )
