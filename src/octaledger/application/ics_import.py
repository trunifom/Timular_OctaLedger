"""Calendar import: turn the appointments of an ``.ics`` file into **proposals**.

Nothing is booked automatically. :func:`parse_ics` only *reads* the file and returns proposals
(start, end, title, overlap flag) for a time window; the user then chooses an activity per
proposal and confirms, and only the confirmed ones are booked, all in **one** transaction
(:meth:`IcsService.apply`). The file is never executed or stored.

Safety rules for a foreign file (see ``SECURITY.md``): a size limit, a mandatory time window of
at most 90 days (so a rule without end date cannot expand without limit), at most 1000
appointments, no attachment or URL in the file is ever opened, and every parser error becomes
an :class:`~octaledger.core.errors.ImportDataError`.

Needs the optional extra ``ics`` (``icalendar`` BSD-2-Clause and ``recurring-ical-events``
LGPL-3.0, loaded only when used).
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from octaledger.application.tracking_service import FUTURE_TOLERANCE
from octaledger.core.errors import ConflictError, ImportDataError, ValidationError
from octaledger.domain.models import Session, SessionSource
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

MAX_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 1000
MAX_WINDOW_DAYS = 90
MAX_APPLY = 200
#: Appointments longer than this are skipped (multi-day events are rarely "work time").
MAX_EVENT_HOURS = 24


def ics_available() -> bool:
    """Whether the optional packages are installed."""
    return all(
        importlib.util.find_spec(name) is not None
        for name in ("icalendar", "recurring_ical_events")
    )


@dataclass(frozen=True, slots=True)
class Proposal:
    """One appointment offered for booking."""

    index: int
    start: datetime
    end: datetime
    title: str
    overlaps: bool


@dataclass(frozen=True, slots=True)
class IcsPreview:
    """The proposals and what was skipped (with the reason counted)."""

    proposals: tuple[Proposal, ...]
    skipped: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IcsEntry:
    """A confirmed proposal with the user's choice of activity."""

    start: datetime
    end: datetime
    activity_id: str
    project_id: str | None = None
    note: str | None = None


def parse_ics(
    content: str | bytes,
    first: date,
    last: date,
    tz: ZoneInfo,
) -> tuple[list[tuple[datetime, datetime, str]], dict[str, int]]:
    """Read appointments between two local dates (inclusive) from ICS text.

    Returns:
        ``([(start_utc, end_utc, title), ...], skipped)`` with the skip reasons counted.

    Raises:
        ValidationError: For a window longer than 90 days or too many appointments.
        ImportDataError: For a too large file, a broken file, or when the optional packages
            are missing.
    """
    if not ics_available():
        raise ImportDataError(
            "icalendar is not installed",
            user_message='Für den Kalender-Import fehlen Zusatzpakete: pip install -e ".[ics]".',
        )
    data = content.encode("utf-8") if isinstance(content, str) else content
    if len(data) > MAX_BYTES:
        raise ImportDataError(
            f"ICS file larger than {MAX_BYTES} bytes",
            user_message="Die Kalenderdatei ist zu groß (höchstens 2 MiB).",
        )
    if last < first or (last - first).days + 1 > MAX_WINDOW_DAYS:
        raise ValidationError(
            "Invalid import window",
            user_message=f"Der Zeitraum darf höchstens {MAX_WINDOW_DAYS} Tage lang sein.",
        )
    import icalendar
    import recurring_ical_events

    start = datetime.combine(first, datetime.min.time(), tzinfo=tz)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    try:
        calendar = icalendar.Calendar.from_ical(data)
        occurrences = recurring_ical_events.of(calendar).between(start, end)
    except Exception as exc:  # noqa: BLE001 - any parser failure is a bad file, not a crash
        raise ImportDataError(
            f"Cannot read the calendar file: {type(exc).__name__}",
            user_message="Die Datei ist keine lesbare Kalenderdatei (.ics).",
        ) from exc
    if len(occurrences) > MAX_EVENTS:
        raise ValidationError(
            "Too many appointments",
            user_message=f"Der Zeitraum enthält mehr als {MAX_EVENTS} Termine; "
            "wählen Sie einen kürzeren.",
        )
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        """Count one skipped appointment under its reason."""
        skipped[reason] = skipped.get(reason, 0) + 1

    found: list[tuple[datetime, datetime, str]] = []
    for event in occurrences:
        try:
            begin, finish = event.start, event.end
            status = str(event.get("STATUS", "")).upper()
            title = " ".join(str(event.get("SUMMARY", "")).split())[:200] or "(ohne Titel)"
        except Exception:  # noqa: BLE001 - one broken appointment must not stop the rest
            skip("unlesbar")
            continue
        if status == "CANCELLED":
            skip("abgesagt")
            continue
        if not isinstance(begin, datetime) or not isinstance(finish, datetime):
            skip("ganztägig")  # DATE values (all-day) are not work intervals
            continue
        # A floating time (no zone) means the user's own clock.
        begin = begin.replace(tzinfo=tz) if begin.tzinfo is None else begin
        finish = finish.replace(tzinfo=tz) if finish.tzinfo is None else finish
        if finish <= begin:
            skip("ohne Dauer")
            continue
        if finish - begin > timedelta(hours=MAX_EVENT_HOURS):
            skip("länger als 24 Stunden")
            continue
        found.append((begin.astimezone(timezone.utc), finish.astimezone(timezone.utc), title))
    return sorted(found), skipped


