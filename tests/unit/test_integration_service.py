"""Tests for the integration service: connections, face actions, trying things out, sending."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from octaledger.application.integration_service import IntegrationService
from octaledger.application.outbox import MAX_ATTEMPTS
from octaledger.core.errors import (
    ConflictError,
    IntegrationConnectionError,
    IntegrationError,
    NotFoundError,
    StorageError,
    ValidationError,
)
from octaledger.core.logging import clear_registered_secrets
from octaledger.core.secrets import SecretStore
from octaledger.domain.models import (
    Device,
    DeviceMode,
    Integration,
    IntegrationJob,
    JobStatus,
)
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from tests.fake_adapter import FakeAdapter

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.secrets = SecretStore(tmp_path / "secrets.json")
        self.adapter = FakeAdapter()
        self.clock = Clock()
        self.service = IntegrationService(
            self.storage, self.secrets, {"fake": self.adapter}, clock=self.clock
        )

    def create(self, name: str = "Licht", **overrides: Any) -> str:
        values = {"host": "10.0.0.5", "password": "richtig"} | overrides
        return self.service.create("fake", name, values).integration.id

    def device(self) -> str:
        with self.storage.transaction() as repos:
            return repos.devices.add(Device(alias="Würfel", mode=DeviceMode.CONTROL)).id

    def enqueue(self, integration_id: str, key: str = "k1", lifetime: float = 30) -> str:
        job = IntegrationJob(
            key,
            integration_id,
            "Lampe",
            {"action": "ping", "target": "x"},
            expires_at=self.clock.now + timedelta(seconds=lifetime),
            created_at=self.clock.now,
        )
        with self.storage.transaction() as repos:
            repos.jobs.enqueue(job)
        return job.id

    def job(self, job_id: str) -> IntegrationJob:
        with self.storage.read() as repos:
            found = repos.jobs.get(job_id)
        assert found is not None
        return found


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear_registered_secrets()


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


# --------------------------------------------------------------------- connections


def test_adapters_describe_themselves(env: Env) -> None:
    (spec,) = env.service.adapter_specs()
    assert spec.kind == "fake" and spec.action("ping").label == "Anpingen"
    with pytest.raises(ValidationError):
        spec.action("nope")


def test_secrets_go_to_the_secret_store_and_never_into_the_settings(env: Env) -> None:
    info = env.service.create("fake", "Licht", {"host": "10.0.0.5", "password": "richtig"})
    assert dict(info.integration.config) == {"host": "10.0.0.5", "port": 80}
    assert info.secrets_set == ("password",)
    assert env.secrets.get(info.integration.id) == {"password": "richtig"}
    with env.storage.read() as repos:
        stored = repos.integrations.require(info.integration.id)
    assert "richtig" not in repr(stored) and "password" not in stored.config
    assert "richtig" not in repr(info)


def test_creation_rejects_bad_input_with_german_messages(env: Env) -> None:
    cases: list[tuple[str, dict[str, Any], str]] = [
        ("unbekannt", {"host": "h", "password": "p"}, "kennt OctaLedger nicht"),
        ("fake", {"password": "p"}, "Adresse"),
        ("fake", {"host": "h"}, "Passwort"),
        ("fake", {"host": "h", "password": "p", "port": "abc"}, "ganze Zahl"),
        ("fake", {"host": "h", "password": "p", "port": 70000}, "höchstens"),
        ("fake", {"host": "h", "password": "p", "extra": "x"}, "Unbekannte Angabe"),
        ("fake", {"host": "h\nX: 1", "password": "p"}, "Zeilenumbrüche"),
        ("fake", {"host": "h", "password": "a\nb"}, "einzeiliger"),
    ]
    for kind, values, fragment in cases:
        with pytest.raises(ValidationError) as info:
            env.service.create(kind, "Neu", values)
        assert fragment in info.value.user_message, (values, info.value.user_message)
    assert env.service.list_integrations() == []


def test_names_are_unique(env: Env) -> None:
    env.create("Licht")
    with pytest.raises(ConflictError):
        env.create("licht")
    assert len(env.service.list_integrations()) == 1


def test_a_failing_secret_store_leaves_no_half_created_connection(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object) -> None:
        raise StorageError("disk full")

    monkeypatch.setattr(env.secrets, "update", broken)
    with pytest.raises(StorageError):
        env.create("Licht")
    assert env.service.list_integrations() == []


def test_update_changes_settings_name_and_flag_and_keeps_blank_secrets(env: Env) -> None:
    integration_id = env.create("Licht")
    changed = env.service.update(
        integration_id, name="Lampe", values={"host": "10.0.0.9", "password": ""}, enabled=False
    )
    assert changed.integration.name == "Lampe" and not changed.integration.enabled
    assert (
        changed.integration.config["host"] == "10.0.0.9"
        and changed.integration.config["port"] == 80
    )
    assert env.secrets.get(integration_id) == {"password": "richtig"}  # blank keeps the secret
    env.service.update(integration_id, values={"password": "neu"})
    assert env.secrets.get(integration_id) == {"password": "neu"}
    with pytest.raises(ValidationError):
        env.service.update(integration_id, values={"port": 0})
    with pytest.raises(NotFoundError):
        env.service.update("ghost", name="x")


def test_delete_is_refused_while_a_face_uses_it_and_then_forgets_the_secrets(env: Env) -> None:
    integration_id, device_id = env.create(), env.device()
    env.service.assign_action(device_id, 1, integration_id, "Lampe", {"action": "toggle"})
    with pytest.raises(ConflictError):
        env.service.delete(integration_id)
    assert env.secrets.names(integration_id) == ("password",)  # nothing was lost
    env.service.clear_action(device_id, 1)
    env.service.delete(integration_id)
    assert env.service.list_integrations() == [] and env.secrets.names(integration_id) == ()


# --------------------------------------------------------------- trying things out


def test_check_and_probe_use_the_stored_settings_and_secrets(env: Env) -> None:
    integration_id = env.create()
    assert env.service.check(integration_id) == "Verbunden mit 10.0.0.5."
    assert env.service.probe(integration_id, {"action": "ping", "target": "x"}) == "gesendet"
    config, secrets, params = env.adapter.calls[-1]
    assert config["host"] == "10.0.0.5" and secrets == {"password": "richtig"}
    assert params == {"action": "ping", "target": "x"}
    env.service.update(integration_id, values={"password": "falsch"})
    with pytest.raises(IntegrationError) as info:
        env.service.check(integration_id)
    assert info.value.user_message == "Zugangsdaten abgelehnt."


def test_probe_validates_the_action_before_sending(env: Env) -> None:
    integration_id = env.create()
    for params in (
        {},
        {"action": "nope"},
        {"action": "ping"},
        {"action": "ping", "target": "x", "z": 1},
    ):
        with pytest.raises(ValidationError):
            env.service.probe(integration_id, params)
    assert env.adapter.calls == []  # nothing invalid ever reaches the adapter


def test_pairing_stores_secrets_and_settings_and_discovery_passes_through(env: Env) -> None:
    integration_id = env.create()
    assert env.service.pair(integration_id) == "Gekoppelt!"
    assert env.secrets.get(integration_id) == {"password": "gekoppelt"}
    assert env.service.get(integration_id).integration.config["host"] == "bridge.local"
    assert env.service.discover(integration_id) == {"lights": [{"id": "1", "name": "Schreibtisch"}]}


# ------------------------------------------------------------------- face actions


def test_actions_are_validated_by_the_adapter_and_versioned(env: Env) -> None:
    integration_id, device_id = env.create(), env.device()
    action = env.service.assign_action(
        device_id, 3, integration_id, " Lampe ", {"action": "toggle"}
    )
    assert action.label == "Lampe" and action.revision == 1
    again = env.service.assign_action(device_id, 3, integration_id, "Lampe", {"action": "toggle"})
    assert again.revision == 1
    changed = env.service.assign_action(
        device_id, 3, integration_id, "Lampe", {"action": "ping", "target": "x"}
    )
    assert changed.revision == 2
    assert [a.face for a in env.service.list_actions(device_id)] == [3]
    with pytest.raises(ValidationError):
        env.service.assign_action(device_id, 4, integration_id, "x", {"action": "ping"})
    with pytest.raises(ValidationError):
        env.service.assign_action(device_id, 9, integration_id, "x", {"action": "toggle"})
    with pytest.raises(NotFoundError):
        env.service.assign_action("ghost", 1, integration_id, "x", {"action": "toggle"})
    with pytest.raises(NotFoundError):
        env.service.assign_action(device_id, 1, "ghost", "x", {"action": "toggle"})
    env.service.clear_action(device_id, 3)
    assert env.service.list_actions(device_id) == []


# --------------------------------------------------------------------- the outbox


def test_a_due_job_is_sent_and_recorded(env: Env) -> None:
    job_id = env.enqueue(env.create())
    assert env.service.process_due() == 1
    job = env.job(job_id)
    assert job.status is JobStatus.DONE and job.attempts == 1 and job.last_error is None
    assert env.adapter.calls[-1][2] == {"action": "ping", "target": "x"}
    assert env.service.process_due() == 0  # nothing left to do


def test_jobs_are_sent_in_the_order_they_were_created(env: Env) -> None:
    integration_id = env.create()
    first = env.enqueue(integration_id, "a")
    env.clock.advance(1)
    second = env.enqueue(integration_id, "b")
    env.clock.advance(1)
    env.service.process_due()
    done = [
        j.job.idempotency_key for j in env.service.list_jobs() if j.job.status is JobStatus.DONE
    ]
    assert sorted(done) == ["a", "b"] and first != second
    assert [c[2]["target"] for c in env.adapter.calls] == ["x", "x"]


def test_a_transient_error_is_retried_later_and_then_succeeds(env: Env) -> None:
    job_id = env.enqueue(env.create())
    env.adapter.script = [IntegrationConnectionError("no route", user_message="Nicht erreichbar.")]
    env.service.process_due()
    waiting = env.job(job_id)
    assert waiting.status is JobStatus.PENDING and waiting.attempts == 1
    assert waiting.last_error == "Nicht erreichbar." and waiting.next_attempt_at > env.clock.now
    assert env.service.process_due() == 0  # not due yet
    env.clock.advance(1.5)
    assert env.service.process_due() == 1
    assert env.job(job_id).status is JobStatus.DONE and env.job(job_id).attempts == 2


def test_retries_stop_after_the_attempts_are_used_up(env: Env) -> None:
    job_id = env.enqueue(env.create(), lifetime=300)
    env.adapter.script = [IntegrationConnectionError("x", user_message="Nicht erreichbar.")] * 5
    for _ in range(MAX_ATTEMPTS + 2):
        env.service.process_due()
        env.clock.advance(5)
    job = env.job(job_id)
    assert job.status is JobStatus.FAILED and job.attempts == MAX_ATTEMPTS
    assert len(env.adapter.calls) == MAX_ATTEMPTS and job.last_error == "Nicht erreichbar."


def test_a_permanent_error_is_not_retried(env: Env) -> None:
    """An action whose outcome is unknown must not be repeated (a toggle would flip twice)."""
    job_id = env.enqueue(env.create())
    env.adapter.script = [IntegrationError("rejected", user_message="Abgelehnt.")]
    env.service.process_due()
    job = env.job(job_id)
    assert job.status is JobStatus.FAILED and job.attempts == 1 and job.last_error == "Abgelehnt."
    env.clock.advance(60)
    env.service.process_due()
    assert len(env.adapter.calls) == 1


def test_a_crashing_adapter_does_not_stop_the_dispatcher(env: Env) -> None:
    integration_id = env.create()
    first = env.enqueue(integration_id, "a")
    env.clock.advance(1)  # a fixed order: the first job meets the crash
    second = env.enqueue(integration_id, "b")
    env.clock.advance(1)
    env.adapter.script = [RuntimeError("bug with secret richtig")]
    assert env.service.process_due() == 2
    crashed, fine = env.job(first), env.job(second)
    assert crashed.status is JobStatus.FAILED and "richtig" not in (crashed.last_error or "")
    assert fine.status is JobStatus.DONE


def test_overdue_jobs_expire_instead_of_being_sent_late(env: Env) -> None:
    job_id = env.enqueue(env.create(), lifetime=30)
    env.clock.advance(31)
    env.service.process_due()
    job = env.job(job_id)
    assert job.status is JobStatus.EXPIRED and "Zu spät" in (job.last_error or "")
    assert env.adapter.calls == []


def test_a_retry_that_would_come_too_late_fails_at_once(env: Env) -> None:
    job_id = env.enqueue(env.create(), lifetime=0.5)
    env.adapter.script = [IntegrationConnectionError("x", user_message="Nicht erreichbar.")]
    env.service.process_due()
    assert env.job(job_id).status is JobStatus.FAILED  # the first retry (1 s) is past its life


def test_jobs_of_a_switched_off_connection_expire(env: Env) -> None:
    integration_id = env.create()
    job_id = env.enqueue(integration_id)
    env.service.update(integration_id, enabled=False)
    env.service.process_due()
    assert env.job(job_id).status is JobStatus.EXPIRED and env.adapter.calls == []


def test_a_job_of_an_unavailable_adapter_fails_clearly(env: Env) -> None:
    with env.storage.transaction() as repos:
        orphan = repos.integrations.add(Integration("gone", "Alt"))
    job_id = env.enqueue(orphan.id)
    env.service.process_due()
    job = env.job(job_id)
    assert job.status is JobStatus.FAILED and "nicht verfügbar" in (job.last_error or "")


def test_the_history_names_the_connection(env: Env) -> None:
    env.enqueue(env.create("Wohnzimmer"))
    env.service.process_due()
    (entry,) = env.service.list_jobs()
    assert entry.integration_name == "Wohnzimmer" and entry.job.status is JobStatus.DONE


def test_old_finished_jobs_are_purged_during_processing(env: Env) -> None:
    job_id = env.enqueue(env.create())
    env.service.process_due()
    env.clock.advance(8 * 24 * 3600)
    env.service.process_due()
    with env.storage.read() as repos:
        assert repos.jobs.get(job_id) is None
