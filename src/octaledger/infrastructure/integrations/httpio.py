"""Shared HTTP helper of the adapters that talk to a web interface (webhook, Home Assistant).

Responsibility
--------------
One place decides how an HTTP request is made and, above all, **how a failure is classified**,
because the retry rule depends on it:

* the request **certainly did not arrive** (cannot connect, name not found, timeout while
  connecting) -> :class:`~octaledger.core.errors.IntegrationConnectionError`, which the queue
  retries;
* anything else that goes wrong (a connection broken half-way, a timeout *after* sending) ->
  :class:`~octaledger.core.errors.IntegrationError`, which is **not** retried, because the
  action may already have happened.

Safe defaults for every adapter that uses it: redirects are never followed, environment proxies
are ignored (a request into the user's own network must not silently travel through a proxy),
every call has a timeout, and the answer body is only read where an adapter asks for it, and
then with a size limit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Final
from urllib.parse import urlsplit

import requests
from requests import Response, Session
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ConnectTimeout, ReadTimeout, RequestException
from urllib3.exceptions import (
    ConnectTimeoutError,
    MaxRetryError,
    NameResolutionError,
    NewConnectionError,
)

from octaledger.core.errors import IntegrationConnectionError, IntegrationError, ValidationError

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

#: Largest answer body an adapter may read (for example a list of lights).
MAX_BODY_BYTES: Final = 4 * 1024 * 1024


def new_session() -> Session:
    """A plain session that ignores proxies and cookies from the environment."""
    session = requests.Session()
    session.trust_env = False
    return session


def not_sent(exc: RequestsConnectionError) -> bool:
    """Whether a connection error happened *before* anything was sent to the target."""
    reason = exc.args[0] if exc.args else None
    if isinstance(reason, MaxRetryError):
        reason = reason.reason
    return isinstance(reason, NewConnectionError | NameResolutionError | ConnectTimeoutError)


def send(
    session_factory: SessionFactory,
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    data: bytes | None,
    timeout: float,
    verify: bool,
) -> Response:
    """Send one request and return the (unread) response; classify failures for the retry rule.

    Raises:
        IntegrationConnectionError: The request certainly did not arrive (retried).
        IntegrationError: Any other failure (not retried).
    """
    session = session_factory()
    try:
        return session.request(
            method,
            url,
            data=data,
            headers=dict(headers),
            timeout=(timeout, timeout),
            allow_redirects=False,
            verify=verify,
            stream=True,  # the answer body is not read unless the adapter asks for it
        )
    except RequestsConnectionError as exc:
        if not_sent(exc):
            raise IntegrationConnectionError(
                "Cannot connect to the target",
                user_message="Das Ziel ist nicht erreichbar. Bitte Adresse, Netzwerk und "
                "Gerät prüfen.",
            ) from exc
        raise IntegrationError(
            "Connection broke while talking to the target",
            user_message="Die Verbindung brach ab. Die Aktion wurde möglicherweise ausgeführt.",
        ) from exc
    except ConnectTimeout as exc:
        raise IntegrationConnectionError(
            "Connect timeout",
            user_message="Das Ziel antwortet nicht (Zeitlimit beim Verbinden).",
        ) from exc
    except ReadTimeout as exc:
        raise IntegrationError(
            "Read timeout after sending",
            user_message="Das Ziel hat nicht rechtzeitig geantwortet. Die Aktion wurde "
            "möglicherweise ausgeführt und wird nicht wiederholt.",
        ) from exc
    except RequestException as exc:
        logger.warning("HTTP request failed: %s", type(exc).__name__)
        raise IntegrationError(
            f"Request failed: {type(exc).__name__}",
            user_message="Die Anfrage konnte nicht gesendet werden. Bitte die Adresse prüfen.",
        ) from exc
    finally:
        session.close()


def read_limited(response: Response, limit: int = MAX_BODY_BYTES) -> bytes:
    """Read at most ``limit`` bytes of the answer body.

    Raises:
        IntegrationError: If the answer is larger than ``limit``.
    """
    data = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        data += chunk
        if len(data) > limit:
            response.close()
            raise IntegrationError(
                "Answer too large",
                user_message="Die Antwort des Ziels ist unerwartet groß und wurde verworfen.",
            )
    return bytes(data)


def check_base_url(value: str) -> str:
    """Accept only ``http(s)://host[:port][/prefix]`` without credentials, query or fragment.

    Returns the address without a trailing slash.

    Raises:
        ValidationError: With a German message for anything else.
    """
    parts = urlsplit(value)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValidationError(
            f"Invalid base address {value!r}",
            user_message="Die Basisadresse muss mit http:// oder https:// beginnen und darf weder "
            "Benutzername noch Abfrage-Teil enthalten.",
            details={"field": "base_url"},
        )
    try:
        _ = parts.port  # raises ValueError for an out-of-range port
    except ValueError:
        raise ValidationError(
            f"Invalid port in {value!r}",
            user_message="Die Basisadresse enthält einen ungültigen Port.",
            details={"field": "base_url"},
        ) from None
    return value.rstrip("/")
