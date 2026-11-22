"""Spotify adapter: play, pause and set the volume on a Spotify Connect device (Premium).

Responsibility
--------------
* Talks to the **Spotify Web API** (``api.spotify.com``) on behalf of the user. Spotify does not
  stream audio to OctaLedger; it *remote controls* a Spotify app or speaker the user already has
  (the "Connect device"). A **Premium** account is required by Spotify for this.
* One-time **pairing** with the *Authorization Code flow with PKCE* (no client secret is stored,
  none exists): OctaLedger opens the Spotify login in the browser, listens on
  ``http://127.0.0.1:<port>/callback`` for the answer, checks the one-time ``state`` and trades the
  code for a **refresh token** (kept in the secret store, never in settings, backups or logs).
* Every request first obtains a short-lived **access token** from the refresh token (cached in
  memory until shortly before it expires).

Safety rules
------------
* The listener binds to the loopback address only and accepts exactly one callback with the right
  ``state``; it is closed after pairing, after the time limit or on any failure.
* Only ``https`` addresses of Spotify are used (the bases are replaceable for tests only);
  redirects are never followed.
* Only ``spotify:`` sources are accepted. Spotify has no "stop"; stopping is **pause**.

Honest limits: verified against a local fake of the documented endpoints only. Whether it works
with your account, app registration and device is **not verified**; Spotify may change its
rules (for example for new apps) at any time.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets as token_source
import threading
import time
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Final
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from octaledger.core.errors import IntegrationConnectionError, IntegrationError, ValidationError
from octaledger.domain.music_source import MusicSource, SourceKind
from octaledger.infrastructure.integrations.base import (
    ActionSpec,
    Adapter,
    AdapterSpec,
    FieldSpec,
    PairResult,
)
from octaledger.infrastructure.integrations.httpio import (
    SessionFactory,
    new_session,
    read_limited,
    send,
)

logger = logging.getLogger(__name__)

API_BASE: Final = "https://api.spotify.com"
ACCOUNTS_BASE: Final = "https://accounts.spotify.com"
SCOPES: Final = "user-modify-playback-state user-read-playback-state"
DEFAULT_PORT: Final = 8898
#: Seconds the user has to finish the login in the browser.
PAIR_SECONDS: Final = 120.0
#: An access token is renewed this many seconds before it expires.
TOKEN_MARGIN: Final = 60.0

SETUP_GUIDE: Final = """\
**Wofür:** Steuert Spotify (Wiedergabe, Pause, Lautstärke) auf einem Gerät, das Sie ohnehin haben –
Handy-App, Desktop-App oder Lautsprecher mit Spotify Connect. Dafür braucht Spotify ein **Premium-Konto**.

**Einmalig bei Spotify einrichten:**
1. Öffnen Sie **developer.spotify.com/dashboard** und melden Sie sich an.
2. **Create app** wählen, einen Namen vergeben. Bei **Redirect URI** tragen Sie genau diese Adresse ein
   (sie steht auch unten in der Verbindung): `http://127.0.0.1:8898/callback`
3. Bei „Which API/SDKs are you planning to use?“ **Web API** ankreuzen, speichern.
4. In der App unter **Settings** die **Client ID** kopieren und hier einfügen. Ein *Client Secret* wird **nicht** gebraucht.

**Dann hier:** Verbindung speichern → **Koppeln** drücken → im Browser bei Spotify zustimmen. Das Fenster
sagt danach „Gekoppelt“; Sie können es schließen.

