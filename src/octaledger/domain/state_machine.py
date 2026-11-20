"""Per-device baseline, debounce and connection state rules.

Responsibility
--------------
Two small, **pure and deterministic** state machines (no I/O, no threads, no real clock),
so every rule can be unit-tested with injected time:

* :class:`OrientationDebouncer` turns the raw stream of orientation values into clean
  events: the first value after (re)connecting is only a *baseline*, duplicates are
  ignored, and a new face counts only after it stayed stable for the debounce time
  (intermediate faces while turning the tracker never trigger a change).
* :class:`ConnectionStateMachine` guards the lifecycle
  ``idle -> scanning -> connecting -> discovering -> subscribing -> baseline -> ready``
  and ``ready -> disconnected -> reconnect_wait -> connecting``. It hands out a new
  *connection id* for every connection cycle so late results of an old cycle can be
  recognised and ignored.

Time is passed in as integer milliseconds of a **monotonic** clock (e.g.
``time.monotonic_ns() // 1_000_000``). Monotonic time is only comparable within one
process, which is exactly how it is used here (see Pflichtenheft section 6).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from octaledger.core.errors import InvalidStateError, ValidationError
from octaledger.domain.models import EventKind, new_id

logger = logging.getLogger(__name__)

#: Highest valid orientation value (0 = neutral, 1..8 = faces).
MAX_VALUE: Final = 8


# ------------------------------------------------------------------ orientation debouncing


@dataclass(frozen=True, slots=True)
class OrientationEvent:
    """A clean event produced by the debouncer.

    Attributes:
        kind: ``BASELINE``, ``FACE_CHANGE`` or ``NEUTRAL``.
        value: The face ``1..8`` or ``0`` for neutral.
        observed_at_ms: Monotonic time at which the value was **first seen**. For a
            debounced change this is the moment the face turned up, not the (later)
            moment the stability period ended, so sessions start at the true time.
    """

    kind: EventKind
    value: int
    observed_at_ms: int


@dataclass(slots=True)
class _Candidate:
    """A value seen but not yet stable for the debounce period."""

    value: int
    since_ms: int


class OrientationDebouncer:
    """Baseline, duplicate and debounce handling for one device.

    Usage: call :meth:`feed` for every received value and :meth:`tick` whenever
    :meth:`next_deadline_ms` has passed (the agent schedules a timer for it). Call
    :meth:`reset` on every new connection so the first value is a baseline again.

    Rules (Pflichtenheft F-06/F-07, acceptance A-02/A-03):

    1. The first value after :meth:`reset` is a ``BASELINE`` event, emitted at once.
    2. A value equal to the committed value is a duplicate and ignored. If a different
       candidate was pending, it is cancelled (the tracker returned before stabilising).
    3. A different value becomes a candidate. It is committed once it has been stable for
       ``debounce_ms``; a different value in between restarts the timer.
    4. Committing ``0`` yields ``NEUTRAL``, committing ``1..8`` yields ``FACE_CHANGE``.
    """

    def __init__(self, debounce_ms: int = 300) -> None:
        """Create a debouncer.

        Args:
            debounce_ms: Stability time in milliseconds (``0`` commits immediately).

        Raises:
            ValidationError: If ``debounce_ms`` is negative or not an integer.
        """
        if isinstance(debounce_ms, bool) or not isinstance(debounce_ms, int) or debounce_ms < 0:
            raise ValidationError(
                "debounce_ms must be a non-negative integer", details={"debounce_ms": debounce_ms}
            )
        self._debounce_ms = debounce_ms
        self._committed: int | None = None
        self._candidate: _Candidate | None = None
        self._last_now_ms: int | None = None
        #: Diagnostics counters (exposed read-only).
        self.duplicates_ignored = 0
        self.unstable_ignored = 0

    # ---------------------------------------------------------------- read-only state

    @property
    def committed_value(self) -> int | None:
        """The last committed value, or ``None`` before the baseline."""
        return self._committed

    @property
    def pending_value(self) -> int | None:
        """The candidate still waiting for stability, if any."""
        return self._candidate.value if self._candidate else None

    @property
    def debounce_ms(self) -> int:
        """Configured stability time."""
        return self._debounce_ms

    def next_deadline_ms(self) -> int | None:
        """Return the monotonic time at which :meth:`tick` will commit, or ``None``."""
        if self._candidate is None:
            return None
        return self._candidate.since_ms + self._debounce_ms

    # ------------------------------------------------------------------- operations

    def reset(self) -> None:
        """Forget everything; the next value is a baseline again (new connection)."""
        self._committed = None
        self._candidate = None
        self._last_now_ms = None
        logger.debug("Orientation debouncer reset")

    def feed(self, value: int, now_ms: int) -> list[OrientationEvent]:
        """Process one received value.

        Args:
            value: Decoded orientation ``0..8``.
            now_ms: Monotonic time in milliseconds when the value arrived.

        Returns:
            Zero or more events (zero for duplicates and not-yet-stable values).

        Raises:
            ValidationError: If ``value`` is outside ``0..8`` or time moved backwards.
        """
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_VALUE:
            raise ValidationError(f"Orientation value must be 0..8, got {value!r}")
        self._advance_clock(now_ms)

        # Rule 1: baseline.
        if self._committed is None:
            self._committed = value
            logger.debug("Baseline value %d", value)
            return [OrientationEvent(EventKind.BASELINE, value, now_ms)]

        events = self._commit_if_due(now_ms)
        # ``_commit_if_due`` may have committed an older candidate; compare afterwards.
        if value == self._committed:
            if self._candidate is not None:
                logger.debug("Returned to %d before stabilising, candidate dropped", value)
                self.unstable_ignored += 1
                self._candidate = None
            else:
                self.duplicates_ignored += 1
            return events

        if self._candidate is None or self._candidate.value != value:
            if self._candidate is not None:
                self.unstable_ignored += 1  # previous candidate never became stable
            self._candidate = _Candidate(value=value, since_ms=now_ms)
        else:
            self.duplicates_ignored += 1  # same candidate again, keep the original start
        return events + self._commit_if_due(now_ms)

    def tick(self, now_ms: int) -> list[OrientationEvent]:
        """Commit a pending candidate that has become stable.

        Args:
            now_ms: Current monotonic time in milliseconds.

        Returns:
            The committed event (at most one) or an empty list.

        Raises:
            ValidationError: If time moved backwards.
        """
        self._advance_clock(now_ms)
        return self._commit_if_due(now_ms)

    # --------------------------------------------------------------------- internals

    def _advance_clock(self, now_ms: int) -> None:
        """Validate that time never moves backwards (monotonic contract)."""
        if isinstance(now_ms, bool) or not isinstance(now_ms, int):
            raise ValidationError("now_ms must be an integer")
        if self._last_now_ms is not None and now_ms < self._last_now_ms:
            raise ValidationError(
                "Monotonic time moved backwards",
                details={"previous_ms": self._last_now_ms, "now_ms": now_ms},
            )
        self._last_now_ms = now_ms

    def _commit_if_due(self, now_ms: int) -> list[OrientationEvent]:
        """Commit the candidate if it was stable for the debounce period."""
        candidate = self._candidate
        if candidate is None or now_ms - candidate.since_ms < self._debounce_ms:
            return []
        self._candidate = None
        self._committed = candidate.value
        kind = EventKind.NEUTRAL if candidate.value == 0 else EventKind.FACE_CHANGE
        logger.debug("Committed %s value %d", kind.value, candidate.value)
        return [OrientationEvent(kind, candidate.value, candidate.since_ms)]


# -------------------------------------------------------------------- connection lifecycle


class ConnectionState(StrEnum):
    """Lifecycle states of one tracker connection (see ARCHITEKTUR.md)."""

    IDLE = "idle"
    SCANNING = "scanning"
    CONNECTING = "connecting"
    DISCOVERING = "discovering"
    SUBSCRIBING = "subscribing"
    BASELINE = "baseline"
    READY = "ready"
    DISCONNECTED = "disconnected"
    RECONNECT_WAIT = "reconnect_wait"
    #: The user stopped the device on purpose; no automatic reconnect happens.
    STOPPED = "stopped"


S = ConnectionState

#: Allowed transitions. ``STOPPED`` is additionally reachable from every state.
_TRANSITIONS: Final[dict[ConnectionState, frozenset[ConnectionState]]] = {
    S.IDLE: frozenset({S.SCANNING, S.CONNECTING}),
    S.SCANNING: frozenset({S.CONNECTING, S.IDLE}),
    S.CONNECTING: frozenset({S.DISCOVERING, S.DISCONNECTED, S.IDLE}),
    S.DISCOVERING: frozenset({S.SUBSCRIBING, S.DISCONNECTED}),
    S.SUBSCRIBING: frozenset({S.BASELINE, S.DISCONNECTED}),
    S.BASELINE: frozenset({S.READY, S.DISCONNECTED}),
    S.READY: frozenset({S.DISCONNECTED}),
    S.DISCONNECTED: frozenset({S.RECONNECT_WAIT}),
    S.RECONNECT_WAIT: frozenset({S.CONNECTING}),
    S.STOPPED: frozenset({S.IDLE}),
}

#: Number of recent transitions kept for diagnostics.
HISTORY_SIZE: Final = 50


class ConnectionStateMachine:
    """Validated lifecycle of one device connection with per-cycle connection ids.

    "Connected" is not the same as "valid orientation available": only ``READY`` means
    the baseline was read and orientation events may be trusted.
    """

    def __init__(self) -> None:
        """Start in ``IDLE`` with no connection id."""
        self._state = ConnectionState.IDLE
        self._connection_id: str | None = None
        self._attempt = 0
        self._history: deque[tuple[ConnectionState, ConnectionState]] = deque(maxlen=HISTORY_SIZE)

    @property
    def state(self) -> ConnectionState:
        """Current state."""
        return self._state

    @property
    def connection_id(self) -> str | None:
        """Identifier of the current connection cycle (``None`` before the first)."""
        return self._connection_id

    @property
    def attempt(self) -> int:
        """Consecutive failed attempts since the last successful ``READY``."""
        return self._attempt

    @property
    def is_ready(self) -> bool:
        """``True`` only when a baseline was read and events can be trusted."""
        return self._state is ConnectionState.READY

    @property
    def history(self) -> list[tuple[ConnectionState, ConnectionState]]:
        """Recent ``(from, to)`` transitions, oldest first."""
        return list(self._history)

    def can_transition(self, target: ConnectionState) -> bool:
        """Return whether ``target`` is allowed from the current state."""
        if target is ConnectionState.STOPPED:
            return self._state is not ConnectionState.STOPPED
        return target in _TRANSITIONS.get(self._state, frozenset())

    def transition(self, target: ConnectionState) -> ConnectionState:
        """Move to ``target`` if the transition is allowed.

        Entering ``CONNECTING`` starts a new connection cycle (new id). Reaching
        ``READY`` resets the failure counter; entering ``DISCONNECTED`` while not yet
        ready counts as a failed attempt.

        Args:
            target: The desired state.

        Returns:
            The new state.

        Raises:
            InvalidStateError: If the transition is not allowed.
        """
        target = ConnectionState(target)
        if not self.can_transition(target):
            raise InvalidStateError(
                f"Illegal connection transition {self._state.value} -> {target.value}",
                details={"from": self._state.value, "to": target.value},
            )
        previous = self._state
        if target is ConnectionState.CONNECTING:
            self._connection_id = new_id()
        if target is ConnectionState.READY:
            self._attempt = 0
        if target is ConnectionState.DISCONNECTED and previous is not ConnectionState.READY:
            self._attempt += 1
        self._state = target
        self._history.append((previous, target))
        logger.info(
            "Connection %s: %s -> %s (attempt %d)",
            (self._connection_id or "-")[:8],
            previous.value,
            target.value,
            self._attempt,
        )
        return target

    def is_current(self, connection_id: str | None) -> bool:
        """Return whether ``connection_id`` belongs to the current cycle.

        Results (events, errors) of an older cycle must be ignored by the caller.
        """
        return connection_id is not None and connection_id == self._connection_id


def reconnect_delay_seconds(
    attempt: int, *, base: float = 1.0, factor: float = 2.0, cap: float = 60.0
) -> float:
    """Return the bounded exponential backoff delay for a reconnect attempt.

    ``attempt`` 0 or 1 waits ``base`` seconds, then ``base*factor``, ... never more than
    ``cap``. The function is deterministic; callers may add jitter.

    Args:
        attempt: Number of consecutive failures so far (``>= 0``).
        base: Initial delay in seconds (``> 0``).
        factor: Growth factor (``>= 1``).
        cap: Maximum delay in seconds (``>= base``).

    Raises:
        ValidationError: If a parameter is out of range.
    """
    if attempt < 0 or base <= 0 or factor < 1 or cap < base:
        raise ValidationError(
            "Invalid backoff parameters",
            details={"attempt": attempt, "base": base, "factor": factor, "cap": cap},
        )
    exponent = max(attempt - 1, 0)
    # Guard against float overflow for absurd attempt counts: the cap is reached long before.
    if exponent > 64:
        return cap
    return min(cap, base * factor**exponent)
