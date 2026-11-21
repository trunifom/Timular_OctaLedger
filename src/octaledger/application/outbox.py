"""Rules of the action queue (the "outbox"): when a face turn becomes a job, and how it is retried.

Responsibility
--------------
A turn of a cube in control mode must reliably become **one** action, and an action must not be
sent minutes late. This module holds the few numbers and the one function that decide that, so
that the tracking service (which writes the job together with the raw event) and the integration
service (which sends it) agree on them.

* **Reliable:** the job is written in the *same transaction* as the raw event.
* **Not twice:** the idempotency key is the id of the raw event.
* **Not late:** every job expires after :data:`JOB_LIFETIME`.
* **Bounded:** at most :data:`MAX_PENDING_JOBS` per integration wait at the same time; further
  ones are stored as expired with a clear reason instead of growing without limit.
* **Retried carefully:** only errors that certainly had no effect are retried, at most
  :data:`MAX_ATTEMPTS` times with growing pauses.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from zoneinfo import ZoneInfo

from octaledger.domain.conditions import holds
from octaledger.domain.models import IntegrationJob, JobStatus
from octaledger.domain.steps import ActionStep
from octaledger.infrastructure.storage.repositories import Repositories

logger = logging.getLogger(__name__)

#: How long an action stays worth sending. A light that switches a minute late is a bug.
JOB_LIFETIME: Final = timedelta(seconds=30)
#: Waiting jobs allowed per integration at the same time.
MAX_PENDING_JOBS: Final = 50
#: Total tries per job (the first try plus retries).
MAX_ATTEMPTS: Final = 3
#: Pause before retry number 1, 2, ... (seconds).
RETRY_DELAYS: Final = (1.0, 3.0)
#: Finished jobs are kept this long for the history.
HISTORY_KEEP: Final = timedelta(days=7)
QUEUE_FULL_MESSAGE: Final = "Zu viele Aktionen warten; diese wurde verworfen."
REPLACED_MESSAGE: Final = "Durch eine neue Seite ersetzt."
PREVIOUS_FAILED_MESSAGE: Final = "Der vorherige Schritt ist fehlgeschlagen."
OUTSIDE_WINDOW_MESSAGE: Final = "Übersprungen: außerhalb des Zeitfensters."


class QueueResult(StrEnum):
    """What :func:`enqueue_face_action` did."""

    QUEUED = "queued"
    #: The face has no action (nothing to do).
    NO_ACTION = "no_action"
    #: The action's integration is switched off.
    DISABLED = "disabled"
    #: The queue was full: the job was stored as expired.
    DROPPED = "dropped"
    #: A job for this trigger already existed.
    DUPLICATE = "duplicate"


def chain_for(repos: Repositories, device_id: str, face: int) -> list[ActionStep]:
    """The steps of a face: its chain, or - for older data - its single action as one step."""
    steps = repos.steps.list_for(device_id, face)
    if steps:
        return steps
    action = repos.actions.get(device_id, face)
    if action is None:
        return []
    return [ActionStep(device_id, face, 0, action.integration_id, action.label, action.params)]


def step_key(trigger_id: str, position: int) -> str:
    """The idempotency key of a step: the raw event id for step 0, a derived key after that."""
    if position == 0:
        return trigger_id
    return hashlib.sha256(f"{trigger_id}#{position}".encode()).hexdigest()[:32]


def enqueue_face_action(
    repos: Repositories,
    device_id: str,
    face: int,
    trigger_id: str,
    now: datetime,
    tz: ZoneInfo | None = None,
) -> QueueResult:
    """Turn "face ``face`` of ``device_id`` came up" into queued jobs, one per step.

    Must run inside the transaction that stores the raw event ``trigger_id``. Earlier steps of this
    device that were not sent yet are cancelled first (a delayed step of the face the user just
    left must not fire). Conditions are evaluated **now**, at the turn: a step outside its time
    window is simply not queued.

    Returns:
        :attr:`QueueResult.QUEUED` if at least one step was queued, otherwise the reason (the
        reason of the *first* step when nothing was queued).
    """
    repos.jobs.expire_unsent_steps(device_id, now, REPLACED_MESSAGE)
    steps = [s for s in chain_for(repos, device_id, face) if s.enabled]
    if not steps:
        logger.warning("Face %d of device %s has no action assigned", face, device_id[:8])
        return QueueResult.NO_ACTION
    local = now.astimezone(tz) if tz is not None else now
    results: list[QueueResult] = []
    for step in steps:
        if not holds(step.condition, local):
            logger.info(
                "Step %d of face %d skipped: outside its time window", step.position + 1, face
            )
            continue
        results.append(_enqueue_step(repos, step, trigger_id, now))
    if QueueResult.QUEUED in results:
        return QueueResult.QUEUED
    return results[0] if results else QueueResult.NO_ACTION


def _enqueue_step(
    repos: Repositories, step: ActionStep, trigger_id: str, now: datetime
) -> QueueResult:
    """Queue one step (its delay becomes the earliest send time and extends its lifetime)."""
    integration = repos.integrations.require(step.integration_id)
    if not integration.enabled:
        logger.info("Integration %s is switched off; step skipped", integration.name)
        return QueueResult.DISABLED
    delay = timedelta(milliseconds=step.delay_ms)
    dropped = repos.jobs.count_pending(integration.id) >= MAX_PENDING_JOBS
    job = IntegrationJob(
        idempotency_key=step_key(trigger_id, step.position),
        integration_id=integration.id,
        label=step.label,
        params=step.params,
        expires_at=now + delay + JOB_LIFETIME,
        device_id=step.device_id,
        face=step.face,
        status=JobStatus.EXPIRED if dropped else JobStatus.PENDING,
        last_error=QUEUE_FULL_MESSAGE if dropped else None,
        created_at=now,
        next_attempt_at=now + delay,
        finished_at=now if dropped else None,
        chain_id=trigger_id,
        step=step.position,
        continue_on_error=step.continue_on_error,
    )
    if not repos.jobs.enqueue(job):
        return QueueResult.DUPLICATE
    if dropped:
        logger.warning("Queue of integration %s is full; an action was dropped", integration.name)
        return QueueResult.DROPPED
    return QueueResult.QUEUED
