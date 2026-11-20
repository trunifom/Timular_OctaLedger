"""Tests for interval algebra: day splitting (incl. DST), overlaps, unions, windows."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from octaledger.core.errors import ValidationError
from octaledger.domain.time_rules import (
    clip_interval,
    find_overlaps,
    local_day_bounds,
    local_week_bounds,
    merge_intervals,
    parse_timezone,
    split_at_day_boundaries,
    sum_durations,
    union_duration,
    validate_interval,
)

UTC = timezone.utc
ZURICH = ZoneInfo("Europe/Zurich")
H = timedelta(hours=1)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def local(*args: int) -> datetime:
    return datetime(*args, tzinfo=ZURICH)


# --------------------------------------------------------------------------- timezone


def test_parse_timezone_ok() -> None:
    assert parse_timezone(" Europe/Zurich ").key == "Europe/Zurich"


@pytest.mark.parametrize("name", ["", "  ", "Mars/Olympus", "../x", 5])
def test_parse_timezone_invalid(name: object) -> None:
    with pytest.raises(ValidationError):
        parse_timezone(name)  # type: ignore[arg-type]


# ------------------------------------------------------------------------ day / week


def test_normal_day_is_24_hours() -> None:
    start, end = local_day_bounds(date(2026, 1, 15), ZURICH)
    assert end - start == 24 * H
    assert start == utc(2026, 1, 14, 23)  # CET = UTC+1


def test_spring_forward_day_is_23_hours() -> None:
    start, end = local_day_bounds(date(2026, 3, 29), ZURICH)
    assert end - start == 23 * H


def test_fall_back_day_is_25_hours() -> None:
    start, end = local_day_bounds(date(2026, 10, 25), ZURICH)
    assert end - start == 25 * H


def test_week_bounds_monday_start() -> None:
    start, end = local_week_bounds(date(2026, 1, 15), ZURICH)  # Thursday
    assert start == utc(2026, 1, 11, 23)  # Monday 2026-01-12 00:00 local
    assert end - start == 7 * 24 * H


def test_week_bounds_sunday_start() -> None:
    start, _ = local_week_bounds(date(2026, 1, 15), ZURICH, week_starts_on=6)
    assert start == utc(2026, 1, 10, 23)  # Sunday 2026-01-11 00:00 local


def test_week_across_dst_is_one_hour_shorter() -> None:
    start, end = local_week_bounds(date(2026, 3, 30), ZURICH)  # week of 03-30, after change
    assert end - start == 7 * 24 * H  # no change inside this week
    start, end = local_week_bounds(date(2026, 3, 26), ZURICH)  # week 03-23..03-30 contains it
    assert end - start == 7 * 24 * H - H


@pytest.mark.parametrize("bad", [-1, 7])
def test_week_start_validation(bad: int) -> None:
    with pytest.raises(ValidationError):
        local_week_bounds(date(2026, 1, 1), ZURICH, week_starts_on=bad)


# -------------------------------------------------------------------- split by midnight


def test_interval_within_one_day_is_not_split() -> None:
    parts = split_at_day_boundaries(local(2026, 1, 15, 9), local(2026, 1, 15, 17), ZURICH)
    assert [d for d, _ in parts] == [date(2026, 1, 15)]
    assert parts[0][1][1] - parts[0][1][0] == 8 * H


def test_interval_across_midnight_is_split_in_two() -> None:
    parts = split_at_day_boundaries(local(2026, 1, 15, 22), local(2026, 1, 16, 3), ZURICH)
    assert [d for d, _ in parts] == [date(2026, 1, 15), date(2026, 1, 16)]
    assert [p[1] - p[0] for _, p in parts] == [2 * H, 3 * H]


def test_parts_are_contiguous_and_sum_to_total() -> None:
    start, end = local(2026, 1, 14, 20), local(2026, 1, 18, 6)
    parts = split_at_day_boundaries(start, end, ZURICH)
    assert len(parts) == 5
    for (_, (_, first_end)), (_, (second_start, _)) in zip(parts, parts[1:], strict=False):
        assert first_end == second_start
    assert sum((b - a for _, (a, b) in parts), timedelta(0)) == end - start


def test_split_across_spring_forward_uses_23_hour_day() -> None:
    parts = split_at_day_boundaries(local(2026, 3, 28, 22), local(2026, 3, 30, 2), ZURICH)
    assert [d for d, _ in parts] == [date(2026, 3, 28), date(2026, 3, 29), date(2026, 3, 30)]
    assert [b - a for _, (a, b) in parts] == [2 * H, 23 * H, 2 * H]


def test_split_across_fall_back_uses_25_hour_day() -> None:
    parts = split_at_day_boundaries(local(2026, 10, 24, 22), local(2026, 10, 26, 2), ZURICH)
    assert [b - a for _, (a, b) in parts] == [2 * H, 25 * H, 2 * H]


def test_interval_ending_exactly_at_midnight_has_no_empty_part() -> None:
    parts = split_at_day_boundaries(local(2026, 1, 15, 22), local(2026, 1, 16, 0), ZURICH)
    assert [d for d, _ in parts] == [date(2026, 1, 15)]


def test_zero_length_interval_yields_single_part() -> None:
    moment = local(2026, 1, 15, 12)
    parts = split_at_day_boundaries(moment, moment, ZURICH)
    assert len(parts) == 1 and parts[0][1][0] == parts[0][1][1]


def test_split_accepts_utc_input_and_uses_local_dates() -> None:
    # 23:30 UTC on 01-14 is already 00:30 on 01-15 in Zurich.
    parts = split_at_day_boundaries(utc(2026, 1, 14, 23, 30), utc(2026, 1, 15, 0, 30), ZURICH)
    assert [d for d, _ in parts] == [date(2026, 1, 15)]


def test_split_rejects_naive_and_inverted() -> None:
    with pytest.raises(ValidationError):
        split_at_day_boundaries(datetime(2026, 1, 1), utc(2026, 1, 2), ZURICH)
    with pytest.raises(ValidationError):
        split_at_day_boundaries(utc(2026, 1, 2), utc(2026, 1, 1), ZURICH)


# ------------------------------------------------------------------------- clip / merge


def test_clip_inside_partial_and_disjoint() -> None:
    window = (utc(2026, 1, 1, 10), utc(2026, 1, 1, 12))
    assert clip_interval((utc(2026, 1, 1, 10, 30), utc(2026, 1, 1, 11)), window) == (
        utc(2026, 1, 1, 10, 30),
        utc(2026, 1, 1, 11),
    )
    assert clip_interval((utc(2026, 1, 1, 9), utc(2026, 1, 1, 11)), window) == (
        utc(2026, 1, 1, 10),
        utc(2026, 1, 1, 11),
    )
    assert clip_interval((utc(2026, 1, 1, 12), utc(2026, 1, 1, 13)), window) is None  # touching
    assert clip_interval((utc(2026, 1, 1, 1), utc(2026, 1, 1, 2)), window) is None


def test_merge_overlapping_touching_and_nested() -> None:
    merged = merge_intervals(
        [
            (utc(2026, 1, 1, 12), utc(2026, 1, 1, 13)),
            (utc(2026, 1, 1, 8), utc(2026, 1, 1, 10)),
            (utc(2026, 1, 1, 9), utc(2026, 1, 1, 11)),  # overlaps previous
            (utc(2026, 1, 1, 11), utc(2026, 1, 1, 11, 30)),  # touches -> merged
            (utc(2026, 1, 1, 8, 30), utc(2026, 1, 1, 9)),  # nested
            (utc(2026, 1, 1, 15), utc(2026, 1, 1, 15)),  # empty -> dropped
        ]
    )
    assert merged == [
        (utc(2026, 1, 1, 8), utc(2026, 1, 1, 11, 30)),
        (utc(2026, 1, 1, 12), utc(2026, 1, 1, 13)),
    ]


def test_merge_empty() -> None:
    assert merge_intervals([]) == []


def test_union_does_not_double_count_but_sum_does() -> None:
    a = (utc(2026, 1, 1, 8), utc(2026, 1, 1, 10))
    b = (utc(2026, 1, 1, 9), utc(2026, 1, 1, 11))
    assert sum_durations([a, b]) == 4 * H  # device times added
    assert union_duration([a, b]) == 3 * H  # personal time: overlap counted once


def test_validate_interval_normalises() -> None:
    start, end = validate_interval(local(2026, 1, 15, 9), local(2026, 1, 15, 10))
    assert start.tzinfo is UTC and end - start == H


# ----------------------------------------------------------------------------- overlaps


def test_find_overlaps_basic() -> None:
    items = [
        ("a", (utc(2026, 1, 1, 8), utc(2026, 1, 1, 10))),
        ("b", (utc(2026, 1, 1, 9), utc(2026, 1, 1, 11))),
        ("c", (utc(2026, 1, 1, 11), utc(2026, 1, 1, 12))),  # touches b: no overlap
        ("d", (utc(2026, 1, 1, 13), utc(2026, 1, 1, 14))),
    ]
    assert find_overlaps(items) == [("a", "b")]


def test_find_overlaps_nested_and_multiple() -> None:
    items = [
        ("outer", (utc(2026, 1, 1, 8), utc(2026, 1, 1, 18))),
        ("x", (utc(2026, 1, 1, 9), utc(2026, 1, 1, 10))),
        ("y", (utc(2026, 1, 1, 12), utc(2026, 1, 1, 13))),
    ]
    assert find_overlaps(items) == [("outer", "x"), ("outer", "y")]


def test_find_overlaps_none_and_unsorted_input() -> None:
    items = [
        ("late", (utc(2026, 1, 1, 12), utc(2026, 1, 1, 13))),
        ("early", (utc(2026, 1, 1, 8), utc(2026, 1, 1, 9))),
    ]
    assert find_overlaps(items) == []
    assert find_overlaps([]) == []
