"""Single-active-tracker session orchestration.

Responsibility
--------------
Turns tracker events and user actions into **sessions** according to the rules of the
Pflichtenheft (section 6), inside atomic database transactions:

* One personal running session at a time, fed by the **selected active tracker**.
  Events of inactive trackers are stored for diagnostics but never create sessions.
* The baseline (first value after connecting) never starts a session on its own unless the
  user chose ``adopt_current``; after a reconnect the running session simply *continues*
  when the same face is up (no accidental new session, acceptance A-04).
* A connection loss never invents history: the running session is flagged ``uncertain``
  (or ended, depending on the policy) and the user confirms or corrects it afterwards.
* Manual start/stop/pause/resume, back-dated sessions, splitting, audited corrections,
  deletion and explicit tracker hand-over (acceptance A-07).

The service holds no BLE or HTTP knowledge; the agent feeds it ``RawEvent`` objects and the
API calls its user operations. Time comes from an injectable clock for deterministic tests.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from octaledger.application.outbox import QueueResult, enqueue_face_action
from octaledger.application.tag_service import TagService
from octaledger.core.errors import InvalidStateError, ValidationError
from octaledger.core.settings import (
    BaselinePolicy,
    DisconnectPolicy,
    NeutralPolicy,
    TrackingSettings,
)
from octaledger.domain.attention import AttentionItem, AttentionKind, AttentionStatus
from octaledger.domain.link_loss import LinkAction, decide
from octaledger.domain.models import (
    FACE_NUMBERS,
    Activity,
    ButtonAction,
    DeviceMode,
    EventKind,
    Project,
    Quality,
    RawEvent,
    Session,
    SessionSource,
)
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.repositories import Repositories, Storage

logger = logging.getLogger(__name__)

#: Keys in the persistent application state.
STATE_ACTIVE_DEVICE = "active_device"
STATE_PAUSED = "paused"
#: Prefix of the per-device marker "connection lost at ..." (JSON value).
STATE_LINK_LOST = "link_lost:"
#: Answers the user can give to a gap question.
GAP_KEEP = "keep"
GAP_DISCARD = "discard"
GAP_ASSIGN = "assign"
GAP_ACTIONS = (GAP_KEEP, GAP_DISCARD, GAP_ASSIGN)
#: Tolerance for "end lies in the future" checks on back-dated sessions.
FUTURE_TOLERANCE = timedelta(minutes=1)


class Outcome(StrEnum):
    """What :meth:`TrackingService.record_event` did with an event."""

    #: Stored for diagnostics only (inactive device, observe-only policy, plain events).
    STORED = "stored"
    #: A new session was started.
    STARTED = "started"
    #: The running session was ended and another one started.
    SWITCHED = "switched"
    #: The already running session matches; nothing changed.
    CONTINUED = "continued"
    #: The running session was ended (pause policy or stop-on-disconnect).
    ENDED = "ended"
    #: The running session was flagged uncertain.
    MARKED_UNCERTAIN = "marked_uncertain"
    #: The face has no activity assigned; nothing was booked.
    UNMAPPED = "unmapped"
    #: Control mode: the face's action was queued for sending.
    ACTION_QUEUED = "action_queued"
    #: Control mode: nothing was queued (face without action, connection off, queue full).
    ACTION_SKIPPED = "action_skipped"


@dataclass(frozen=True, slots=True)
class EventResult:
    """Result of handling one event."""

    outcome: Outcome
    session: Session | None = None


@dataclass(frozen=True, slots=True)
class TrackingStatus:
    """Snapshot for the dashboard's overview page."""

    running: Session | None
    activity: Activity | None
    project: Project | None
    elapsed: timedelta
    paused: bool
    active_device_id: str | None
    uncertain_count: int


