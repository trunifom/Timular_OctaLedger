"""The stored state of the music mode: settings, "now playing" and the stop recipes.

Kept apart from :mod:`octaledger.application.music_service` so the integration service (which
sends the jobs) can update "now playing" without importing the service that depends on it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from typing import Any, Final

from octaledger.domain.models import DeviceMode
from octaledger.domain.music import MusicSettings, NowPlaying
from octaledger.domain.time_rules import ensure_utc
from octaledger.infrastructure.storage.repositories import Repositories

STATE_SETTINGS: Final = "music:"
STATE_NOW: Final = "music_now:"
STATE_STOP: Final = "music_stop:"
STATE_LOST: Final = "music_lost:"
#: ``music_owner:<target>``: which cube started what plays on a target (AP-55).
STATE_OWNER: Final = "music_owner:"
#: Actions that really start sound; only their success marks "now playing".
PLAY_ACTIONS: Final = frozenset(
    {"play_url", "play_file", "play_path", "media_play", "spotify_play", "browser_play"}
)


def load_settings(repos: Repositories, device_id: str) -> MusicSettings:
    """The music settings of a cube (defaults if none were saved)."""
    raw = repos.state.get(STATE_SETTINGS + device_id)
    return MusicSettings(**json.loads(raw)) if raw else MusicSettings()


def load_now(repos: Repositories, device_id: str) -> NowPlaying | None:
    """What plays on a cube, or ``None``."""
    raw = repos.state.get(STATE_NOW + device_id)
    return NowPlaying(**json.loads(raw)) if raw else None


def music_target(integration_id: str, params: Mapping[str, Any]) -> str:
    """The place music plays: the connection and, where there is one, its media player.

    Only one title can play per target. Two Home Assistant speakers are two targets, the local
    player, a Spotify account and the browser player are one target each.
    """
    entity = str(params.get("entity_id") or "")
    return f"{integration_id}|{entity}" if entity else integration_id


def owner_of(repos: Repositories, target: str) -> str | None:
    """The cube that owns a target (started what plays there), or ``None``."""
    raw = repos.state.get(STATE_OWNER + target)
    return str(json.loads(raw)["device_id"]) if raw else None


def mark_sent(
    repos: Repositories,
    device_id: str,
    face: int | None,
    params: Mapping[str, Any],
    integration_id: str,
    label: str,
    now: datetime,
) -> str | None:
    """A job of a music cube was sent: update "now playing" and the owner of the target.

    A play action sets it and makes this cube the **owner** of the target; the music of a
    previous owner is replaced (its "now playing" is cleared, so its holder no longer stops what
    now belongs to someone else). A stop/pause action (no face) clears the cube's state and, if
    the cube was the owner, the ownership. Other jobs (for example a volume step) change nothing.

    Returns:
        A note for the history when a title of another cube was replaced, else ``None``.
    """
    device = repos.devices.get(device_id)
    if device is None or device.mode is not DeviceMode.MUSIC:
        return None
    target = music_target(integration_id, params)
    if face is None:
        repos.state.delete(STATE_NOW + device_id)
        if owner_of(repos, target) == device_id:
            repos.state.delete(STATE_OWNER + target)
        return None
    if str(params.get("action")) not in PLAY_ACTIONS:
        return None
    note = None
    previous = owner_of(repos, target)
    if previous is not None and previous != device_id:
        replaced = load_now(repos, previous)
        if replaced is not None and replaced.target in ("", target):
            repos.state.delete(STATE_NOW + previous)
        other = repos.devices.get(previous)
        name = other.alias if other else "einem anderen Würfel"
        note = f"Ersetzt die Musik von {name}."
    action = repos.actions.get(device_id, face)
    shown = action.label if action is not None else label
    stamp = ensure_utc(now).isoformat()
    repos.state.set(
        STATE_NOW + device_id,
        json.dumps(asdict(NowPlaying(face, shown, integration_id, stamp, target))),
    )
    repos.state.set(
        STATE_OWNER + target,
        json.dumps({"device_id": device_id, "label": shown, "since": stamp}),
    )
    return note
