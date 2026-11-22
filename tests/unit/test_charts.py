"""The chart builders: every chart builds, numbers add up, clicks map back to entries (AP-59)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from octaledger.dashboard import charts as ch

UTC = UTC
NOW = datetime(2026, 3, 20, 12, 0, tzinfo=UTC)
TZ = "Europe/Zurich"  # UTC+1 in March before the DST change: 08:00 UTC is 09:00 local


def entry(
    key: str,
    start: datetime,
    minutes: int | None,
    activity: str = "Meeting",
    project: str | None = None,
    tags: list[str] | None = None,
    device: str | None = None,
    quality: str = "confirmed",
) -> dict[str, Any]:
    end = None if minutes is None else (start + timedelta(minutes=minutes)).isoformat()
    return {
        "id": key,
        "activity_name": activity,
        "project_name": project,
        "device_alias": device,
        "started_at": start.isoformat(),
        "ended_at": end,
        "quality": quality,
        "tags": tags or [],
    }


def sample() -> list[dict[str, Any]]:
    monday = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)  # a Monday, 09:00 local
    return [
        entry("a", monday, 90, "Meeting", "Alpha", ["PERSON-B"], "Büro"),
        entry("b", monday + timedelta(hours=3), 120, "Code", "Alpha", ["TAG-1", "PERSON-B"]),
        entry("c", monday + timedelta(days=1), 45, "Code", None, [], None, "uncertain"),
        # crosses local midnight: 22:30 local Wednesday to 01:30 local Thursday
        entry("d", monday + timedelta(days=2, hours=13, minutes=30), 180, "Review", "Beta"),
        entry(
            "e", monday + timedelta(days=18), None, "Code", "Alpha"
        ),  # running since Friday 09:00
    ]


@pytest.fixture
def frame() -> pd.DataFrame:
    return ch.to_frame(sample(), TZ, NOW)


@pytest.fixture
def colors(frame: pd.DataFrame) -> dict[str, str]:
    return ch.colors_for(frame, {"activities": {"Meeting": "#112233"}})


def test_the_frame_has_local_times_and_running_entries_end_now(frame: pd.DataFrame) -> None:
    first = frame.iloc[0]
    assert first["start"] == pd.Timestamp("2026-03-02 09:00") and first["weekday"] == 0
    assert first["day"] == "2026-03-02" and first["week"] == "2026-03-02"
    assert first["minutes"] == 90 and first["project"] == "Alpha"
    assert frame.iloc[2]["project"] == ch.NO_PROJECT and frame.iloc[2]["device"] == "von Hand"
    running = frame.iloc[4]
    assert (
        running["end"] == pd.Timestamp("2026-03-20 13:00")
        and running["minutes"] == 240
        and running["minutes"] > 0
    )
    assert bool(frame.iloc[2]["uncertain"]) and not bool(frame.iloc[0]["uncertain"])


def test_colors_prefer_the_catalog_and_are_unique_otherwise(
    frame: pd.DataFrame, colors: dict[str, str]
) -> None:
    assert colors["Meeting"] == "#112233"
    others = [v for k, v in colors.items() if k != "Meeting"]
    assert len(others) == len(set(others))


def test_hm_formats_minutes() -> None:
    assert ch.hm(185) == "3 h 05 min" and ch.hm(0) == "0 h 00 min"


def test_pieces_cut_at_midnight_and_hours_and_keep_every_minute(frame: pd.DataFrame) -> None:
    days = ch.split_pieces(frame, "day")
    assert days["minutes"].sum() == pytest.approx(frame["minutes"].sum())
    night = days[days["id"] == "d"].sort_values("slot")
    assert list(night["minutes"]) == [90.0, 90.0]  # 22:30-24:00 and 00:00-01:30
    hours = ch.split_pieces(frame, "hour")
    assert hours["minutes"].sum() == pytest.approx(frame["minutes"].sum())
    assert hours["minutes"].max() <= 60


def test_every_chart_builds_with_every_option(frame: pd.DataFrame, colors: dict[str, str]) -> None:
    for definition in ch.CHARTS:
        combos: list[dict[str, str]] = [{}]
        for option in definition.options:
            combos = [{**c, option.name: choice} for c in combos for choice in option.choices]
        for chosen in combos:
            built = ch.build(definition, frame, "plotly_white", colors, chosen)
            assert built.figure.to_dict()["data"], (definition.key, chosen)
            assert isinstance(built.table, pd.DataFrame) and len(built.table) > 0, definition.key


def test_the_gallery_is_complete_and_well_formed() -> None:
    assert len(ch.CHARTS) >= 15 and len({c.key for c in ch.CHARTS}) == len(ch.CHARTS)
    assert {c.group for c in ch.CHARTS} == set(ch.GROUPS)
    for definition in ch.CHARTS:
        assert definition.title and definition.about
        for option in definition.options:
            assert option.default in option.choices and option.help


def build(key: str, frame: pd.DataFrame, colors: dict[str, str], **chosen: str) -> ch.Chart:
    return ch.build(ch.BY_KEY[key], frame, "plotly_white", colors, chosen)


def test_per_period_sums_to_the_total_and_clicks_map_to_entries(
    frame: pd.DataFrame, colors: dict[str, str]
) -> None:
    built = build("per_period", frame, colors, granularity="day", by="activity")
    total = built.table.drop(columns=ch.GRANULARITY["day"]).drop(columns="Summe").to_numpy().sum()
    assert total == pytest.approx(frame["minutes"].sum() / 60, abs=0.05)
    assert built.drill is not None
    assert built.drill([["2026-03-02", "Meeting"]]) == {"a"}
    assert built.drill([["2026-03-02", "Code"]]) == {"b"}
    assert built.drill([["2026-03-02", "Nope"]]) == set() and built.drill([[]]) == set()
    week = build("per_period", frame, colors, granularity="week", by="project")
    assert week.drill is not None and week.drill([["2026-03-02", "Alpha"]]) == {"a", "b"}


def test_share_table_and_drill(frame: pd.DataFrame, colors: dict[str, str]) -> None:
    built = build("share", frame, colors, by="activity")
    assert built.table["Anteil"].iloc[0].endswith("%") and set(built.table["Tätigkeit"]) == {
        "Code",
        "Meeting",
        "Review",
    }
    assert built.drill is not None and built.drill([["Code"]]) == {"b", "c", "e"}


def test_heat_map_counts_hours_in_the_right_cells(
    frame: pd.DataFrame, colors: dict[str, str]
) -> None:
    built = build("heat", frame, colors)
    row = built.table[built.table["Wochentag"] == "Montag"].iloc[0]
    assert row["09"] == pytest.approx(1.0) and row["10"] == pytest.approx(0.5)  # 09:00-10:30
    assert built.drill is not None
    assert built.drill([[0, 9]]) == {"a"} and built.drill([[0, 12]]) == {"b"}
    assert built.drill([[6, 3]]) == set()


def test_calendar_and_weekday_and_tags(frame: pd.DataFrame, colors: dict[str, str]) -> None:
    calendar = build("calendar", frame, colors)
    day = calendar.table[calendar.table["Tag"] == "2026-03-02"].iloc[0]
    assert day["Stunden"] == pytest.approx(3.5) and day["Wochentag"] == "Montag"
    assert calendar.drill is not None and calendar.drill([["2026-03-02"]]) == {"a", "b"}
    weekday = build("weekday", frame, colors, mode="average")
    monday = weekday.table[weekday.table["Wochentag"] == "Montag"].iloc[0]
    assert monday["Tage mit Einträgen"] == 1  # only 2 March has entries on a Monday
    tags = build("tags", frame, colors)
    by_tag = dict(zip(tags.table["Tag"], tags.table["Stunden"], strict=True))
    assert by_tag["PERSON-B"] == pytest.approx(3.5) and ch.NO_TAG in by_tag
    assert tags.drill is not None and tags.drill([["PERSON-B"]]) == {"a", "b"}
    assert "mehreren Tags" in tags.note


def test_distribution_charts_report_statistics(frame: pd.DataFrame, colors: dict[str, str]) -> None:
    hist = build("hist", frame, colors, bins="10")
    assert hist.table["Einträge"].sum() == len(frame) and "Median" in hist.note
    box = build("box", frame, colors, by="activity")
    assert set(box.table["Tätigkeit"]) == {"Code", "Meeting", "Review"}


def test_scatter_and_timeline_click_to_single_entries(
    frame: pd.DataFrame, colors: dict[str, str]
) -> None:
    for key in ("scatter", "timeline"):
        built = build(key, frame, colors, by="activity")
        assert built.drill is not None and built.drill([["a"], ["c"]]) == {"a", "c"}


def test_the_timeline_is_capped_and_says_so(colors: dict[str, str]) -> None:
    many = [
        entry(f"x{i}", datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=10 * i), 5)
        for i in range(ch.MAX_TIMELINE + 20)
    ]
    big = ch.to_frame(many, TZ, NOW)
    built = ch.build(ch.BY_KEY["timeline"], big, "plotly_white", colors, {"by": "activity"})
    assert len(built.table) == ch.MAX_TIMELINE and str(ch.MAX_TIMELINE) in built.note


def test_trend_cumulative_and_first_last(frame: pd.DataFrame, colors: dict[str, str]) -> None:
    trend = build("trend", frame, colors, window="7")
    assert trend.table["Stunden"].sum() == pytest.approx(frame["minutes"].sum() / 60, abs=0.05)
    assert trend.drill is not None and trend.drill([["2026-03-02"]]) == {"a", "b"}
    cumulative = build("cumulative", frame, colors, by="activity")
    last = cumulative.table.iloc[-1].drop("Tag")
    assert last.sum() == pytest.approx(frame["minutes"].sum() / 60, abs=0.05)
    first_last = build("first_last", frame, colors)
    row = first_last.table[first_last.table["Tag"] == "2026-03-02"].iloc[0]
    assert row["Erster Beginn"] == "09:00" and row["Letztes Ende"] == "14:00"
    assert first_last.drill is not None and first_last.drill([["2026-03-02"]]) == {"a", "b"}


def test_hierarchy_and_flow_charts_have_matching_tables(
    frame: pd.DataFrame, colors: dict[str, str]
) -> None:
    for key in ("sunburst", "treemap", "sankey"):
        built = build(key, frame, colors)
        assert built.table["Stunden"].sum() == pytest.approx(
            frame["minutes"].sum() / 60, abs=0.05
        ), key
    assert build("matrix", frame, colors).drill is not None


def test_absurd_input_is_refused_instead_of_freezing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ch, "MAX_PIECES", 5)
    long_entry = [entry("z", datetime(2026, 1, 1, tzinfo=UTC), 60 * 24 * 30)]
    with pytest.raises(ValueError):
        ch.split_pieces(ch.to_frame(long_entry, TZ, NOW), "day")
