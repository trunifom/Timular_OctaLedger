"""Tests for the orientation debouncer and the connection state machine.

Time is injected as monotonic milliseconds, so every scenario is deterministic.
"""

import pytest

from octaledger.core.errors import InvalidStateError, ValidationError
from octaledger.domain.models import EventKind
from octaledger.domain.state_machine import (
    ConnectionState,
    ConnectionStateMachine,
    OrientationDebouncer,
    reconnect_delay_seconds,
)

S = ConnectionState


def kinds(events: list) -> list[EventKind]:  # type: ignore[type-arg]
    return [e.kind for e in events]


# ------------------------------------------------------------------------------ baseline


def test_first_value_is_baseline_and_immediate() -> None:
    deb = OrientationDebouncer(300)
    events = deb.feed(3, 1000)
    assert [(e.kind, e.value, e.observed_at_ms) for e in events] == [(EventKind.BASELINE, 3, 1000)]
    assert deb.committed_value == 3


def test_neutral_baseline_is_still_a_baseline() -> None:
    deb = OrientationDebouncer(300)
    assert kinds(deb.feed(0, 0)) == [EventKind.BASELINE]


def test_reset_makes_next_value_baseline_again() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 0)
    deb.reset()
    assert deb.committed_value is None
    assert kinds(deb.feed(1, 5000)) == [EventKind.BASELINE]  # same face, but new baseline


def test_baseline_never_starts_a_change() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(2, 0)
    assert deb.tick(10_000) == []
    assert deb.pending_value is None


# ------------------------------------------------------------------------- duplicates A-02


def test_twenty_identical_values_cause_no_additional_change() -> None:
    deb = OrientationDebouncer(300)
    events = list(deb.feed(4, 0))
    for i in range(1, 21):
        events += deb.feed(4, i * 100)
    assert kinds(events) == [EventKind.BASELINE]
    assert deb.duplicates_ignored == 20


def test_duplicates_of_pending_candidate_keep_original_start() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 0)
    deb.feed(2, 1000)
    deb.feed(2, 1100)  # duplicate, must not restart the timer
    events = deb.feed(2, 1300)
    assert [(e.kind, e.value, e.observed_at_ms) for e in events] == [
        (EventKind.FACE_CHANGE, 2, 1000)
    ]


# ------------------------------------------------------------------------ debounce A-03


def test_stable_face_commits_after_debounce_via_feed() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 0)
    assert deb.feed(2, 1000) == []
    assert deb.pending_value == 2
    events = deb.feed(2, 1300)
    assert kinds(events) == [EventKind.FACE_CHANGE]
    assert deb.committed_value == 2 and deb.pending_value is None


def test_tick_commits_without_new_value() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 0)
    deb.feed(5, 1000)
    assert deb.next_deadline_ms() == 1300
    assert deb.tick(1299) == []
    events = deb.tick(1300)
    assert [(e.value, e.observed_at_ms) for e in events] == [(5, 1000)]  # time of first sight
    assert deb.next_deadline_ms() is None


def test_intermediate_face_below_stability_is_ignored() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 0)
    deb.feed(2, 1000)  # passing through face 2 ...
    events = deb.feed(3, 1100)  # ... to face 3
    assert events == []
    assert deb.pending_value == 3
    assert deb.tick(1400) and deb.committed_value == 3  # only the final face counts


def test_returning_to_committed_face_cancels_candidate() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 0)
    deb.feed(2, 1000)
    assert deb.feed(1, 1100) == []
    assert deb.pending_value is None
    assert deb.tick(5000) == []  # nothing left to commit
    assert deb.unstable_ignored == 1


def test_changing_candidate_restarts_the_timer() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 0)
    deb.feed(2, 1000)
    deb.feed(3, 1250)  # 2 never became stable
    assert deb.tick(1500) == []  # only 250 ms since 3 appeared
    events = deb.tick(1550)
    assert [(e.value, e.observed_at_ms) for e in events] == [(3, 1250)]


def test_late_feed_commits_old_candidate_before_judging_new_value() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 0)
    deb.feed(2, 1000)
    # No tick happened; the next value arrives after the debounce time elapsed. The old
    # candidate (2) must be committed first, then 1 is a real change back.
    events = deb.feed(1, 2000)
    assert [(e.kind, e.value) for e in events] == [(EventKind.FACE_CHANGE, 2)]
    assert deb.pending_value == 1