**Wichtig:**
- Auf dem Zielgerät muss Spotify **gerade geöffnet** (oder kürzlich aktiv) sein, sonst meldet Spotify „kein aktives Gerät“.
- Die Spotify-Regeln für Entwickler-Apps ändern sich; ob es mit Ihrem Konto funktioniert, ist **nicht geprüft**.
- Ändert sich die Redirect-URI oder der Port, muss beides bei Spotify und hier gleich sein.
"""  # noqa: E501


@dataclass(slots=True)
class _Token:
    """An access token with its expiry on the monotonic clock."""

    value: str
    expires_at: float


@dataclass(slots=True)
class _Callback:
    """What the loopback listener received (filled by the handler thread)."""

    expected_state: str
    code: str | None = None
    error: str | None = None
    done: threading.Event = field(default_factory=threading.Event)


def _challenge(verifier: str) -> str:
    """The PKCE S256 challenge of a verifier (base64url without padding)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _page(text: str) -> bytes:
    """A tiny German answer page for the browser tab (the text is fixed, never user input)."""
    body = f"<!doctype html><meta charset=utf-8><title>OctaLedger</title><p>{text}</p>"
    return body.encode("utf-8")


def _make_handler(state: _Callback) -> type[BaseHTTPRequestHandler]:
    """Build the request handler class bound to one pairing attempt."""

    class Handler(BaseHTTPRequestHandler):
        """Accepts the single redirect of the Spotify login on ``/callback``."""

        def do_GET(self) -> None:
            """Check path and ``state``, then store the code or the refusal."""
            parts = urlsplit(self.path)
            if parts.path != "/callback":
                self._send(404, "Nicht gefunden.")
                return
            query = parse_qs(parts.query)
            if (query.get("state") or [""])[0] != state.expected_state:
                # A stranger (or a stale tab) must not complete or abort the pairing.
                self._send(400, "Ungültige Anfrage. Bitte das Koppeln in OctaLedger neu starten.")
                return
            if "error" in query:
                state.error = (query["error"] or ["unknown"])[0][:50]
                self._send(200, "Abgebrochen. Sie können dieses Fenster schließen.")
            else:
                state.code = (query.get("code") or [""])[0][:2000] or None
                self._send(200, "Gekoppelt. Sie können dieses Fenster schließen.")
            state.done.set()

        def _send(self, status: int, text: str) -> None:
            data = _page(text)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            """Stay silent: the request line contains the one-time code."""

    return Handler