class IcsService:
    """Preview and apply a calendar import."""

    def __init__(self, storage: Storage, *, clock=utc_now) -> None:  # type: ignore[no-untyped-def]
        """Create the service (``clock`` returns the current UTC time)."""
        self._storage = storage
        self._clock = clock

    def preview(self, content: str | bytes, first: date, last: date, tz: ZoneInfo) -> IcsPreview:
        """Read the file and return proposals; **nothing is booked or stored**."""
        found, skipped = parse_ics(content, first, last, tz)
        with self._storage.read() as repos:
            proposals = tuple(
                Proposal(
                    index,
                    start,
                    end,
                    title,
                    overlaps=bool(
                        [
                            s
                            for s in repos.sessions.list_between(start, end)
                            if s.started_at < end and (s.ended_at is None or s.ended_at > start)
                        ]
                    ),
                )
                for index, (start, end, title) in enumerate(found)
            )
        return IcsPreview(proposals, skipped)

    def apply(self, entries: Sequence[IcsEntry]) -> list[Session]:
        """Book the confirmed entries in **one** transaction (all or nothing).

        Raises:
            ValidationError: For an empty or oversized batch, or an end in the future.
            NotFoundError: If an activity or project does not exist.
            ConflictError: If an entry overlaps an existing entry or another one of the batch.
        """
        if not entries:
            raise ValidationError(
                "Nothing to import", user_message="Es wurde nichts zum Übernehmen ausgewählt."
            )
        if len(entries) > MAX_APPLY:
            raise ValidationError(
                "Too many entries", user_message=f"Höchstens {MAX_APPLY} Termine auf einmal."
            )
        limit = ensure_utc(self._clock()) + FUTURE_TOLERANCE
        created: list[Session] = []
        with self._storage.transaction() as repos:
            for entry in entries:
                if ensure_utc(entry.end) > limit:
                    raise ValidationError(
                        "Entry ends in the future", user_message="Ein Termin endet in der Zukunft."
                    )
                repos.activities.require(entry.activity_id)
                if entry.project_id is not None:
                    repos.projects.require(entry.project_id)
                try:
                    created.append(
                        repos.sessions.add(
                            Session(
                                activity_id=entry.activity_id,
                                project_id=entry.project_id,
                                started_at=entry.start,
                                ended_at=entry.end,
                                source=SessionSource.MANUAL,
                                note=entry.note,
                            )
                        )
                    )
                except ConflictError as exc:
                    raise ConflictError(
                        str(exc),
                        user_message="Ein Termin überschneidet sich mit einem vorhandenen Eintrag. "
                        "Es wurde nichts übernommen.",
                    ) from exc
            repos.audit.add("import_ics", "session", None, f"{len(created)} entries")
        logger.info("Calendar import applied: %d entries", len(created))
        return created
