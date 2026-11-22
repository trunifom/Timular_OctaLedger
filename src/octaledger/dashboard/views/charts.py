"""Page "Diagramme": many interactive charts of the time entries (AP-59).

The page loads the entries of a period, narrows them down with the same filter bar as the page
*Einträge*, shows a few key figures and then a **gallery of charts**, ordered in five groups
(Verlauf, Anteile, Muster, Dauer, Zeitstrahl). Every chart can be zoomed, hovered and (where it
makes sense) **clicked**: the entries behind the clicked bar, slice or cell are listed below the
chart. Every chart has its numbers as a table and as a CSV download.

The builders are pure functions in :mod:`octaledger.dashboard.charts`; this module only draws.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from octaledger.core.settings import Theme
from octaledger.dashboard import charts as ch
from octaledger.dashboard import entry_filter as ef
from octaledger.dashboard import filter_bar as fb
from octaledger.dashboard.theme import PALETTES
from octaledger.dashboard.ui import call, format_hm, page_help
from octaledger.dashboard.views.datasheet import to_csv
from octaledger.dashboard.views.entries import entry_frame
from octaledger.dashboard_client.client import ApiClient

PREFIX: Final = "chart"
GROUP_HELP: Final = {
    "Verlauf": "Wie entwickelt sich Ihre Zeit über die Tage, Wochen und Monate?",
    "Anteile": "Wohin fließt die Zeit: Tätigkeiten, Projekte, Tags?",
    "Muster": "Wann arbeiten Sie, an welchen Tagen, in welchen Kombinationen?",
    "Dauer": "Wie lang sind die einzelnen Einträge?",
    "Zeitstrahl": "Jeder Eintrag auf der Zeitachse.",
}


def render(client: ApiClient, tz: str) -> None:
    """Render the chart page."""
    st.header("Diagramme")
    page_help(
        "So lesen Sie die Diagramme",
        "Hier sehen Sie Ihre Zeiten als **viele verschiedene Diagramme**.\n\n"
        "1. **Zeitraum und Filter** wählen (dieselben wie auf der Seite *Einträge*).\n"
        "2. Eine **Gruppe** wählen: *Verlauf*, *Anteile*, *Muster*, *Dauer* oder *Zeitstrahl*.\n"
        "3. **Interaktiv:** Mit der Maus über ein Element fahren zeigt die genauen Werte; "
        "ziehen zoomt, Doppelklick setzt zurück; ein Klick auf einen Eintrag der **Legende** "
        "blendet ihn aus. Wo es sinnvoll ist, zeigt ein **Klick auf ein Element** darunter die "
        "**Einträge dahinter**.\n"
        "4. Zu jedem Diagramm gibt es die **Zahlen als Tabelle** und als CSV.\n\n"
        "**Gerätezeit:** Die Diagramme zählen die Einträge der Würfel so, wie sie gespeichert "
        "sind; überlappen sich zwei Tracker, wird das hier nicht herausgerechnet. Die "
        "„persönliche Arbeitszeit“ ohne Doppelzählung zeigt die Seite *Statistik*.",
    )
    ok_a, activities = call(client.list_items, "activities", True)
    ok_p, projects = call(client.list_items, "projects", True)
    ok_d, devices = call(client.devices)
    ok_t, tags = call(client.tags)
    if not (ok_a and ok_p and ok_d and ok_t):
        return
    assert activities is not None and projects is not None
    assert devices is not None and tags is not None
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
    with st.expander("Suchen und filtern", key="chart_filter_box"):
        flt = fb.filter_widgets(PREFIX, activities, projects, devices, tags)
        st.button(
            "Filter zurücksetzen",
            key="chart_reset",
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
    st.caption(
        f"**{len(hits)}** von {len(loaded)} Einträgen im Zeitraum „{label}“. "
        f"Filter: {ef.describe(flt, names)}."
    )
    if not hits:
        st.info(
            "Keine Einträge für die Diagramme. Wählen Sie einen größeren Zeitraum oder lockern "
            "Sie die Filter."
        )
        return
    frame = ch.to_frame(hits, tz, datetime.now(UTC))
    _key_figures(frame)
    catalog = {
        "activities": {a["name"]: a["color"] for a in activities if a.get("color")},
        "projects": {p["name"]: p["color"] for p in projects if p.get("color")},
    }
    colors = ch.colors_for(frame, catalog)
    theme = Theme(st.session_state.get("_display", {}).get("theme", Theme.LIGHT.value))
    template = PALETTES[theme].plotly_template
    group = st.radio(
        "Gruppe",
        list(ch.GROUPS),
        key="chart_group",
        horizontal=True,
        help="Wählt, welche Diagramme gezeigt werden. Es wird immer nur eine Gruppe gezeichnet.",
    )
    st.caption(GROUP_HELP[group])
    for definition in (c for c in ch.CHARTS if c.group == group):
        _block(definition, frame, hits, tz, template, colors)


def _key_figures(frame: pd.DataFrame) -> None:
    """The row of key figures above the charts."""
    total = float(frame["minutes"].sum())
    days = int(frame["day"].nunique())
    longest = float(frame["minutes"].max())
    uncertain = float(frame.loc[frame["uncertain"], "minutes"].sum())
    a, b, c, d, e = st.columns(5)
    a.metric("Einträge", len(frame), help="Anzahl der Einträge im gewählten Zeitraum und Filter.")
    b.metric("Gesamtzeit", format_hm(int(total * 60)), help="Summe aller Einträge (Gerätezeit).")
    c.metric("Tage mit Einträgen", days, help="An wie vielen Tagen etwas erfasst wurde.")
    d.metric(
        "Ø je Tag",
        format_hm(int(total / days * 60)) if days else "–",
        help="Durchschnittliche Zeit an einem Tag, an dem etwas erfasst wurde.",
    )
    e.metric(
        "Längster Eintrag",
        format_hm(int(longest * 60)),
        help=f"Der längste einzelne Eintrag. Davon unsicher: {format_hm(int(uncertain * 60))}.",
    )


def _block(
    definition: ch.ChartDef,
    frame: pd.DataFrame,
    hits: list[dict[str, Any]],
    tz: str,
    template: str,
    colors: dict[str, str],
) -> None:
    """One chart with its options, its table and the entries behind a click."""
    with st.container(border=True):
        st.subheader(definition.title)
        st.caption(definition.about)
        chosen: dict[str, str] = {}
        if definition.options:
            for column, option in zip(
                st.columns(len(definition.options)), definition.options, strict=True
            ):
                chosen[option.name] = column.selectbox(
                    option.label,
                    list(option.choices),
                    index=list(option.choices).index(option.default),
                    key=f"chart_{definition.key}_{option.name}",
                    format_func=option.choices.__getitem__,
                    help=option.help,
                )
        try:
            built = ch.build(definition, frame, template, colors, chosen)
        except ValueError:
            st.warning(
                "Für dieses Diagramm sind es zu viele Daten. Wählen Sie einen kleineren Zeitraum."
            )
            return
        figure_key = f"chart_fig_{definition.key}"
        if built.drill is None:
            st.plotly_chart(built.figure, width="stretch", key=figure_key)
        else:
            event = st.plotly_chart(
                built.figure,
                width="stretch",
                key=figure_key,
                on_select="rerun",
                selection_mode="points",
            )
            _behind_click(event, built, hits, tz, definition.key)
        if built.note:
            st.caption(built.note)
        with st.expander("Zahlen zu diesem Diagramm", key=f"chart_data_{definition.key}"):
            st.dataframe(built.table, hide_index=True, width="stretch")
            st.download_button(
                "Als CSV speichern",
                to_csv(
                    [{str(k): val for k, val in r.items()} for r in built.table.to_dict("records")]
                ),
                file_name=f"diagramm-{definition.key}.csv",
                mime="text/csv",
                key=f"chart_csv_{definition.key}",
                icon=":material/table:",
                help="Speichert die Zahlen dieses Diagramms (für Excel; Formeln werden "
                "entschärft).",
            )


def _behind_click(
    event: Any, built: ch.Chart, hits: list[dict[str, Any]], tz: str, key: str
) -> None:
    """List the entries behind the clicked points of a chart."""
    points = list(event.selection.points) if event and event.selection else []
    if not points or built.drill is None:
        return
    ids = built.drill([p["customdata"] for p in points if isinstance(p.get("customdata"), list)])
    chosen = [e for e in hits if e["id"] in ids]
    if not chosen:
        return
    total = sum(e["duration_seconds"] for e in chosen)
    st.markdown(
        f"**{len(chosen)} Einträge** hinter Ihrer Auswahl, zusammen **{format_hm(total)}**."
    )
    st.dataframe(
        entry_frame(chosen, tz),
        hide_index=True,
        width="stretch",
        key=f"chart_behind_{key}",
    )