def test_zero_debounce_commits_immediately() -> None:
    deb = OrientationDebouncer(0)
    deb.feed(1, 0)
    events = deb.feed(2, 10)
    assert [(e.value, e.observed_at_ms) for e in events] == [(2, 10)]


def test_neutral_commit_yields_neutral_event() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 0)
    deb.feed(0, 100)
    assert kinds(deb.tick(400)) == [EventKind.NEUTRAL]
    deb.feed(2, 500)
    assert kinds(deb.tick(800)) == [EventKind.FACE_CHANGE]


def test_full_turn_sequence() -> None:
    deb = OrientationDebouncer(300)
    out: list[tuple[EventKind, int]] = []

    def run(events: list) -> None:  # type: ignore[type-arg]
        out.extend((e.kind, e.value) for e in events)

    run(deb.feed(1, 0))  # baseline
    run(deb.feed(2, 100))
    run(deb.feed(2, 450))  # stable -> change to 2
    run(deb.feed(0, 500))  # neutral while turning ...
    run(deb.feed(5, 600))  # ... but quickly on 5
    run(deb.tick(900))  # 5 stable -> change to 5
    assert out == [
        (EventKind.BASELINE, 1),
        (EventKind.FACE_CHANGE, 2),
        (EventKind.FACE_CHANGE, 5),
    ]


# ------------------------------------------------------------------------------ validation


@pytest.mark.parametrize("debounce", [-1, 1.5, True, "300", None])
def test_invalid_debounce_rejected(debounce: object) -> None:
    with pytest.raises(ValidationError):
        OrientationDebouncer(debounce)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-1, 9, True, "1", 1.0, None])
def test_invalid_value_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        OrientationDebouncer().feed(value, 0)  # type: ignore[arg-type]


def test_time_going_backwards_is_rejected() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 1000)
    with pytest.raises(ValidationError):
        deb.feed(1, 999)
    with pytest.raises(ValidationError):
        deb.tick(500)


def test_non_integer_time_rejected() -> None:
    with pytest.raises(ValidationError):
        OrientationDebouncer().feed(1, 1.5)  # type: ignore[arg-type]


def test_reset_clears_clock_so_new_connection_may_restart_at_zero() -> None:
    deb = OrientationDebouncer(300)
    deb.feed(1, 10_000)
    deb.reset()
    deb.feed(1, 0)  # must not complain about backwards time


# ------------------------------------------------------------------ connection lifecycle


def _walk_to_ready(machine: ConnectionStateMachine) -> None:
    for state in (S.SCANNING, S.CONNECTING, S.DISCOVERING, S.SUBSCRIBING, S.BASELINE, S.READY):
        machine.transition(state)


def test_happy_path_to_ready() -> None:
    machine = ConnectionStateMachine()
    assert machine.state is S.IDLE and not machine.is_ready
    _walk_to_ready(machine)
    assert machine.is_ready and machine.attempt == 0
    assert machine.connection_id is not None


def test_connected_is_not_ready_until_baseline() -> None:
    machine = ConnectionStateMachine()
    for state in (S.CONNECTING, S.DISCOVERING, S.SUBSCRIBING, S.BASELINE):
        machine.transition(state)
    assert not machine.is_ready  # subscribed but no valid orientation yet
    machine.transition(S.READY)
    assert machine.is_ready


def test_reconnect_cycle_creates_new_connection_id() -> None:
    machine = ConnectionStateMachine()
    _walk_to_ready(machine)
    first = machine.connection_id
    machine.transition(S.DISCONNECTED)
    machine.transition(S.RECONNECT_WAIT)
    machine.transition(S.CONNECTING)
    assert machine.connection_id != first
    assert machine.is_current(machine.connection_id)
    assert not machine.is_current(first)  # late result of the old cycle is recognised
    assert not machine.is_current(None)


def test_attempt_counter_counts_failures_and_resets_on_ready() -> None:
    machine = ConnectionStateMachine()
    for _ in range(3):
        machine.transition(S.CONNECTING)
        machine.transition(S.DISCONNECTED)  # failed before ready
        machine.transition(S.RECONNECT_WAIT)
    assert machine.attempt == 3
    for state in (S.CONNECTING, S.DISCOVERING, S.SUBSCRIBING, S.BASELINE, S.READY):
        machine.transition(state)
    assert machine.attempt == 0
    machine.transition(S.DISCONNECTED)  # loss after being ready is not a failed attempt
    assert machine.attempt == 0


