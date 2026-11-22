"""The pure search and filter rules of the entry list (AP-58)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from octaledger.dashboard import entry_filter as ef
from octaledger.dashboard.views.entries_history import history_rows

UTC = UTC
ZURICH = ZoneInfo("Europe/Zurich")
MONDAY = datetime(2026, 3, 2, 8, 30, tzinfo=UTC)  # a Monday, 09:30 in Zurich


def entry(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "e1",
        "activity_id": "a1",
        "activity_name": "Meeting",
        "project_id": None,
        "project_name": None,
        "device_id": None,
        "device_alias": None,
        "started_at": MONDAY.isoformat(),
        "ended_at": (MONDAY + timedelta(minutes=45)).isoformat(),
        "running": False,
        "duration_seconds": 45 * 60,
        "source": "manual",
        "quality": "confirmed",
        "note": "Planung mit Müller",
        "revision": 1,
        "tags": [],
    }
    return base | kw


def keep(flt: ef.EntryFilter, *entries: dict[str, Any]) -> list[str]:
    return [e["id"] for e in ef.apply(entries, flt, ZURICH)]


def test_an_empty_filter_keeps_everything() -> None:
    assert ef.EntryFilter().is_empty() and keep(ef.EntryFilter(), entry(), entry(id="e2")) == [
        "e1",
        "e2",
    ]


def test_text_needs_every_word_in_any_field_ignoring_case() -> None:
    e = entry(project_name="Alpha", tags=["PERSON-B"], device_alias="Büro")
    for text in ("müller", "MEETING planung", "alpha person-b", "büro"):
        assert keep(ef.EntryFilter(text=text), e) == ["e1"], text
    assert keep(ef.EntryFilter(text="müller zeitung"), e) == []
    assert keep(ef.EntryFilter(text="   "), e) == ["e1"]


def test_lists_and_the_none_marker() -> None:
    withp = entry(id="p", project_id="p1", device_id="d1")
    bare = entry(id="b")
    assert keep(ef.EntryFilter(project_ids=("p1",)), withp, bare) == ["p"]
    assert keep(ef.EntryFilter(project_ids=(ef.NONE_ID,)), withp, bare) == ["b"]
    assert keep(ef.EntryFilter(device_ids=(ef.NONE_ID, "d9")), withp, bare) == ["b"]
    assert keep(ef.EntryFilter(activity_ids=("zzz",)), withp, bare) == []
    assert keep(ef.EntryFilter(sources=("device",)), withp, bare) == []
    assert keep(ef.EntryFilter(qualities=("confirmed",)), withp, bare) == ["p", "b"]


def test_tag_modes_any_all_none() -> None:
    both = entry(id="both", tags=["TAG-1", "PERSON-B"])
    one = entry(id="one", tags=["TAG-1"])
    none = entry(id="none")
    chosen = ("TAG-1", "PERSON-B")
    assert keep(ef.EntryFilter(tags=chosen, tag_mode="any"), both, one, none) == ["both", "one"]
    assert keep(ef.EntryFilter(tags=chosen, tag_mode="all"), both, one, none) == ["both"]
    assert keep(ef.EntryFilter(tags=chosen, tag_mode="none"), both, one, none) == ["none"]


def test_duration_limits_are_inclusive_minutes() -> None:
    short = entry(id="s", duration_seconds=10 * 60)
    long = entry(id="l", duration_seconds=120 * 60)
    assert keep(ef.EntryFilter(min_minutes=10), short, long) == ["s", "l"]
    assert keep(ef.EntryFilter(min_minutes=11), short, long) == ["l"]
    assert keep(ef.EntryFilter(max_minutes=10), short, long) == ["s"]
    assert keep(ef.EntryFilter(min_minutes=20, max_minutes=60), short, long) == []


def test_weekday_and_hour_use_the_display_timezone() -> None:
    monday = entry(id="mon")  # Monday 09:30 in Zurich (08:30 UTC)
    late = entry(id="late", started_at=(MONDAY + timedelta(days=1, hours=14)).isoformat())
    assert keep(ef.EntryFilter(weekdays=(0,)), monday, late) == ["mon"]
    assert keep(ef.EntryFilter(weekdays=(1,)), monday, late) == ["late"]
    assert keep(ef.EntryFilter(hour_from=9, hour_to=10), monday, late) == ["mon"]
    assert keep(ef.EntryFilter(hour_from=12), monday, late) == ["late"]
    # 23:30 UTC on Sunday is already Monday 00:30 in Zurich
    midnight = entry(id="m", started_at=datetime(2026, 3, 1, 23, 30, tzinfo=UTC).isoformat())
    assert keep(ef.EntryFilter(weekdays=(0,)), midnight) == ["m"]


def test_describe_names_every_restriction() -> None:
    flt = ef.EntryFilter(
        text="x",
        activity_ids=("a1",),
        project_ids=(ef.NONE_ID,),
        tags=("T",),
        tag_mode="all",
        qualities=("uncertain",),
        min_minutes=5,
        weekdays=(0, 4),
        hour_from=8,
        hour_to=12,
    )
    text = ef.describe(flt, {"a1": "Meeting"})
    for part in (
        "„x“",
        "Meeting",
        "ohne",
        "alle diese Tags",
        "unsicher",
        "ab 5 min",
        "Mo, Fr",
        "8–12",
    ):
        assert part in text, part
    assert ef.describe(ef.EntryFilter()) == "keine Einschränkung"


def test_totals_and_selection_summary() -> None:
    rows = [entry(), entry(id="r", running=True, ended_at=None, duration_seconds=60)]
    assert ef.totals(rows) == (2, 45 * 60 + 60)
    info = ef.selection_summary(rows, ZURICH)
    assert info["count"] == 2 and info["running"] == 1 and info["first"].hour == 9
    assert ef.selection_summary([], ZURICH)["first"] is None


def test_history_rows_show_names_times_and_dashes() -> None:
    rows = history_rows(
        [
            {
                "at": MONDAY.isoformat(),
                "kind": "Korrektur",
                "session_id": "abcdef1234567890",
                "field": "started_at",
                "old_value": MONDAY.isoformat(),
                "new_value": None,
                "reason": "Sammelbearbeitung: Test",
                "revision": 2,
            },
            {
                "at": MONDAY.isoformat(),
                "kind": "Aktion",
                "session_id": None,
                "field": "delete",
                "old_value": None,
                "new_value": None,
                "reason": "3 selected sessions",
                "revision": None,
            },
        ],
        "Europe/Zurich",
    )
    assert rows[0]["Was"] == "Beginn" and rows[0]["Vorher"].endswith("09:30")
    assert rows[0]["Nachher"] == "–" and rows[0]["Eintrag"] == "abcdef12"
    assert rows[1]["Was"] == "Gelöscht" and rows[1]["Vorher"] == ""
