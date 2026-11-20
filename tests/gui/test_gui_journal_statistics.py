"""GUI tests for the journal and statistics pages (AppTest against the real API server)."""

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from octaledger.domain.models import Quality
from tests.conftest import RunningApi
from tests.gui.test_gui_core import button, open_app, texts
from tests.gui.test_gui_devices_catalog import all_help, open_page

JOURNAL = "📒 Zeitjournal"
STATS = "📊 Statistik"
UTC = timezone.utc


def today_at(hour: int, minute: int = 0) -> datetime:
    """A moment today in UTC (the default display timezone)."""
    return datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC).replace(
        hour=hour, minute=minute
    )


def seed(api: RunningApi) -> dict[str, str]:
    """Meeting 00:00-01:00 and Code 01:00-03:00 (project Alpha) today (UTC)."""
    client = api.client
    meeting = client.create_item("activities", "Meeting")
    code = client.create_item("activities", "Code")
    alpha = client.create_item("projects", "Alpha")
    a = client.add_session(meeting["id"], today_at(0), today_at(1), note="Planung")
    b = client.add_session(code["id"], today_at(1), today_at(3), alpha["id"])
    return {
        "meeting": meeting["id"],
        "code": code["id"],
        "alpha": alpha["id"],
        "first": a["id"],
        "second": b["id"],
    }


def clock_ok() -> bool:
    """The seeded sessions must lie in the past; skip around midnight edge cases."""
    return datetime.now(UTC) > today_at(3, 30)


needs_afternoon = pytest.mark.skipif(
    not clock_ok(), reason="seeded sessions would lie in the future"
)


# ----------------------------------------------------------------------------- journal


@needs_afternoon
def test_journal_lists_sessions_with_names_and_durations(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, JOURNAL)
    assert at.header[0].value == "Zeitjournal"
    labels = [tab.label for tab in at.tabs]
    assert {"Journal", "Zu prüfen", "Nachtragen", "Korrigieren", "Teilen", "Löschen"} <= set(labels)
    table = at.dataframe[0].value
    assert list(table["Tätigkeit"]) == ["Code", "Meeting"]  # newest first
    assert list(table["Dauer"]) == ["2 h 00 min", "1 h 00 min"]
    assert list(table["Projekt"]) == ["Alpha", "–"] and list(table["Notiz"]) == ["", "Planung"]
    assert any("3 h 00 min" in c.value for c in at.caption)


def test_journal_empty_state_and_inverted_range(api_server: RunningApi) -> None:
    at = open_page(api_server, JOURNAL)
    assert any("keine Zeiten" in i.value for i in at.info)
    at.date_input(key="journal_from").set_value(date.today())
    at.date_input(key="journal_to").set_value(date.today() - timedelta(days=3))
    at.run()
    assert any("Ende liegt vor dem Beginn" in e.value for e in at.error)


@needs_afternoon
def test_journal_filter_by_activity(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, JOURNAL)
    at.selectbox(key="journal_activity").select_index(2).run()  # options: Alle, Code, Meeting
    assert list(at.dataframe[0].value["Tätigkeit"]) == ["Meeting"]


@needs_afternoon
def test_correct_a_session_with_reason(api_server: RunningApi) -> None:
    ids = seed(api_server)
    at = open_page(api_server, JOURNAL)
    at.selectbox(key="edit_pick").select_index(1).run()  # the Meeting session
    sid = ids["first"]
    at.text_input(key=f"c_note_{sid}").input("Geändert")
    button(at, "Korrektur speichern").click().run()
    assert any("OL-VALID-001" in c.value for c in at.caption)  # reason is mandatory
    at.text_input(key=f"c_note_{sid}").input("Geändert")
    at.text_input(key=f"c_reason_{sid}").input("Tippfehler")
    button(at, "Korrektur speichern").click().run()
    corrected = [
        e for e in api_server.client.journal(today_at(0), today_at(23, 59)) if e["id"] == sid
    ]
    assert corrected[0]["note"] == "Geändert" and corrected[0]["revision"] == 2


@needs_afternoon
def test_split_and_delete_a_session(api_server: RunningApi) -> None:
    ids = seed(api_server)
    at = open_page(api_server, JOURNAL)
    at.selectbox(key="edit_pick").select_index(0).run()  # Code 01:00-03:00
    sid = ids["second"]
    at.time_input(key=f"s_at_{sid}_time").set_value(datetime(2026, 1, 1, 2, 0).time())
    at.text_input(key=f"s_reason_{sid}").input("Pause vergessen")
    button(at, "Teilen").click().run()
    entries = api_server.client.journal(today_at(0), today_at(23, 59))
    assert len(entries) == 3 and sorted(e["duration_seconds"] for e in entries) == [
        3600,
        3600,
        3600,
    ]

    at = open_page(api_server, JOURNAL)
    at.selectbox(key="edit_pick").select_index(0).run()
    target = at.selectbox(key="edit_pick").value["id"]
    assert at.button(key=f"del_{target}").disabled
    at.text_input(key=f"del_reason_{target}").input("Testdaten")
    at.checkbox(key=f"del_confirm_{target}").check().run()
    at.button(key=f"del_{target}").click().run()
    assert len(api_server.client.journal(today_at(0), today_at(23, 59))) == 2


@needs_afternoon
def test_review_tab_confirms_uncertain_sessions(api_server: RunningApi) -> None:
    ids = seed(api_server)
    with api_server.storage.transaction() as repos:
        repos.sessions.set_quality(ids["first"], Quality.UNCERTAIN)
    at = open_page(api_server, JOURNAL)
    assert any("unsicher" in w.value for w in at.warning)
    at.button(key=f"review_confirm_{ids['first']}").click().run()
    assert api_server.client.uncertain_sessions() == []
    assert any("nichts zu prüfen" in s.value for s in at.success)


