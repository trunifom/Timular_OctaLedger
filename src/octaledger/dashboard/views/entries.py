"""Page "Einträge": search, filter, mark and manage many time entries at once (AP-58).

The page loads the entries of a period from the API, narrows them down with the pure functions of
:mod:`octaledger.dashboard.entry_filter`, shows **all values in one table** and lets the user
act on a **selection** (clicked rows) or on **all hits**: assign, tag, move in time, change the
note or quality, delete. The actions live in :mod:`octaledger.dashboard.views.entries_bulk`, the
change protocol in :mod:`octaledger.dashboard.views.entries_history`.

The *search log* keeps the last filters of the session (one click applies one again). It lives in
``st.session_state`` only: nothing is written to disk.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from octaledger.dashboard import entry_filter as ef
from octaledger.dashboard.ui import call, format_hm, from_local, page_help
from octaledger.dashboard.views.entries_bulk import render as render_bulk
from octaledger.dashboard.views.entries_history import render as render_history
from octaledger.dashboard_client.client import ApiClient

HISTORY_KEY: Final = "ent_history"
LAST_KEY: Final = "ent_last_fingerprint"
MAX_HISTORY: Final = 20
MAX_ROWS_SHOWN: Final = 3000
PERIODS: Final = {
    "today": "Heute",
    "yesterday": "Gestern",
    "week": "Letzte 7 Tage",
    "month": "Letzte 30 Tage",
    "year": "Dieses Jahr",
    "all": "Alles",
    "custom": "Eigener Zeitraum",
}
#: The widget keys that make up a filter (what the search log stores and restores).
FILTER_KEYS: Final = (
    "ent_period",
    "ent_from",
    "ent_to",
    "ent_text",
    "ent_act",
    "ent_proj",
    "ent_dev",
    "ent_tags",
    "ent_tagmode",
    "ent_qual",
    "ent_src",
    "ent_min",
    "ent_max",
    "ent_days",
    "ent_hours",
)
_EPOCH: Final = date(2000, 1, 1)


def render(client: ApiClient, tz: str) -> None:
    """Render the entries page."""
    st.header("Einträge")
    page_help(
        "So funktioniert die Seite „Einträge“",
        "Hier finden, prüfen und ändern Sie **viele Einträge auf einmal**.\n\n"
        "1. **Suchen und filtern:** Wählen Sie einen Zeitraum, tippen Sie ein Suchwort und "
        "grenzen Sie nach Tätigkeit, Projekt, Gerät, Tags, Qualität, Dauer, Wochentag oder "
        "Tageszeit ein. Frühere Suchen stehen im **Suchprotokoll**.\n"
        "2. **Auswählen:** Klicken Sie links in der Tabelle auf Zeilen (Strg oder Umschalt für "
        "mehrere) – oder wählen Sie unter der Tabelle **alle Treffer**.\n"
        "3. **Bearbeiten:** Ordnen Sie zu, vergeben Sie Tags (z. B. `PERSON-B`), verschieben Sie "
        "die Zeit, ändern Sie Notiz oder Qualität oder löschen Sie.\n\n"
        "**Sicher:** Jede Änderung gilt für alle gewählten Einträge **oder für keinen**, verlangt "
        "einen **Grund** und steht im **Änderungsprotokoll**. Vor dem Löschen wird automatisch "
        "eine Sicherung angelegt. Laufende Einträge werden nie gelöscht oder verschoben.",
    )
    ok_a, activities = call(client.list_items, "activities", True)
    ok_p, projects = call(client.list_items, "projects", True)
    ok_d, devices = call(client.devices)
    ok_t, tags = call(client.tags)
    if not (ok_a and ok_p and ok_d and ok_t):
        return
    assert activities is not None and projects is not None
    assert devices is not None and tags is not None
    flash = st.session_state.pop("ent_flash", None)
    if flash:
        st.success(flash)
    entries_tab, history_tab = st.tabs(["Einträge", "Änderungsprotokoll"])
    with entries_tab:
        _entries(client, tz, activities, projects, devices, tags)
    with history_tab:
        render_history(client, tz)


# ------------------------------------------------------------------------------- filter


def _window(period: str, tz: str) -> tuple[datetime, datetime]:
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


def _sanitize(valid: dict[str, set[str]]) -> None:
    """Drop remembered choices that no longer exist (renamed, deleted) before the widgets."""
    for key, ids in valid.items():
        current = st.session_state.get(key)
        if isinstance(current, list):
            st.session_state[key] = [c for c in current if c in ids]


def _apply_history(index: int) -> None:
    """Callback of a search-log button: put the stored filter back into the widgets."""
    saved = st.session_state.get(HISTORY_KEY, [])
    if 0 <= index < len(saved):
        for key, value in saved[index]["state"].items():
            st.session_state[key] = value


def _clear_filters() -> None:
    """Callback of the reset button."""
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


def _filter_widgets(
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    devices: list[dict[str, Any]],
    tags: list[dict[str, Any]],
) -> ef.EntryFilter:
    """The filter bar; returns the filter the widgets describe."""
    act_names = {a["id"]: a["name"] for a in activities}
    proj_names = {p["id"]: p["name"] for p in projects} | {ef.NONE_ID: "– kein Projekt –"}
    dev_names = {d["id"]: d["alias"] for d in devices} | {ef.NONE_ID: "von Hand"}
    st.text_input(
        "Suche",
        key="ent_text",
        placeholder="z. B. Müller Planung",
        max_chars=200,
        help="Findet Einträge, in deren Notiz, Tätigkeit, Projekt, Gerät oder Tags **alle** "
        "eingetippten Wörter vorkommen (Groß-/Kleinschreibung egal). Mit Enter bestätigen.",
    )
    a_col, p_col, d_col = st.columns(3)
    activity_ids = a_col.multiselect(
        "Tätigkeit",
        list(act_names),
        key="ent_act",
        format_func=act_names.__getitem__,
        placeholder="Alle",
        help="Nur Einträge dieser Tätigkeiten. Leer = alle.",
    )
    project_ids = p_col.multiselect(
        "Projekt",
        list(proj_names),
        key="ent_proj",
        format_func=proj_names.__getitem__,
        placeholder="Alle",
        help="Nur Einträge dieser Projekte (auch „kein Projekt“). Leer = alle.",
    )
    device_ids = d_col.multiselect(
        "Gerät",
        list(dev_names),
        key="ent_dev",
        format_func=dev_names.__getitem__,
        placeholder="Alle",
        help="Nur Einträge dieser Würfel (oder von Hand erfasste). Leer = alle.",
    )
    t_col, m_col, q_col, s_col = st.columns([3, 2, 2, 2])
    chosen_tags = t_col.multiselect(
        "Tags",
        [t["name"] for t in tags],
        key="ent_tags",
        placeholder="Alle",
        help="Nach Tags filtern, z. B. eine Person oder ein Vorgang. Leer = alle.",
    )
    tag_mode = m_col.selectbox(
        "Eintrag hat …",
        list(ef.TAG_MODES),
        key="ent_tagmode",
        format_func=ef.TAG_MODES.__getitem__,
        help="Wie die gewählten Tags geprüft werden: mindestens einer, alle oder keiner.",
    )
    qualities = q_col.multiselect(
        "Qualität",
        list(ef.QUALITY_TEXT),
        key="ent_qual",
        format_func=ef.QUALITY_TEXT.__getitem__,
        placeholder="Alle",
        help="„unsicher“ sind Zeiten, die Sie noch nicht bestätigt haben.",
    )
    sources = s_col.multiselect(
        "Quelle",
        list(ef.SOURCE_TEXT),
        key="ent_src",
        format_func=ef.SOURCE_TEXT.__getitem__,
        placeholder="Alle",
        help="Vom Würfel erfasst oder von Hand nachgetragen.",
    )
    with st.expander("Weitere Filter: Dauer, Wochentag, Tageszeit", key="ent_more"):
        lo, hi, days_col = st.columns([1, 1, 2])
        min_minutes = lo.number_input(
            "Mindestens (Minuten)",
            0,
            100000,
            0,
            key="ent_min",
            help="Nur Einträge, die mindestens so lange dauern. 0 = keine Grenze.",
        )
        max_minutes = hi.number_input(
            "Höchstens (Minuten)",
            0,
            100000,
            0,
            key="ent_max",
            help="Nur Einträge, die höchstens so lange dauern. 0 = keine Grenze.",
        )
        weekdays = days_col.multiselect(
            "Wochentage",
            list(range(7)),
            key="ent_days",
            format_func=lambda d: ef.WEEKDAYS[d],
            placeholder="Alle",
            help="Nur Einträge, die an diesen Wochentagen beginnen (Ihre Zeitzone).",
        )
        hour_from, hour_to = st.slider(
            "Beginn zwischen … und … Uhr",
            0,
            24,
            (0, 24),
            key="ent_hours",
            help="Nur Einträge, die in diesem Zeitfenster des Tages beginnen (Ihre Zeitzone).",
        )
    return ef.EntryFilter(
        text=st.session_state.get("ent_text", ""),
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


def _period_widgets(tz: str) -> tuple[datetime, datetime, str]:
    """The period chooser; returns the UTC window and its German name."""
    period = st.radio(
        "Zeitraum",
        list(PERIODS),
        key="ent_period",
        index=2,
        horizontal=True,
        format_func=PERIODS.__getitem__,
        help="Welche Tage geladen werden. „Alles“ lädt jeden gespeicherten Eintrag.",
    )
    if period != "custom":
        start, end = _window(period, tz)
        return start, end, PERIODS[period]
    today = datetime.now(ZoneInfo(tz)).date()
    first, second = st.columns(2)
    day_a = first.date_input(
        "Von",
        today - timedelta(days=6),
        key="ent_from",
        format="DD.MM.YYYY",
        help="Erster Tag (Ihre Zeitzone).",
    )
    day_b = second.date_input(
        "Bis (einschließlich)",
        today,
        key="ent_to",
        format="DD.MM.YYYY",
        help="Letzter Tag, einschließlich.",
    )
    if day_b < day_a:
        day_a, day_b = day_b, day_a
    start = from_local(day_a, time(0, 0), tz)
    end = from_local(day_b + timedelta(days=1), time(0, 0), tz)
    return start, end, f"{day_a:%d.%m.%Y} – {day_b:%d.%m.%Y}"


def _remember(flt: ef.EntryFilter, label: str, names: dict[str, str], hits: int) -> None:
    """Put a changed, non-empty filter at the top of the search log (no duplicates)."""
    state = {key: st.session_state[key] for key in FILTER_KEYS if key in st.session_state}
    fingerprint = repr(sorted(state.items(), key=lambda item: item[0]))
    if st.session_state.get(LAST_KEY) == fingerprint or flt.is_empty():
        st.session_state[LAST_KEY] = fingerprint
        return
    st.session_state[LAST_KEY] = fingerprint
    history = [h for h in st.session_state.get(HISTORY_KEY, []) if h["fingerprint"] != fingerprint]
    history.insert(
        0,
        {
            "fingerprint": fingerprint,
            "state": state,
            "text": f"{label}; {ef.describe(flt, names)}",
            "hits": hits,
            "at": datetime.now().strftime("%H:%M"),
        },
    )
    st.session_state[HISTORY_KEY] = history[:MAX_HISTORY]


def _search_log() -> None:
    """The search log: the last filters of this session, one click applies one."""
    history = st.session_state.get(HISTORY_KEY, [])
    with st.expander(f"Suchprotokoll ({len(history)})", key="ent_log_box"):
        if not history:
            st.caption(
                "Noch leer. Jede Suche mit einem Filter oder Suchwort wird hier festgehalten, "
                "damit Sie sie mit einem Klick wiederholen können (nur solange die App "
                "geöffnet ist)."
            )
            return
        for index, item in enumerate(history):
            text_col, button_col = st.columns([5, 1])
            text_col.markdown(f"**{item['at']}** · {item['text']}  \n{item['hits']} Treffer")
            button_col.button(
                "Anwenden",
                key=f"ent_log_apply_{index}",
                on_click=_apply_history,
                args=(index,),
                width="stretch",
                help="Stellt genau diese Suche und diese Filter wieder her.",
            )
        st.button(
            "Suchprotokoll leeren",
            key="ent_log_clear",
            on_click=lambda: st.session_state.pop(HISTORY_KEY, None),
            help="Löscht die Liste der letzten Suchen (Einträge und Daten bleiben unberührt).",
        )


# -------------------------------------------------------------------------------- table


def _frame(entries: list[dict[str, Any]], tz: str) -> pd.DataFrame:
    """The table with all values; times are naive local times so sorting works."""
    zone = ZoneInfo(tz)

    def local(text: str | None) -> pd.Timestamp | None:
        """An ISO time as a naive local timestamp (``None`` stays empty)."""
        if text is None:
            return None
        return pd.Timestamp(datetime.fromisoformat(text).astimezone(zone).replace(tzinfo=None))

    return pd.DataFrame(
        [
            {
                "Beginn": local(e["started_at"]),
                "Ende": local(e["ended_at"]),
                "Dauer (min)": round(e["duration_seconds"] / 60, 1),
                "Tätigkeit": e["activity_name"],
                "Projekt": e["project_name"] or "–",
                "Tags": list(e.get("tags", [])),
                "Gerät": e["device_alias"] or "von Hand",
                "Quelle": ef.SOURCE_TEXT.get(e["source"], e["source"]),
                "Qualität": ("⚠️ " if e["quality"] == "uncertain" else "✅ ")
                + ef.QUALITY_TEXT.get(e["quality"], e["quality"]),
                "Läuft": "▶ läuft" if e["running"] else "",
                "Rev.": e["revision"],
                "Notiz": e["note"] or "",
                "Betrag (€)": None if e["amount_cents"] is None else e["amount_cents"] / 100,
            }
            for e in entries
        ]
    )


def _table(entries: list[dict[str, Any]], tz: str) -> list[int]:
    """Show the table; returns the row numbers the user marked."""
    shown = entries[:MAX_ROWS_SHOWN]
    event = st.dataframe(
        _frame(shown, tz),
        hide_index=True,
        width="stretch",
        key="ent_table",
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "Beginn": st.column_config.DatetimeColumn(
                "Beginn", format="DD.MM.YYYY HH:mm", help="Beginn in Ihrer Zeitzone."
            ),
            "Ende": st.column_config.DatetimeColumn(
                "Ende", format="DD.MM.YYYY HH:mm", help="Ende; leer bei einem laufenden Eintrag."
            ),
            "Dauer (min)": st.column_config.NumberColumn(
                "Dauer (min)", format="%.1f", help="Dauer in Minuten."
            ),
            "Tags": st.column_config.ListColumn("Tags", help="Tags des Eintrags."),
            "Betrag (€)": st.column_config.NumberColumn(
                "Betrag (€)", format="%.2f", help="Nur bei abrechenbaren Projekten mit Stundensatz."
            ),
        },
    )
    if len(entries) > len(shown):
        st.caption(
            f"Angezeigt werden die neuesten {len(shown)} von {len(entries)} Treffern. "
            "„Alle Treffer“ wirkt trotzdem auf alle."
        )
    return [int(r) for r in event.selection.rows if int(r) < len(shown)]


def _entries(
    client: ApiClient,
    tz: str,
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    devices: list[dict[str, Any]],
    tags: list[dict[str, Any]],
) -> None:
    """Filter bar, table, selection and actions."""
    _sanitize(
        {
            "ent_act": {a["id"] for a in activities},
            "ent_proj": {p["id"] for p in projects} | {ef.NONE_ID},
            "ent_dev": {d["id"] for d in devices} | {ef.NONE_ID},
            "ent_tags": {t["name"] for t in tags},
        }
    )
    start, end, label = _period_widgets(tz)
    flt = _filter_widgets(activities, projects, devices, tags)
    st.button(
        "Filter zurücksetzen",
        key="ent_reset",
        on_click=_clear_filters,
        icon=":material/filter_alt_off:",
        help="Entfernt Suchwort und alle Filter; der Zeitraum geht auf „Letzte 7 Tage“.",
    )
    ok, loaded = call(client.journal, start, end)
    if not ok or loaded is None:
        return
    names = (
        {a["id"]: a["name"] for a in activities}
        | {p["id"]: p["name"] for p in projects}
        | {d["id"]: d["alias"] for d in devices}
    )
    hits = ef.apply(loaded, flt, ZoneInfo(tz))
    _remember(flt, label, names, len(hits))
    _search_log()
    count, seconds = ef.totals(hits)
    st.caption(
        f"**{count}** von {len(loaded)} Einträgen im Zeitraum „{label}“, zusammen "
        f"**{format_hm(seconds)}** (Gerätezeit). Filter: {ef.describe(flt, names)}."
    )
    if not hits:
        st.info(
            "Keine Einträge gefunden. Lockern Sie die Filter oder wählen Sie einen größeren "
            "Zeitraum."
            if loaded
            else "Im gewählten Zeitraum gibt es keine Einträge. Wählen Sie oben „Alles“ oder "
            "einen anderen Zeitraum."
        )
        return
    rows = _table(hits, tz)
    scope = st.radio(
        "Bearbeiten wirkt auf …",
        ["marked", "all"],
        key="ent_scope",
        horizontal=True,
        format_func=lambda s: (
            f"die markierten Zeilen ({len(rows)})" if s == "marked" else f"alle {count} Treffer"
        ),
        help="Entweder nur auf die Zeilen, die Sie in der Tabelle angeklickt haben, oder auf "
        "sämtliche Treffer der aktuellen Suche (auch die nicht sichtbaren).",
    )
    target = [hits[i] for i in rows] if scope == "marked" else hits
    render_bulk(client, tz, target, activities, projects, tags)
