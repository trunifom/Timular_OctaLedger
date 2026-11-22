"""Battery rules: stages, what to record, and an honest estimate of the remaining time (pure).

The cube reports its battery as a percentage (standard battery characteristic). OctaLedger shows it
all the time, stores a small history and warns when it drops to a lower stage. Nothing here talks to
the cube or to the database.

Honest limits: the percentage is **the cube's own value** (OctaLedger measures nothing), and the
estimate is a straight line through the stored history - good enough to say "about 3 weeks", never
a promise. Without enough history there is **no** estimate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

#: The percentage is stored when it changed, and at the latest this often.
RECORD_EVERY: Final = timedelta(hours=6)
#: History older than this is deleted.
KEEP: Final = timedelta(days=400)
#: An estimate needs at least this much time and this many points.
MIN_SPAN: Final = timedelta(days=3)
MIN_POINTS: Final = 5
#: Points are only used from this long ago (older discharge behaviour says little about now).
WINDOW: Final = timedelta(days=45)
#: A rise of this many percent between two readings means "the battery was replaced".
REPLACED_JUMP: Final = 10
#: Largest estimate that is shown (longer is "more than 10 years", not a number).
MAX_DAYS: Final = 3650.0


@dataclass(frozen=True, slots=True)
class Stage:
    """A battery stage with its German text (shown **with** the number, never colour alone)."""

    key: str
    rank: int  # 3 = good ... 0 = nearly empty (lower is worse)
    text: str
    icon: str
    level: str  # ok / warn / bad (the interface colours)


STAGES: Final = (
    Stage("good", 3, "gut", "✔", "ok"),
    Stage("soon", 2, "bald tauschen", "▲", "warn"),
    Stage("weak", 1, "schwach", "▲", "warn"),
    Stage("empty", 0, "fast leer", "✖", "bad"),
)
_BY_KEY: Final = {s.key: s for s in STAGES}


def stage_for(percent: int) -> Stage:
    """The stage of a percentage: 40+ good, 20-39 soon, 10-19 weak, below 10 nearly empty."""
    if percent >= 40:
        return _BY_KEY["good"]
    if percent >= 20:
        return _BY_KEY["soon"]
    if percent >= 10:
        return _BY_KEY["weak"]
    return _BY_KEY["empty"]


def stage_by_key(key: str) -> Stage:
    """The stage with this key (``good``, ``soon``, ``weak``, ``empty``)."""
    return _BY_KEY[key]


def bar(percent: int) -> str:
    """Five-segment bar, one segment per started 20 %: 62 % gives four, 60 % three, 0 none."""
    filled = max(0, min(5, -(-percent // 20)))
    return "▮" * filled + "▯" * (5 - filled)


def should_record(
    last_percent: int | None, last_at: datetime | None, percent: int, now: datetime
) -> bool:
    """Whether a reading is stored: the first one, a changed one, or one after ``RECORD_EVERY``."""
    if last_percent is None or last_at is None:
        return True
    return percent != last_percent or now - last_at >= RECORD_EVERY


def is_worse(previous: Stage | None, current: Stage) -> bool:
    """Whether ``current`` is a lower stage than ``previous`` (``None`` counts as good)."""
    before = previous.rank if previous is not None else 3
    return current.rank < before


def estimate_days_left(points: Sequence[tuple[datetime, int]], now: datetime) -> float | None:
    """Days until the battery is empty, from a straight line through the history (or ``None``).

    Uses the points of the last ``WINDOW`` after the latest battery replacement (a rise by
    ``REPLACED_JUMP`` or more). Needs ``MIN_POINTS`` points over at least ``MIN_SPAN`` and a
    falling trend; otherwise there is no estimate.
    """
    ordered = sorted((p for p in points if now - p[0] <= WINDOW), key=lambda p: p[0])
    for index in range(len(ordered) - 1, 0, -1):
        if ordered[index][1] - ordered[index - 1][1] >= REPLACED_JUMP:
            ordered = ordered[index:]  # only what happened since the replacement counts
            break
    if len(ordered) < MIN_POINTS or ordered[-1][0] - ordered[0][0] < MIN_SPAN:
        return None
    origin = ordered[0][0]
    xs = [(t - origin).total_seconds() / 86400 for t, _ in ordered]
    ys = [float(v) for _, v in ordered]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / spread
    if slope >= -0.01:  # not falling (or only measurement noise): no estimate
        return None
    return min(MAX_DAYS, max(0.0, ordered[-1][1] / -slope))


def describe_days(days: float | None) -> str:
    """The estimate as German text (always marked as an estimate)."""
    if days is None:
        return "noch keine Schätzung (zu wenig Verlauf)"
    if days < 1:
        return "Schätzung: weniger als 1 Tag"
    if days < 14:
        return f"Schätzung: etwa {round(days)} Tage"
    if days < 90:
        return f"Schätzung: etwa {round(days / 7)} Wochen"
    if days < MAX_DAYS:
        return f"Schätzung: etwa {round(days / 30)} Monate"
    return "Schätzung: mehr als 10 Jahre"