def test_review_tab_when_everything_is_confirmed(api_server: RunningApi) -> None:
    at = open_page(api_server, JOURNAL)
    assert any("nichts zu prüfen" in s.value for s in at.success)


@needs_afternoon
def test_add_past_session_and_overlap_error(api_server: RunningApi) -> None:
    ids = seed(api_server)
    at = open_page(api_server, JOURNAL)
    at.selectbox(key="add_activity").select_index(0)
    at.time_input(key="add_start_time").set_value(datetime(2026, 1, 1, 0, 30).time())
    at.time_input(key="add_end_time").set_value(datetime(2026, 1, 1, 1, 30).time())
    at.date_input(key="add_start_date").set_value(date.today())
    at.date_input(key="add_end_date").set_value(date.today())
    button(at, "Nachtragen").click().run()
    assert any("OL-STATE-002" in c.value for c in at.caption)  # overlaps the seeded sessions
    assert len(api_server.client.journal(today_at(0), today_at(23, 59))) == 2
    assert ids["meeting"]


def test_journal_widgets_have_help_texts(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Meeting")
    at = open_page(api_server, JOURNAL)
    for widget in [*all_help(at), *at.date_input, *at.time_input]:
        assert widget.help, f"{widget.key or widget.label} has no help text"


# --------------------------------------------------------------------------- statistics


@needs_afternoon
def test_day_statistics_show_metrics_charts_and_tables(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, STATS)
    assert at.header[0].value == "Statistik"
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Persönliche Arbeitszeit"] == "3 h 00 min"
    assert metrics["Gerätezeit"] == "3 h 00 min" and metrics["Überschneidung"] == "0 min"
    assert metrics["Davon unsicher"] == "0 min"
    assert len(at.get("plotly_chart")) == 2  # one day: no daily chart, activity + project pies
    by_activity = [d.value for d in at.dataframe if "Name" in d.value.columns][0]
    assert list(by_activity["Name"]) == ["Code", "Meeting"] and list(by_activity["Anteil"]) == [
        "67%",
        "33%",
    ]


@needs_afternoon
def test_week_statistics_add_the_daily_chart(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, STATS)
    at.radio(key="stat_period").set_value("week").run()
    assert len(at.get("plotly_chart")) == 3  # daily + activity + project
    daily = at.dataframe[0].value
    assert len(daily) == 7 and round(float(daily["Persönliche Zeit (h)"].sum()), 2) == 3.0


@needs_afternoon
def test_custom_period_filter_and_uncertainty_warning(api_server: RunningApi) -> None:
    ids = seed(api_server)
    with api_server.storage.transaction() as repos:
        repos.sessions.set_quality(ids["second"], Quality.UNCERTAIN)
    at = open_page(api_server, STATS)
    at.radio(key="stat_period").set_value("custom").run()
    at.selectbox(key="stat_activity").select_index(1).run()  # Code only
    metrics = {m.label: m.value for m in at.metric}
    assert (
        metrics["Persönliche Arbeitszeit"] == "2 h 00 min"
        and metrics["Davon unsicher"] == "2 h 00 min"
    )
    assert any("unsicher" in w.value for w in at.warning)


def test_statistics_empty_state_and_inverted_custom_range(api_server: RunningApi) -> None:
    at = open_page(api_server, STATS)
    assert any("keine Zeiten" in i.value for i in at.info)
    at.radio(key="stat_period").set_value("custom").run()
    at.date_input(key="stat_from").set_value(date.today())
    at.date_input(key="stat_to").set_value(date.today() - timedelta(days=2)).run()
    assert any("Ende liegt vor dem Beginn" in e.value for e in at.error)


def test_statistics_range_over_400_days_gives_a_clear_error(api_server: RunningApi) -> None:
    at = open_page(api_server, STATS)
    at.radio(key="stat_period").set_value("custom").run()
    at.date_input(key="stat_from").set_value(date.today() - timedelta(days=800)).run()
    assert any("zu lang" in e.value for e in at.error)
    assert not at.exception


@needs_afternoon
def test_statistics_charts_follow_the_dark_theme(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_app(api_server.client)
    at.sidebar.button(key="btn_theme").click().run()
    at.sidebar.radio(key="nav").set_value(STATS).run()
    assert not at.exception and len(at.get("plotly_chart")) == 2
    assert "rgb(17,17,17)" in str(at.get("plotly_chart")[0].proto.spec)  # dark template colours
    at.sidebar.button(key="btn_theme").click().run()  # back to light
    assert "rgb(17,17,17)" not in str(at.get("plotly_chart")[0].proto.spec)


def test_statistics_widgets_have_help_texts(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Meeting")
    at = open_page(api_server, STATS)
    for widget in [*at.selectbox, *at.radio, *at.date_input]:
        assert widget.help, f"{widget.key or widget.label} has no help text"
    for metric in at.metric:
        assert metric.help, metric.label


def test_navigation_contains_all_pages_in_order(api_server: RunningApi) -> None:
    from octaledger.dashboard.pages import PAGES

    at = open_app(api_server.client)
    labels = list(PAGES)
    assert at.sidebar.radio(key="nav").options == labels
    assert labels.index(JOURNAL) < labels.index(STATS)
    assert texts(at)  # renders


def _unused(_: Any) -> None:  # keeps the shared helpers referenced for type checkers
    return None
