"""The shared period chooser and filter bar of the pages *Einträge* and *Diagramme* (AP-58/59).

Both pages narrow the entries down in exactly the same way, so the widgets live here once. Every
widget key starts with a **prefix** (``ent`` on the entries page, ``chart`` on the chart page):
Streamlit forgets the state of widgets that are not drawn, so each page keeps its own filter and
the two pages never overwrite each other. The result is an
:class:`~octaledger.dashboard.entry_filter.EntryFilter` plus the UTC window to load.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

import streamlit as st

from octaledger.dashboard import entry_filter as ef
from octaledger.dashboard.ui import from_local

PERIODS: Final = {
    "today": "Heute",
    "yesterday": "Gestern",
    "week": "Letzte 7 Tage",
    "month": "Letzte 30 Tage",
    "year": "Dieses Jahr",
    "all": "Alles",
    "custom": "Eigener Zeitraum",
}
#: Widget names of a filter (the key is ``<prefix>_<name>``).
FILTER_NAMES: Final = (
    "period",
    "from",
    "to",
    "text",
    "act",
    "proj",
    "dev",
    "tags",
    "tagmode",
    "qual",
    "src",
    "min",
    "max",
    "days",
    "hours",
)
_EPOCH: Final = date(2000, 1, 1)


def filter_keys(prefix: str) -> tuple[str, ...]:
    """The session-state keys that make up the filter of a page."""
    return tuple(f"{prefix}_{name}" for name in FILTER_NAMES)


def window_of(period: str, tz: str) -> tuple[datetime, datetime]:
    """The UTC window of a quick period (the user's calendar days)."""
    today = datetime.now(ZoneInfo(tz)).date()
    first, last = {
        "today": (today, today),
        "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
        "week": (today - timedelta(days=6), today),
        "month": (today - timedelta(days=29), today),
        "year": (date(today.year, 1, 1), today),
        "all": (_EPOCH, today),
    }[period]
    return from_local(first, time(0, 0), tz), from_local(last + timedelta(days=1), time(0, 0), tz)


def sanitize(prefix: str, valid: dict[str, set[str]]) -> None:
    """Drop remembered choices that no longer exist (renamed, deleted) before the widgets.

    Args:
        prefix: The page prefix.
        valid: ``name -> allowed values`` (``name`` without the prefix, e.g. ``act``).
    """
    for name, allowed in valid.items():
        key = f"{prefix}_{name}"
        current = st.session_state.get(key)
        if isinstance(current, list):
            st.session_state[key] = [c for c in current if c in allowed]


def clear_filters(prefix: str) -> None:
    """Callback of a reset button: forget the whole filter of the page."""
    for key in filter_keys(prefix):
        st.session_state.pop(key, None)


def period_widgets(prefix: str, tz: str) -> tuple[datetime, datetime, str]:
    """The period chooser; returns the UTC window and its German name."""
    period = st.radio(
        "Zeitraum",
        list(PERIODS),
        key=f"{prefix}_period",
        index=2,
        horizontal=True,
        format_func=PERIODS.__getitem__,
        help="Welche Tage geladen werden. „Alles“ lädt jeden gespeicherten Eintrag.",
    )
    if period != "custom":
        start, end = window_of(period, tz)
        return start, end, PERIODS[period]
    today = datetime.now(ZoneInfo(tz)).date()
    first, second = st.columns(2)
    day_a = first.date_input(
        "Von",
        today - timedelta(days=6),
        key=f"{prefix}_from",
        format="DD.MM.YYYY",
        help="Erster Tag (Ihre Zeitzone).",
    )
    day_b = second.date_input(
        "Bis (einschließlich)",
        today,
        key=f"{prefix}_to",
        format="DD.MM.YYYY",
        help="Letzter Tag, einschließlich.",
    )
    if day_b < day_a:
        day_a, day_b = day_b, day_a
    start = from_local(day_a, time(0, 0), tz)
    end = from_local(day_b + timedelta(days=1), time(0, 0), tz)
    return start, end, f"{day_a:%d.%m.%Y} – {day_b:%d.%m.%Y}"


def filter_widgets(
    prefix: str,
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    devices: list[dict[str, Any]],
    tags: list[dict[str, Any]],
) -> ef.EntryFilter:
    """The filter bar; returns the filter the widgets describe."""
    key = prefix + "_"
    act_names = {a["id"]: a["name"] for a in activities}
    proj_names = {p["id"]: p["name"] for p in projects} | {ef.NONE_ID: "– kein Projekt –"}
    dev_names = {d["id"]: d["alias"] for d in devices} | {ef.NONE_ID: "von Hand"}
    text = st.text_input(
        "Suche",
        key=key + "text",
        placeholder="z. B. Müller Planung",
        max_chars=200,
        help="Findet Einträge, in deren Notiz, Tätigkeit, Projekt, Gerät oder Tags **alle** "
        "eingetippten Wörter vorkommen (Groß-/Kleinschreibung egal). Mit Enter bestätigen.",
    )
    a_col, p_col, d_col = st.columns(3)
    activity_ids = a_col.multiselect(
        "Tätigkeit",
        list(act_names),
        key=key + "act",
        format_func=act_names.__getitem__,
        placeholder="Alle",
        help="Nur Einträge dieser Tätigkeiten. Leer = alle.",
    )
    project_ids = p_col.multiselect(
        "Projekt",
        list(proj_names),
        key=key + "proj",
        format_func=proj_names.__getitem__,
        placeholder="Alle",
        help="Nur Einträge dieser Projekte (auch „kein Projekt“). Leer = alle.",
    )
    device_ids = d_col.multiselect(
        "Gerät",
        list(dev_names),
        key=key + "dev",
        format_func=dev_names.__getitem__,
        placeholder="Alle",
        help="Nur Einträge dieser Würfel (oder von Hand erfasste). Leer = alle.",
    )
    t_col, m_col, q_col, s_col = st.columns([3, 2, 2, 2])
    chosen_tags = t_col.multiselect(
        "Tags",
        [t["name"] for t in tags],
        key=key + "tags",
        placeholder="Alle",
        help="Nach Tags filtern, z. B. eine Person oder ein Vorgang. Leer = alle.",
    )
    tag_mode = m_col.selectbox(
        "Eintrag hat …",
        list(ef.TAG_MODES),
        key=key + "tagmode",
        format_func=ef.TAG_MODES.__getitem__,
        help="Wie die gewählten Tags geprüft werden: mindestens einer, alle oder keiner.",
    )
    qualities = q_col.multiselect(
        "Qualität",
        list(ef.QUALITY_TEXT),
        key=key + "qual",
        format_func=ef.QUALITY_TEXT.__getitem__,
        placeholder="Alle",
        help="„unsicher“ sind Zeiten, die Sie noch nicht bestätigt haben.",
    )
    sources = s_col.multiselect(
        "Quelle",
        list(ef.SOURCE_TEXT),
        key=key + "src",
        format_func=ef.SOURCE_TEXT.__getitem__,
        placeholder="Alle",
        help="Vom Würfel erfasst oder von Hand nachgetragen.",
    )
    with st.expander("Weitere Filter: Dauer, Wochentag, Tageszeit", key=key + "more"):
        lo, hi, days_col = st.columns([1, 1, 2])
        min_minutes = lo.number_input(
            "Mindestens (Minuten)",
            0,
            100000,
            0,
            key=key + "min",
            help="Nur Einträge, die mindestens so lange dauern. 0 = keine Grenze.",
        )
        max_minutes = hi.number_input(
            "Höchstens (Minuten)",
            0,
            100000,
            0,
            key=key + "max",
            help="Nur Einträge, die höchstens so lange dauern. 0 = keine Grenze.",
        )
        weekdays = days_col.multiselect(
            "Wochentage",
            list(range(7)),
            key=key + "days",
            format_func=lambda d: ef.WEEKDAYS[d],
            placeholder="Alle",
            help="Nur Einträge, die an diesen Wochentagen beginnen (Ihre Zeitzone).",
        )
        hour_from, hour_to = st.slider(
            "Beginn zwischen … und … Uhr",
            0,
            24,
            (0, 24),
            key=key + "hours",
            help="Nur Einträge, die in diesem Zeitfenster des Tages beginnen (Ihre Zeitzone).",
        )
    return ef.EntryFilter(
        text=text,
        activity_ids=tuple(activity_ids),
        project_ids=tuple(project_ids),
        device_ids=tuple(device_ids),
        tags=tuple(chosen_tags),
        tag_mode=tag_mode,
        qualities=tuple(qualities),
        sources=tuple(sources),
        min_minutes=int(min_minutes) or None,
        max_minutes=int(max_minutes) or None,
        weekdays=tuple(weekdays),
        hour_from=hour_from,
        hour_to=hour_to,
    )
