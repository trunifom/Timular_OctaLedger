"""Connection loss with a grace period and the attention centre (AP-36)."""

from datetime import UTC, datetime, timedelta

import pytest

from octaledger.application.tracking_service import GAP_ASSIGN, GAP_DISCARD, GAP_KEEP, Outcome
from octaledger.core.errors import InvalidStateError, NotFoundError, ValidationError
from octaledger.core.settings import DisconnectPolicy, TrackingSettings
from octaledger.domain.attention import AttentionItem, AttentionKind, AttentionStatus
from octaledger.domain.link_loss import LinkAction, decide
from octaledger.domain.models import EventKind, Quality
from tests.unit.test_tracking_service import T0, Env, M, env, sessions  # noqa: F401

# ------------------------------------------------------------------- pure rule

LOST = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
GRACE = timedelta(minutes=5)


def test_decide_waits_inside_the_grace_period() -> None:
    assert decide(LOST, LOST + timedelta(minutes=4, seconds=59), GRACE, already_stopped=False) is (
        LinkAction.NONE
    )


def test_decide_stops_exactly_at_the_boundary() -> None:
    assert decide(LOST, LOST + GRACE, GRACE, already_stopped=False) is LinkAction.STOP_AT_LOSS


def test_decide_zero_grace_stops_immediately() -> None:
    assert decide(LOST, LOST, timedelta(0), already_stopped=False) is LinkAction.STOP_AT_LOSS


def test_decide_does_nothing_twice() -> None:
    assert decide(LOST, LOST + 2 * GRACE, GRACE, already_stopped=True) is LinkAction.NONE


# ------------------------------------------------------------------ watchdog


def start_and_lose(env: Env, minutes: float = 10) -> None:  # noqa: F811
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    env.service.record_event(env.event(EventKind.DISCONNECT, None, minutes))


def open_items(env: Env) -> list[AttentionItem]:  # noqa: F811
    with env.storage.read() as repos:
        return repos.attention.list_open()


def test_entry_keeps_running_during_the_grace_period(env: Env) -> None:  # noqa: F811
    start_and_lose(env)
    assert env.service.watchdog(T0 + 14 * M) == []
    running = sessions(env)[0]
    assert running.is_running and running.quality is Quality.UNCERTAIN
    assert env.device in env.service.link_lost_since()


def test_entry_ends_at_the_loss_after_the_grace_period_and_a_question_is_raised(
    env: Env,  # noqa: F811
) -> None:
    start_and_lose(env)
    raised = env.service.watchdog(T0 + 15 * M)  # 10 min loss + 5 min grace
    assert len(raised) == 1 and raised[0].kind is AttentionKind.GAP
    ended = sessions(env)[0]
    assert ended.ended_at == T0 + 10 * M and ended.quality is Quality.UNCERTAIN
    assert env.service.watchdog(T0 + 60 * M) == []  # asked only once
    assert len(open_items(env)) == 1
    assert env.service.link_lost_since() == {}  # no longer "waiting"


def test_return_inside_the_grace_period_continues_without_a_question(env: Env) -> None:  # noqa: F811
    start_and_lose(env)
    env.service.record_event(env.event(EventKind.BASELINE, 1, 12))
    assert env.service.watchdog(T0 + 30 * M) == []
    assert sessions(env)[0].is_running and open_items(env) == []


def test_return_after_the_grace_period_adds_the_return_time(env: Env) -> None:  # noqa: F811
    start_and_lose(env)
    env.service.watchdog(T0 + 16 * M)
    env.service.record_event(env.event(EventKind.RECONNECT, None, 40))
    (item,) = open_items(env)
    assert item.payload["returned_at"] == (T0 + 40 * M).isoformat()


def test_a_manual_stop_during_the_grace_period_means_no_question(env: Env) -> None:  # noqa: F811
    start_and_lose(env)
    env.clock.now = T0 + 12 * M
    env.service.stop()
    assert env.service.watchdog(T0 + 20 * M) == []
    assert open_items(env) == [] and env.service.link_lost_since() == {}


def test_zero_grace_behaves_like_stop_session(env: Env) -> None:  # noqa: F811
    service = env.make_service(
        disconnect_policy=DisconnectPolicy.GRACE_THEN_STOP, disconnect_grace_seconds=0
    )
    service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    result = service.record_event(env.event(EventKind.DISCONNECT, None, 10))
    assert result.outcome is Outcome.ENDED and sessions(env)[0].ended_at == T0 + 10 * M


def test_mark_uncertain_policy_sets_no_marker(env: Env) -> None:  # noqa: F811
    service = env.make_service(disconnect_policy=DisconnectPolicy.MARK_UNCERTAIN)
    service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    service.record_event(env.event(EventKind.DISCONNECT, None, 10))
    assert service.link_lost_since() == {} and service.watchdog(T0 + 600 * M) == []


