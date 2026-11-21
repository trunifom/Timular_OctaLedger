"""Safe media addresses: what a cube-triggered player or speaker may be pointed at.

A media address is typed by the user, but a wrong or malicious one must never make OctaLedger
reach into places a web address has no business in (server-side request forgery). The rules:

* only ``http`` and ``https``; no user name or password in the address; no spaces or control
  characters; a bounded length;
* the host is **resolved** and every resulting address is checked: loopback, link-local
  (169.254.0.0/16, fe80::/10), unspecified, multicast, reserved and the well-known cloud metadata
  addresses are always refused; **private home-network addresses** (192.168.x.x, 10.x.x.x,
  172.16-31.x.x) only when the user allowed them, because an internet radio on the home network
  is legitimate;
* redirects are never followed blindly: each hop is checked again (:func:`follow_redirects`).

Names are resolved at check time **and again** when the connection is made by the caller, who
should use :func:`resolve_checked` for the address it actually connects to (DNS can change in
between).
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Final
from urllib.parse import urlsplit

from octaledger.core.errors import ValidationError

MAX_URL_LENGTH: Final = 2000
MAX_REDIRECTS: Final = 3
#: Addresses that must never be reachable, even on a "LAN allowed" setting.
_METADATA: Final = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("169.254.170.2"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)

Resolver = Callable[[str, int], list[str]]


def _system_resolver(host: str, port: int) -> list[str]:
    """Resolve a name to its addresses with the operating system."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValidationError(
            f"Cannot resolve {host!r}",
            user_message=f"Der Name „{host}“ lässt sich nicht auflösen. Bitte die Adresse prüfen.",
        ) from exc
    return sorted({str(info[4][0]) for info in infos})


def _refuse(address: str, allow_lan: bool) -> str | None:
    """Return the German reason an address is refused, or ``None`` if it is fine."""
    ip = ipaddress.ip_address(address.split("%")[0])
    if ip in _METADATA:
        return "Die Adresse zeigt auf eine Verwaltungsschnittstelle (Metadaten)."
    if ip.is_loopback:
        return "Adressen dieses Computers („localhost“) sind nicht erlaubt."
    if ip.is_link_local:
        return "Verbindungslokale Adressen (169.254.x.x) sind nicht erlaubt."
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return "Diese Adresse ist nicht erlaubt."
    if ip.is_private and not allow_lan:
        return (
            "Adressen im Heimnetz sind ausgeschaltet. Schalten Sie „LAN-Adressen erlauben“ ein, "
            "wenn der Sender in Ihrem Netz steht."
        )
    return None


def check_media_url(
    url: str, *, allow_lan: bool = False, resolver: Resolver = _system_resolver
) -> str:
    """Validate a media address and return it unchanged.

    Raises:
        ValidationError: With a German explanation of what is wrong.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("Empty URL", user_message="Bitte eine Adresse eintragen.")
    url = url.strip()
    if len(url) > MAX_URL_LENGTH or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValidationError(
            "Invalid characters or length in URL",
            user_message="Die Adresse enthält Leerzeichen oder Sonderzeichen oder ist zu lang.",
        )
    try:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise ValidationError("Unparsable URL", user_message="Die Adresse ist ungültig.") from exc
    if parts.scheme not in ("http", "https"):
        raise ValidationError(
            f"Scheme {parts.scheme!r} not allowed",
            user_message="Die Adresse muss mit http:// oder https:// beginnen.",
        )
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValidationError(
            "Credentials in URL",
            user_message="Benutzername und Passwort gehören nicht in die Adresse.",
        )
    host = parts.hostname
    if not host:
        raise ValidationError("No host in URL", user_message="In der Adresse fehlt der Servername.")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = resolver(host, port)
    if not addresses:
        raise ValidationError(
            "Host resolves to nothing", user_message="Der Servername ergibt keine Adresse."
        )
    for address in addresses:
        reason = _refuse(address, allow_lan)
        if reason is not None:
            raise ValidationError(f"Address {address} refused: {reason}", user_message=reason)
    return url


def resolve_checked(
    url: str, *, allow_lan: bool = False, resolver: Resolver = _system_resolver
) -> list[str]:
    """Check ``url`` and return the addresses to connect to (check again right before use)."""
    check_media_url(url, allow_lan=allow_lan, resolver=resolver)
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        return resolver(host, port)


def follow_redirects(
    url: str,
    fetch_location: Callable[[str], str | None],
    *,
    allow_lan: bool = False,
    resolver: Resolver = _system_resolver,
) -> str:
    """Follow up to :data:`MAX_REDIRECTS` redirects, checking **every** hop.

    Args:
        url: The first address (checked).
        fetch_location: Returns the ``Location`` of a redirect answer for an address, or ``None``
            if the address answers with the content itself.
        allow_lan: Whether home-network addresses are allowed.
        resolver: Name resolution (replaceable for tests).

    Returns:
        The final address (checked), which answers with content.

    Raises:
        ValidationError: If a hop is refused or there are too many redirects.
    """
    current = check_media_url(url, allow_lan=allow_lan, resolver=resolver)
    for _ in range(MAX_REDIRECTS + 1):
        location = fetch_location(current)
        if location is None:
            return current
        current = check_media_url(location, allow_lan=allow_lan, resolver=resolver)
    raise ValidationError(
        "Too many redirects",
        user_message=f"Die Adresse leitet mehr als {MAX_REDIRECTS}-mal weiter und wird abgelehnt.",
    )
