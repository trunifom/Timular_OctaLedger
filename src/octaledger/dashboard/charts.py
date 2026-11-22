"""Interactive charts for the time entries: pure builders from entries to Plotly figures (AP-59).

Every builder takes the entries as a pandas frame (see :func:`to_frame`) and returns a
:class:`Chart`: the Plotly figure, the **table behind it** (every chart is also readable as
numbers) and an optional ``drill`` function that turns the points a user clicked into the ids of
the entries behind them (the page then lists exactly those entries).

Rules
-----
* **Device time:** the entries are the tracker entries as they are stored; overlaps between
  trackers are *not* removed here (the page *Statistik* shows the personal work time).
* **Time of day** uses naive *local* timestamps (the display timezone) - an entry that crosses
  midnight (or an hour) is **split** where a chart is organised by day (or hour), so every minute
  is counted once, in the slot where it happened.
* **Colours:** activities and projects keep the colour of the catalog; everything else cycles
  through a colour-blind-safe palette. Meaning is never carried by colour alone (labels, legend,
  hover text).
* No Streamlit, no HTTP, no clock: ``now`` is passed in for running entries.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

#: Okabe-Ito based, readable for the common colour-vision deficiencies.
PALETTE: Final = (
    "#0072B2",
    "#E69F00",
    "#009E73",
    "#CC79A7",
    "#56B4E9",
    "#D55E00",
    "#F0E442",
    "#7A7A7A",
    "#8E44AD",
    "#2E8B57",
)
WEEKDAYS: Final = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
NO_PROJECT: Final = "kein Projekt"
NO_TAG: Final = "(ohne Tag)"
BY: Final = {"activity": "Tätigkeit", "project": "Projekt", "device": "Gerät"}
GRANULARITY: Final = {"day": "Tag", "week": "Woche", "month": "Monat"}
#: Protection against absurd inputs (split pieces per chart).
MAX_PIECES: Final = 400_000
MAX_TIMELINE: Final = 1500

Drill = Callable[[list[list[Any]]], set[str]]


@dataclass(frozen=True, slots=True)
class Chart:
    """A built chart.

    Attributes:
        figure: The Plotly figure (already styled with the theme template).
        table: The numbers behind the chart, ready to show and to export.
        drill: Turns the ``customdata`` of the clicked points into entry ids (``None`` = the
            chart cannot be clicked through).
        note: One honest sentence about what the chart does not show (may be empty).
    """

    figure: go.Figure
    table: pd.DataFrame
    drill: Drill | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class Option:
    """A choice offered above a chart (rendered as a select box)."""

    name: str
    label: str
    choices: dict[str, str]
    default: str
    help: str


@dataclass(frozen=True, slots=True)
class ChartDef:
    """A chart in the gallery."""

    key: str
    group: str
    title: str
    about: str
    build: Callable[..., Chart]
    options: tuple[Option, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------------------ the frame


def to_frame(entries: Iterable[dict[str, Any]], tz: str, now: datetime) -> pd.DataFrame:
    """The entries as one row each, with local times and the columns the charts group by.

    Args:
        entries: Journal entries as returned by the API.
        tz: Display timezone name.
        now: The current moment (end of running entries).
    """
    zone = ZoneInfo(tz)
    local_now = now.astimezone(zone).replace(tzinfo=None)
    rows: list[dict[str, Any]] = []
    for e in entries:
        start = datetime.fromisoformat(e["started_at"]).astimezone(zone).replace(tzinfo=None)
        end = (
            local_now
            if e["ended_at"] is None
            else datetime.fromisoformat(e["ended_at"]).astimezone(zone).replace(tzinfo=None)
        )
        end = max(end, start)
        monday = start.date() - timedelta(days=start.weekday())
        rows.append(
            {
                "id": e["id"],
                "activity": e["activity_name"],
                "project": e["project_name"] or NO_PROJECT,
                "device": e["device_alias"] or "von Hand",
                "tags": list(e.get("tags", [])),
                "start": pd.Timestamp(start),
                "end": pd.Timestamp(end),
                "minutes": (end - start).total_seconds() / 60,
                "day": start.date().isoformat(),
                "week": monday.isoformat(),
                "month": f"{start.year:04d}-{start.month:02d}",
                "weekday": start.weekday(),
                "start_hour": start.hour + start.minute / 60,
                "uncertain": e["quality"] == "uncertain",
            }
        )
    columns = [
        "id",
        "activity",
        "project",
        "device",
        "tags",
        "start",
        "end",
        "minutes",
        "day",
        "week",
        "month",
        "weekday",
        "start_hour",
        "uncertain",
    ]
    return pd.DataFrame(rows, columns=columns)


def colors_for(
    frame: pd.DataFrame, catalog: dict[str, dict[str, str]] | None = None
) -> dict[str, str]:
    """One colour per name: the catalog colour where there is one, the palette otherwise."""
    result: dict[str, str] = {}
    names: list[str] = []
    for column in ("activity", "project", "device"):
        names += [n for n in frame[column].unique() if n not in names]
    for tags in frame["tags"]:
        names += [t for t in tags if t not in names]
    lookup: dict[str, str] = {}
    for part in (catalog or {}).values():
        lookup.update(part)
    spare = iter(PALETTE * 20)
    for name in names:
        result[name] = lookup.get(name) or next(spare)
    return result


def hm(minutes: float) -> str:
    """``185`` -> ``3 h 05 min``."""
    whole = int(round(minutes))
    return f"{whole // 60} h {whole % 60:02d} min"


def _style(fig: go.Figure, template: str, *, title_y: str | None = None) -> go.Figure:
    fig.update_layout(
        template=template,
        margin={"t": 30, "l": 10, "r": 10, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        hoverlabel={"namelength": -1},
    )
    if title_y:
        fig.update_yaxes(title_text=title_y)
    return fig


def _ids(frame: pd.DataFrame, columns: tuple[str, ...], points: list[list[Any]]) -> set[str]:
    """Ids of the entries whose ``columns`` equal the clicked points' values."""
    found: set[str] = set()
    for values in points:
        if not isinstance(values, list) or len(values) < len(columns):
            continue
        mask = pd.Series(True, index=frame.index)
        for column, value in zip(columns, values, strict=False):
            mask &= frame[column].astype(str) == str(value)
        found.update(frame.loc[mask, "id"])
    return found


