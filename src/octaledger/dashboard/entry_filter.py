"""Search and filter for the entry list (pure functions, no Streamlit, no HTTP).

The page *Einträge* loads the entries of a period from the API and narrows them down here. All
data is local and small, so filtering in the dashboard keeps the API simple and makes every
rule testable. An entry is the dictionary the journal endpoint returns.

Rules
-----
* **Text:** every word must occur (case-insensitive) in the note, activity, project, device or
  one of the tags (so ``"meeting müller"`` finds entries that mention both).
* **Lists** (activities, projects, devices, qualities, sources): empty = no restriction.
  :data:`NONE_ID` stands for "no project" / "by hand" (no device).
* **Tags:** ``any`` (at least one of the chosen), ``all`` (every chosen one) or ``none``
  (none of the chosen); empty choice = no restriction.
* **Duration** in minutes, **weekdays** (0 = Monday) and the **start hour** use the display
  timezone, because "Monday morning" means the local one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

#: Stands for "no project" and "no device (by hand)" in the id lists.
NONE_ID: Final = "-"
TAG_MODES: Final = {
    "any": "mindestens einen dieser Tags",
    "all": "alle diese Tags",
    "none": "keinen dieser Tags",
}
WEEKDAYS: Final = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
QUALITY_TEXT: Final = {"confirmed": "bestätigt", "uncertain": "unsicher"}
SOURCE_TEXT: Final = {"device": "Würfel", "manual": "von Hand"}


@dataclass(frozen=True, slots=True)
class EntryFilter:
    """Everything the user can narrow the list down by (an empty filter keeps everything)."""

    text: str = ""
    activity_ids: tuple[str, ...] = ()
    project_ids: tuple[str, ...] = ()
    device_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    tag_mode: str = "any"
    qualities: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    min_minutes: int | None = None
    max_minutes: int | None = None
    weekdays: tuple[int, ...] = ()
    hour_from: int = 0
    hour_to: int = 24
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    def is_empty(self) -> bool:
        """True if nothing narrows the list down."""
        return self == EntryFilter()


def _haystack(entry: dict[str, Any]) -> str:
    parts = [
        entry.get("note") or "",
        entry.get("activity_name") or "",
        entry.get("project_name") or "",
        entry.get("device_alias") or "",
        *entry.get("tags", []),
    ]
    return " ".join(parts).casefold()


def _local_start(entry: dict[str, Any], tz: ZoneInfo) -> datetime:
    return datetime.fromisoformat(entry["started_at"]).astimezone(tz)


def matches(entry: dict[str, Any], flt: EntryFilter, tz: ZoneInfo) -> bool:
    """Does one entry pass the filter?"""
    words = flt.text.casefold().split()
    if words:
        hay = _haystack(entry)
        if not all(word in hay for word in words):
            return False
    if flt.activity_ids and entry["activity_id"] not in flt.activity_ids:
        return False
    if flt.project_ids and (entry["project_id"] or NONE_ID) not in flt.project_ids:
        return False
    if flt.device_ids and (entry["device_id"] or NONE_ID) not in flt.device_ids:
        return False
    if flt.qualities and entry["quality"] not in flt.qualities:
        return False
    if flt.sources and entry["source"] not in flt.sources:
        return False
    if flt.tags:
        have = set(entry.get("tags", []))
        wanted = set(flt.tags)
        if flt.tag_mode == "all" and not wanted <= have:
            return False
        if flt.tag_mode == "none" and wanted & have:
            return False
        if flt.tag_mode == "any" and not wanted & have:
            return False
    minutes = entry["duration_seconds"] / 60
    if flt.min_minutes is not None and minutes < flt.min_minutes:
        return False
    if flt.max_minutes is not None and minutes > flt.max_minutes:
        return False
    if flt.weekdays or flt.hour_from > 0 or flt.hour_to < 24:
        start = _local_start(entry, tz)
        if flt.weekdays and start.weekday() not in flt.weekdays:
            return False
        if not flt.hour_from <= start.hour < max(flt.hour_to, flt.hour_from + 1):
            return False
    return True


def apply(
    entries: Iterable[dict[str, Any]], flt: EntryFilter, tz: ZoneInfo
) -> list[dict[str, Any]]:
    """The entries that pass the filter, in their original order."""
    return [e for e in entries if matches(e, flt, tz)]


def describe(flt: EntryFilter, names: dict[str, str] | None = None) -> str:
    """The filter in one German line (for the search log and the result caption).

    Args:
        flt: The filter.
        names: ``id -> name`` of activities, projects and devices (ids are shown otherwise).
    """
    label = names or {}

    def pick(ids: tuple[str, ...]) -> str:
        """Names of the chosen ids, joined."""
        return ", ".join(label.get(i, "ohne" if i == NONE_ID else i) for i in ids)

    parts: list[str] = []
    if flt.text.strip():
        parts.append(f"Text „{flt.text.strip()}“")
    if flt.activity_ids:
        parts.append(f"Tätigkeit: {pick(flt.activity_ids)}")
    if flt.project_ids:
        parts.append(f"Projekt: {pick(flt.project_ids)}")
    if flt.device_ids:
        parts.append(f"Gerät: {pick(flt.device_ids)}")
    if flt.tags:
        parts.append(f"Tags ({TAG_MODES.get(flt.tag_mode, flt.tag_mode)}): {', '.join(flt.tags)}")
    if flt.qualities:
        parts.append("Qualität: " + ", ".join(QUALITY_TEXT.get(q, q) for q in flt.qualities))
    if flt.sources:
        parts.append("Quelle: " + ", ".join(SOURCE_TEXT.get(s, s) for s in flt.sources))
    if flt.min_minutes is not None or flt.max_minutes is not None:
        low = "" if flt.min_minutes is None else f"ab {flt.min_minutes} min"
        high = "" if flt.max_minutes is None else f"bis {flt.max_minutes} min"
        parts.append("Dauer " + " ".join(p for p in (low, high) if p))
    if flt.weekdays:
        parts.append("Tage: " + ", ".join(WEEKDAYS[d] for d in flt.weekdays))
    if flt.hour_from > 0 or flt.hour_to < 24:
        parts.append(f"Beginn {flt.hour_from}–{flt.hour_to} Uhr")
    return "; ".join(parts) if parts else "keine Einschränkung"


def totals(entries: Iterable[dict[str, Any]]) -> tuple[int, int]:
    """``(count, seconds)`` of a list of entries."""
    rows = list(entries)
    return len(rows), sum(int(e["duration_seconds"]) for e in rows)


def selection_summary(entries: Iterable[dict[str, Any]], tz: ZoneInfo) -> dict[str, Any]:
    """Count, total seconds and the covered time span of the selected entries."""
    rows = list(entries)
    count, seconds = totals(rows)
    starts = [_local_start(e, tz) for e in rows]
    ends = [
        datetime.fromisoformat(e["ended_at"]).astimezone(tz)
        for e in rows
        if e["ended_at"] is not None
    ]
    return {
        "count": count,
        "seconds": seconds,
        "first": min(starts) if starts else None,
        "last": max(ends) if ends else (max(starts) if starts else None),
        "running": sum(1 for e in rows if e["running"]),
    }
