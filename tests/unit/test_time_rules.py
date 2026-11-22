"""Interval validation independent of the local machine timezone."""

from datetime import UTC, datetime, timedelta

import pytest

from octaledger.domain.time_rules import interval_duration


def test_elapsed_utc() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert interval_duration(start, start + timedelta(hours=1)) == timedelta(hours=1)


def test_rejects_naive() -> None:
    with pytest.raises(ValueError):
        interval_duration(datetime(2026, 1, 1), datetime(2026, 1, 2))


def test_rejects_inverted() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        interval_duration(start, start - timedelta(seconds=1))
