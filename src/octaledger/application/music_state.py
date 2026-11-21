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
#: Actions that really start sound; only their success marks "now playing".
PLAY_ACTIONS: Final = frozenset(
    {"play_url", "play_file", "media_play", "spotify_play", "browser_play"}
)


def load_settings(repos: Repositories, device_id: str) -> MusicSettings:
    """The music settings of a cube (defaults if none were saved)."""
    raw = repos.state.get(STATE_SETTINGS + device_id)
    return MusicSettings(**json.loads(raw)) if raw else MusicSettings()


def load_now(repos: Repositories, device_id: str) -> NowPlaying | None:
    """What plays on a cube, or ``None``."""
    raw = repos.state.get(STATE_NOW + device_id)
    return NowPlaying(**json.loads(raw)) if raw else None


def mark_sent(
    repos: Repositories,
    device_id: str,
    face: int | None,
    params: Mapping[str, Any],
    integration_id: str,
    label: str,
    now: datetime,
) -> None:
    """A job of a music cube was sent: update the "now playing" state accordingly.

    A play action sets it, a stop/pause action (no face) clears it. Other jobs (for example a
    volume step) do not change it.
    """
    device = repos.devices.get(device_id)
    if device is None or device.mode is not DeviceMode.MUSIC:
        return
    if face is None:
        repos.state.delete(STATE_NOW + device_id)
        return
    if str(params.get("action")) in PLAY_ACTIONS:
        action = repos.actions.get(device_id, face)
        shown = action.label if action is not None else label
        repos.state.set(
            STATE_NOW + device_id,
            json.dumps(
                asdict(NowPlaying(face, shown, integration_id, ensure_utc(now).isoformat()))
            ),
        )