class SpotifyAdapter(Adapter):
    """Remote control of Spotify via the Web API (see the module docstring)."""

    spec = AdapterSpec(
        kind="spotify",
        title="Spotify (direkt)",
        description=(
            "Startet Titel, Alben und Playlists auf Ihrem Spotify-Gerät, pausiert und stellt die "
            "Lautstärke ein. Braucht ein Spotify-Premium-Konto und eine eigene App bei Spotify."
        ),
        setup_guide=SETUP_GUIDE,
        can_pair=True,
        pair_help=(
            "Öffnet die Spotify-Anmeldung in Ihrem Browser. Stimmen Sie dort zu; OctaLedger "
            "wartet bis zu zwei Minuten. Es wird kein Passwort und kein Client Secret gespeichert."
        ),
        config_fields=(
            FieldSpec(
                "client_id",
                "Client ID",
                required=True,
                placeholder="32 Zeichen aus dem Spotify-Dashboard",
                help="Die Client ID Ihrer App auf developer.spotify.com/dashboard.",
            ),
            FieldSpec(
                "device_id",
                "Gerät (optional)",
                advanced=True,
                help="Die Spotify-Geräte-ID, falls immer dasselbe Gerät spielen soll. Leer = das "
                "gerade aktive Gerät.",
            ),
            FieldSpec(
                "callback_port",
                "Port der Rückmeldung",
                kind="int",
                advanced=True,
                default=DEFAULT_PORT,
                minimum=1024,
                maximum=65535,
                help="Über diesen lokalen Port kehrt die Spotify-Anmeldung zu OctaLedger zurück. "
                "Die Redirect URI bei Spotify muss http://127.0.0.1:<Port>/callback lauten. "
                "Voreinstellung: 8898.",
            ),
            FieldSpec(
                "refresh_token",
                "Zugriffsberechtigung",
                kind="password",
                advanced=True,
                help="Entsteht beim Koppeln automatisch; muss nicht eingegeben werden.",
            ),
        ),
        actions=(
            ActionSpec(
                "spotify_play",
                "Spotify abspielen",
                "Startet einen Spotify-Titel, ein Album, eine Playlist oder einen Künstler.",
                fields=(
                    FieldSpec(
                        "uri",
                        "Spotify-Verweis",
                        required=True,
                        placeholder="spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
                        help="Der Verweis (spotify:track:… usw.). Einfacher: im Musik-Modus den "
                        "Link einfügen.",
                    ),
                ),
                idempotent=True,
                capability="music",
            ),
            ActionSpec(
                "spotify_pause",
                "Spotify pausieren",
                "Hält die Wiedergabe an (Spotify kennt kein „Stopp“).",
                idempotent=True,
                capability="music",
            ),
            ActionSpec(
                "spotify_volume",
                "Spotify-Lautstärke",
                "Stellt die Lautstärke des Spotify-Geräts ein.",
                fields=(
                    FieldSpec(
                        "volume",
                        "Lautstärke in %",
                        kind="int",
                        required=True,
                        default=50,
                        minimum=0,
                        maximum=100,
                        help="0 bis 100 Prozent.",
                    ),
                ),
                idempotent=True,
                capability="music",
            ),
        ),
    )

    def __init__(
        self,
        *,
        api_base: str = API_BASE,
        accounts_base: str = ACCOUNTS_BASE,
        session_factory: SessionFactory = new_session,
        open_browser: Callable[[str], object] = webbrowser.open,
        pair_seconds: float = PAIR_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create the adapter.

        Args:
            api_base / accounts_base: Replaceable only for tests against a local fake.
            session_factory: Builds the HTTP session.
            open_browser: Opens the login address (replaceable for tests).
            pair_seconds: How long pairing waits for the browser.
            monotonic: Clock for token expiry (replaceable for tests).
        """
        self._api = api_base.rstrip("/")
        self._accounts = accounts_base.rstrip("/")
        self._session_factory = session_factory
        self._open_browser = open_browser
        self._pair_seconds = pair_seconds
        self._monotonic = monotonic
        self._tokens: dict[str, _Token] = {}
        self._lock = threading.Lock()

    # ----------------------------------------------------------------------- music

    def music_play_params(
        self, source: MusicSource, volume: int, options: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        """Volume first, then the title (Spotify sources only)."""
        if source.kind is not SourceKind.SPOTIFY:
            raise ValidationError(
                "Spotify plays only Spotify sources",
                user_message="Spotify spielt nur Spotify-Links. Für YouTube oder Streams nehmen "
                "Sie den Lokalen Player, Home Assistant oder den Player in der App.",
            )
        return [
            {"action": "spotify_volume", "volume": volume},
            {"action": "spotify_play", "uri": f"spotify:{source.ref}"},
        ]

    def music_stop_params(
        self, play_params: Mapping[str, Any], pause: bool = False
    ) -> dict[str, Any] | None:
        """Spotify can only pause, so stop and pause are the same action."""
        return {"action": "spotify_pause"}

    # ------------------------------------------------------------------ operations

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """Obtain an access token and read the profile name (no side effects)."""
        token = self._access_token(config, secrets, timeout)
        body = self._call("GET", f"{self._api}/v1/me", token, None, timeout, expect_body=True)
        try:
            name = str(json.loads(body).get("display_name") or "").strip()
        except (ValueError, AttributeError):
            name = ""
        return "Spotify ist erreichbar" + (f" (Konto: {name})." if name else ".")

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Run one action on the chosen (or active) device."""
        token = self._access_token(config, secrets, timeout)
        device = str(config.get("device_id") or "")
        action = str(params.get("action"))
        if action == "spotify_volume":
            query = {"volume_percent": str(int(params["volume"]))}
            self._call(
                "PUT", self._url("/v1/me/player/volume", query, device), token, None, timeout
            )
            return "Spotify-Lautstärke gesetzt."
        if action == "spotify_pause":
            self._call("PUT", self._url("/v1/me/player/pause", {}, device), token, None, timeout)
            return "Spotify pausiert."
        if action == "spotify_play":
            body = json.dumps(_play_body(str(params["uri"]))).encode()
            self._call("PUT", self._url("/v1/me/player/play", {}, device), token, body, timeout)
            return "Spotify spielt."
        raise IntegrationError(
            f"Unknown Spotify action {action!r}",
            user_message="Diese Aktion kennt Spotify nicht.",
        )

    # --------------------------------------------------------------------- pairing

    def pair(self, config: Mapping[str, Any], *, timeout: float) -> PairResult:
        """Authorise OctaLedger with PKCE through the browser (see the module docstring).

        Raises:
            IntegrationError: If the port is busy, the user declines or the time runs out, or
                Spotify rejects the code.
        """
        del timeout  # the browser round trip has its own, longer limit
        client_id = str(config.get("client_id") or "").strip()
        if not client_id:
            raise IntegrationError(
                "Missing client id",
                user_message="Bitte zuerst die Client ID aus dem Spotify-Dashboard eintragen und "
                "speichern.",
            )
        port = int(config.get("callback_port") or DEFAULT_PORT)
        redirect = f"http://127.0.0.1:{port}/callback"
        verifier = token_source.token_urlsafe(64)[:96]
        state = _Callback(expected_state=token_source.token_urlsafe(24))
        try:
            server = HTTPServer(("127.0.0.1", port), _make_handler(state))
        except OSError as exc:
            raise IntegrationError(
                f"Cannot listen on port {port}",
                user_message=f"Der lokale Port {port} ist belegt. Wählen Sie unter „Erweiterte "
                "Einstellungen“ einen anderen Port (und tragen Sie die Redirect URI bei Spotify "
                "entsprechend ein).",
            ) from exc
        server.timeout = 0.2
        query = urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect,
                "scope": SCOPES,
                "state": state.expected_state,
                "code_challenge_method": "S256",
                "code_challenge": _challenge(verifier),
            },
            quote_via=quote,
        )
        try:
            self._open_browser(f"{self._accounts}/authorize?{query}")
            deadline = self._monotonic() + self._pair_seconds
            while not state.done.is_set() and self._monotonic() < deadline:
                server.handle_request()  # returns after at most ``server.timeout``
        finally:
            server.server_close()
        if state.error:
            raise IntegrationError(
                f"Spotify authorisation refused: {state.error}",
                user_message="Die Zustimmung bei Spotify wurde abgebrochen oder abgelehnt.",
            )
        if not state.code:
            raise IntegrationError(
                "Spotify authorisation timed out",
                user_message="Es kam keine Antwort von Spotify. Drücken Sie „Koppeln“ erneut und "
                "stimmen Sie im Browser innerhalb von zwei Minuten zu. Prüfen Sie, dass die "
                f"Redirect URI bei Spotify genau {redirect} lautet.",
            )
        reply = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": state.code,
                "redirect_uri": redirect,
                "client_id": client_id,
                "code_verifier": verifier,
            },
            timeout=20.0,
        )
        refresh = str(reply.get("refresh_token") or "")
        if not refresh:
            raise IntegrationError(
                "No refresh token in the answer",
                user_message="Spotify hat keine dauerhafte Berechtigung geliefert. Bitte erneut "
                "koppeln.",
            )
        logger.info("Spotify paired")
        return PairResult(secrets={"refresh_token": refresh}, message="Mit Spotify gekoppelt.")

    # --------------------------------------------------------------------- helpers

    def _url(self, path: str, query: dict[str, str], device: str) -> str:
        full = dict(query)
        if device:
            full["device_id"] = device
        return f"{self._api}{path}" + (f"?{urlencode(full)}" if full else "")

    def _access_token(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], timeout: float
    ) -> str:
        refresh = secrets.get("refresh_token", "")
        client_id = str(config.get("client_id") or "")
        if not refresh or not client_id:
            raise IntegrationError(
                "Spotify is not paired",
                user_message="Spotify ist noch nicht gekoppelt. Drücken Sie auf der Seite der "
                "Verbindung „Koppeln“.",
            )
        with self._lock:
            cached = self._tokens.get(refresh)
            if cached and self._monotonic() < cached.expires_at - TOKEN_MARGIN:
                return cached.value
            reply = self._token_request(
                {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id},
                timeout=timeout,
            )
            value = str(reply.get("access_token") or "")
            if not value:
                raise IntegrationError(
                    "No access token in the answer",
                    user_message="Spotify hat keinen Zugang geliefert. Bitte erneut koppeln.",
                )
            lifetime = float(reply.get("expires_in") or 3600)
            self._tokens[refresh] = _Token(value, self._monotonic() + lifetime)
            return value

    def _token_request(self, form: dict[str, str], *, timeout: float) -> dict[str, Any]:
        response = send(
            self._session_factory,
            "POST",
            f"{self._accounts}/api/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urlencode(form).encode(),
            timeout=timeout,
            verify=True,
        )
        status = response.status_code
        raw = read_limited(response)
        if status != 200:
            logger.warning("Spotify token request answered %s", status)
            raise IntegrationError(
                f"Spotify token request failed: {status}",
                user_message="Spotify hat die Anmeldung abgelehnt. Bitte Client ID prüfen und "
                "erneut koppeln (die Berechtigung kann widerrufen worden sein).",
            )
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise IntegrationError(
                "Unreadable token answer", user_message="Spotify hat unverständlich geantwortet."
            )
        return data

    def _call(
        self,
        method: str,
        url: str,
        token: str,
        body: bytes | None,
        timeout: float,
        *,
        expect_body: bool = False,
    ) -> bytes:
        headers = {"Authorization": f"Bearer {token}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        response = send(
            self._session_factory,
            method,
            url,
            headers=headers,
            data=body if body is not None else (b"" if method == "PUT" else None),
            timeout=timeout,
            verify=True,
        )
        status = response.status_code
        retry_after = response.headers.get("Retry-After", "")
        raw = read_limited(response) if expect_body and status < 300 else b""
        response.close()
        if status < 300:
            return raw
        self._raise_for_status(status, retry_after)
        return raw  # unreachable; keeps the type checker calm

    @staticmethod
    def _raise_for_status(status: int, retry_after: str) -> None:
        if status == 429:
            # Not executed: Spotify asks to slow down, so a later retry is safe.
            raise IntegrationConnectionError(
                "Spotify rate limit",
                user_message="Spotify bittet, langsamer zu senden"
                + (f" (in {retry_after} s wieder)." if retry_after.isdigit() else "."),
            )
        messages = {
            401: "Spotify hat den Zugang abgelehnt. Bitte erneut koppeln.",
            403: "Spotify erlaubt das nicht. Ein Premium-Konto ist nötig, und die App braucht die "
            "Zustimmung (erneut koppeln).",
            404: "Spotify findet kein aktives Gerät. Öffnen Sie Spotify auf Ihrem Gerät und "
            "starten Sie dort kurz etwas.",
        }
        raise IntegrationError(
            f"Spotify answered {status}",
            user_message=messages.get(status, f"Spotify meldet einen Fehler (Code {status})."),
        )


def _play_body(uri: str) -> dict[str, Any]:
    """The play request body: tracks and episodes go as ``uris``, everything else as context."""
    kind = uri.split(":")[1] if uri.count(":") == 2 else ""
    if kind in ("track", "episode"):
        return {"uris": [uri]}
    return {"context_uri": uri}
