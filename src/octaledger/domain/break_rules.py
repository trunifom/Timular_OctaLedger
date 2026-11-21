"""Break hints: how long a break should be after a given working time (information only).

**This is orientation, not legal advice, and never enforced.** OctaLedger does not deduct breaks
and does not tell anyone what the law demands; it only notices a long working day without a
recorded break and asks once. The thresholds live in the tables below with their **source and
status date** so they can be checked and corrected in one place.

Sources (secondary sources, to be checked against the primary text before relying on them):

* ``ch``: Swiss Arbeitsgesetz (ArG, SR 822.11) Art. 15 and the SECO guidance: a break of at least
  15 minutes for more than 5.5 hours, 30 minutes for more than 7 hours, 60 minutes for more than
  9 hours of daily working time; breaks can be split. Status of the table: 2026-11.
* ``eu``: Directive 2003/88/EC Art. 4: a rest break when the working day exceeds 6 hours; length
  and conditions are set by national law or collective agreements, so 20 minutes is only a
  common orientation value here. Status of the table: 2026-11.

The law applies to certain employers and persons only (self-employed people are generally
excluded).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final

from octaledger.domain.time_rules import merge_intervals


class BreakRegion(StrEnum):
    """Which table the hints follow."""

    OFF = "off"
    CH = "ch"
    EU = "eu"


#: ``region -> ((more than this many minutes of work, required break in minutes), ...)``
THRESHOLDS: Final[dict[BreakRegion, tuple[tuple[int, int], ...]]] = {
    BreakRegion.OFF: (),
    BreakRegion.CH: ((330, 15), (420, 30), (540, 60)),
    BreakRegion.EU: ((360, 20),),
}

SOURCES: Final[dict[BreakRegion, str]] = {
    BreakRegion.OFF: "",
    BreakRegion.CH: "ArG Art. 15 (SR 822.11), SECO-Wegleitung; Stand der Tabelle 2026-11",
    BreakRegion.EU: "Richtlinie 2003/88/EG Art. 4; Stand der Tabelle 2026-11",
}


def required_break_minutes(region: BreakRegion, worked_minutes: float) -> int:
    """Return the orientation value for the break after ``worked_minutes`` of work (0 = none).

    The comparison is "more than": exactly 5.5 hours (330 minutes) needs no break yet in the
    Swiss table.
    """
    required = 0
    for threshold, minutes in THRESHOLDS[region]:
        if worked_minutes > threshold:
            required = minutes
    return required


def summarize_day(
    intervals: list[tuple[datetime, datetime]],
) -> tuple[float, float]:
    """Return ``(worked_minutes, recorded_break_minutes)`` of one day's entries.

    Overlapping entries are merged first (no double counting). The break is the total of the
    gaps **between** the first start and the last end; time before the first entry or after the
    last one is not a break (a break at the beginning or end of a day is none).
    """
    merged = merge_intervals(intervals)
    if not merged:
        return 0.0, 0.0
    worked = sum((end - start).total_seconds() for start, end in merged) / 60
    gaps = sum((merged[i + 1][0] - merged[i][1]).total_seconds() for i in range(len(merged) - 1))
    return worked, gaps / 60