# ------------------------------------------------------------------- splitting into slots


def split_pieces(frame: pd.DataFrame, unit: str) -> pd.DataFrame:
    """Cut every entry at local midnight (``unit="day"``) or at every full hour (``"hour"``).

    Returns one row per piece: ``id``, ``slot`` (start of the day/hour), ``minutes``, plus the
    grouping columns of the entry. A piece never leaves its slot, so sums per slot are exact.

    Raises:
        ValueError: If the entries would produce an absurd number of pieces.
    """
    step = timedelta(days=1) if unit == "day" else timedelta(hours=1)
    rows: list[dict[str, Any]] = []
    for rid, start, stop, activity, project, device in zip(
        frame["id"].tolist(),
        frame["start"].tolist(),
        frame["end"].tolist(),
        frame["activity"].tolist(),
        frame["project"].tolist(),
        frame["device"].tolist(),
        strict=True,
    ):
        cursor: datetime = start.to_pydatetime()
        end: datetime = stop.to_pydatetime()
        while cursor < end:
            floor = (
                cursor.replace(hour=0, minute=0, second=0, microsecond=0)
                if unit == "day"
                else cursor.replace(minute=0, second=0, microsecond=0)
            )
            boundary = min(end, floor + step)
            rows.append(
                {
                    "id": rid,
                    "slot": pd.Timestamp(floor),
                    "minutes": (boundary - cursor).total_seconds() / 60,
                    "activity": activity,
                    "project": project,
                    "device": device,
                }
            )
            cursor = boundary
            if len(rows) > MAX_PIECES:
                raise ValueError("too many pieces")
    return pd.DataFrame(
        rows, columns=["id", "slot", "minutes", "activity", "project", "device"]
    ).astype({"minutes": float})


def _period_of(slot: pd.Series, granularity: str) -> Any:
    if granularity == "week":
        return (slot - pd.to_timedelta(slot.dt.day_of_week, unit="D")).dt.strftime("%Y-%m-%d")
    if granularity == "month":
        return slot.dt.strftime("%Y-%m")
    return slot.dt.strftime("%Y-%m-%d")


# ------------------------------------------------------------------------------- builders


def per_period(
    frame: pd.DataFrame, template: str, colors: dict[str, str], *, granularity: str, by: str
) -> Chart:
    """Stacked bars: hours per day/week/month, split by activity, project or device."""
    pieces = split_pieces(frame, "day")
    pieces["period"] = _period_of(pieces["slot"], granularity)
    grouped = pieces.groupby(["period", by])["minutes"].sum().reset_index()
    grouped["hours"] = grouped["minutes"] / 60
    fig = go.Figure()
    for name, part in grouped.groupby(by):
        fig.add_bar(
            x=part["period"],
            y=part["hours"],
            name=str(name),
            marker_color=colors.get(str(name)),
            customdata=[[p, name] for p in part["period"]],
            hovertemplate="%{x}<br>" + str(name) + ": %{y:.2f} h<extra></extra>",
        )
    fig.update_layout(barmode="stack", xaxis={"type": "category"}, hovermode="x unified")
    table = (
        grouped.pivot(index="period", columns=by, values="hours")
        .fillna(0)
        .round(2)
        .assign(Summe=lambda t: t.sum(axis=1).round(2))
        .reset_index()
        .rename(columns={"period": GRANULARITY[granularity]})
    )
    column = {"day": "day", "week": "week", "month": "month"}[granularity]

    def drill(points: list[list[Any]]) -> set[str]:
        """Entries that start in a clicked period with the clicked group."""
        return _ids(frame, (column, by), points)

    return Chart(_style(fig, template, title_y="Stunden"), table, drill)