class TrackingService:
    """Session logic for one person with one active tracker."""

    def __init__(
        self,
        storage: Storage,
        settings: TrackingSettings | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
        timezone: Callable[[], str] = lambda: "UTC",
    ) -> None:
        """Create the service.

        Args:
            storage: Transactional storage.
            settings: Tracking rules (baseline, neutral, disconnect policy).
            clock: Returns the current UTC time (injectable for tests).
            timezone: Returns the display timezone; the time windows of action steps use it.
        """
        self._storage = storage
        self._settings = settings or TrackingSettings()
        self._clock = clock
        self._timezone = timezone

    # ------------------------------------------------------------------ helpers

    def _now(self) -> datetime:
        return ensure_utc(self._clock(), name="clock")

    @staticmethod
    def _floor(repos: Repositories) -> datetime | None:
        """Earliest moment a new session may start without overlapping history."""
        running = repos.sessions.get_running()
        last_end = repos.sessions.last_ended()
        candidates = [t for t in (running.started_at if running else None, last_end) if t]
        return max(candidates) if candidates else None

    def _effective(self, repos: Repositories, wanted: datetime) -> datetime:
        """Clamp ``wanted`` so it never precedes the running start or the last end.

        Protects against clock jumps and late events; the clamped session may become
        zero-length but never overlaps.
        """
        wanted = ensure_utc(wanted, name="time")
        floor = self._floor(repos)
        if floor is not None and wanted < floor:
            logger.warning(
                "Event time %s precedes %s; clamped", wanted.isoformat(), floor.isoformat()
            )
            return floor
        return wanted

    @staticmethod
    def _clear_pause(repos: Repositories) -> None:
        repos.state.delete(STATE_PAUSED)

    @staticmethod
    def _require_refs(repos: Repositories, activity_id: str, project_id: str | None) -> None:
        """Ensure referenced activity/project exist (clear NotFoundError instead of FK error)."""
        repos.activities.require(activity_id)
        if project_id is not None:
            repos.projects.require(project_id)

    def _switch_to(
        self,
        repos: Repositories,
        *,
        activity_id: str,
        project_id: str | None,
        device_id: str | None,
        at: datetime,
        source: SessionSource,
    ) -> EventResult:
        """End the running session (if different) and start the requested one."""
        running = repos.sessions.get_running()
        if (
            running is not None
            and running.activity_id == activity_id
            and running.project_id == project_id
        ):
            return EventResult(Outcome.CONTINUED, running)
        when = self._effective(repos, at)
        if running is not None:
            repos.sessions.end(running.id, when)
        session = repos.sessions.add(
            Session(
                activity_id=activity_id,
                project_id=project_id,
                device_id=device_id,
                started_at=when,
                source=source,
            )
        )
        TagService.apply_default_tags(repos, session.id, session.activity_id)
        self._clear_pause(repos)
        return EventResult(Outcome.SWITCHED if running else Outcome.STARTED, session)

    # --------------------------------------------------------------- active tracker

    def get_active_device_id(self) -> str | None:
        """Return the selected active tracker (``None`` if none or it no longer exists)."""
        with self._storage.read() as repos:
            device_id = repos.state.get(STATE_ACTIVE_DEVICE)
            if device_id is not None and repos.devices.get(device_id) is None:
                return None
            return device_id

    def set_active_device(self, device_id: str | None) -> None:
        """Select the tracker whose events feed the personal session.

        Raises:
            NotFoundError: If the device is not registered.
        """
        with self._storage.transaction() as repos:
            if device_id is None:
                repos.state.delete(STATE_ACTIVE_DEVICE)
            else:
                repos.devices.require(device_id)
                repos.state.set(STATE_ACTIVE_DEVICE, device_id)
        logger.info("Active tracker set to %s", device_id[:8] if device_id else "none")

    def handover(self, new_device_id: str, at: datetime | None = None) -> Session | None:
        """Explicitly hand over to another tracker without double-counting time.

        A running **device** session of the old tracker is ended at ``at``; the new tracker
        starts its own session with its next orientation event. Manual sessions keep running.

        Returns:
            The session that was ended, or ``None``.

        Raises:
            NotFoundError: If the new device is not registered.
            InvalidStateError: If the new device is in control mode.
        """
        with self._storage.transaction() as repos:
            candidate = repos.devices.require(new_device_id)
            if candidate.mode is DeviceMode.CONTROL:
                raise InvalidStateError(
                    f"Device {new_device_id} is in control mode",
                    user_message=(
                        "Ein Würfel im Steuerungsmodus kann nicht der aktive Zeit-Tracker sein. "
                        "Stellen Sie ihn zuerst auf Zeiterfassung."
                    ),
                )
            current = repos.state.get(STATE_ACTIVE_DEVICE)
            if current == new_device_id:
                return None
            ended: Session | None = None
            running = repos.sessions.get_running()
            if running is not None and running.source is SessionSource.DEVICE:
                ended = repos.sessions.end(running.id, self._effective(repos, at or self._now()))
            repos.state.set(STATE_ACTIVE_DEVICE, new_device_id)
        logger.info("Hand-over to tracker %s", new_device_id[:8])
        return ended

    # --------------------------------------------------------------- tracker events

    def record_event(self, event: RawEvent) -> EventResult:
        """Store ``event`` and apply the session rules, atomically.

        Events of devices other than the active one are stored but have no session effect.
        A tracker in **control mode** never touches sessions: a face change queues the action of
        that face (in the same transaction, so it is neither lost nor sent twice), everything
        else is only stored. The first value after connecting (baseline) never triggers an action.

        Args:
            event: The observation; ``received_at`` is the time the value was first seen.

        Returns:
            What happened (see :class:`Outcome`).

        Raises:
            ConflictError: If the device is unknown (foreign key) or a rule is violated.
        """
        with self._storage.transaction() as repos:
            repos.events.add(event)
            device = repos.devices.require(event.device_id)
            if device.mode is DeviceMode.CONTROL:
                result = self._control_event(repos, event)
            elif repos.state.get(STATE_ACTIVE_DEVICE) != event.device_id:
                logger.debug("Event %s of inactive device stored only", event.kind.value)
                return EventResult(Outcome.STORED)
            else:
                result = self._apply_event(repos, event)
        logger.info("Event %s (%s) -> %s", event.kind.value, event.raw_value, result.outcome.value)
        return result

    def _control_event(self, repos: Repositories, event: RawEvent) -> EventResult:
        """Control mode: only a real face change (1..8) queues the action of that face."""
        if (
            event.kind is not EventKind.FACE_CHANGE
            or event.raw_value is None
            or event.raw_value not in FACE_NUMBERS
        ):
            return EventResult(Outcome.STORED)
        queued = enqueue_face_action(
            repos,
            event.device_id,
            event.raw_value,
            event.id,
            self._now(),
            ZoneInfo(self._timezone()),
        )
        if queued is QueueResult.QUEUED:
            return EventResult(Outcome.ACTION_QUEUED)
        return EventResult(Outcome.ACTION_SKIPPED)

    def _apply_event(self, repos: Repositories, event: RawEvent) -> EventResult:
        kind = event.kind
        if kind in (EventKind.BASELINE, EventKind.RECONNECT):
            self._on_return(repos, event)
        if kind is EventKind.FACE_CHANGE:
            return self._on_face(repos, event)
        if kind is EventKind.BASELINE:
            return self._on_baseline(repos, event)
        if kind is EventKind.NEUTRAL:
            return self._on_neutral(repos, event)
        if kind is EventKind.DISCONNECT:
            return self._on_disconnect(repos, event)
        if kind is EventKind.BUTTON:
            return self._on_button(repos, event)
        return EventResult(Outcome.STORED)  # reconnect / invalid: diagnostics only

    def _mapping(self, repos: Repositories, event: RawEvent) -> tuple[str, str | None] | None:
        """Return ``(activity_id, project_id)`` for the event's face, if configured."""
        if event.raw_value is None or event.raw_value == 0:
            return None
        mapping = repos.mappings.get(event.device_id, event.raw_value)
        if mapping is None or mapping.activity_id is None:
            logger.warning(
                "Face %s of device %s has no activity assigned",
                event.raw_value,
                event.device_id[:8],
            )
            return None
        return mapping.activity_id, mapping.project_id

    def _on_face(self, repos: Repositories, event: RawEvent) -> EventResult:
        target = self._mapping(repos, event)
        if target is None:
            return EventResult(Outcome.UNMAPPED)
        return self._switch_to(
            repos,
            activity_id=target[0],
            project_id=target[1],
            device_id=event.device_id,
            at=event.received_at,
            source=SessionSource.DEVICE,
        )

    def _on_baseline(self, repos: Repositories, event: RawEvent) -> EventResult:
        target = self._mapping(repos, event)
        running = repos.sessions.get_running()
        if (
            running is not None
            and running.device_id == event.device_id
            and target == (running.activity_id, running.project_id)
        ):
            # Reconnect with the same face up: continue, never start a new session (A-04).
            # An 'uncertain' flag stays until the user confirms it.
            return EventResult(Outcome.CONTINUED, running)
        if self._settings.baseline_policy is BaselinePolicy.ADOPT_CURRENT and target is not None:
            return self._switch_to(
                repos,
                activity_id=target[0],
                project_id=target[1],
                device_id=event.device_id,
                at=event.received_at,
                source=SessionSource.DEVICE,
            )
        return EventResult(Outcome.STORED)  # observe only

    def _on_neutral(self, repos: Repositories, event: RawEvent) -> EventResult:
        if self._settings.neutral_policy is not NeutralPolicy.PAUSE:
            return EventResult(Outcome.STORED)
        running = repos.sessions.get_running()
        if running is None or running.device_id != event.device_id:
            return EventResult(Outcome.STORED)
        ended = repos.sessions.end(running.id, self._effective(repos, event.received_at))
        repos.state.set(
            STATE_PAUSED,
            json.dumps({"activity_id": running.activity_id, "project_id": running.project_id}),
        )
        return EventResult(Outcome.ENDED, ended)

    def _on_disconnect(self, repos: Repositories, event: RawEvent) -> EventResult:
        running = repos.sessions.get_running()
        if running is None or running.device_id != event.device_id:
            return EventResult(Outcome.STORED)  # nothing of this device is running
        policy = self._settings.disconnect_policy
        stop_now = policy is DisconnectPolicy.STOP_SESSION or (
            policy is DisconnectPolicy.GRACE_THEN_STOP
            and self._settings.disconnect_grace_seconds == 0
        )
        if stop_now:
            ended = repos.sessions.end(
                running.id, self._effective(repos, event.received_at), Quality.UNCERTAIN
            )
            return EventResult(Outcome.ENDED, ended)
        marked = repos.sessions.set_quality(running.id, Quality.UNCERTAIN)
        if policy is DisconnectPolicy.GRACE_THEN_STOP:
            when = self._effective(repos, event.received_at)
            repos.state.set(
                STATE_LINK_LOST + event.device_id,
                json.dumps({"at": when.isoformat(), "stopped": False, "session": running.id}),
            )
            logger.info(
                "Connection lost; grace period of %d s started",
                self._settings.disconnect_grace_seconds,
            )
        return EventResult(Outcome.MARKED_UNCERTAIN, marked)

    def _on_button(self, repos: Repositories, event: RawEvent) -> EventResult:
        """Run the action assigned to a button press (nothing is assigned by default).

        Only the **active** tracker's button gets here (see :meth:`record_event`). The actions
        use the same rules as the manual operations, in this event's transaction.
        """
        action = repos.buttons.get(event.device_id, str(event.detail))
        if action is None:
            return EventResult(Outcome.STORED)
        running = repos.sessions.get_running()
        when = self._effective(repos, event.received_at)
        if action is ButtonAction.STOP:
            if running is None:
                return EventResult(Outcome.STORED)
            ended = repos.sessions.end(running.id, when)
            self._clear_pause(repos)
            return EventResult(Outcome.ENDED, ended)
        if action is ButtonAction.PAUSE_RESUME:
            if running is not None:
                ended = repos.sessions.end(running.id, when)
                repos.state.set(
                    STATE_PAUSED,
                    json.dumps(
                        {"activity_id": running.activity_id, "project_id": running.project_id}
                    ),
                )
                return EventResult(Outcome.ENDED, ended)
            raw = repos.state.get(STATE_PAUSED)
            if raw is None:
                return EventResult(Outcome.STORED)
            data = json.loads(raw)
            return self._start_for_button(repos, data["activity_id"], data.get("project_id"), when)
        # START_LAST: the most recently used activity, unless something is running already.
        if running is not None:
            return EventResult(Outcome.CONTINUED, running)
        last = repos.sessions.list_all()
        if not last:
            return EventResult(Outcome.STORED)
        latest = max(last, key=lambda s: s.started_at)
        return self._start_for_button(repos, latest.activity_id, latest.project_id, when)

    def _start_for_button(
        self, repos: Repositories, activity_id: str, project_id: str | None, when: datetime
    ) -> EventResult:
        """Start a manual entry for a button press (the activity may have been deleted)."""
        if repos.activities.get(activity_id) is None:
            return EventResult(Outcome.STORED)
        session = repos.sessions.add(
            Session(
                activity_id=activity_id,
                project_id=project_id,
                started_at=when,
                source=SessionSource.MANUAL,
            )
        )
        TagService.apply_default_tags(repos, session.id, session.activity_id)
        self._clear_pause(repos)
        return EventResult(Outcome.STARTED, session)

    def _on_return(self, repos: Repositories, event: RawEvent) -> None:
        """The tracker is back: end the grace period or record when the gap ended."""
        key = STATE_LINK_LOST + event.device_id
        raw = repos.state.get(key)
        if raw is None:
            return
        marker = json.loads(raw)
        repos.state.delete(key)
        if not marker.get("stopped"):
            logger.info("Tracker returned within the grace period; entry continues")
            return
        for item in repos.attention.list_open():
            if item.kind is AttentionKind.GAP and item.payload.get("device_id") == event.device_id:
                repos.attention.update_payload(
                    item.id, {**item.payload, "returned_at": event.received_at.isoformat()}
                )
                logger.info("Tracker returned after the grace period; gap question updated")

    # ------------------------------------------------------------ link-loss watchdog

    def watchdog(self, now: datetime | None = None) -> list[AttentionItem]:
        """End entries whose lost connection outlasted the grace period (called by a timer).

        For every device with a "connection lost" marker the pure rule
        :func:`octaledger.domain.link_loss.decide` is applied. When the period is over the
        running entry of that device is ended **at the moment of the loss** (flagged uncertain)
        and a ``gap`` question is raised. If the entry was already ended or replaced by the user
        in the meantime, the marker is simply dropped; no time is invented.

        Args:
            now: Current time (default: the service clock).

        Returns:
            The newly raised questions.
        """
        moment = ensure_utc(now, name="now") if now is not None else self._now()
        grace = timedelta(seconds=self._settings.disconnect_grace_seconds)
        raised: list[AttentionItem] = []
        with self._storage.transaction() as repos:
            for key, raw in repos.state.items().items():
                if not key.startswith(STATE_LINK_LOST):
                    continue
                marker = json.loads(raw)
                device_id = key[len(STATE_LINK_LOST) :]
                lost_at = datetime.fromisoformat(marker["at"])
                action = decide(lost_at, moment, grace, already_stopped=bool(marker.get("stopped")))
                if action is not LinkAction.STOP_AT_LOSS:
                    continue
                running = repos.sessions.get_running()
                if running is None or running.id != marker.get("session"):
                    repos.state.delete(key)  # the user acted meanwhile; nothing to decide
                    continue
                repos.sessions.end(running.id, self._effective(repos, lost_at), Quality.UNCERTAIN)
                marker["stopped"] = True
                repos.state.set(key, json.dumps(marker))
                item = repos.attention.add(
                    AttentionItem(
                        kind=AttentionKind.GAP,
                        created_at=moment,
                        session_id=running.id,
                        payload={
                            "device_id": device_id,
                            "lost_at": lost_at.isoformat(),
                            "returned_at": None,
                            "activity_id": running.activity_id,
                            "project_id": running.project_id,
                        },
                    )
                )
                raised.append(item)
                logger.warning("Grace period over: entry ended at the loss, gap question raised")
        return raised

    def link_lost_since(self) -> dict[str, datetime]:
        """Return ``device_id -> loss time`` for connections that are lost but not yet ended."""
        result: dict[str, datetime] = {}
        with self._storage.read() as repos:
            for key, raw in repos.state.items().items():
                if key.startswith(STATE_LINK_LOST):
                    marker = json.loads(raw)
                    if not marker.get("stopped"):
                        result[key[len(STATE_LINK_LOST) :]] = datetime.fromisoformat(marker["at"])
        return result

    def resolve_gap(
        self,
        item_id: str,
        action: str,
        *,
        activity_id: str | None = None,
        project_id: str | None = None,
    ) -> AttentionItem:
        """Answer a gap question; every change is audited.

        Args:
            item_id: The attention item (kind ``gap``, status open).
            action: ``keep`` (extend the ended entry over the gap), ``discard`` (leave the gap
                empty) or ``assign`` (book the gap on another activity).
            activity_id: Required for ``assign``.
            project_id: Optional project for ``assign``.

        Returns:
            The closed item.

        Raises:
            ValidationError: For an unknown action or ``assign`` without an activity.
            InvalidStateError: If the item is not an open gap question or the gap is already
                occupied by another entry.
            NotFoundError: If the item, activity or project does not exist.
        """
        if action not in GAP_ACTIONS:
            raise ValidationError(
                f"Unknown gap action {action!r}",
                user_message="Unbekannte Antwort. Erlaubt sind: behalten, verwerfen, zuordnen.",
            )
        with self._storage.transaction() as repos:
            item = repos.attention.require(item_id)
            if item.kind is not AttentionKind.GAP or item.status is not AttentionStatus.OPEN:
                raise InvalidStateError(
                    f"Attention item {item_id} is not an open gap question",
                    user_message="Diese Rückfrage ist schon beantwortet oder keine Lücke.",
                )
            if action != GAP_DISCARD:
                self._fill_gap(repos, item, action, activity_id, project_id)
            repos.attention.close(item.id, AttentionStatus.RESOLVED, action, self._now())
            repos.audit.add("resolve_gap", "attention", item.id, action)
            closed = repos.attention.require(item.id)
        logger.info("Gap question answered: %s", action)
        return closed

    def _fill_gap(
        self,
        repos: Repositories,
        item: AttentionItem,
        action: str,
        activity_id: str | None,
        project_id: str | None,
    ) -> None:
        """Extend the ended entry (``keep``) or book the gap (``assign``)."""
        lost_at = datetime.fromisoformat(str(item.payload["lost_at"]))
        returned = item.payload.get("returned_at")
        end = datetime.fromisoformat(str(returned)) if returned else self._now()
        # Never overlap the next entry: the gap ends where the next one starts.
        later = [
            s
            for s in repos.sessions.list_between(lost_at, end + timedelta(days=1))
            if s.started_at >= lost_at and s.id != item.session_id
        ]
        if later:
            end = min(end, min(s.started_at for s in later))
        if end <= lost_at:
            raise InvalidStateError(
                "The gap is already occupied",
                user_message="Die Lücke ist schon von einem anderen Eintrag belegt.",
            )
        if action == GAP_KEEP:
            repos.sessions.correct(
                str(item.session_id),
                {"ended_at": end},
                "Lücke nach Verbindungsverlust behalten",
            )
            return
        if activity_id is None:
            raise ValidationError(
                "assign requires an activity",
                user_message="Bitte wählen Sie eine Tätigkeit für die Lücke.",
            )
        self._require_refs(repos, activity_id, project_id)
        repos.sessions.add(
            Session(
                activity_id=activity_id,
                project_id=project_id,
                started_at=lost_at,
                ended_at=end,
                source=SessionSource.MANUAL,
                quality=Quality.UNCERTAIN,
                note="Lücke nach Verbindungsverlust",
            )
        )

    # ----------------------------------------------------------- manual operations

    def start_manual(
        self,
        activity_id: str,
        project_id: str | None = None,
        note: str | None = None,
        at: datetime | None = None,
    ) -> Session:
        """Start a manual session now (or at ``at``); a running session is ended first.

        Raises:
            NotFoundError: If activity or project do not exist.
        """
        with self._storage.transaction() as repos:
            self._require_refs(repos, activity_id, project_id)
            when = self._effective(repos, at or self._now())
            running = repos.sessions.get_running()
            if running is not None:
                repos.sessions.end(running.id, when)
            session = repos.sessions.add(
                Session(
                    activity_id=activity_id,
                    project_id=project_id,
                    started_at=when,
                    source=SessionSource.MANUAL,
                    note=note,
                )
            )
            TagService.apply_default_tags(repos, session.id, session.activity_id)
            self._clear_pause(repos)
        return session

    def stop(self, at: datetime | None = None) -> Session:
        """End the running session.

        Raises:
            InvalidStateError: If nothing is running.
        """
        with self._storage.transaction() as repos:
            running = repos.sessions.get_running()
            if running is None:
                raise InvalidStateError(
                    "No running session to stop",
                    user_message="Es läuft gerade keine Zeiterfassung.",
                )
            ended = repos.sessions.end(running.id, self._effective(repos, at or self._now()))
            self._clear_pause(repos)
        return ended

    def pause(self) -> Session:
        """End the running session and remember its activity so :meth:`resume` can continue.

        Raises:
            InvalidStateError: If nothing is running.
        """
        with self._storage.transaction() as repos:
            running = repos.sessions.get_running()
            if running is None:
                raise InvalidStateError(
                    "No running session to pause",
                    user_message="Es läuft gerade keine Zeiterfassung, die pausiert werden könnte.",
                )
            ended = repos.sessions.end(running.id, self._effective(repos, self._now()))
            repos.state.set(
                STATE_PAUSED,
                json.dumps({"activity_id": running.activity_id, "project_id": running.project_id}),
            )
        return ended

    def resume(self) -> Session:
        """Continue the activity that was paused (as a new session).

        Raises:
            InvalidStateError: If tracking is not paused.
            NotFoundError: If the paused activity no longer exists.
        """
        with self._storage.transaction() as repos:
            raw = repos.state.get(STATE_PAUSED)
            if raw is None:
                raise InvalidStateError(
                    "Tracking is not paused",
                    user_message="Es ist keine Pause aktiv, die fortgesetzt werden könnte.",
                )
            data = json.loads(raw)
            if repos.sessions.get_running() is not None:
                raise InvalidStateError("A session is already running")
            self._require_refs(repos, data["activity_id"], data.get("project_id"))
            session = repos.sessions.add(
                Session(
                    activity_id=data["activity_id"],
                    project_id=data.get("project_id"),
                    started_at=self._effective(repos, self._now()),
                    source=SessionSource.MANUAL,
                )
            )
            TagService.apply_default_tags(repos, session.id, session.activity_id)
            self._clear_pause(repos)
        return session

    def add_manual_session(
        self,
        activity_id: str,
        start: datetime,
        end: datetime,
        project_id: str | None = None,
        note: str | None = None,
    ) -> Session:
        """Add a finished, back-dated session.

        Raises:
            ValidationError: If ``end`` is before ``start`` or clearly in the future.
            NotFoundError: If activity or project do not exist.
            ConflictError: If it overlaps an existing session.
        """
        end_utc = ensure_utc(end, name="end")
        if end_utc > self._now() + FUTURE_TOLERANCE:
            raise ValidationError(
                "Session ends in the future",
                user_message="Das Ende liegt in der Zukunft.",
            )
        with self._storage.transaction() as repos:
            self._require_refs(repos, activity_id, project_id)
            return repos.sessions.add(
                Session(
                    activity_id=activity_id,
                    project_id=project_id,
                    started_at=start,
                    ended_at=end_utc,
                    source=SessionSource.MANUAL,
                    note=note,
                )
            )

    # ------------------------------------------------- correcting existing sessions

    def correct_session(
        self, session_id: str, changes: Mapping[str, object], reason: str
    ) -> Session:
        """Change a session with an audit trail (see ``SessionRepository.correct``)."""
        with self._storage.transaction() as repos:
            if "activity_id" in changes or "project_id" in changes:
                # Check references up front for a clear "not found" instead of a database
                # constraint error.
                current = repos.sessions.require(session_id)
                activity_id = changes.get("activity_id", current.activity_id)
                project_id = changes.get("project_id", current.project_id)
                if isinstance(activity_id, str):
                    repos.activities.require(activity_id)
                if isinstance(project_id, str):
                    repos.projects.require(project_id)
            return repos.sessions.correct(session_id, changes, reason)

    def confirm_session(self, session_id: str) -> Session:
        """Mark an uncertain session as confirmed (idempotent)."""
        with self._storage.transaction() as repos:
            session = repos.sessions.require(session_id)
            if session.quality is Quality.CONFIRMED:
                return session
            return repos.sessions.correct(
                session_id, {"quality": Quality.CONFIRMED}, "Vom Benutzer bestätigt"
            )

    def split_session(self, session_id: str, at: datetime, reason: str) -> tuple[Session, Session]:
        """Split a session in two at ``at``; the second part inherits all attributes.

        A running session keeps running as the second part. Both parts together cover
        exactly the original span.

        Raises:
            ValidationError: If ``at`` is not strictly inside the session.
        """
        at = ensure_utc(at, name="at")
        with self._storage.transaction() as repos:
            original = repos.sessions.require(session_id)
            end_limit = original.ended_at or self._now()
            if not original.started_at < at < end_limit:
                raise ValidationError(
                    "Split time must lie strictly inside the session",
                    user_message="Der Teilungszeitpunkt muss innerhalb der Sitzung liegen.",
                    details={"session_id": session_id},
                )
            first = repos.sessions.correct(session_id, {"ended_at": at}, reason)
            second = repos.sessions.add(
                Session(
                    activity_id=original.activity_id,
                    project_id=original.project_id,
                    device_id=original.device_id,
                    started_at=at,
                    ended_at=original.ended_at,
                    source=original.source,
                    quality=original.quality,
                    note=original.note,
                )
            )
        return first, second

    def delete_session(self, session_id: str, reason: str) -> None:
        """Delete a session; the deletion is recorded with its reason."""
        with self._storage.transaction() as repos:
            repos.sessions.delete(session_id, reason, repos.audit)

    def list_uncertain(self) -> list[Session]:
        """Return sessions awaiting the user's confirmation."""
        with self._storage.read() as repos:
            return repos.sessions.list_by_quality(Quality.UNCERTAIN)

    # ----------------------------------------------------------------------- status

    def status(self) -> TrackingStatus:
        """Return a snapshot for the overview page."""
        now = self._now()
        with self._storage.read() as repos:
            running = repos.sessions.get_running()
            activity = repos.activities.get(running.activity_id) if running else None
            project = (
                repos.projects.get(running.project_id) if running and running.project_id else None
            )
            device_id = repos.state.get(STATE_ACTIVE_DEVICE)
            if device_id is not None and repos.devices.get(device_id) is None:
                device_id = None
            return TrackingStatus(
                running=running,
                activity=activity,
                project=project,
                elapsed=running.duration(now) if running else timedelta(0),
                paused=repos.state.get(STATE_PAUSED) is not None,
                active_device_id=device_id,
                uncertain_count=len(repos.sessions.list_by_quality(Quality.UNCERTAIN)),
            )
