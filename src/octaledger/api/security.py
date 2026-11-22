"""Token, host and origin validation before enabling the server.

Threat model (MVP)
------------------
The API listens on the loopback interface only, but that alone is not enough:

* Any other program of the same user, and *any web page open in the browser*, can send
  requests to ``127.0.0.1`` (CSRF, "DNS rebinding"). A **secret token** therefore protects all
  routes with side effects or personal data.
* **Host header** validation defeats DNS rebinding (an attacker's hostname resolving to
  127.0.0.1 would carry a foreign ``Host``).
* **Origin header** validation rejects browser requests coming from foreign sites. The
  dashboard calls the API from the Streamlit *server* (no ``Origin`` header), so a request
  that does carry a non-loopback ``Origin`` is browser traffic from somewhere else.

Rules (``CLAUDE.md`` / Pflichtenheft section 8)
-----------------------------------------------
* The token travels only in the ``Authorization: Bearer`` header - **never** in URLs - and is
  compared in constant time. It is registered with the log redaction so it can never appear in
  a log file.
* State changes never happen through ``GET`` (enforced in the route definitions).
* The token file is created once with random content (256 bit) in the user's data folder, never
  in the repository. On Windows file permissions are inherited from the user profile folder;
  POSIX permissions (0600) are set on a best-effort basis.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from octaledger.core.errors import AuthenticationError, ConfigurationError, ForbiddenOriginError
from octaledger.core.fileio import atomic_write_text, read_text_limited
from octaledger.core.logging import register_secret

logger = logging.getLogger(__name__)

TOKEN_FILE_NAME: Final = "api_token"  # noqa: S105 - a file name, not a secret
ENV_TOKEN: Final = "OCTALEDGER_API_TOKEN"  # noqa: S105 - an environment variable name
#: Minimum accepted token length (a generated token has 43 characters / 256 bit).
MIN_TOKEN_LENGTH: Final = 32
MAX_TOKEN_LENGTH: Final = 256
_TOKEN_CHARS = re.compile(r"^[A-Za-z0-9_\-.~+/=]+$")
#: Host names that are accepted for the ``Host`` and ``Origin`` headers.
LOOPBACK_NAMES: Final = frozenset({"127.0.0.1", "localhost", "[::1]", "::1"})


def generate_token() -> str:
    """Return a new random URL-safe token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def validate_token_format(token: str) -> str:
    """Check that ``token`` is long enough and uses only safe characters.

    Raises:
        ConfigurationError: If the token is too short, too long or has unusual characters.
    """
    if not MIN_TOKEN_LENGTH <= len(token) <= MAX_TOKEN_LENGTH or not _TOKEN_CHARS.match(token):
        raise ConfigurationError(
            "API token has an invalid format",
            user_message=(
                f"Das API-Token ist ungültig (mindestens {MIN_TOKEN_LENGTH} Zeichen aus "
                "Buchstaben, Ziffern und - _ . ~ + / =). Löschen Sie die Token-Datei, um ein "
                "neues Token zu erzeugen."
            ),
        )
    return token


def load_or_create_token(path: Path, environ: Mapping[str, str] | None = None) -> str:
    """Return the API token: environment override, else file, else create a new one.

    The token is registered with the log redaction in every case.

    Args:
        path: Token file (inside the user's data folder).
        environ: Environment mapping (defaults to ``os.environ``).

    Raises:
        ConfigurationError: If an existing token is malformed or the file cannot be read.
        StorageError: If a new token cannot be written.
    """
    env = os.environ if environ is None else environ
    from_env = env.get(ENV_TOKEN, "").strip()
    if from_env:
        token = validate_token_format(from_env)
        logger.info("Using API token from environment variable")
    elif path.exists():
        token = validate_token_format(
            read_text_limited(path, max_bytes=1024, error_cls=ConfigurationError).strip()
        )
        logger.info("Loaded API token from %s", path.name)
    else:
        token = generate_token()
        atomic_write_text(path, token + "\n")
        try:
            path.chmod(0o600)  # effective on POSIX; Windows keeps the profile folder's ACL
        except OSError:
            logger.debug("Could not restrict permissions of %s", path.name)
        logger.info("Created a new API token file %s", path.name)
    register_secret(token)
    return token


def parse_bearer(header: str | None) -> str | None:
    """Extract the token from an ``Authorization: Bearer <token>`` header (or ``None``)."""
    if not header:
        return None
    scheme, _, value = header.strip().partition(" ")
    return value.strip() or None if scheme.lower() == "bearer" else None


def verify_token(provided: str | None, expected: str) -> None:
    """Compare tokens in constant time.

    Raises:
        AuthenticationError: If ``provided`` is missing or wrong (the message never reveals
            which of the two).
    """
    if provided is None or not hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise AuthenticationError(
            "Missing or invalid API token",
            user_message=(
                "Die Anmeldung an der lokalen Schnittstelle ist fehlgeschlagen. Starten Sie "
                "Agent und Dashboard mit demselben Token."
            ),
        )


def is_allowed_host(host_header: str | None, port: int) -> bool:
    """Whether the ``Host`` header names a loopback address on exactly the API port.

    ``127.0.0.1:8765``, ``localhost:8765`` and ``[::1]:8765`` are accepted for port 8765.
    A header without port is rejected because the API never runs on the default port 80.
    """
    if not host_header:
        return False
    value = host_header.strip().lower()
    if value.startswith("["):  # IPv6 literal such as "[::1]:8765"
        closing = value.find("]")
        if closing == -1:
            return False
        host, rest = value[: closing + 1], value[closing + 1 :]
        if not rest.startswith(":"):
            return False
        host_port = rest[1:]
    else:
        host, separator, host_port = value.partition(":")
        if not separator:
            return False
    return host in LOOPBACK_NAMES and host_port == str(port)


def is_allowed_origin(origin: str | None) -> bool:
    """Whether the ``Origin`` header is absent or names a loopback address.

    A missing header is accepted (non-browser clients such as the dashboard's server-side
    requests); the literal ``null`` and any foreign site are rejected.
    """
    if origin is None:
        return True
    try:
        parts = urlsplit(origin.strip())
        port_ok = parts.port is None or 0 < parts.port < 65536  # raises ValueError if absurd
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return (
        parts.scheme in ("http", "https") and port_ok and host in {"127.0.0.1", "localhost", "::1"}
    )


def check_request_origin(host_header: str | None, origin: str | None, port: int) -> None:
    """Reject requests with a foreign ``Host`` or ``Origin``.

    Raises:
        ForbiddenOriginError: If the request does not come from a loopback context.
    """
    if not is_allowed_host(host_header, port):
        raise ForbiddenOriginError(
            "Request rejected: unexpected Host header", details={"reason": "host"}
        )
    if not is_allowed_origin(origin):
        raise ForbiddenOriginError(
            "Request rejected: foreign Origin header", details={"reason": "origin"}
        )
