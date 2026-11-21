"""The working-day service: applies the rules of :mod:`octaledger.domain.workday`.

The housekeeper calls :meth:`tick` every few seconds. The service reads the clock, the running
entry and (only when idle detection is switched on) the idle time, asks the pure rules what to
do and applies it **in one transaction**: it ends an entry at the configured end of the workday,
or raises a question / reminder in the attention centre. Answers to those questions are
handled by :meth:`resolve_idle` and :meth:`resolve_auto_stop`; nothing is ever deleted, and every
change that touches booked time is flagged ``uncertain`` and audited.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from octaledger.application.tracking_service import STATE_PAUSED
from octaledger.core.errors import InvalidStateError, ValidationError
from octaledger.core.settings import Settings
from octaledger.domain.attention import AttentionItem, AttentionKind, AttentionStatus
from octaledger.domain.models import Quality
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.domain.workday import (
    DayState,
    RunningEntry,
    WorkAction,
    evaluate,
)
from octaledger.infrastructure.storage.repositories import Repositories, Storage
from octaledger.infrastructure.system.idle import InputProbe

logger = logging.getLogger(__name__)

STATE_AUTO_STOPPED = "work:auto_stopped_on"
STATE_NO_TIMER = "work:reminded_no_timer_on"
STATE_RUNNING_REMINDER = "work:reminded_running"
STATE_IDLE_ASKED = "work:idle_asked_for"

#: Answers to an idle question.
IDLE_KEEP, IDLE_DISCARD, IDLE_PAUSE = "keep", "discard", "pause"
IDLE_ACTIONS = (IDLE_KEEP, IDLE_DISCARD, IDLE_PAUSE)
#: Answers to an automatic-stop question.
STOP_KEEP, STOP_EXTEND = "keep", "extend"
STOP_ACTIONS = (STOP_KEEP, STOP_EXTEND)


class WorkdayService:
    """Auto-stop, idle questions and reminders."""

    def __init__(
        self,
        storage: Storage,
        settings: Callable[[], Settings],
        probe: InputProbe,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create the service.

        Args:
            storage: Transactional storage.
            settings: Returns the current settings (read on every tick, so changes apply live).
            probe: Source of the idle time.
            clock: Returns the current UTC time (injectable for tests).
        """
        self._storage = storage
        self._settings = settings
        self._probe = probe
        self._clock = clock

    # ------------------------------------------------------------------------- tick

    def tick(self, now: datetime | None = None) -> list[AttentionItem]:
        """Apply the rules once; returns the questions and reminders that were raised."""
        moment = ensure_utc(now) if now is not None else ensure_utc(self._clock())
        settings = self._settings()
        work = settings.work
        # Nothing configured: do not even read the idle time (privacy and cost).
        if not (
            work.workday_end
            or work.idle_minutes
            or work.reminder_no_timer_after
            or work.reminder_running_hours
        ):
            return []
        tz = ZoneInfo(settings.display.timezone)
        idle = self._probe.idle_seconds() if work.idle_minutes > 0 else None
        raised: list[AttentionItem] = []
        with self._storage.transaction() as repos:
            running = repos.sessions.get_running()
            state = DayState(
                auto_stopped_on=repos.state.get(STATE_AUTO_STOPPED),
                reminded_no_timer_on=repos.state.get(STATE_NO_TIMER),
                reminded_running=repos.state.get(STATE_RUNNING_REMINDER),
                idle_asked_for=repos.state.get(STATE_IDLE_ASKED),
            )
            entry = RunningEntry(running.id, running.started_at) if running else None
            for decision in evaluate(moment, tz, work, entry, idle, state):
                item = self._apply(repos, decision.action, decision.at, moment, tz, running)
                if item is not None:
                    raised.append(item)
        return raised

    def _apply(
        self,
        repos: Repositories,
        action: WorkAction,
        at: datetime,
        now: datetime,
        tz: ZoneInfo,
        running: object,
    ) -> AttentionItem | None:
        today = now.astimezone(tz).date().isoformat()
        session = repos.sessions.get_running()
        if action is WorkAction.AUTO_STOP and session is not None:
            repos.sessions.end(session.id, at, Quality.UNCERTAIN)
            repos.state.set(STATE_AUTO_STOPPED, today)
            logger.warning("End of the workday: running entry ended automatically")
            return repos.attention.add(
                AttentionItem(
                    kind=AttentionKind.AUTO_STOP,
                    created_at=now,
                    session_id=session.id,
                    payload={"ended_at": at.isoformat()},
                )
            )
        if action is WorkAction.IDLE and session is not None:
            repos.state.set(STATE_IDLE_ASKED, session.id)
            logger.info("Idle period detected; question raised")
            return repos.attention.add(
                AttentionItem(
                    kind=AttentionKind.IDLE,
                    created_at=now,
                    session_id=session.id,
                    payload={"idle_since": at.isoformat()},
                )
            )
        if action is WorkAction.REMIND_NO_TIMER:
            repos.state.set(STATE_NO_TIMER, today)
            return repos.attention.add(
                AttentionItem(
                    kind=AttentionKind.REMINDER, created_at=now, payload={"reason": "no_timer"}
                )
            )
        if action is WorkAction.REMIND_RUNNING and session is not None:
            repos.state.set(STATE_RUNNING_REMINDER, session.id)
            hours = round((now - session.started_at).total_seconds() / 3600, 1)
            return repos.attention.add(
                AttentionItem(
                    kind=AttentionKind.REMINDER,
                    created_at=now,
                    session_id=session.id,
                    payload={"reason": "running_long", "hours": hours},
                )
            )
        return None

    # --------------------------------------------------------------------- answers

    def resolve_idle(self, item_id: str, action: str) -> AttentionItem:
        """Answer an idle question.

        Args:
            item_id: The open ``idle`` item.
            action: ``keep`` (the time counts), ``discard`` (the entry ends where the idle time
                began) or ``pause`` (like discard, and tracking is remembered as paused so it
                can be continued).

        Raises:
            ValidationError: For an unknown action.
            InvalidStateError: If the item is not an open idle question or the entry no longer
                runs.
        """
        if action not in IDLE_ACTIONS:
            raise ValidationError(
                f"Unknown idle action {action!r}",
                user_message="Unbekannte Antwort. Erlaubt sind: behalten, verwerfen, pausieren.",
            )
        with self._storage.transaction() as repos:
            item = self._open_item(repos, item_id, AttentionKind.IDLE)
            if action != IDLE_KEEP:
                running = repos.sessions.get_running()
                if running is None or running.id != item.session_id:
                    raise InvalidStateError(
                        "The entry no longer runs",
                        user_message="Der Eintrag läuft nicht mehr; es gibt nichts zu beenden.",
                    )
                since = datetime.fromisoformat(str(item.payload["idle_since"]))
                repos.sessions.end(running.id, max(since, running.started_at), Quality.UNCERTAIN)
                if action == IDLE_PAUSE:
                    repos.state.set(
                        STATE_PAUSED,
                        json.dumps(
                            {"activity_id": running.activity_id, "project_id": running.project_id}
                        ),
                    )
            repos.attention.close(
                item.id, AttentionStatus.RESOLVED, action, ensure_utc(self._clock())
            )
            repos.audit.add("resolve_idle", "attention", item.id, action)
            return repos.attention.require(item.id)

    def resolve_auto_stop(
        self, item_id: str, action: str, until: datetime | None = None
    ) -> AttentionItem:
        """Answer an automatic-stop question.

        Args:
            item_id: The open ``auto_stop`` item.
            action: ``keep`` (the stop was right) or ``extend`` (work continued until ``until``).
            until: New end for ``extend``; must lie after the automatic end and not in the
                future.

        Raises:
            ValidationError: For an unknown action or a missing/invalid ``until``.
            InvalidStateError: If the item is not an open auto-stop question or the time is
                taken by another entry.
        """
        if action not in STOP_ACTIONS:
            raise ValidationError(
                f"Unknown auto-stop action {action!r}",
                user_message="Unbekannte Antwort. Erlaubt sind: so lassen, verlängern.",
            )
        now = ensure_utc(self._clock())
        with self._storage.transaction() as repos:
            item = self._open_item(repos, item_id, AttentionKind.AUTO_STOP)
            if action == STOP_EXTEND:
                ended = datetime.fromisoformat(str(item.payload["ended_at"]))
                if until is None:
                    raise ValidationError(
                        "extend needs a time",
                        user_message="Bitte geben Sie an, bis wann Sie gearbeitet haben.",
                    )
                end = ensure_utc(until)
                if end <= ended or end > now + timedelta(minutes=1):
                    raise ValidationError(
                        "until out of range",
                        user_message="Die Zeit muss nach dem automatischen Ende und darf nicht "
                        "in der Zukunft liegen.",
                    )
                later = [
                    s
                    for s in repos.sessions.list_between(ended, end)
                    if s.id != item.session_id and s.started_at >= ended
                ]
                if later:
                    raise InvalidStateError(
                        "The time is taken by another entry",
                        user_message="In dieser Zeit läuft oder lief schon ein anderer Eintrag.",
                    )
                repos.sessions.correct(
                    str(item.session_id),
                    {"ended_at": end},
                    "Automatischen Stopp am Arbeitsende verlängert",
                )
            repos.attention.close(item.id, AttentionStatus.RESOLVED, action, now)
            repos.audit.add("resolve_auto_stop", "attention", item.id, action)
            return repos.attention.require(item.id)

    @staticmethod
    def _open_item(repos: Repositories, item_id: str, kind: AttentionKind) -> AttentionItem:
        item = repos.attention.require(item_id)
        if item.kind is not kind or item.status is not AttentionStatus.OPEN:
            raise InvalidStateError(
                f"Attention item {item_id} is not an open {kind.value} question",
                user_message="Diese Rückfrage ist schon beantwortet oder von anderer Art.",
            )
        return item