def share(frame: pd.DataFrame, template: str, colors: dict[str, str], *, by: str) -> Chart:
    """Donut: share of the total time per activity, project or device."""
    grouped = (
        frame.groupby(by)["minutes"].sum().reset_index().sort_values("minutes", ascending=False)
    )
    fig = go.Figure(
        go.Pie(
            labels=grouped[by],
            values=grouped["minutes"] / 60,
            hole=0.5,
            sort=False,
            marker={"colors": [colors.get(n) for n in grouped[by]]},
            customdata=[[n] for n in grouped[by]],
            textinfo="label+percent",
            hovertemplate="%{label}: %{value:.2f} h (%{percent})<extra></extra>",
        )
    )
    table = pd.DataFrame(
        {
            BY[by]: grouped[by],
            "Zeit": [hm(m) for m in grouped["minutes"]],
            "Stunden": (grouped["minutes"] / 60).round(2),
            "Anteil": (grouped["minutes"] / grouped["minutes"].sum()).map("{:.0%}".format),
        }
    )

    def drill(points: list[list[Any]]) -> set[str]:
        """Entries of the clicked slice."""
        return _ids(frame, (by,), points)

    return Chart(_style(fig, template), table, drill)


def sunburst(frame: pd.DataFrame, template: str, colors: dict[str, str]) -> Chart:
    """Sunburst: activity in the middle, projects around it (click to zoom in)."""
    grouped = frame.groupby(["activity", "project"])["minutes"].sum().reset_index()
    grouped["hours"] = (grouped["minutes"] / 60).round(2)
    fig = px.sunburst(
        grouped,
        path=["activity", "project"],
        values="hours",
        color="activity",
        color_discrete_map=colors,
    )
    fig.update_traces(hovertemplate="%{label}: %{value:.2f} h<extra></extra>")
    table = grouped.rename(
        columns={"activity": "Tätigkeit", "project": "Projekt", "hours": "Stunden"}
    ).drop(columns="minutes")
    return Chart(_style(fig, template), table, note="Ein Klick zoomt hinein, die Mitte zurück.")


def treemap(frame: pd.DataFrame, template: str, colors: dict[str, str]) -> Chart:
    """Treemap: area = time; project, then activity."""
    grouped = frame.groupby(["project", "activity"])["minutes"].sum().reset_index()
    grouped["hours"] = (grouped["minutes"] / 60).round(2)
    fig = px.treemap(
        grouped,
        path=["project", "activity"],
        values="hours",
        color="activity",
        color_discrete_map=colors,
    )
    fig.update_traces(hovertemplate="%{label}: %{value:.2f} h<extra></extra>")
    table = grouped.rename(
        columns={"activity": "Tätigkeit", "project": "Projekt", "hours": "Stunden"}
    ).drop(columns="minutes")
    return Chart(_style(fig, template), table, note="Ein Klick zoomt hinein.")


def sankey(frame: pd.DataFrame, template: str, colors: dict[str, str]) -> Chart:
    """Flow diagram: from activities to projects, width = time."""
    grouped = frame.groupby(["activity", "project"])["minutes"].sum().reset_index()
    activities = list(dict.fromkeys(grouped["activity"]))
    projects = list(dict.fromkeys(grouped["project"]))
    labels = [*activities, *projects]
    index = {name: i for i, name in enumerate(activities)} | {
        name: len(activities) + i for i, name in enumerate(projects)
    }
    fig = go.Figure(
        go.Sankey(
            node={
                "label": labels,
                "pad": 14,
                "color": [colors.get(n, "#7A7A7A") for n in labels],
            },
            link={
                "source": [index[a] for a in grouped["activity"]],
                "target": [index[p] for p in grouped["project"]],
                "value": (grouped["minutes"] / 60).round(2),
                "hovertemplate": "%{source.label} → %{target.label}: %{value:.2f} h<extra></extra>",
            },
        )
    )
    table = pd.DataFrame(
        {
            "Tätigkeit": grouped["activity"],
            "Projekt": grouped["project"],
            "Stunden": (grouped["minutes"] / 60).round(2),
        }
    )
    return Chart(_style(fig, template), table, note="Linke Seite: Tätigkeiten, rechte: Projekte.")