def test_two_devices_are_independent(env: Env) -> None:  # noqa: F811
    env.service.record_event(env.event(EventKind.FACE_CHANGE, 1, 0))
    # an inactive tracker losing its link neither ends nor questions anything
    env.service.record_event(env.event(EventKind.DISCONNECT, None, 5, device=env.other_device))
    assert env.service.watchdog(T0 + 60 * M) == []
    assert sessions(env)[0].is_running


def test_the_marker_survives_a_restart(env: Env) -> None:  # noqa: F811
    start_and_lose(env)
    restarted = env.make_service()  # a new service object = a restarted agent
    assert len(restarted.watchdog(T0 + 20 * M)) == 1


# ------------------------------------------------------------------- answers


def gap(env: Env, returned_minutes: float | None = 40) -> AttentionItem:  # noqa: F811
    start_and_lose(env)
    (item,) = env.service.watchdog(T0 + 16 * M)
    if returned_minutes is not None:
        env.service.record_event(env.event(EventKind.BASELINE, 1, returned_minutes))
    env.clock.now = T0 + 45 * M
    return item


def test_keep_extends_the_entry_over_the_gap_and_is_audited(env: Env) -> None:  # noqa: F811
    item = gap(env)
    closed = env.service.resolve_gap(item.id, GAP_KEEP)
    assert closed.status is AttentionStatus.RESOLVED and closed.resolution == GAP_KEEP
    assert sessions(env)[0].ended_at == T0 + 40 * M
    with env.storage.read() as repos:
        assert [a.action for a in repos.audit.list_all()][-1] == "resolve_gap"
        assert repos.sessions.list_corrections(item.session_id)


def test_discard_leaves_the_gap_empty(env: Env) -> None:  # noqa: F811
    item = gap(env)
    env.service.resolve_gap(item.id, GAP_DISCARD)
    (only,) = sessions(env)
    assert only.ended_at == T0 + 10 * M and open_items(env) == []


def test_assign_books_the_gap_on_another_activity(env: Env) -> None:  # noqa: F811
    item = gap(env)
    env.service.resolve_gap(item.id, GAP_ASSIGN, activity_id=env.code, project_id=env.project)
    first, booked = sessions(env)
    assert (booked.started_at, booked.ended_at) == (T0 + 10 * M, T0 + 40 * M)
    assert booked.activity_id == env.code and booked.quality is Quality.UNCERTAIN
    assert first.ended_at == T0 + 10 * M


def test_assign_without_an_activity_is_rejected_and_changes_nothing(env: Env) -> None:  # noqa: F811
    item = gap(env)
    with pytest.raises(ValidationError):
        env.service.resolve_gap(item.id, GAP_ASSIGN)
    assert len(open_items(env)) == 1 and len(sessions(env)) == 1


def test_keep_without_a_return_uses_now(env: Env) -> None:  # noqa: F811
    item = gap(env, returned_minutes=None)
    env.service.resolve_gap(item.id, GAP_KEEP)
    assert sessions(env)[0].ended_at == T0 + 45 * M


def test_the_gap_never_overlaps_a_later_entry(env: Env) -> None:  # noqa: F811
    item = gap(env, returned_minutes=None)
    env.clock.now = T0 + 30 * M
    env.service.start_manual(env.code)  # the user started something at +30
    env.clock.now = T0 + 45 * M
    env.service.resolve_gap(item.id, GAP_KEEP)
    assert sessions(env)[0].ended_at == T0 + 30 * M


def test_a_fully_occupied_gap_is_refused(env: Env) -> None:  # noqa: F811
    item = gap(env, returned_minutes=None)
    env.clock.now = T0 + 10 * M
    env.service.start_manual(env.code, at=T0 + 10 * M)
    with pytest.raises(InvalidStateError):
        env.service.resolve_gap(item.id, GAP_KEEP)


def test_an_answered_question_cannot_be_answered_twice(env: Env) -> None:  # noqa: F811
    item = gap(env)
    env.service.resolve_gap(item.id, GAP_DISCARD)
    with pytest.raises(InvalidStateError):
        env.service.resolve_gap(item.id, GAP_KEEP)


def test_unknown_action_and_unknown_item(env: Env) -> None:  # noqa: F811
    item = gap(env)
    with pytest.raises(ValidationError):
        env.service.resolve_gap(item.id, "fly")
    with pytest.raises(NotFoundError):
        env.service.resolve_gap("0" * 32, GAP_KEEP)


def test_deleting_the_entry_removes_its_question(env: Env) -> None:  # noqa: F811
    item = gap(env)
    with env.storage.transaction() as repos:
        repos.sessions.delete(str(item.session_id), "test", repos.audit)
    assert open_items(env) == []


def test_default_policy_is_grace_then_stop() -> None:
    settings = TrackingSettings()
    assert settings.disconnect_policy is DisconnectPolicy.GRACE_THEN_STOP
    assert settings.disconnect_grace_seconds == 300
    with pytest.raises(Exception, match="disconnect_grace_seconds"):
        TrackingSettings(disconnect_grace_seconds=4000)
