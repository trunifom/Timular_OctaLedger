"""MQTT adapter: publish a message to a broker (MQTT 3.1.1, publish only).

MQTT is the standard of the smart home: Mosquitto, Home Assistant, Node-RED, Zigbee2MQTT, Tasmota
and ESPHome all speak it. A turn of the cube becomes one **published message** (a topic and a
payload), for example ``zigbee2mqtt/desk-lamp/set`` with ``{"state": "TOGGLE"}``.

Why this module speaks the protocol itself
------------------------------------------
Only a *publisher* is needed: connect, send one PUBLISH, disconnect. That is a few dozen bytes of a
simple, fully specified protocol, and writing it here (standard library only) gives exactly what
the action queue needs and a generic client library does not:

* a **hard timeout** on every step (connecting included), and
* an exact answer to "did the message certainly *not* go out?" - the basis of the retry rule.

No new dependency, no background thread, nothing is left connected between two actions.

Retry rule
----------
Failing to connect (refused, unreachable, name not found, timeout while connecting, TLS
handshake) means nothing was sent: :class:`IntegrationConnectionError`, retried. A broker that
refuses the credentials is a permanent :class:`IntegrationError`. Anything that goes wrong *after*
the PUBLISH was written (no acknowledgement, connection closed) leaves the outcome unknown and is a
permanent :class:`IntegrationError`: repeating "TOGGLE" could switch the light twice.

Limits: MQTT 3.1.1 only, no subscribing, QoS 0 and 1 (QoS 2 adds nothing for a switch command),
no websockets, no client certificates, no persistent session, text payloads up to 500 characters.
Verified against a protocol-level fake broker, not against Mosquitto or a real hub.
"""

from __future__ import annotations

import logging
import secrets as _secrets
import socket
import ssl
import struct
from collections.abc import Callable, Mapping
from typing import Any, Final

from octaledger.core.errors import IntegrationConnectionError, IntegrationError, ValidationError
from octaledger.infrastructure.integrations.base import (
    ActionSpec,
    Adapter,
    AdapterSpec,
    FieldSpec,
)

logger = logging.getLogger(__name__)

PROTOCOL_NAME: Final = b"MQTT"
PROTOCOL_LEVEL: Final = 4  # MQTT 3.1.1
KEEP_ALIVE: Final = 15
PUBLISH_ID: Final = 1
#: Largest packet accepted from the broker (it only ever sends two-to-four byte replies).
MAX_REPLY_BYTES: Final = 1024

_CONNACK: Final = 0x20
_PUBACK: Final = 0x40
_CONNACK_PROBLEMS: Final = {
    1: "Der Broker unterstützt MQTT 3.1.1 nicht.",
    2: "Der Broker hat die Client-Kennung abgelehnt.",
    3: "Der Broker ist gerade nicht verfügbar.",
    4: "Benutzername oder Passwort sind falsch.",
    5: "Der Broker erlaubt diesem Benutzer den Zugriff nicht.",
}

SocketFactory = Callable[[str, int, float], socket.socket]
ContextFactory = Callable[[bool], ssl.SSLContext]


# ------------------------------------------------------------------ packet encoding


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    if len(raw) > 0xFFFF:
        raise ValidationError("MQTT string longer than 65535 bytes")
    return struct.pack("!H", len(raw)) + raw


def _remaining_length(length: int) -> bytes:
    """MQTT variable-length integer (7 bits per byte)."""
    encoded = bytearray()
    while True:
        byte, length = length % 128, length // 128
        encoded.append(byte | (0x80 if length else 0))
        if not length:
            return bytes(encoded)


def build_connect(client_id: str, username: str | None, password: str | None) -> bytes:
    """The CONNECT packet (clean session, keep-alive 15 s, optional user name and password)."""
    flags = 0x02  # clean session
    payload = _utf8(client_id)
    if username:
        flags |= 0x80
        payload += _utf8(username)
        if password:
            flags |= 0x40
            payload += _utf8(password)
    body = _utf8(PROTOCOL_NAME.decode()) + bytes([PROTOCOL_LEVEL, flags])
    body += struct.pack("!H", KEEP_ALIVE) + payload
    return b"\x10" + _remaining_length(len(body)) + body


