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

from datetime import datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from octaledger.dashboard import entry_filter as ef
from octaledger.dashboard import filter_bar as fb
from octaledger.dashboard.ui import call, format_hm, page_help
from octaledger.dashboard.views.entries_bulk import render as render_bulk
from octaledger.dashboard.views.entries_history import render as render_history
from octaledger.dashboard_client.client import ApiClient

PREFIX: Final = "ent"
HISTORY_KEY: Final = "ent_history"
LAST_KEY: Final = "ent_last_fingerprint"
MAX_HISTORY: Final = 20
MAX_ROWS_SHOWN: Final = 3000
FILTER_KEYS: Final = fb.filter_keys(PREFIX)


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


def _apply_history(index: int) -> None:
    """Callback of a search-log button: put the stored filter back into the widgets."""
    saved = st.session_state.get(HISTORY_KEY, [])
    if 0 <= index < len(saved):
        for key, value in saved[index]["state"].items():
            st.session_state[key] = value


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


def entry_frame(entries: list[dict[str, Any]], tz: str) -> pd.DataFrame:
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
        entry_frame(shown, tz),
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
    fb.sanitize(
        PREFIX,
        {
            "act": {a["id"] for a in activities},
            "proj": {p["id"] for p in projects} | {ef.NONE_ID},
            "dev": {d["id"] for d in devices} | {ef.NONE_ID},
            "tags": {t["name"] for t in tags},
        },
    )
    start, end, label = fb.period_widgets(PREFIX, tz)
    flt = fb.filter_widgets(PREFIX, activities, projects, devices, tags)
    st.button(
        "Filter zurücksetzen",
        key="ent_reset",
        on_click=fb.clear_filters,
        args=(PREFIX,),
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