@pytest.mark.parametrize(
    "start, target",
    [
        (S.IDLE, S.READY),
        (S.IDLE, S.DISCOVERING),
        (S.CONNECTING, S.READY),
        (S.READY, S.CONNECTING),
        (S.READY, S.SCANNING),
        (S.DISCONNECTED, S.CONNECTING),  # must pass through RECONNECT_WAIT
        (S.RECONNECT_WAIT, S.READY),
        (S.STOPPED, S.CONNECTING),
    ],
)
def test_illegal_transitions_raise(start: ConnectionState, target: ConnectionState) -> None:
    machine = ConnectionStateMachine()
    _force(machine, start)
    assert not machine.can_transition(target)
    with pytest.raises(InvalidStateError) as info:
        machine.transition(target)
    assert info.value.details == {"from": start.value, "to": target.value}
    assert machine.state is start  # unchanged after a rejected transition


def _force(machine: ConnectionStateMachine, state: ConnectionState) -> None:
    """Drive the machine into ``state`` through legal transitions only."""
    paths = {
        S.IDLE: [],
        S.CONNECTING: [S.CONNECTING],
        S.READY: [S.CONNECTING, S.DISCOVERING, S.SUBSCRIBING, S.BASELINE, S.READY],
        S.DISCONNECTED: [S.CONNECTING, S.DISCONNECTED],
        S.RECONNECT_WAIT: [S.CONNECTING, S.DISCONNECTED, S.RECONNECT_WAIT],
        S.STOPPED: [S.STOPPED],
    }
    for step in paths[state]:
        machine.transition(step)


@pytest.mark.parametrize("state", [S.IDLE, S.CONNECTING, S.READY, S.DISCONNECTED, S.RECONNECT_WAIT])
def test_user_stop_possible_from_every_active_state(state: ConnectionState) -> None:
    machine = ConnectionStateMachine()
    _force(machine, state)
    machine.transition(S.STOPPED)
    assert machine.state is S.STOPPED


def test_stopped_blocks_reconnect_until_explicit_restart() -> None:
    machine = ConnectionStateMachine()
    _walk_to_ready(machine)
    machine.transition(S.STOPPED)
    assert not machine.can_transition(S.RECONNECT_WAIT)
    assert not machine.can_transition(S.STOPPED)  # already stopped
    machine.transition(S.IDLE)  # explicit restart
    machine.transition(S.CONNECTING)


def test_string_target_is_coerced_and_unknown_rejected() -> None:
    machine = ConnectionStateMachine()
    machine.transition("connecting")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        machine.transition("flying")  # type: ignore[arg-type]


def test_history_is_recorded_and_bounded() -> None:
    machine = ConnectionStateMachine()
    machine.transition(S.CONNECTING)
    assert machine.history == [(S.IDLE, S.CONNECTING)]
    for _ in range(60):
        machine.transition(S.DISCONNECTED)
        machine.transition(S.RECONNECT_WAIT)
        machine.transition(S.CONNECTING)
    assert len(machine.history) == 50


# ------------------------------------------------------------------------------- backoff


@pytest.mark.parametrize(
    "attempt, expected", [(0, 1), (1, 1), (2, 2), (3, 4), (4, 8), (7, 60), (100, 60), (10_000, 60)]
)
def test_backoff_grows_and_is_capped(attempt: int, expected: float) -> None:
    assert reconnect_delay_seconds(attempt) == expected


def test_backoff_custom_parameters() -> None:
    assert reconnect_delay_seconds(3, base=0.5, factor=3, cap=10) == 4.5
    assert reconnect_delay_seconds(9, base=0.5, factor=3, cap=10) == 10


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempt": -1},
        {"attempt": 1, "base": 0},
        {"attempt": 1, "factor": 0.5},
        {"attempt": 1, "base": 5, "cap": 1},
    ],
)
def test_backoff_invalid_parameters(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        reconnect_delay_seconds(**kwargs)  # type: ignore[arg-type]
