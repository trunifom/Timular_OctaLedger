"""Tests for the Spotify adapter against a local fake of the documented endpoints (plain HTTP).

The browser step of the pairing is simulated: the injected ``open_browser`` reads the ``state`` from
the login address and calls the loopback listener itself. Nothing here talks to Spotify.
"""

import json
import socket
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from octaledger.core.errors import (
    IntegrationConnectionError,
    IntegrationError,
    ValidationError,
)
from octaledger.domain.music_source import parse_source
from octaledger.infrastructure.integrations.registry import default_adapters
from octaledger.infrastructure.integrations.spotify import (
    SpotifyAdapter,
    _challenge,
    _play_body,
)

TIMEOUT = 2.0
CONFIG = {"client_id": "client-123"}
SECRETS = {"refresh_token": "refresh-abc"}
PLAYLIST = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
TRACK = "https://open.spotify.com/track/11dFghVXANMlKmJXsNCbNl"


class FakeSpotify:
    """Token endpoint plus the three player endpoints."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.token_answer: tuple[int, dict[str, Any]] = (
            200,
            {"access_token": "access-1", "expires_in": 3600, "refresh_token": "refresh-new"},
        )
        self.player_status = 204
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _read(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def _answer(self, status: int, payload: Any = None, headers: Any = None) -> None:
                body = json.dumps(payload).encode() if payload is not None else b""
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _record(self, body: bytes) -> None:
                outer.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "auth": self.headers.get("Authorization"),
                        "body": body.decode(),
                    }
                )

            def do_POST(self) -> None:
                self._record(self._read())
                status, payload = outer.token_answer
                self._answer(status, payload)

            def do_PUT(self) -> None:
                self._record(self._read())
                if outer.player_status == 429:
                    self._answer(429, headers={"Retry-After": "3"})
                else:
                    self._answer(outer.player_status)

            def do_GET(self) -> None:
                self._record(b"")
                self._answer(200, {"display_name": "Tester"})

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def player(self) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["method"] == "PUT"]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake() -> Iterator[FakeSpotify]:
    server = FakeSpotify()
    yield server
    server.close()


def adapter(fake: FakeSpotify, **extra: Any) -> SpotifyAdapter:
    return SpotifyAdapter(api_base=fake.base, accounts_base=fake.base, **extra)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# ----------------------------------------------------------------------- pure helpers


def test_registered_and_music_capable() -> None:
    spotify = default_adapters()["spotify"]
    assert spotify.spec.music_capable and spotify.spec.can_pair


def test_pkce_challenge_matches_the_rfc_example() -> None:
    # RFC 7636 appendix B
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert _challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_play_body_uses_context_or_uris() -> None:
    assert _play_body("spotify:track:abc") == {"uris": ["spotify:track:abc"]}
    assert _play_body("spotify:episode:abc") == {"uris": ["spotify:episode:abc"]}
    assert _play_body("spotify:playlist:abc") == {"context_uri": "spotify:playlist:abc"}


def test_only_spotify_sources_are_accepted(fake: FakeSpotify) -> None:
    plays = adapter(fake).music_play_params(parse_source(PLAYLIST), 40, {})
    assert plays == [
        {"action": "spotify_volume", "volume": 40},
        {"action": "spotify_play", "uri": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"},
    ]
    with pytest.raises(ValidationError):
        adapter(fake).music_play_params(parse_source("https://radio.example/live.mp3"), 40, {})


def test_stop_is_pause(fake: FakeSpotify) -> None:
    spotify = adapter(fake)
    assert spotify.music_stop_params({}, pause=False) == {"action": "spotify_pause"}
    assert spotify.music_stop_params({}, pause=True) == {"action": "spotify_pause"}


def test_action_validation(fake: FakeSpotify) -> None:
    spotify = adapter(fake)
    assert spotify.validate_action({"action": "spotify_volume", "volume": 20})["volume"] == 20
    with pytest.raises(ValidationError):
        spotify.validate_action({"action": "spotify_volume", "volume": 101})
    with pytest.raises(ValidationError):
        spotify.validate_action({"action": "spotify_play"})


# ------------------------------------------------------------------------- operations


def test_check_reads_the_profile(fake: FakeSpotify) -> None:
    message = adapter(fake).check(CONFIG, SECRETS, timeout=TIMEOUT)
    assert "Tester" in message
    token_call = fake.requests[0]
    assert "grant_type=refresh_token" in token_call["body"]
    assert "client_id=client-123" in token_call["body"]
    assert fake.requests[1]["auth"] == "Bearer access-1"


def test_play_sends_the_body_and_device(fake: FakeSpotify) -> None:
    spotify = adapter(fake)
    config = {**CONFIG, "device_id": "dev 1"}
    spotify.execute(
        config,
        SECRETS,
        {"action": "spotify_play", "uri": "spotify:playlist:abc"},
        timeout=TIMEOUT,
    )
    call = fake.player()[0]
    assert call["path"] == "/v1/me/player/play?device_id=dev+1"
    assert json.loads(call["body"]) == {"context_uri": "spotify:playlist:abc"}


def test_volume_and_pause(fake: FakeSpotify) -> None:
    spotify = adapter(fake)
    spotify.execute(CONFIG, SECRETS, {"action": "spotify_volume", "volume": 35}, timeout=TIMEOUT)
    spotify.execute(CONFIG, SECRETS, {"action": "spotify_pause"}, timeout=TIMEOUT)
    paths = [r["path"] for r in fake.player()]
    assert paths == ["/v1/me/player/volume?volume_percent=35", "/v1/me/player/pause"]


def test_the_access_token_is_cached_and_renewed(fake: FakeSpotify) -> None:
    clock = [0.0]
    spotify = adapter(fake, monotonic=lambda: clock[0])
    pause = {"action": "spotify_pause"}
    spotify.execute(CONFIG, SECRETS, pause, timeout=TIMEOUT)
    spotify.execute(CONFIG, SECRETS, pause, timeout=TIMEOUT)
    assert sum(r["method"] == "POST" for r in fake.requests) == 1
    clock[0] = 3600.0  # expired (minus the safety margin)
    spotify.execute(CONFIG, SECRETS, pause, timeout=TIMEOUT)
    assert sum(r["method"] == "POST" for r in fake.requests) == 2


def test_not_paired_is_explained(fake: FakeSpotify) -> None:
    with pytest.raises(IntegrationError, match="not paired"):
        adapter(fake).execute(CONFIG, {}, {"action": "spotify_pause"}, timeout=TIMEOUT)


@pytest.mark.parametrize(
    ("status", "fragment"),
    [(401, "erneut koppeln"), (403, "Premium"), (404, "aktives Gerät"), (500, "Code 500")],
)
def test_player_errors_are_translated(fake: FakeSpotify, status: int, fragment: str) -> None:
    fake.player_status = status
    with pytest.raises(IntegrationError) as caught:
        adapter(fake).execute(CONFIG, SECRETS, {"action": "spotify_pause"}, timeout=TIMEOUT)
    assert fragment in caught.value.user_message
    assert not isinstance(caught.value, IntegrationConnectionError)  # not retried blindly


def test_rate_limit_is_retryable(fake: FakeSpotify) -> None:
    fake.player_status = 429
    with pytest.raises(IntegrationConnectionError) as caught:
        adapter(fake).execute(CONFIG, SECRETS, {"action": "spotify_pause"}, timeout=TIMEOUT)
    assert "3 s" in caught.value.user_message


def test_a_rejected_refresh_asks_to_pair_again(fake: FakeSpotify) -> None:
    fake.token_answer = (400, {"error": "invalid_grant"})
    with pytest.raises(IntegrationError) as caught:
        adapter(fake).check(CONFIG, SECRETS, timeout=TIMEOUT)
    assert "koppeln" in caught.value.user_message
    assert "refresh-abc" not in str(caught.value)


# --------------------------------------------------------------------------- pairing


def browser_that(visit: Any) -> Any:
    """An ``open_browser`` replacement that calls ``visit(query, redirect)`` in a thread."""

    def open_browser(url: str) -> bool:
        query = parse_qs(urlsplit(url).query)
        threading.Thread(target=visit, args=(query,), daemon=True).start()
        return True

    return open_browser


def test_pairing_stores_the_refresh_token(fake: FakeSpotify) -> None:
    port = free_port()
    seen: dict[str, Any] = {}

    def visit(query: dict[str, list[str]]) -> None:
        seen.update(query)
        redirect = query["redirect_uri"][0]
        urllib.request.urlopen(
            f"{redirect}?code=the-code&state={query['state'][0]}", timeout=5
        ).read()

    spotify = adapter(fake, open_browser=browser_that(visit), pair_seconds=10)
    result = spotify.pair({**CONFIG, "callback_port": port}, timeout=TIMEOUT)
    assert result.secrets == {"refresh_token": "refresh-new"}
    assert seen["code_challenge_method"] == ["S256"]
    assert seen["redirect_uri"] == [f"http://127.0.0.1:{port}/callback"]
    assert "user-modify-playback-state" in seen["scope"][0]
    exchange = fake.requests[0]["body"]
    assert "grant_type=authorization_code" in exchange and "code=the-code" in exchange
    # the verifier belongs to the challenge that was sent
    verifier = parse_qs(exchange)["code_verifier"][0]
    assert _challenge(verifier) == seen["code_challenge"][0]


def test_a_wrong_state_does_not_complete_the_pairing(fake: FakeSpotify) -> None:
    port = free_port()
    answers: list[int] = []

    def visit(query: dict[str, list[str]]) -> None:
        redirect = query["redirect_uri"][0]
        try:
            urllib.request.urlopen(f"{redirect}?code=evil&state=wrong", timeout=5)
        except urllib.error.HTTPError as exc:
            answers.append(exc.code)

    spotify = adapter(fake, open_browser=browser_that(visit), pair_seconds=1.5)
    with pytest.raises(IntegrationError, match="timed out"):
        spotify.pair({**CONFIG, "callback_port": port}, timeout=TIMEOUT)
    assert answers == [400]
    assert not any(r["method"] == "POST" for r in fake.requests)  # nothing was exchanged


def test_declined_authorisation(fake: FakeSpotify) -> None:
    port = free_port()

    def visit(query: dict[str, list[str]]) -> None:
        redirect = query["redirect_uri"][0]
        urllib.request.urlopen(
            f"{redirect}?error=access_denied&state={query['state'][0]}", timeout=5
        ).read()

    spotify = adapter(fake, open_browser=browser_that(visit), pair_seconds=10)
    with pytest.raises(IntegrationError, match="refused"):
        spotify.pair({**CONFIG, "callback_port": port}, timeout=TIMEOUT)


def test_busy_port_and_missing_client_id(fake: FakeSpotify) -> None:
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        port = blocker.getsockname()[1]
        with pytest.raises(IntegrationError, match="Cannot listen"):
            adapter(fake).pair({**CONFIG, "callback_port": port}, timeout=TIMEOUT)
    with pytest.raises(IntegrationError, match="client id"):
        adapter(fake).pair({}, timeout=TIMEOUT)
