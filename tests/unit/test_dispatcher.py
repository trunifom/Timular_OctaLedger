"""Tests for the action dispatcher thread (real thread, tiny intervals, bounded waits)."""

import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from octaledger.agent.dispatcher import ActionDispatcher
from octaledger.application.integration_service import IntegrationService
from octaledger.core.secrets import SecretStore
from octaledger.domain.models import IntegrationJob, JobStatus
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from tests.fake_adapter import FakeAdapter


def wait_for(predicate: Callable[[], Any], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.01)


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.adapter = FakeAdapter()
        self.service = IntegrationService(
            self.storage, SecretStore(tmp_path / "secrets.json"), {"fake": self.adapter}
        )
        self.integration = self.service.create(
            "fake", "Licht", {"host": "h", "password": "richtig"}
        ).integration.id

    def enqueue(self, key: str) -> str:
        now = datetime.now(timezone.utc)
        job = IntegrationJob(
            key,
            self.integration,
            "Lampe",
            {"action": "ping", "target": key},
            expires_at=now + timedelta(seconds=30),
        )
        with self.storage.transaction() as repos:
            repos.jobs.enqueue(job)
        return job.id

    def status(self, job_id: str) -> JobStatus:
        with self.storage.read() as repos:
            job = repos.jobs.get(job_id)
        assert job is not None
        return job.status


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_a_queued_action_is_sent_by_the_background_thread(env: Env) -> None:
    dispatcher = ActionDispatcher(env.service, interval=0.01)
    dispatcher.start()
    try:
        assert dispatcher.running
        first = env.enqueue("a")
        wait_for(lambda: env.status(first) is JobStatus.DONE)
        second = env.enqueue("b")  # work that arrives later is picked up as well
        wait_for(lambda: env.status(second) is JobStatus.DONE)
    finally:
        dispatcher.stop()
    assert [call[2]["target"] for call in env.adapter.calls] == ["a", "b"]
    assert not dispatcher.running


def test_starting_twice_runs_one_thread_and_stopping_is_prompt(env: Env) -> None:
    dispatcher = ActionDispatcher(env.service, interval=30.0)  # a long wait must not delay stop()
    dispatcher.start()
    dispatcher.start()
    names = [t.name for t in threading.enumerate() if t.name == "octaledger-dispatcher"]
    assert names == ["octaledger-dispatcher"]
    began = time.monotonic()
    dispatcher.stop()
    assert time.monotonic() - began < 2.0 and not dispatcher.running
    dispatcher.stop()  # stopping again is harmless


def test_an_unexpected_error_does_not_end_the_dispatcher(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = env.service.process_due
    calls = {"count": 0}

    def flaky(max_jobs: int = 20) -> int:
        calls["count"] += 1
        if calls["count"] <= 2:
            raise RuntimeError("database hiccup")
        return real(max_jobs)

    monkeypatch.setattr(env.service, "process_due", flaky)
    dispatcher = ActionDispatcher(env.service, interval=0.01)
    dispatcher.start()
    try:
        job_id = env.enqueue("a")
        wait_for(lambda: env.status(job_id) is JobStatus.DONE)  # it kept going after the errors
        assert calls["count"] >= 3 and dispatcher.running
    finally:
        dispatcher.stop()


def test_a_failing_adapter_does_not_block_the_next_action(env: Env) -> None:
    env.adapter.script = [RuntimeError("bug")]
    dispatcher = ActionDispatcher(env.service, interval=0.01)
    dispatcher.start()
    try:
        first = env.enqueue("a")
        wait_for(lambda: env.status(first) is JobStatus.FAILED)
        second = env.enqueue("b")
        wait_for(lambda: env.status(second) is JobStatus.DONE)
    finally:
        dispatcher.stop()
