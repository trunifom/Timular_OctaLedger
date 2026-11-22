"""Tests for control mode: face turns become queued actions, time tracking is left alone."""

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octaledger.application.device_service import DeviceService
from octaledger.application.outbox import MAX_PENDING_JOBS, QUEUE_FULL_MESSAGE
from octaledger.application.tracking_service import Outcome, TrackingService
from octaledger.core.errors import InvalidStateError, NotFoundError
from octaledger.domain.models import (
    Activity,
    Device,
    DeviceMode,
    EventKind,
    Integration,
    IntegrationJob,
    JobStatus,
    RawEvent,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


@dataclass
class Env:
    storage: Storage
    tracking: TrackingService
    devices: DeviceService
    control: str  # a tracker in control mode
    timer: str  # a tracker in time mode (the active one)
    meeting: str
    lamp: str  # integration id
    sequence: int = 0

    def event(self, kind: EventKind, value: int | None, device: str | None = None) -> RawEvent:
        self.sequence += 1
        return RawEvent(
            device_id=device or self.control,
            kind=kind,
            sequence=self.sequence,
            connection_id="c1",
            raw_value=value,
            received_at=T0,
        )

    def face(self, value: int, device: str | None = None) -> Outcome:
        return self.tracking.record_event(self.event(EventKind.FACE_CHANGE, value, device)).outcome

    def jobs(self) -> list[IntegrationJob]:
        with self.storage.read() as repos:
            return list(reversed(repos.jobs.list_recent(500)))

    def pending(self) -> int:
        with self.storage.read() as repos:
            return repos.jobs.count_pending(self.lamp)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    devices = DeviceService(storage)
    timer = devices.register("Zeit")  # the first tracker becomes the active one
    control = devices.register("Steuerung")
    devices.set_mode(control.id, DeviceMode.CONTROL)
    with storage.transaction() as repos:
        meeting = repos.activities.add(Activity(name="Meeting"))
        repos.mappings.assign(timer.id, 1, meeting.id)
        lamp = repos.integrations.add(Integration("webhook", "Lampe"))
        repos.actions.assign(control.id, 2, lamp.id, "Schreibtischlampe", {"action": "toggle"})
    return Env(
        storage,
        TrackingService(storage, clock=lambda: T0),
        devices,
        control.id,
        timer.id,
        meeting.id,
        lamp.id,
    )


# ------------------------------------------------------------------ queueing actions


def test_a_face_change_queues_exactly_the_action_of_that_face(env: Env) -> None:
    assert env.face(2) is Outcome.ACTION_QUEUED
    (job,) = env.jobs()
    assert job.status is JobStatus.PENDING and job.integration_id == env.lamp
    assert (job.label, job.face, job.device_id) == ("Schreibtischlampe", 2, env.control)
    assert dict(job.params) == {"action": "toggle"}
    assert job.expires_at == T0 + timedelta(seconds=30)  # worthless when late


def test_the_job_is_tied_to_the_event_so_a_trigger_cannot_be_sent_twice(env: Env) -> None:
    event = env.event(EventKind.FACE_CHANGE, 2)
    env.tracking.record_event(event)
    (job,) = env.jobs()
    assert job.idempotency_key == event.id


def test_only_a_real_face_change_triggers_anything(env: Env) -> None:
    """The first value after connecting (baseline) must never switch a light."""
    for kind, value in (
        (EventKind.BASELINE, 2),
        (EventKind.NEUTRAL, 0),
        (EventKind.DISCONNECT, None),
        (EventKind.RECONNECT, None),
        (EventKind.INVALID, None),
    ):
        outcome = env.tracking.record_event(env.event(kind, value)).outcome
        assert outcome is Outcome.STORED, kind
    assert env.jobs() == []


def test_a_face_without_an_action_does_nothing(env: Env) -> None:
    assert env.face(5) is Outcome.ACTION_SKIPPED
    assert env.jobs() == []


def test_a_switched_off_connection_queues_nothing(env: Env) -> None:
    with env.storage.transaction() as repos:
        lamp = repos.integrations.require(env.lamp)
        repos.integrations.update(dataclasses.replace(lamp, enabled=False))
    assert env.face(2) is Outcome.ACTION_SKIPPED
    assert env.jobs() == []


def test_the_queue_is_bounded_and_says_why_it_dropped_an_action(env: Env) -> None:
    with env.storage.transaction() as repos:
        for number in range(MAX_PENDING_JOBS):
            repos.jobs.enqueue(
                IntegrationJob(
                    f"old-{number}", env.lamp, "x", {}, expires_at=T0 + timedelta(minutes=5)
                )
            )
    assert env.pending() == MAX_PENDING_JOBS
    assert env.face(2) is Outcome.ACTION_SKIPPED
    assert env.pending() == MAX_PENDING_JOBS  # did not grow
    dropped = [j for j in env.jobs() if j.status is JobStatus.EXPIRED]
    assert len(dropped) == 1 and dropped[0].last_error == QUEUE_FULL_MESSAGE


def test_editing_the_face_later_does_not_change_a_queued_job(env: Env) -> None:
    env.face(2)
    with env.storage.transaction() as repos:
        repos.actions.assign(env.control, 2, env.lamp, "Andere Lampe", {"action": "off"})
    (job,) = env.jobs()
    assert job.label == "Schreibtischlampe" and dict(job.params) == {"action": "toggle"}


# --------------------------------------------- control mode leaves time tracking alone


def test_control_events_never_create_or_touch_time_entries(env: Env) -> None:
    env.tracking.start_manual(env.meeting, None)
    env.face(2)
    env.face(5)
    with env.storage.read() as repos:
        sessions = repos.sessions.list_all()
    assert len(sessions) == 1 and sessions[0].ended_at is None  # the running entry is untouched


def test_a_control_tracker_works_whether_or_not_it_is_the_active_tracker(env: Env) -> None:
    assert env.devices.get(env.control).is_active is False
    assert env.face(2) is Outcome.ACTION_QUEUED


def test_time_trackers_behave_exactly_as_before_and_queue_nothing(env: Env) -> None:
    assert env.face(1, device=env.timer) is Outcome.STARTED
    assert env.jobs() == []


# ------------------------------------------------------------------------ mode switch


def test_switching_the_active_tracker_to_control_hands_the_role_on(env: Env) -> None:
    other = env.devices.register("Dritter").id  # another time tracker
    env.devices.set_mode(env.timer, DeviceMode.CONTROL)
    assert env.devices.get(env.timer).device.mode is DeviceMode.CONTROL
    assert env.devices.get(other).is_active and not env.devices.get(env.timer).is_active


def test_the_last_time_tracker_leaves_nobody_active_and_the_way_back_restores_it(
    env: Env,
) -> None:
    env.devices.set_mode(env.timer, DeviceMode.CONTROL)
    assert not any(info.is_active for info in env.devices.list_devices())
    env.devices.set_mode(env.timer, DeviceMode.TIME)
    assert env.devices.get(env.timer).is_active


def test_a_running_time_entry_blocks_switching_that_tracker_to_control(env: Env) -> None:
    assert env.face(1, device=env.timer) is Outcome.STARTED
    with pytest.raises(InvalidStateError) as info:
        env.devices.set_mode(env.timer, DeviceMode.CONTROL)
    assert "Stopp" in info.value.user_message
    assert env.devices.get(env.timer).device.mode is DeviceMode.TIME  # nothing changed


def test_a_running_manual_entry_does_not_block_the_switch(env: Env) -> None:
    env.tracking.start_manual(env.meeting, None)
    env.devices.set_mode(env.timer, DeviceMode.CONTROL)
    assert env.devices.get(env.timer).device.mode is DeviceMode.CONTROL


def test_setting_the_same_mode_again_is_harmless_and_unknown_devices_are_reported(env: Env) -> None:
    again = env.devices.set_mode(env.control, DeviceMode.CONTROL)
    assert again.mode is DeviceMode.CONTROL
    with pytest.raises(NotFoundError):
        env.devices.set_mode("ghost", DeviceMode.CONTROL)


def test_a_control_tracker_cannot_be_handed_the_time_role(env: Env) -> None:
    with pytest.raises(InvalidStateError) as info:
        env.tracking.handover(env.control)
    assert "Steuerungsmodus" in info.value.user_message


def test_configured_faces_count_actions_in_control_mode_and_activities_in_time_mode(
    env: Env,
) -> None:
    assert env.devices.get(env.control).configured_faces == 1  # one action
    assert env.devices.get(env.timer).configured_faces == 1  # one activity
    assert env.devices.get(env.control).actions[2].label == "Schreibtischlampe"


def test_other_devices_keep_their_modes_when_one_switches(env: Env) -> None:
    with env.storage.transaction() as repos:
        extra = repos.devices.add(Device(alias="Extra"))
    env.devices.set_mode(extra.id, DeviceMode.CONTROL)
    modes = {i.device.alias: i.device.mode for i in env.devices.list_devices()}
    assert modes == {
        "Extra": DeviceMode.CONTROL,
        "Steuerung": DeviceMode.CONTROL,
        "Zeit": DeviceMode.TIME,
    }
