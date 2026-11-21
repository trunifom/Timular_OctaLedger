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

import logging
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from octaledger.domain.models import IntegrationJob, JobStatus
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


def enqueue_face_action(
    repos: Repositories, device_id: str, face: int, trigger_id: str, now: datetime
) -> QueueResult:
    """Turn "face ``face`` of ``device_id`` came up" into a queued job, if it has an action.

    Must run inside the transaction that stores the raw event ``trigger_id``.
    """
    action = repos.actions.get(device_id, face)
    if action is None:
        logger.warning("Face %d of device %s has no action assigned", face, device_id[:8])
        return QueueResult.NO_ACTION
    integration = repos.integrations.require(action.integration_id)
    if not integration.enabled:
        logger.info("Integration %s is switched off; action skipped", integration.name)
        return QueueResult.DISABLED
    dropped = repos.jobs.count_pending(integration.id) >= MAX_PENDING_JOBS
    job = IntegrationJob(
        idempotency_key=trigger_id,
        integration_id=integration.id,
        label=action.label,
        params=action.params,
        expires_at=now + JOB_LIFETIME,
        device_id=device_id,
        face=face,
        status=JobStatus.EXPIRED if dropped else JobStatus.PENDING,
        last_error=QUEUE_FULL_MESSAGE if dropped else None,
        created_at=now,
        finished_at=now if dropped else None,
    )
    if not repos.jobs.enqueue(job):
        return QueueResult.DUPLICATE
    if dropped:
        logger.warning("Queue of integration %s is full; an action was dropped", integration.name)
        return QueueResult.DROPPED
    return QueueResult.QUEUED