def build_publish(topic: str, payload: bytes, *, qos: int, retain: bool) -> bytes:
    """The PUBLISH packet (packet identifier only for QoS 1)."""
    header = 0x30 | (qos << 1) | int(retain)
    body = _utf8(topic)
    if qos:
        body += struct.pack("!H", PUBLISH_ID)
    body += payload
    return bytes([header]) + _remaining_length(len(body)) + body


DISCONNECT: Final = b"\xe0\x00"


def read_packet(connection: socket.socket) -> tuple[int, bytes]:
    """Read one packet; returns ``(first byte, body)``. Bounded: nothing large is accepted."""
    first = _read_exactly(connection, 1)[0]
    length, shift = 0, 0
    for _ in range(4):
        byte = _read_exactly(connection, 1)[0]
        length |= (byte & 0x7F) << shift
        if not byte & 0x80:
            break
        shift += 7
    else:
        raise OSError("malformed MQTT length")
    if length > MAX_REPLY_BYTES:
        raise OSError("MQTT reply too large")
    return first, _read_exactly(connection, length) if length else b""


def _read_exactly(connection: socket.socket, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise ConnectionError("the broker closed the connection")
        data += chunk
    return bytes(data)


# ----------------------------------------------------------------------- transport


def _open(host: str, port: int, timeout: float) -> socket.socket:
    return socket.create_connection((host, port), timeout=timeout)


def _tls_context(verify: bool) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


SETUP_GUIDE: Final = """\
**Wofür:** Nachrichten an einen MQTT-Broker senden (Mosquitto, Zigbee2MQTT, Tasmota, ESPHome, Node-RED).

1. **Adresse des Brokers** eintragen (Name oder IP, ohne `mqtt://`), meist mit **Port 1883**.
2. **Benutzername und Passwort**: die Zugangsdaten **des Brokers** (nicht die eines Cloud-Kontos). Bei einem
   Mosquitto-Add-on in Home Assistant sind es ein Benutzer aus Home Assistant; ohne Anmeldung am Broker
   lassen Sie beide Felder leer.
3. **Verschlüsselung (TLS)** brauchen Sie nur, wenn der Broker es verlangt (meist Port **8883**): unter
   *Erweiterte Einstellungen* einschalten.
4. **Verbindung testen**, dann pro Würfelseite **Thema** und **Inhalt** festlegen.

**Beispiele**
- Zigbee2MQTT-Lampe: Thema `zigbee2mqtt/schreibtischlampe/set`, Inhalt `{"state": "ON"}`.
- Bevorzugen Sie `ON` und `OFF` vor `TOGGLE`: Umschalten wirkt bei jedem Senden erneut.
- Themen dürfen keine Platzhalter (`+`, `#`) enthalten und nicht mit `$` beginnen.
"""  # noqa: E501


class MqttAdapter(Adapter):
    """Publishes MQTT messages (see the module docstring)."""

    spec = AdapterSpec(
        kind="mqtt",
        title="MQTT (Broker)",
        description=(
            "Veröffentlicht eine Nachricht an einen MQTT-Broker, zum Beispiel Mosquitto. "
            "Der Standard des Smarthomes: Home Assistant, Zigbee2MQTT, Tasmota, ESPHome und "
            "Node-RED verstehen ihn."
        ),
        setup_guide=SETUP_GUIDE,
        config_fields=(
            FieldSpec(
                "host",
                "Adresse des Brokers",
                required=True,
                placeholder="192.168.1.10",
                help="Name oder IP-Adresse des MQTT-Brokers, ohne „mqtt://“.",
            ),
            FieldSpec(
                "port",
                "Port",
                kind="int",
                default=1883,
                minimum=1,
                maximum=65535,
                help="Meist 1883 (ohne Verschlüsselung) oder 8883 (mit TLS).",
            ),
            FieldSpec(
                "username",
                "Benutzername",
                help="Nur nötig, wenn der Broker eine Anmeldung verlangt.",
            ),
            FieldSpec(
                "password",
                "Passwort",
                kind="password",
                help="Gehört zum Benutzernamen. Wird getrennt und nie in Sicherungen gespeichert.",
            ),
            FieldSpec(
                "use_tls",
                "Verschlüsselt verbinden (TLS)",
                advanced=True,
                kind="bool",
                default=False,
                help="Für Port 8883 oder wenn der Broker TLS verlangt.",
            ),
            FieldSpec(
                "verify_tls",
                "Zertifikat prüfen",
                advanced=True,
                kind="bool",
                default=True,
                help="Bei TLS das Zertifikat des Brokers prüfen. Nur ausschalten bei einem selbst "
                "erzeugten Zertifikat.",
            ),
        ),
        actions=(
            ActionSpec(
                "publish",
                "Nachricht veröffentlichen",
                "Veröffentlicht eine Nachricht (Thema und Inhalt) beim Broker.",
                (
                    FieldSpec(
                        "topic",
                        "Thema",
                        required=True,
                        placeholder="zigbee2mqtt/schreibtischlampe/set",
                        help="Das MQTT-Thema. Keine Platzhalter („+“, „#“) und nicht mit „$“ "
                        "beginnen.",
                    ),
                    FieldSpec(
                        "payload",
                        "Inhalt",
                        placeholder='{"state": "TOGGLE"}',
                        help="Der Inhalt der Nachricht. Inhalte wie „TOGGLE“ schalten bei jedem "
                        "Senden erneut um; bevorzugen Sie „ON“ und „OFF“.",
                    ),
                    FieldSpec(
                        "qos",
                        "Zustellung (QoS)",
                        advanced=True,
                        kind="choice",
                        default="1",
                        choices=(
                            ("0", "0 – höchstens einmal, ohne Bestätigung"),
                            ("1", "1 – mit Bestätigung des Brokers"),
                        ),
                        help="Bei 1 wartet OctaLedger auf die Bestätigung des Brokers und meldet "
                        "sonst einen Fehler.",
                    ),
                    FieldSpec(
                        "retain",
                        "Nachricht behalten (retain)",
                        advanced=True,
                        kind="bool",
                        default=False,
                        help="Der Broker merkt sich die Nachricht für später verbindende "
                        "Teilnehmer. "
                        "Für Schalter meist aus.",
                    ),
                ),
            ),
        ),
    )

    def __init__(
        self,
        socket_factory: SocketFactory = _open,
        context_factory: ContextFactory = _tls_context,
    ) -> None:
        """Create the adapter (the factories are replaceable for tests)."""
        self._open = socket_factory
        self._context = context_factory

    # ------------------------------------------------------------------ validation

    def validate_config(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Check the settings; the host must be a plain name or address."""
        config = super().validate_config(values)
        host = config["host"]
        if "://" in host or "/" in host or " " in host:
            raise ValidationError(
                f"Invalid MQTT host {host!r}",
                user_message="Die Adresse des Brokers darf nur ein Name oder eine IP-Adresse sein "
                "(ohne „mqtt://“ und ohne Pfad).",
                details={"field": "host"},
            )
        config.setdefault("port", 1883)
        return config

    def validate_action(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Check the message: a concrete topic without wildcards or system prefix."""
        cleaned = super().validate_action(params)
        topic = str(cleaned["topic"])
        if "+" in topic or "#" in topic or topic.startswith("$") or "\x00" in topic:
            raise ValidationError(
                f"Invalid MQTT topic {topic!r}",
                user_message="Das Thema darf keine Platzhalter („+“, „#“) enthalten und nicht mit "
                "„$“ beginnen.",
                details={"field": "topic"},
            )
        cleaned.setdefault("payload", "")
        cleaned.setdefault("qos", "1")
        cleaned.setdefault("retain", False)
        return cleaned

    # ----------------------------------------------------------------- operations

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """Connect and log in, then disconnect without publishing anything."""
        connection = self._connect(config, secrets, timeout)
        try:
            connection.sendall(DISCONNECT)
        except OSError:
            logger.debug("Broker closed during the check", exc_info=True)
        finally:
            connection.close()
        return f"Verbunden mit dem Broker {config['host']}:{config.get('port', 1883)}."

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Publish one message; with QoS 1 wait for the broker's acknowledgement."""
        qos = int(params.get("qos", 1))
        packet = build_publish(
            str(params["topic"]),
            str(params.get("payload", "")).encode("utf-8"),
            qos=qos,
            retain=bool(params.get("retain", False)),
        )
        connection = self._connect(config, secrets, timeout)  # failures here: nothing was sent
        try:
            try:
                connection.sendall(packet)
                if qos == 1:
                    self._await_ack(connection)
                connection.sendall(DISCONNECT)
            except (OSError, ConnectionError) as exc:
                raise IntegrationError(
                    f"Publishing failed after sending: {type(exc).__name__}",
                    user_message="Der Broker hat die Nachricht nicht bestätigt. Sie wurde "
                    "möglicherweise zugestellt und wird nicht wiederholt.",
                ) from exc
        finally:
            connection.close()
        return "Nachricht veröffentlicht" + (" und bestätigt." if qos == 1 else ".")

    # -------------------------------------------------------------------- internals

    def _connect(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], timeout: float
    ) -> socket.socket:
        """Open the connection and log in. Every failure here means nothing was published."""
        host, port = str(config["host"]), int(config.get("port", 1883))
        try:
            raw = self._open(host, port, timeout)
        except OSError as exc:  # refused, unreachable, unknown name, timeout while connecting
            raise IntegrationConnectionError(
                f"Cannot connect to the broker: {type(exc).__name__}",
                user_message="Der Broker ist nicht erreichbar. Bitte Adresse, Port und "
                "Netzwerk prüfen.",
            ) from exc
        connection: socket.socket = raw
        try:
            raw.settimeout(timeout)
            if config.get("use_tls"):
                connection = self._context(bool(config.get("verify_tls", True))).wrap_socket(
                    raw, server_hostname=host
                )
            client_id = "octaledger-" + _secrets.token_hex(4)
            connection.sendall(
                build_connect(client_id, config.get("username") or None, secrets.get("password"))
            )
            kind, body = read_packet(connection)
            if kind != _CONNACK or len(body) != 2:
                raise IntegrationError(
                    "Unexpected answer to CONNECT",
                    user_message="Das Ziel antwortet nicht wie ein MQTT-Broker. Bitte Adresse und "
                    "Port prüfen.",
                )
            if body[1] != 0:
                raise IntegrationError(
                    f"The broker refused the connection (code {body[1]})",
                    user_message=_CONNACK_PROBLEMS.get(
                        body[1], "Der Broker hat die Anmeldung abgelehnt."
                    ),
                )
            return connection
        except ssl.SSLError as exc:
            connection.close()
            raise IntegrationError(
                f"TLS failed: {type(exc).__name__}",
                user_message="Die verschlüsselte Verbindung kam nicht zustande. Bitte Port und "
                "„Zertifikat prüfen“ kontrollieren.",
            ) from exc
        except IntegrationError:
            connection.close()
            raise
        except (OSError, ConnectionError) as exc:
            connection.close()
            raise IntegrationConnectionError(
                f"Login to the broker failed: {type(exc).__name__}",
                user_message="Der Broker hat die Anmeldung nicht beantwortet. Bitte Adresse und "
                "Port prüfen.",
            ) from exc

    @staticmethod
    def _await_ack(connection: socket.socket) -> None:
        kind, body = read_packet(connection)
        if kind != _PUBACK or body != struct.pack("!H", PUBLISH_ID):
            raise ConnectionError("unexpected acknowledgement")
