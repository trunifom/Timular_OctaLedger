"""The music mode: turning cube movements into play and stop commands.

Responsibility
--------------
* :func:`handle_event` is called by the tracking service, **inside the transaction of the raw
  event**, for a cube in music mode. It asks the pure rules (:mod:`octaledger.domain.music`) what
  to do and queues the jobs (stops before the play) in the same transaction, after cancelling every
  job of this cube that was not sent yet (a new face replaces everything).
* :class:`MusicService` offers the use cases of the interface: set a title for a face from a
  pasted link, per-cube settings, the "now playing" state, and the watchdog that stops music some
  time after the connection to a cube was lost.
* "Now playing" is **state**: it is set only when a play job was really sent and cleared when a
  stop/pause job was sent; a failed job leaves it unchanged (and shows up in the history).

Stopping needs to know *how* to stop a target (Home Assistant stops one media player, the local
player just stops). That knowledge belongs to the adapters, so it is computed **when a title is
saved** and stored (``music_stop:<device>:<connection>``); the event handler then needs no
adapter.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

from octaledger.application.integration_service import IntegrationService
from octaledger.application.music_state import (
    PLAY_ACTIONS,
    STATE_LOST,
    STATE_OWNER,
    STATE_SETTINGS,
    STATE_STOP,
    load_now,
    load_settings,
)
from octaledger.application.outbox import chain_for, enqueue_job
from octaledger.core.errors import InvalidStateError, ValidationError
from octaledger.core.settings import Settings
from octaledger.domain.models import Device, DeviceMode, RawEvent, new_id
from octaledger.domain.music import (
    CommandKind,
    MusicCommand,
    MusicSettings,
    decide,
)
from octaledger.domain.music_source import MusicSource, parse_source
from octaledger.domain.time_rules import ensure_utc, utc_now
from octaledger.infrastructure.storage.repositories import Repositories, Storage

logger = logging.getLogger(__name__)

REPLACED: Final = "Durch eine neue Seite ersetzt."


# ----------------------------------------------------------------- state in app_state


def _titles(repos: Repositories, device_id: str) -> dict[int, str]:
    """``face -> connection id`` of the faces that have a title."""
    return {a.face: a.integration_id for a in repos.actions.list_for_device(device_id)}


def _stop_params(
    repos: Repositories, device_id: str, integration_id: str, kind: CommandKind
) -> dict[str, Any] | None:
    """The stored action that stops (or pauses) a target of this cube, if one is known."""
    raw = repos.state.get(f"{STATE_STOP}{device_id}:{integration_id}")
    if not raw:
        return None
    stored = json.loads(raw)
    chosen = stored.get("pause") if kind is CommandKind.PAUSE else None
    result = chosen or stored.get("stop")
    return dict(result) if isinstance(result, dict) else None


# --------------------------------------------------------------- the event handler


def handle_event(
    repos: Repositories, device: Device, event: RawEvent, now: datetime, tz: ZoneInfo | None = None
) -> tuple[int, bool]:
    """Apply the music rules to an event of a music cube.

    Returns:
        ``(jobs queued, whether a title is played)``; ``(n, False)`` means the music is stopped.
    """
    del tz  # reserved: conditions on music titles are not part of this version
    if event.kind.value == "disconnect":
        if load_now(repos, device.id) is not None:
            repos.state.set(STATE_LOST + device.id, now.isoformat())
        return 0, False
    if event.kind.value in ("reconnect", "baseline"):
        repos.state.delete(STATE_LOST + device.id)
    if event.kind.value not in ("face_change", "neutral", "baseline"):
        return 0, False
    commands = decide(
        event.kind.value,
        event.raw_value,
        load_now(repos, device.id),
        _titles(repos, device.id),
        frozenset(_titles(repos, device.id).values()),
        load_settings(repos, device.id),
    )
    if not commands:
        return 0, False
    plays = any(c.kind is CommandKind.PLAY for c in commands)
    return _queue(repos, device, commands, event.id, now), plays


def _queue(
    repos: Repositories,
    device: Device,
    commands: list[MusicCommand],
    trigger_id: str,
    now: datetime,
) -> int:
    """Cancel what is not sent yet and queue the commands in order (one transaction)."""
    repos.jobs.expire_pending_of_device(device.id, now, REPLACED)
    queued = 0
    position = 0
    for command in commands:
        if command.kind is CommandKind.PLAY:
            assert command.face is not None
            for step in (s for s in chain_for(repos, device.id, command.face) if s.enabled):
                enqueue_job(
                    repos,
                    integration_id=step.integration_id,
                    label=step.label,
                    params=step.params,
                    device_id=device.id,
                    face=command.face,
                    trigger_id=trigger_id,
                    position=position,
                    delay_ms=step.delay_ms,
                    continue_on_error=step.continue_on_error,
                    now=now,
                )
                position += 1
                queued += 1
            continue
        params = _stop_params(repos, device.id, command.integration_id, command.kind)
        if params is None:
            logger.warning("No stop action known for a music target; nothing queued for it")
            continue
        enqueue_job(
            repos,
            integration_id=command.integration_id,
            label="Musik pausieren" if command.kind is CommandKind.PAUSE else "Musik stoppen",
            params=params,
            device_id=device.id,
            face=None,
            trigger_id=trigger_id,
            position=position,
            delay_ms=command.delay_ms,
            continue_on_error=True,  # stopping the other targets must still be tried
            now=now,
        )
        position += 1
        queued += 1
    return queued


# ------------------------------------------------------------------------ use cases


class MusicService:
    """The use cases of the music mode (see the module docstring)."""

    def __init__(
        self,
        storage: Storage,
        integrations: IntegrationService,
        settings: Callable[[], Settings],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """Create the service.

        Args:
            storage: The database.
            integrations: Used to validate titles with the adapters and to assign steps.
            settings: Current settings (the watchdog uses the connection-loss grace period).
            clock: Returns the current UTC time.
        """
        self._storage = storage
        self._integrations = integrations
        self._settings = settings
        self._clock = clock

    # -------------------------------------------------------------------- reading

    @staticmethod
    def parse(text: str) -> MusicSource:
        """Recognise a pasted link (changes nothing).

        Raises:
            ValidationError: If it is not a recognised source.
        """
        return parse_source(text)

    def get_settings(self, device_id: str) -> MusicSettings:
        """The music settings of a cube."""
        with self._storage.read() as repos:
            repos.devices.require(device_id)
            return load_settings(repos, device_id)

    def set_settings(self, device_id: str, new: MusicSettings) -> MusicSettings:
        """Save the music settings of a cube."""
        with self._storage.transaction() as repos:
            repos.devices.require(device_id)
            repos.state.set(STATE_SETTINGS + device_id, json.dumps(asdict(new)))
        return new

    def state(self) -> list[dict[str, Any]]:
        """For every music cube: its name and what plays (``None`` if nothing)."""
        with self._storage.read() as repos:
            result = []
            for device in repos.devices.list_all():
                if device.mode is not DeviceMode.MUSIC:
                    continue
                now = load_now(repos, device.id)
                result.append(
                    {
                        "device_id": device.id,
                        "alias": device.alias,
                        "playing": None if now is None else asdict(now),
                        "lost_since": repos.state.get(STATE_LOST + device.id),
                    }
                )
            return result

    def owners(self) -> list[dict[str, Any]]:
        """Who controls what: for every target with music, the cube that started it (AP-55)."""
        with self._storage.read() as repos:
            result = []
            for key, raw in sorted(repos.state.items().items()):
                if not key.startswith(STATE_OWNER):
                    continue
                target = key[len(STATE_OWNER) :]
                connection_id, _, entity = target.partition("|")
                connection = repos.integrations.get(connection_id)
                device_id = str(json.loads(raw)["device_id"])
                device = repos.devices.get(device_id)
                if connection is None or device is None:
                    continue
                data = json.loads(raw)
                result.append(
                    {
                        "target": connection.name + (f" · {entity}" if entity else ""),
                        "device_id": device_id,
                        "alias": device.alias,
                        "label": data.get("label", ""),
                        "since": data.get("since"),
                    }
                )
            return result

    # -------------------------------------------------------------------- titles

    def set_title(
        self,
        device_id: str,
        face: int,
        integration_id: str,
        link: str,
        label: str,
        *,
        volume: int | None = None,
        options: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Give a face a title from a pasted link (validated by the target's adapter).

        Raises:
            ValidationError: For an unrecognised link, a target that cannot play it, a wrong
                volume or an invalid face.
            InvalidStateError: If the cube is not in music mode or the connection cannot play
                music.
            NotFoundError: If the cube or the connection does not exist.
        """
        source = parse_source(link)
        with self._storage.read() as repos:
            device = repos.devices.require(device_id)
            integration = repos.integrations.require(integration_id)
            default = load_settings(repos, device_id).default_volume
        if device.mode is not DeviceMode.MUSIC:
            raise InvalidStateError(
                "Device is not in music mode",
                user_message="Dieser Würfel ist nicht im Musik-Modus.",
            )
        level = default if volume is None else volume
        if not 0 <= level <= 100:
            raise ValidationError(
                "Volume out of range", user_message="Die Lautstärke muss 0 bis 100 % betragen."
            )
        adapter = self._integrations.adapter_for(integration.kind)
        if not adapter.spec.music_capable:
            raise InvalidStateError(
                f"{integration.kind} cannot play music",
                user_message="Diese Verbindung kann keine Musik abspielen.",
            )
        plays = adapter.music_play_params(source, level, options or {})
        steps = [
            {
                "integration_id": integration_id,
                "label": label,
                "params": params,
                "delay_ms": 300 if index else 0,  # the title starts a moment after the volume
            }
            for index, params in enumerate(plays)
        ]
        built = self._integrations.assign_steps(device_id, face, steps)
        play = next((s for s in built if str(s.params.get("action")) in PLAY_ACTIONS), built[-1])
        stop = adapter.music_stop_params(play.params, pause=False)
        pause = adapter.music_stop_params(play.params, pause=True)
        with self._storage.transaction() as repos:
            repos.state.set(
                f"{STATE_STOP}{device_id}:{integration_id}",
                json.dumps({"stop": stop, "pause": pause}),
            )
        logger.info("Music title set for face %d (%s)", face, source.kind.value)
        return [{"position": s.position, "action": s.params.get("action")} for s in built]

    # ---------------------------------------------------------------------- watchdog

    def watchdog(self, now: datetime | None = None) -> int:
        """Stop music on cubes whose connection stayed lost longer than the grace period.

        Music that keeps playing without the cube is unexpected. Nothing happens at the moment of
        the loss (it may be a short dropout); after ``disconnect_grace_seconds`` every target
        the cube uses is stopped. Returns how many stop jobs were queued.
        """
        moment = ensure_utc(now) if now is not None else ensure_utc(self._clock())
        grace = timedelta(seconds=self._settings().tracking.disconnect_grace_seconds)
        queued = 0
        with self._storage.transaction() as repos:
            for key, raw in repos.state.items().items():
                if not key.startswith(STATE_LOST):
                    continue
                device_id = key[len(STATE_LOST) :]
                device = repos.devices.get(device_id)
                lost_at = datetime.fromisoformat(raw)
                if device is None or device.mode is not DeviceMode.MUSIC:
                    repos.state.delete(key)
                    continue
                if moment - lost_at < grace:
                    continue
                repos.state.delete(key)
                playing = load_now(repos, device_id)
                if playing is None:
                    continue
                settings = load_settings(repos, device_id)
                kind = CommandKind.PAUSE if settings.base_action == "pause" else CommandKind.STOP
                targets = sorted(set(_titles(repos, device_id).values()))
                queued += _queue(
                    repos,
                    device,
                    [MusicCommand(kind, target) for target in targets],
                    new_id(),
                    moment,
                )
                logger.warning(
                    "Music stopped: the cube stayed disconnected beyond the grace period"
                )
        return queued
