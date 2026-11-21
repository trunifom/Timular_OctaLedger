"""Use cases of control mode: connections, actions per face, testing and sending.

Responsibility
--------------
* **Connections** (``Integration``): create, change, switch on or off, delete. The settings go
  into the database, the secrets (passwords, tokens) into the separate
  :class:`~octaledger.core.secrets.SecretStore`; the API only ever reports *which* secrets exist.
* **Actions per face**: assign what a face does in control mode, validated by the adapter.
* **Trying things out**: test a connection, run an action once, pair, discover lights/scenes.
  These run in the caller's thread (an API request), never inside a database transaction.
* **Sending**: :meth:`process_due` takes the due jobs of the outbox, calls the adapters and
  records the result. It is called in a loop by the agent's dispatcher thread.

The adapters are injected as a mapping ``kind -> Adapter``, so tests use fakes and the agent
passes :func:`~octaledger.infrastructure.integrations.registry.default_adapters`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Final

from octaledger.application.outbox import (
    HISTORY_KEEP,
    MAX_ATTEMPTS,
    RETRY_DELAYS,
)
from octaledger.core.errors import (
    IntegrationConnectionError,
    IntegrationError,
    OctaLedgerError,
    ValidationError,
)
from octaledger.core.secrets import SecretStore
from octaledger.domain.models import FaceAction, Integration, IntegrationJob
from octaledger.domain.time_rules import utc_now
from octaledger.infrastructure.integrations.base import Adapter, AdapterSpec
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

#: Seconds an adapter may take for one request.
DEFAULT_TIMEOUT: Final = 5.0
EXPIRED_MESSAGE: Final = "Zu spät: Die Aktion wurde nicht mehr rechtzeitig gesendet."


@dataclass(frozen=True, slots=True)
class IntegrationInfo:
    """A connection plus the names (never the values) of its stored secrets."""

    integration: Integration
    secrets_set: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JobInfo:
    """A queued/finished job together with the name of its connection."""

    job: IntegrationJob
    integration_name: str


class IntegrationService:
    """Use cases around integrations (see the module docstring)."""

    def __init__(
        self,
        storage: Storage,
        secrets: SecretStore,
        adapters: Mapping[str, Adapter],
        *,
        timeout: float = DEFAULT_TIMEOUT,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create the service.

        Args:
            storage: The database.
            secrets: Where passwords and tokens are kept.
            adapters: ``kind -> adapter``.
            timeout: Seconds one adapter call may take.
            clock: Time source (tests inject a fixed clock).
        """
        self._storage = storage
        self._secrets = secrets
        self._adapters = dict(adapters)
        self._timeout = timeout
        self._clock = clock

    # --------------------------------------------------------------------- adapters

    def adapter_specs(self) -> list[AdapterSpec]:
        """Descriptions of every available adapter (the dashboard renders forms from them)."""
        return [adapter.spec for adapter in self._adapters.values()]

    def _adapter(self, kind: str) -> Adapter:
        adapter = self._adapters.get(kind)
        if adapter is None:
            raise ValidationError(
                f"Unknown integration kind {kind!r}",
                user_message="Diese Art von Verbindung kennt OctaLedger nicht.",
                details={"kind": kind},
            )
        return adapter

    def _split(
        self, adapter: Adapter, values: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Separate non-secret settings from secrets (settings are validated by the caller).

        The caller validates the settings because only it knows the complete set: on an update
        the changed values are merged into the stored ones before they are checked.
        """
        secret_names = {spec.name for spec in adapter.spec.config_fields if spec.secret}
        settings = {k: v for k, v in values.items() if k not in secret_names}
        secrets: dict[str, str] = {}
        for name in secret_names & set(values):
            value = values[name]
            if value is None:
                continue
            if not isinstance(value, str) or "\n" in value or "\r" in value:
                raise ValidationError(
                    f"Secret {name} must be single-line text",
                    user_message="Ein Zugangsdatum muss einzeiliger Text sein.",
                )
            if value.strip():
                secrets[name] = value.strip()
        return settings, secrets

    # ------------------------------------------------------------------ connections

    def _info(self, integration: Integration) -> IntegrationInfo:
        return IntegrationInfo(integration, self._secrets.names(integration.id))

    def list_integrations(self) -> list[IntegrationInfo]:
        """All connections with the names of their stored secrets."""
        with self._storage.read() as repos:
            return [self._info(i) for i in repos.integrations.list_all()]

    def get(self, integration_id: str) -> IntegrationInfo:
        """Return one connection.

        Raises:
            NotFoundError: If it does not exist.
        """
        with self._storage.read() as repos:
            return self._info(repos.integrations.require(integration_id))

    def create(self, kind: str, name: str, values: Mapping[str, Any]) -> IntegrationInfo:
        """Create a connection.

        Args:
            kind: The adapter kind.
            name: A unique, user-chosen name.
            values: Settings and secrets together (secrets are routed to the secret store).

        Raises:
            ValidationError: For unknown kinds or invalid values (German message).
            ConflictError: If the name is taken.
        """
        adapter = self._adapter(kind)
        settings, secrets = self._split(adapter, values)
        config = adapter.validate_config(settings)
        missing = [
            spec.label
            for spec in adapter.spec.config_fields
            if spec.secret and spec.required and spec.name not in secrets
        ]
        if missing:
            raise ValidationError(
                f"Missing secrets: {missing}",
                user_message=f"Bitte füllen Sie aus: {', '.join(missing)}.",
            )
        integration = Integration(kind=kind, name=name, config=config)
        with self._storage.transaction() as repos:
            repos.integrations.add(integration)
        try:
            self._secrets.update(integration.id, secrets)
        except OctaLedgerError:
            with self._storage.transaction() as repos:  # no half-created connection
                repos.integrations.delete(integration.id)
            raise
        return self._info(integration)

    def update(
        self,
        integration_id: str,
        *,
        name: str | None = None,
        values: Mapping[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> IntegrationInfo:
        """Change a connection. Blank secrets keep the stored value.

        Raises:
            NotFoundError: If missing.
            ValidationError: For invalid values.
            ConflictError: If the new name is taken.
        """
        with self._storage.transaction() as repos:
            current = repos.integrations.require(integration_id)
            adapter = self._adapter(current.kind)
            config: dict[str, Any] = dict(current.config)
            secrets: dict[str, str] = {}
            if values is not None:
                changes, secrets = self._split(adapter, values)
                config = adapter.validate_config({**current.config, **changes})
            updated = replace(
                current,
                name=current.name if name is None else name,
                config=config,
                enabled=current.enabled if enabled is None else enabled,
            )
            repos.integrations.update(updated)
        if secrets:
            self._secrets.update(integration_id, secrets)
        return self.get(integration_id)

    def forget_secrets(self, integration_ids: list[str]) -> None:
        """Forget the stored credentials of connections that no longer exist (factory reset)."""
        for integration_id in integration_ids:
            self._secrets.delete(integration_id)

    def delete(self, integration_id: str) -> None:
        """Delete a connection, its queued jobs and its secrets.

        Raises:
            NotFoundError: If missing.
            ConflictError: If a face still uses it (remove that action first).
        """
        with self._storage.transaction() as repos:
            repos.integrations.delete(integration_id, repos.audit)
        self._secrets.delete(integration_id)

    # -------------------------------------------------------------- trying things out

    def _target(self, integration_id: str) -> tuple[Integration, Adapter, dict[str, str]]:
        with self._storage.read() as repos:
            integration = repos.integrations.require(integration_id)
        return integration, self._adapter(integration.kind), self._secrets.get(integration_id)

    def check(self, integration_id: str) -> str:
        """Test a connection without side effects; returns a short German message.

        Raises:
            IntegrationError: If the target is unreachable or rejects the credentials.
        """
        integration, adapter, secrets = self._target(integration_id)
        return adapter.check(integration.config, secrets, timeout=self._timeout)

    def probe(self, integration_id: str, params: Mapping[str, Any]) -> str:
        """Run one action **right now** ("try it"), independent of any face.

        Raises:
            ValidationError: For invalid parameters.
            IntegrationError: If the action fails.
        """
        integration, adapter, secrets = self._target(integration_id)
        cleaned = adapter.validate_action(params)
        return adapter.execute(integration.config, secrets, cleaned, timeout=self._timeout)

    def pair(self, integration_id: str) -> str:
        """Run the adapter's one-time pairing and store what it returns.

        Raises:
            IntegrationError: If pairing fails (for example the button was not pressed).
        """
        integration, adapter, _ = self._target(integration_id)
        result = adapter.pair(integration.config, timeout=self._timeout)
        if result.config:
            merged = adapter.validate_config({**integration.config, **result.config})
            with self._storage.transaction() as repos:
                repos.integrations.update(replace(integration, config=merged))
        if result.secrets:
            self._secrets.update(integration_id, result.secrets)
        return result.message

    def discover(self, integration_id: str) -> dict[str, list[dict[str, str]]]:
        """List what the target offers to choose from (lights, scenes ...)."""
        integration, adapter, secrets = self._target(integration_id)
        return adapter.discover(integration.config, secrets, timeout=self._timeout)

    # ----------------------------------------------------------------- face actions

    def list_actions(self, device_id: str) -> list[FaceAction]:
        """The actions assigned to the faces of a device."""
        with self._storage.read() as repos:
            repos.devices.require(device_id)
            return repos.actions.list_for_device(device_id)

    def assign_action(
        self,
        device_id: str,
        face: int,
        integration_id: str,
        label: str,
        params: Mapping[str, Any],
    ) -> FaceAction:
        """Give a face an action (validated by the adapter).

        Raises:
            ValidationError: For an invalid face, label or action parameters.
            NotFoundError: If the device or the connection does not exist.
        """
        with self._storage.transaction() as repos:
            repos.devices.require(device_id)
            integration = repos.integrations.require(integration_id)
            cleaned = self._adapter(integration.kind).validate_action(params)
            return repos.actions.assign(device_id, face, integration_id, label, cleaned)

    def clear_action(self, device_id: str, face: int) -> None:
        """Remove the action of a face."""
        with self._storage.transaction() as repos:
            repos.devices.require(device_id)
            repos.actions.clear(device_id, face)

    # --------------------------------------------------------------- sending (outbox)

    def list_jobs(self, limit: int = 50) -> list[JobInfo]:
        """The newest jobs (history of what was sent), newest first."""
        with self._storage.read() as repos:
            names = {i.id: i.name for i in repos.integrations.list_all()}
            return [
                JobInfo(j, names.get(j.integration_id, "?")) for j in repos.jobs.list_recent(limit)
            ]

    def process_due(self, max_jobs: int = 20) -> int:
        """Send due jobs; returns how many were handled.

        Called in a loop by the dispatcher. It never raises for a failing job: every outcome
        is recorded on the job. Adapter calls happen **outside** database transactions.
        """
        now = self._clock()
        with self._storage.transaction() as repos:
            repos.jobs.expire_overdue(now, EXPIRED_MESSAGE)
            repos.jobs.delete_finished_before(now - HISTORY_KEEP)
        with self._storage.read() as repos:
            due = repos.jobs.due(now, max_jobs)
        for job in due:
            self._run(job)
        return len(due)

    def _run(self, job: IntegrationJob) -> None:
        attempts = job.attempts + 1
        with self._storage.read() as repos:
            integration = repos.integrations.get(job.integration_id)
        if integration is None or not integration.enabled:
            self._finish(
                job, "expired", attempts, "Die Verbindung ist ausgeschaltet oder gelöscht."
            )
            return
        adapter = self._adapters.get(integration.kind)
        if adapter is None:
            self._finish(job, "failed", attempts, "Diese Art von Verbindung ist nicht verfügbar.")
            return
        try:
            message = adapter.execute(
                integration.config,
                self._secrets.get(integration.id),
                job.params,
                timeout=self._timeout,
            )
        except IntegrationConnectionError as exc:
            self._retry_or_fail(job, attempts, exc.user_message)
        except IntegrationError as exc:
            logger.warning("Action %r of %s failed: %s", job.label, integration.name, exc)
            self._finish(job, "failed", attempts, exc.user_message)
        except Exception:  # noqa: BLE001 - the dispatcher must survive any adapter bug
            logger.exception("Adapter %s crashed on action %r", integration.kind, job.label)
            self._finish(job, "failed", attempts, "Unerwarteter Fehler in der Verbindung.")
        else:
            logger.info("Action %r of %s sent: %s", job.label, integration.name, message)
            self._finish(job, "done", attempts, None)

    def _retry_or_fail(self, job: IntegrationJob, attempts: int, error: str) -> None:
        now = self._clock()
        if attempts >= MAX_ATTEMPTS:
            self._finish(job, "failed", attempts, error)
            return
        retry_at = now + timedelta(seconds=RETRY_DELAYS[min(attempts, len(RETRY_DELAYS)) - 1])
        if retry_at >= job.expires_at:
            self._finish(job, "failed", attempts, error)
            return
        logger.info("Action %r will be retried at %s: %s", job.label, retry_at.time(), error)
        with self._storage.transaction() as repos:
            repos.jobs.mark_retry(job.id, attempts, retry_at, error)

    def _finish(self, job: IntegrationJob, status: str, attempts: int, error: str | None) -> None:
        now = self._clock()
        with self._storage.transaction() as repos:
            if status == "done":
                repos.jobs.mark_done(job.id, now, attempts)
            elif status == "expired":
                repos.jobs.mark_expired(job.id, now, attempts, error or EXPIRED_MESSAGE)
            else:
                repos.jobs.mark_failed(job.id, now, attempts, error or "Fehlgeschlagen.")
