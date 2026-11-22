"""The music player as seen from the app: start, control and stop what plays (AP-62).

The page *Musik-Player* needs one place that knows the three players:

* the **local player** (files, folders, playlists and streams on this computer),
* the **player in the app** (YouTube / YouTube Music in an embedded frame; the page draws it),
* **Spotify** (a connection to a Spotify account; OctaLedger only sends commands).

The service starts a source *directly* (without a cube), reports what plays, controls it and
stops everything. It uses the same adapters as the cube's music mode, so there is exactly one
implementation of "play this": the cube and the page differ only in who asks.

**Stopping from the app** also clears the stored "now playing" and ownership of the music cubes
(:mod:`octaledger.application.music_state`); otherwise the overview would claim that a title
plays that the user just stopped.

Honest limits: Spotify needs a connection and an active Spotify device; the embedded YouTube
player plays only while the page *Musik-Player* is open in a browser; neither was tested against
the real service here.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from octaledger.application.integration_service import IntegrationService
from octaledger.application.music_state import STATE_NOW, STATE_OWNER
from octaledger.core.errors import InvalidStateError, ValidationError
from octaledger.domain.music_source import SourceKind, parse_source
from octaledger.infrastructure.integrations.browser import BrowserAdapter
from octaledger.infrastructure.integrations.player import PlayerAdapter
from octaledger.infrastructure.storage.repositories import Storage

logger = logging.getLogger(__name__)

TARGETS: Final = ("local", "browser", "spotify")
LOCAL_ACTIONS: Final = (
    "stop",
    "pause",
    "resume",
    "next",
    "previous",
    "volume",
    "repeat",
    "shuffle",
    "jump",
)


class PlayerService:
    """Direct control of the players (see the module docstring)."""

    def __init__(self, storage: Storage, integrations: IntegrationService) -> None:
        """Create the service.

        Args:
            storage: The database (to clear "now playing" when the user stops).
            integrations: Provides the adapters and the Spotify connection.
        """
        self._storage = storage
        self._integrations = integrations

    # ------------------------------------------------------------------ adapters

    def _local(self) -> PlayerAdapter:
        adapter = self._integrations.adapter_for("player")
        if not isinstance(adapter, PlayerAdapter):  # pragma: no cover - the registry guarantees it
            raise InvalidStateError("No local player", user_message="Der Player fehlt.")
        return adapter

    def _browser(self) -> BrowserAdapter:
        adapter = self._integrations.adapter_for("browser")
        if not isinstance(adapter, BrowserAdapter):  # pragma: no cover - the registry guarantees it
            raise InvalidStateError("No browser player", user_message="Der Player fehlt.")
        return adapter

    def _spotify_connection(self) -> str | None:
        """The id of the first enabled Spotify connection, if there is one."""
        for info in self._integrations.list_integrations():
            if info.integration.kind == "spotify" and info.integration.enabled:
                return str(info.integration.id)
        return None

    # -------------------------------------------------------------------- status

    def status(self) -> dict[str, Any]:
        """What each player does, for the page (never raises for a missing player)."""
        return {
            "local": self._local().status(),
            "browser": self._browser().state(),
            "spotify": {"connection_id": self._spotify_connection()},
        }

    # ---------------------------------------------------------------------- play

    def play(
        self,
        source: str,
        *,
        repeat: str = "off",
        shuffle: bool = False,
        volume: int = 50,
    ) -> dict[str, Any]:
        """Play a pasted link or a local path now, on the player that fits it.

        Args:
            source: A path (file, folder, ``.m3u``), a stream address, a YouTube or YouTube Music
                link or a Spotify link.
            repeat: ``off``, ``all`` or ``one`` (local sources).
            shuffle: Mix the order (local sources).
            volume: Volume in percent.

        Returns:
            ``{"player": "local"|"browser"|"spotify", "message": ..., "tracks": n}``.

        Raises:
            ValidationError: For an unrecognised or unsafe source or a wrong value.
            InvalidStateError: For Spotify without a connection.
        """
        parsed = parse_source(source)
        if not 0 <= volume <= 100:
            raise ValidationError(
                "Volume out of range", user_message="Die Lautstärke muss 0 bis 100 % betragen."
            )
        if parsed.kind is SourceKind.LOCAL:
            tracks = self._local().play(parsed.ref, repeat=repeat, shuffle=shuffle, volume=volume)
            return {
                "player": "local",
                "message": f"{tracks} Titel werden abgespielt.",
                "tracks": tracks,
            }
        if parsed.kind is SourceKind.URL:
            adapter = self._local()
            params = adapter.validate_action({"action": "play_url", "url": parsed.ref})
            message = adapter.execute(
                {"volume": volume}, {}, {**params, "volume": volume}, timeout=5
            )
            return {"player": "local", "message": message, "tracks": 1}
        if parsed.kind is SourceKind.YOUTUBE:
            (params,) = self._browser().music_play_params(
                parsed, volume, {"repeat": repeat, "shuffle": str(shuffle)}
            )
            message = self._browser().execute(
                {}, {}, self._browser().validate_action(params), timeout=1
            )
            return {"player": "browser", "message": message, "tracks": 1}
        connection = self._spotify_connection()
        if connection is None:
            raise InvalidStateError(
                "No Spotify connection",
                user_message="Für Spotify brauchen Sie eine Verbindung (Seite „Smarthome & "
                "Verbindungen“). Legen Sie dort „Spotify“ an.",
            )
        steps = self._integrations.adapter_for("spotify").music_play_params(parsed, volume, {})
        message = ""
        for params in steps:
            message = self._integrations.probe(connection, params)
        return {"player": "spotify", "message": message, "tracks": 1}

    # ------------------------------------------------------------------- control

    def control(self, target: str, action: str, value: Any = None) -> str:
        """Control one player.

        Args:
            target: ``local``, ``browser`` or ``spotify``.
            action: For ``local`` see :data:`LOCAL_ACTIONS`; ``browser`` and ``spotify`` know
                ``stop`` (Spotify: pause).
            value: The level, mode or position some actions need.

        Raises:
            ValidationError: For an unknown target or action or a wrong value.
        """
        if target == "local":
            if action not in LOCAL_ACTIONS:
                raise ValidationError(
                    f"Unknown action {action!r}",
                    user_message="Diese Aktion kennt der Player nicht.",
                )
            self._local().control(action, value)
            if action == "stop":
                self._clear_now()
            return "ok"
        if target == "browser" and action == "stop":
            browser = self._browser()
            browser.execute({}, {}, {"action": "browser_stop"}, timeout=1)
            self._clear_now()
            return "ok"
        if target == "spotify" and action == "stop":
            connection = self._spotify_connection()
            if connection is None:
                raise InvalidStateError(
                    "No Spotify connection", user_message="Es gibt keine Spotify-Verbindung."
                )
            self._integrations.probe(connection, {"action": "spotify_pause"})
            self._clear_now()
            return "ok"
        raise ValidationError(
            f"Unknown player control {target}/{action}",
            user_message="Diese Aktion gibt es für diesen Player nicht.",
        )

    def stop_all(self) -> list[str]:
        """Stop every player (each one tried, a failing one does not stop the others).

        Returns:
            Short German notes about players that could not be stopped (empty on success).
        """
        problems: list[str] = []
        for target in TARGETS:
            try:
                if target == "spotify" and self._spotify_connection() is None:
                    continue
                self.control(target, "stop")
            except Exception as exc:  # noqa: BLE001 - one player failing must not keep the others on
                logger.warning("Could not stop %s: %s", target, exc)
                problems.append(f"{target}: {getattr(exc, 'user_message', 'Fehler')}")
        self._clear_now()
        return problems

    def _clear_now(self) -> None:
        """Forget what the music cubes believe plays (the user ended it from the app)."""
        with self._storage.transaction() as repos:
            for key in list(repos.state.items()):
                if key.startswith((STATE_NOW, STATE_OWNER)):
                    repos.state.delete(key)