def tag_bars(frame: pd.DataFrame, template: str, colors: dict[str, str]) -> Chart:
    """Horizontal bars: time per tag (an entry with two tags counts for both)."""
    exploded = frame.assign(tag=frame["tags"].map(lambda t: t or [NO_TAG])).explode("tag")
    grouped = exploded.groupby("tag")["minutes"].sum().reset_index().sort_values("minutes")
    fig = go.Figure(
        go.Bar(
            x=grouped["minutes"] / 60,
            y=grouped["tag"],
            orientation="h",
            marker_color=[colors.get(t, "#7A7A7A") for t in grouped["tag"]],
            customdata=[[t] for t in grouped["tag"]],
            hovertemplate="%{y}: %{x:.2f} h<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Stunden")
    table = pd.DataFrame(
        {
            "Tag": grouped["tag"][::-1],
            "Zeit": [hm(m) for m in grouped["minutes"][::-1]],
            "Stunden": (grouped["minutes"][::-1] / 60).round(2),
        }
    )

    def drill(points: list[list[Any]]) -> set[str]:
        """Entries that carry a clicked tag (or none, for the ``ohne Tag`` bar)."""
        wanted = {str(p[0]) for p in points if p}
        return {
            rid
            for rid, row_tags in zip(frame["id"].tolist(), frame["tags"].tolist(), strict=True)
            if wanted & set(row_tags or [NO_TAG])
        }

    return Chart(
        _style(fig, template),
        table,
        drill,
        note="Ein Eintrag mit mehreren Tags zählt bei jedem Tag voll; die Summe kann größer sein "
        "als die Gesamtzeit.",
    )


def heat_weekday_hour(frame: pd.DataFrame, template: str, colors: dict[str, str]) -> Chart:
    """Heat map: hours per weekday and hour of the day (when do you work?)."""
    pieces = split_pieces(frame, "hour")
    pieces["weekday"] = pieces["slot"].dt.day_of_week
    pieces["hour"] = pieces["slot"].dt.hour
    grid = (
        pieces.groupby(["weekday", "hour"])["minutes"]
        .sum()
        .unstack(fill_value=0)
        .reindex(index=range(7), columns=range(24), fill_value=0)
    )
    fig = go.Figure(
        go.Heatmap(
            z=(grid / 60).round(2).to_numpy(),
            x=[f"{h:02d}" for h in range(24)],
            y=list(WEEKDAYS),
            colorscale="Blues",
            colorbar={"title": "Stunden"},
            customdata=[[[d, h] for h in range(24)] for d in range(7)],
            hovertemplate="%{y}, %{x} Uhr: %{z:.2f} h<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Uhrzeit (Stunde)", type="category")
    table = (grid / 60).round(2)
    table.index = pd.Index(list(WEEKDAYS), name="Wochentag")
    table.columns = [f"{h:02d}" for h in range(24)]

    def drill(points: list[list[Any]]) -> set[str]:
        """Entries that have time in a clicked weekday/hour cell."""
        found: set[str] = set()
        for p in points:
            if isinstance(p, list) and len(p) >= 2:
                hit = pieces[(pieces["weekday"] == int(p[0])) & (pieces["hour"] == int(p[1]))]
                found.update(hit["id"])
        return found

    return Chart(_style(fig, template), table.reset_index(), drill)


def calendar_heat(frame: pd.DataFrame, template: str, colors: dict[str, str]) -> Chart:
    """Calendar heat map: one cell per day, columns are weeks (like a contribution calendar)."""
    pieces = split_pieces(frame, "day")
    per_day = pieces.groupby("slot")["minutes"].sum()
    first = per_day.index.min().normalize()
    last = per_day.index.max().normalize()
    days = pd.date_range(first - pd.Timedelta(days=first.weekday()), last, freq="D")
    values = per_day.reindex(days, fill_value=0) / 60
    weeks = (days - pd.to_timedelta(days.day_of_week, unit="D")).strftime("%Y-%m-%d")
    frame_days = pd.DataFrame(
        {"week": weeks, "weekday": days.day_of_week, "hours": values.to_numpy(), "day": days}
    )
    grid = frame_days.pivot(index="weekday", columns="week", values="hours").reindex(range(7))
    texts = frame_days.pivot(index="weekday", columns="week", values="day").reindex(range(7))
    fig = go.Figure(
        go.Heatmap(
            z=grid.round(2).to_numpy(),
            x=list(grid.columns),
            y=list(WEEKDAYS),
            colorscale="Greens",
            colorbar={"title": "Stunden"},
            customdata=[
                [[pd.Timestamp(d).strftime("%Y-%m-%d")] if pd.notna(d) else [""] for d in row]
                for row in texts.to_numpy()
            ],
            hovertemplate="%{customdata[0]}: %{z:.2f} h<extra></extra>",
            xgap=2,
            ygap=2,
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Woche (Montag)", type="category")
    table = pd.DataFrame(
        {
            "Tag": frame_days["day"].dt.strftime("%Y-%m-%d"),
            "Wochentag": [WEEKDAYS[d] for d in frame_days["weekday"]],
            "Stunden": frame_days["hours"].round(2),
        }
    )
    table = table[table["Stunden"] > 0]

    def drill(points: list[list[Any]]) -> set[str]:
        """Entries with time on a clicked day."""
        wanted = {str(p[0]) for p in points if p}
        return set(pieces[pieces["slot"].dt.strftime("%Y-%m-%d").isin(wanted)]["id"])

    return Chart(_style(fig, template), table, drill)


def weekday_bars(frame: pd.DataFrame, template: str, colors: dict[str, str], *, mode: str) -> Chart:
    """Bars per weekday: the sum of hours or the average per day that had entries."""
    pieces = split_pieces(frame, "day")
    pieces["weekday"] = pieces["slot"].dt.day_of_week
    sums = pieces.groupby("weekday")["minutes"].sum().reindex(range(7), fill_value=0)
    days = pieces.groupby("weekday")["slot"].nunique().reindex(range(7), fill_value=0)
    hours = sums / 60
    values = hours if mode == "sum" else (hours / days.where(days > 0)).fillna(0)
    fig = go.Figure(
        go.Bar(
            x=list(WEEKDAYS),
            y=values.round(2),
            customdata=[[d] for d in range(7)],
            marker_color=PALETTE[0],
            hovertemplate="%{x}: %{y:.2f} h<extra></extra>",
        )
    )
    label = "Stunden gesamt" if mode == "sum" else "Ø Stunden pro Tag mit Einträgen"
    table = pd.DataFrame(
        {
            "Wochentag": list(WEEKDAYS),
            "Tage mit Einträgen": days.to_numpy(),
            "Stunden gesamt": hours.round(2).to_numpy(),
            "Ø pro Tag": (hours / days.where(days > 0)).fillna(0).round(2).to_numpy(),
        }
    )

    def drill(points: list[list[Any]]) -> set[str]:
        """Entries with time on a clicked weekday."""
        wanted = {int(p[0]) for p in points if p}
        return set(pieces[pieces["weekday"].isin(wanted)]["id"])

    return Chart(_style(fig, template, title_y=label), table, drill)


def scatter_start_duration(
    frame: pd.DataFrame, template: str, colors: dict[str, str], *, by: str
) -> Chart:
    """Scatter: start time of day against duration; every dot is one entry."""
    shown = frame.assign(
        Dauer_h=(frame["minutes"] / 60).round(2),
        Beginn=frame["start_hour"].round(2),
        Dauer=[hm(m) for m in frame["minutes"]],
        Tag=frame["day"],
    )
    fig = px.scatter(
        shown,
        x="Beginn",
        y="Dauer_h",
        color=by,
        color_discrete_map=colors,
        custom_data=["id"],
        hover_data={"Tag": True, "Dauer": True, "Beginn": ":.2f", "Dauer_h": False, by: False},
    )
    fig.update_xaxes(title_text="Beginn (Uhrzeit, Stunde)", range=[0, 24], dtick=3)
    fig.update_yaxes(title_text="Dauer (Stunden)")
    table = shown[["Tag", "Beginn", "Dauer", by]].rename(columns={by: BY[by]})

    def drill(points: list[list[Any]]) -> set[str]:
        """The clicked entries."""
        return {str(p[0]) for p in points if p}

    return Chart(_style(fig, template), table, drill)


def matrix(frame: pd.DataFrame, template: str, colors: dict[str, str]) -> Chart:
    """Heat map: hours per project (rows) and activity (columns)."""
    grid = frame.pivot_table(
        index="project", columns="activity", values="minutes", aggfunc="sum", fill_value=0
    )
    fig = go.Figure(
        go.Heatmap(
            z=(grid / 60).round(2).to_numpy(),
            x=list(grid.columns),
            y=list(grid.index),
            colorscale="Purples",
            colorbar={"title": "Stunden"},
            customdata=[[[p, a] for a in grid.columns] for p in grid.index],
            hovertemplate="%{y} · %{x}: %{z:.2f} h<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    table = (grid / 60).round(2).reset_index().rename(columns={"project": "Projekt"})

    def drill(points: list[list[Any]]) -> set[str]:
        """Entries of a clicked project/activity cell."""
        return _ids(frame, ("project", "activity"), points)

    return Chart(_style(fig, template), table, drill)


def duration_hist(
    frame: pd.DataFrame, template: str, colors: dict[str, str], *, bins: int
) -> Chart:
    """Histogram: how long are the entries?"""
    minutes = frame["minutes"]
    fig = go.Figure(
        go.Histogram(
            x=minutes,
            nbinsx=bins,
            marker_color=PALETTE[0],
            hovertemplate="%{x} min: %{y} Einträge<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Dauer (Minuten)")
    fig.update_yaxes(title_text="Anzahl Einträge")
    counts = pd.cut(minutes, bins=bins)
    binned = counts.value_counts().sort_index()
    table = pd.DataFrame(
        {
            "Von (min)": [round(float(i.left), 1) for i in binned.index],
            "Bis (min)": [round(float(i.right), 1) for i in binned.index],
            "Einträge": binned.to_numpy(),
        }
    )
    return Chart(
        _style(fig, template),
        table,
        note=f"Mittelwert {hm(float(minutes.mean()))}, Median {hm(float(minutes.median()))}.",
    )


def duration_box(frame: pd.DataFrame, template: str, colors: dict[str, str], *, by: str) -> Chart:
    """Box plot: spread of the entry lengths per activity, project or device."""
    fig = go.Figure()
    for name, part in frame.groupby(by):
        fig.add_trace(
            go.Box(
                y=part["minutes"],
                name=str(name),
                marker_color=colors.get(str(name)),
                boxmean=True,
                hovertemplate=str(name) + ": %{y:.0f} min<extra></extra>",
            )
        )
    fig.update_yaxes(title_text="Dauer eines Eintrags (Minuten)")
    stats = frame.groupby(by)["minutes"].describe().round(1)
    table = stats.rename(
        columns={
            "count": "Einträge",
            "mean": "Mittel (min)",
            "std": "Streuung",
            "min": "Kürzester",
            "25%": "25 %",
            "50%": "Median",
            "75%": "75 %",
            "max": "Längster",
        }
    ).reset_index()
    return Chart(
        _style(fig, template),
        table.rename(columns={by: BY[by]}),
        note="Kasten = mittlere 50 %, Strich = Median, Raute = Mittelwert.",
    )


def timeline(frame: pd.DataFrame, template: str, colors: dict[str, str], *, by: str) -> Chart:
    """Gantt-like time line: one bar per entry on a time axis (zoom and pan)."""
    shown = frame.sort_values("start").tail(MAX_TIMELINE)
    labelled = shown.assign(Dauer=[hm(m) for m in shown["minutes"]])
    fig = px.timeline(
        labelled,
        x_start="start",
        x_end="end",
        y=by,
        color=by,
        color_discrete_map=colors,
        custom_data=["id"],
        hover_data={"Dauer": True, "start": "|%d.%m.%Y %H:%M", "end": "|%d.%m.%Y %H:%M", by: False},
    )
    fig.update_yaxes(title_text=BY[by])
    fig.update_xaxes(rangeslider_visible=True)
    table = labelled[["start", "end", "Dauer", "activity", "project"]].rename(
        columns={"start": "Beginn", "end": "Ende", "activity": "Tätigkeit", "project": "Projekt"}
    )

    def drill(points: list[list[Any]]) -> set[str]:
        """The clicked entries."""
        return {str(p[0]) for p in points if p}

    note = (
        f"Gezeigt werden die neuesten {MAX_TIMELINE} von {len(frame)} Einträgen."
        if len(frame) > MAX_TIMELINE
        else "Mit dem Regler unten oder per Ziehen im Bild zoomen."
    )
    return Chart(_style(fig, template), table, drill, note)


def cumulative(frame: pd.DataFrame, template: str, colors: dict[str, str], *, by: str) -> Chart:
    """Lines: the hours added up over time, one line per activity, project or device."""
    pieces = split_pieces(frame, "day")
    pieces["day"] = pieces["slot"].dt.strftime("%Y-%m-%d")
    grouped = pieces.groupby(["day", by])["minutes"].sum().reset_index()
    days = pd.date_range(grouped["day"].min(), grouped["day"].max(), freq="D").strftime("%Y-%m-%d")
    fig = go.Figure()
    columns: dict[str, Any] = {"Tag": list(days)}
    for name, part in grouped.groupby(by):
        series = (part.set_index("day")["minutes"].reindex(days, fill_value=0).cumsum() / 60).round(
            2
        )
        columns[str(name)] = series.to_numpy()
        fig.add_scatter(
            x=list(days),
            y=series,
            name=str(name),
            mode="lines",
            line={"shape": "hv", "color": colors.get(str(name))},
            hovertemplate="%{x}: %{y:.2f} h<extra>" + str(name) + "</extra>",
        )
    fig.update_xaxes(rangeslider_visible=True, type="date")
    return Chart(_style(fig, template, title_y="Stunden (aufsummiert)"), pd.DataFrame(columns))


def trend(frame: pd.DataFrame, template: str, colors: dict[str, str], *, window: int) -> Chart:
    """Bars per day with a moving average (the trend of your daily hours)."""
    pieces = split_pieces(frame, "day")
    pieces["day"] = pieces["slot"].dt.normalize()
    per_day = pieces.groupby("day")["minutes"].sum() / 60
    days = pd.date_range(per_day.index.min(), per_day.index.max(), freq="D")
    per_day = per_day.reindex(days, fill_value=0)
    average = per_day.rolling(window, min_periods=1).mean()
    fig = go.Figure()
    fig.add_bar(
        x=per_day.index,
        y=per_day.round(2),
        name="Stunden pro Tag",
        marker_color=PALETTE[4],
        customdata=[[d.strftime("%Y-%m-%d")] for d in per_day.index],
        hovertemplate="%{x|%d.%m.%Y}: %{y:.2f} h<extra></extra>",
    )
    fig.add_scatter(
        x=average.index,
        y=average.round(2),
        name=f"Ø der letzten {window} Tage",
        mode="lines",
        line={"color": PALETTE[5], "width": 3},
        hovertemplate="%{x|%d.%m.%Y}: Ø %{y:.2f} h<extra></extra>",
    )
    fig.update_xaxes(rangeslider_visible=True)
    table = pd.DataFrame(
        {
            "Tag": pd.DatetimeIndex(per_day.index).strftime("%Y-%m-%d"),
            "Stunden": per_day.round(2).to_numpy(),
            f"Ø {window} Tage": average.round(2).to_numpy(),
        }
    )

    def drill(points: list[list[Any]]) -> set[str]:
        """Entries with time on a clicked day."""
        wanted = {str(p[0]) for p in points if p}
        return set(pieces[pieces["day"].dt.strftime("%Y-%m-%d").isin(wanted)]["id"])

    return Chart(_style(fig, template, title_y="Stunden"), table, drill)


def first_last(frame: pd.DataFrame, template: str, colors: dict[str, str]) -> Chart:
    """Per day: when did the first entry start and when did the last one end?"""
    per_day = frame.groupby("day").agg(first=("start", "min"), last=("end", "max"))
    first_hour = per_day["first"].dt.hour + per_day["first"].dt.minute / 60
    last_hour = (per_day["last"] - per_day["last"].dt.normalize()).dt.total_seconds() / 3600
    # an entry that ends after midnight would otherwise jump to the top of the chart
    last_hour = last_hour.where(per_day["last"].dt.strftime("%Y-%m-%d") == per_day.index, 24)
    fig = go.Figure()
    fig.add_scatter(
        x=per_day.index,
        y=last_hour.round(2),
        name="Letztes Ende",
        mode="lines+markers",
        line={"color": PALETTE[5]},
        hovertemplate="%{x}: Ende %{y:.2f} Uhr<extra></extra>",
    )
    fig.add_scatter(
        x=per_day.index,
        y=first_hour.round(2),
        name="Erster Beginn",
        mode="lines+markers",
        line={"color": PALETTE[0]},
        fill="tonexty",
        fillcolor="rgba(0,114,178,0.15)",
        customdata=[[d] for d in per_day.index],
        hovertemplate="%{x}: Beginn %{y:.2f} Uhr<extra></extra>",
    )
    fig.update_yaxes(title_text="Uhrzeit (Stunde)", range=[0, 24], dtick=3)
    fig.update_xaxes(type="category", rangeslider_visible=True)
    table = pd.DataFrame(
        {
            "Tag": per_day.index,
            "Erster Beginn": per_day["first"].dt.strftime("%H:%M"),
            "Letztes Ende": per_day["last"].dt.strftime("%H:%M"),
            "Spanne": [
                hm((b - a).total_seconds() / 60)
                for a, b in zip(per_day["first"], per_day["last"], strict=True)
            ],
        }
    )

    def drill(points: list[list[Any]]) -> set[str]:
        """Entries that start on a clicked day."""
        return _ids(frame, ("day",), points)

    return Chart(
        _style(fig, template),
        table,
        drill,
        note="Die Fläche ist die Spanne vom ersten Beginn bis zum letzten Ende, Pausen "
        "eingeschlossen.",
    )


# ----------------------------------------------------------------------------- the gallery

_BY = Option("by", "Aufteilen nach", BY, "activity", "Wonach die Zeit aufgeteilt wird.")
_GRAN = Option(
    "granularity",
    "Zeitabschnitt",
    GRANULARITY,
    "day",
    "Ob je Tag, je Woche oder je Monat zusammengefasst wird.",
)

GROUPS: Final = ("Verlauf", "Anteile", "Muster", "Dauer", "Zeitstrahl")

CHARTS: Final = (
    ChartDef(
        "per_period",
        "Verlauf",
        "Stunden je Tag, Woche oder Monat",
        "Gestapelte Balken: wie viel Zeit pro Abschnitt, aufgeteilt nach Tätigkeit, Projekt oder "
        "Gerät. Ein Klick auf einen Balkenabschnitt zeigt die Einträge dahinter.",
        per_period,
        (_GRAN, _BY),
    ),
    ChartDef(
        "trend",
        "Verlauf",
        "Tagesstunden mit Durchschnitt",
        "Balken je Tag und eine Linie mit dem gleitenden Durchschnitt: Wird es mehr oder "
        "weniger? Mit dem Regler unten zoomen.",
        trend,
        (
            Option(
                "window",
                "Durchschnitt über",
                {"3": "3 Tage", "7": "7 Tage", "14": "14 Tage", "30": "30 Tage"},
                "7",
                "Über wie viele Tage der Durchschnitt gebildet wird.",
            ),
        ),
    ),
    ChartDef(
        "cumulative",
        "Verlauf",
        "Aufsummierte Stunden",
        "Linien, die die Stunden über die Zeit aufaddieren: Wie schnell wächst ein Projekt?",
        cumulative,
        (_BY,),
    ),
    ChartDef(
        "first_last",
        "Verlauf",
        "Arbeitsbeginn und -ende je Tag",
        "Wann begann der erste Eintrag, wann endete der letzte? Zeigt Ihre Arbeitszeitfenster.",
        first_last,
    ),
    ChartDef(
        "share",
        "Anteile",
        "Anteile (Ring)",
        "Wie verteilt sich die Zeit? Ein Klick auf ein Stück zeigt die Einträge.",
        share,
        (_BY,),
    ),
    ChartDef(
        "sunburst",
        "Anteile",
        "Sonnenstrahl: Tätigkeit → Projekt",
        "Innen die Tätigkeiten, außen die Projekte darin.",
        sunburst,
    ),
    ChartDef(
        "treemap",
        "Anteile",
        "Treemap: Projekt → Tätigkeit",
        "Fläche = Zeit. Gut für viele Projekte.",
        treemap,
    ),
    ChartDef(
        "sankey",
        "Anteile",
        "Fluss: Tätigkeit → Projekt",
        "Breite = Zeit: Wohin fließt die Zeit jeder Tätigkeit?",
        sankey,
    ),
    ChartDef(
        "tags",
        "Anteile",
        "Zeit je Tag",
        "Wie viel Zeit trägt jeder Tag (z. B. Person oder Vorgang)?",
        tag_bars,
    ),
    ChartDef(
        "heat",
        "Muster",
        "Wärmekarte: Wochentag × Uhrzeit",
        "Wann arbeiten Sie? Dunkel = viel Zeit. Ein Klick auf ein Feld zeigt die Einträge.",
        heat_weekday_hour,
    ),
    ChartDef(
        "calendar",
        "Muster",
        "Kalender-Wärmekarte",
        "Ein Feld je Tag, Spalten sind Wochen. Dunkel = viele Stunden.",
        calendar_heat,
    ),
    ChartDef(
        "weekday",
        "Muster",
        "Wochentage im Vergleich",
        "Welcher Wochentag ist der längste? Summe oder Durchschnitt je Tag mit Einträgen.",
        weekday_bars,
        (
            Option(
                "mode",
                "Wert",
                {"sum": "Summe", "average": "Durchschnitt je Tag"},
                "sum",
                "Gesamtzeit oder Durchschnitt pro Tag, an dem etwas erfasst wurde.",
            ),
        ),
    ),
    ChartDef(
        "matrix",
        "Muster",
        "Projekt × Tätigkeit",
        "Welche Tätigkeiten stecken in welchem Projekt? Ein Klick auf ein Feld zeigt die Einträge.",
        matrix,
    ),
    ChartDef(
        "hist",
        "Dauer",
        "Histogramm der Eintragslängen",
        "Wie lang sind Ihre Einträge: viele kurze oder wenige lange?",
        duration_hist,
        (
            Option(
                "bins",
                "Feinheit",
                {"10": "grob (10)", "20": "mittel (20)", "40": "fein (40)"},
                "20",
                "In wie viele Längenklassen die Einträge eingeteilt werden.",
            ),
        ),
    ),
    ChartDef(
        "box",
        "Dauer",
        "Boxplot der Eintragslängen",
        "Streuung der Längen je Tätigkeit, Projekt oder Gerät: Ausreißer fallen auf.",
        duration_box,
        (_BY,),
    ),
    ChartDef(
        "scatter",
        "Dauer",
        "Streudiagramm: Beginn × Dauer",
        "Jeder Punkt ist ein Eintrag: wann er begann und wie lange er dauerte. Ein Klick "
        "zeigt ihn.",
        scatter_start_duration,
        (_BY,),
    ),
    ChartDef(
        "timeline",
        "Zeitstrahl",
        "Zeitstrahl aller Einträge",
        "Jeder Eintrag als Balken auf der Zeitachse (wie ein Gantt-Diagramm). Zoomen und "
        "Verschieben mit der Maus.",
        timeline,
        (_BY,),
    ),
)

#: ``key -> definition``
BY_KEY: Final = {c.key: c for c in CHARTS}


def build(
    chart: ChartDef,
    frame: pd.DataFrame,
    template: str,
    colors: dict[str, str],
    chosen: dict[str, str],
) -> Chart:
    """Build one gallery chart with the user's choices.

    Args:
        chart: The definition.
        frame: The entries (not empty).
        template: Plotly template name of the theme.
        colors: Colour per name (see :func:`colors_for`).
        chosen: The option values (option name -> key of the choice).
    """
    args: dict[str, Any] = {o.name: chosen.get(o.name, o.default) for o in chart.options}
    if "bins" in args:
        args["bins"] = int(args["bins"])
    if "window" in args:
        args["window"] = int(args["window"])
    return chart.build(frame, template, colors, **args)
