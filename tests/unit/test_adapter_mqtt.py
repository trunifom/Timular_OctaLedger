"""Tests for the MQTT adapter against a protocol-level fake broker.

The fake broker parses the packets itself (independently of the adapter's encoder), so the two
check each other. It cannot prove behaviour with Mosquitto or a real hub.
"""

import socket
import ssl
import struct
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from octaledger.application.integration_service import IntegrationService
from octaledger.core.errors import (
    IntegrationConnectionError,
    IntegrationError,
    ValidationError,
)
from octaledger.core.logging import clear_registered_secrets
from octaledger.core.secrets import SecretStore
from octaledger.domain.models import IntegrationJob, JobStatus
from octaledger.infrastructure.integrations.mqtt import (
    MqttAdapter,
    _remaining_length,
    build_connect,
    build_publish,
)
from octaledger.infrastructure.integrations.registry import default_adapters
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

TIMEOUT = 2.0


# --------------------------------------------------------------------- the fake broker


def _read(connection: socket.socket, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise EOFError
        data += chunk
    return bytes(data)


def _packet(connection: socket.socket) -> tuple[int, bytes]:
    first = _read(connection, 1)[0]
    length, shift = 0, 0
    while True:
        byte = _read(connection, 1)[0]
        length |= (byte & 0x7F) << shift
        if not byte & 0x80:
            break
        shift += 7
    return first, _read(connection, length) if length else b""


def _string(data: bytes, offset: int) -> tuple[str, int]:
    (size,) = struct.unpack_from("!H", data, offset)
    return data[offset + 2 : offset + 2 + size].decode("utf-8"), offset + 2 + size


class Broker:
    """Accepts one connection at a time, records what it receives, misbehaves on request."""

    def __init__(self) -> None:
        self.connects: list[dict[str, Any]] = []
        self.publishes: list[dict[str, Any]] = []
        self.disconnects = 0
        self.connack_code = 0
        self.silent_on_connect = False
        self.garbage_on_connect = False
        self.hang_up_on_connect = False
        self.ack_mode = "ack"  # "ack", "none" (never answer) or "close" (hang up)
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(5)
        self.port = self.server.getsockname()[1]
        self._stop = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        self.server.settimeout(0.1)
        while not self._stop.is_set():
            try:
                connection, _ = self.server.accept()
            except (TimeoutError, OSError):
                continue
            threading.Thread(target=self._client, args=(connection,), daemon=True).start()

    def _client(self, connection: socket.socket) -> None:
        with connection:
            try:
                kind, body = _packet(connection)
                assert kind == 0x10
                name, offset = _string(body, 0)
                level, flags = body[offset], body[offset + 1]
                offset += 4  # level, flags, keep alive (2 bytes)
                client_id, offset = _string(body, offset)
                user = password = None
                if flags & 0x80:
                    user, offset = _string(body, offset)
                if flags & 0x40:
                    password, offset = _string(body, offset)
                self.connects.append(
                    {
                        "protocol": (name, level),
                        "clean": bool(flags & 0x02),
                        "client_id": client_id,
                        "user": user,
                        "password": password,
                    }
                )
                if self.silent_on_connect:
                    time.sleep(2.0)
                    return
                if self.hang_up_on_connect:
                    return
                if self.garbage_on_connect:
                    connection.sendall(b"\x30\x00")  # well-framed, but not a CONNACK
                    return
                connection.sendall(bytes([0x20, 0x02, 0x00, self.connack_code]))
                if self.connack_code:
                    return
                while True:
                    kind, body = _packet(connection)
                    if kind & 0xF0 == 0x30:
                        qos = (kind >> 1) & 0x03
                        topic, offset = _string(body, 0)
                        packet_id = None
                        if qos:
                            (packet_id,) = struct.unpack_from("!H", body, offset)
                            offset += 2
                        self.publishes.append(
                            {
                                "topic": topic,
                                "payload": body[offset:].decode("utf-8"),
                                "qos": qos,
                                "retain": bool(kind & 0x01),
                            }
                        )
                        if qos and self.ack_mode == "ack":
                            connection.sendall(bytes([0x40, 0x02]) + struct.pack("!H", packet_id))
                        elif qos and self.ack_mode == "close":
                            return
                    elif kind == 0xE0:
                        self.disconnects += 1
                        return
            except (EOFError, OSError, AssertionError):
                return

    def close(self) -> None:
        self._stop.set()
        self.server.close()


@pytest.fixture
def broker() -> Iterator[Broker]:
    instance = Broker()
    yield instance
    instance.close()


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear_registered_secrets()


def adapter() -> MqttAdapter:
    return MqttAdapter()


def config(broker: Broker, **extra: Any) -> dict[str, Any]:
    return adapter().validate_config({"host": "127.0.0.1", "port": broker.port, **extra})


def publish(**fields: Any) -> dict[str, Any]:
    return adapter().validate_action({"action": "publish", "topic": "licht/schreibtisch", **fields})


def wait_until(predicate: Any, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.01)


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


# ------------------------------------------------------------------------ encoding


@pytest.mark.parametrize(
    ("length", "encoded"),
    [
        (0, b"\x00"),
        (127, b"\x7f"),
        (128, b"\x80\x01"),
        (16383, b"\xff\x7f"),
        (16384, b"\x80\x80\x01"),
        (2097151, b"\xff\xff\x7f"),
        (2097152, b"\x80\x80\x80\x01"),
    ],
)
def test_the_variable_length_integer_matches_the_specification(length: int, encoded: bytes) -> None:
    assert _remaining_length(length) == encoded


def test_packets_match_hand_computed_bytes() -> None:
    assert build_connect("c", None, None) == bytes.fromhex("100d00044d5154540402000f000163")
    assert build_publish("a/b", b"hi", qos=0, retain=False) == bytes.fromhex("30070003612f626869")
    assert build_publish("a/b", b"hi", qos=1, retain=True) == bytes.fromhex(
        "330900036" + "12f620001" + "6869"
    )
    with_login = build_connect("c", "u", "p")
    assert with_login[9] == 0xC2 and with_login.endswith(
        b"\x00\x01u\x00\x01p"
    )  # user+password+clean


def test_a_password_without_a_user_name_is_not_sent() -> None:
    assert build_connect("c", None, "geheim")[9] == 0x02


# ----------------------------------------------------------------------- validation


def test_a_plain_host_and_the_default_port_are_accepted() -> None:
    cleaned = adapter().validate_config({"host": "mqtt.local"})
    assert (
        cleaned["host"] == "mqtt.local"
        and cleaned["port"] == 1883
        and cleaned["verify_tls"] is True
    )


@pytest.mark.parametrize("host", ["mqtt://broker", "broker/path", "bro ker", ""])
def test_a_host_with_scheme_or_path_is_rejected(host: str) -> None:
    with pytest.raises(ValidationError):
        adapter().validate_config({"host": host})


@pytest.mark.parametrize("port", [0, 70000, "abc"])
def test_invalid_ports_are_rejected(port: Any) -> None:
    with pytest.raises(ValidationError):
        adapter().validate_config({"host": "h", "port": port})


def test_the_password_is_a_secret_and_not_part_of_the_settings() -> None:
    cleaned = adapter().validate_config({"host": "h", "username": "u", "password": "geheim"})
    assert "password" not in cleaned and "geheim" not in repr(cleaned)


@pytest.mark.parametrize("topic", ["a/#", "a/+/b", "#", "$SYS/broker/uptime", "a\x00b", ""])
def test_topics_with_wildcards_system_prefix_or_nothing_are_rejected(topic: str) -> None:
    with pytest.raises(ValidationError):
        adapter().validate_action({"action": "publish", "topic": topic})


def test_message_defaults_and_choices() -> None:
    cleaned = publish()
    assert cleaned == {
        "action": "publish",
        "topic": "licht/schreibtisch",
        "qos": "1",
        "retain": False,
        "payload": "",
    }
    assert publish(qos="0", retain=True, payload="ON")["qos"] == "0"
    for bad in ({"qos": "2"}, {"zusatz": "x"}):
        with pytest.raises(ValidationError):
            publish(**bad)


# ----------------------------------------------------------------------- publishing


def test_a_message_reaches_the_broker_with_everything_as_configured(broker: Broker) -> None:
    message = adapter().execute(
        config(broker, username="anna"),
        {"password": "geheim-123"},
        publish(payload='{"state": "ON"} Grüße', retain=True),
        timeout=TIMEOUT,
    )
    (seen,) = broker.publishes
    assert seen == {
        "topic": "licht/schreibtisch",
        "payload": '{"state": "ON"} Grüße',
        "qos": 1,
        "retain": True,
    }
    (login,) = broker.connects
    assert login["protocol"] == ("MQTT", 4) and login["clean"] is True
    assert login["user"] == "anna" and login["password"] == "geheim-123"
    assert login["client_id"].startswith("octaledger-")
    assert "geheim-123" not in message and "bestätigt" in message
    time.sleep(0.1)
    assert broker.disconnects == 1  # nothing stays connected


def test_qos_0_needs_no_acknowledgement(broker: Broker) -> None:
    broker.ack_mode = "none"
    started = time.monotonic()
    message = adapter().execute(config(broker), {}, publish(qos="0", payload="ON"), timeout=TIMEOUT)
    assert time.monotonic() - started < 1.0 and message == "Nachricht veröffentlicht."
    wait_until(lambda: broker.publishes)  # the broker thread records it a moment later
    assert broker.publishes[0]["qos"] == 0 and broker.connects[0]["user"] is None


def test_every_attempt_uses_a_fresh_client_id(broker: Broker) -> None:
    for _ in range(2):
        adapter().execute(config(broker), {}, publish(qos="0"), timeout=TIMEOUT)
    assert broker.connects[0]["client_id"] != broker.connects[1]["client_id"]


# --------------------------------------------------------------- failures and retries


def test_wrong_credentials_are_a_permanent_error(broker: Broker) -> None:
    broker.connack_code = 4
    with pytest.raises(IntegrationError) as info:
        adapter().execute(
            config(broker, username="x"), {"password": "y"}, publish(), timeout=TIMEOUT
        )
    assert not isinstance(info.value, IntegrationConnectionError)
    assert "Benutzername oder Passwort" in info.value.user_message
    assert broker.publishes == []


def test_a_user_the_broker_does_not_allow_is_reported(broker: Broker) -> None:
    broker.connack_code = 5
    with pytest.raises(IntegrationError) as info:
        adapter().check(config(broker), {}, timeout=TIMEOUT)
    assert "erlaubt diesem Benutzer den Zugriff nicht" in info.value.user_message


def test_an_unreachable_broker_is_retried_later() -> None:
    refused = adapter().validate_config({"host": "127.0.0.1", "port": closed_port()})
    with pytest.raises(IntegrationConnectionError) as info:
        adapter().execute(refused, {}, publish(), timeout=TIMEOUT)
    assert "nicht erreichbar" in info.value.user_message


def test_an_unknown_host_is_retried_later() -> None:
    unknown = adapter().validate_config({"host": "gibt-es-nicht.invalid"})
    with pytest.raises(IntegrationConnectionError):
        adapter().execute(unknown, {}, publish(), timeout=TIMEOUT)


def test_a_broker_that_never_answers_the_login_is_retried_and_nothing_was_sent(
    broker: Broker,
) -> None:
    broker.silent_on_connect = True
    with pytest.raises(IntegrationConnectionError):
        adapter().execute(config(broker), {}, publish(), timeout=0.3)
    assert broker.publishes == []


def test_a_broker_that_hangs_up_during_the_login_is_retried(broker: Broker) -> None:
    """Nothing was published yet, so trying again is safe."""
    broker.hang_up_on_connect = True
    with pytest.raises(IntegrationConnectionError):
        adapter().execute(config(broker), {}, publish(), timeout=TIMEOUT)
    assert broker.publishes == []


def test_something_that_is_not_an_mqtt_broker_is_reported(broker: Broker) -> None:
    broker.garbage_on_connect = True
    with pytest.raises(IntegrationError) as info:
        adapter().execute(config(broker), {}, publish(), timeout=TIMEOUT)
    assert "nicht wie ein MQTT-Broker" in info.value.user_message


@pytest.mark.parametrize("mode", ["none", "close"])
def test_a_missing_acknowledgement_is_not_retried(broker: Broker, mode: str) -> None:
    """The message may have been delivered; repeating a TOGGLE could switch the light twice."""
    broker.ack_mode = mode
    with pytest.raises(IntegrationError) as info:
        adapter().execute(config(broker), {}, publish(payload="TOGGLE"), timeout=0.4)
    assert not isinstance(info.value, IntegrationConnectionError)
    assert "möglicherweise zugestellt" in info.value.user_message
    assert len(broker.publishes) == 1  # it arrived once and was not repeated


# --------------------------------------------------------------------------- check


def test_the_check_logs_in_but_publishes_nothing(broker: Broker) -> None:
    message = adapter().check(config(broker, username="anna"), {"password": "p"}, timeout=TIMEOUT)
    assert f"127.0.0.1:{broker.port}" in message
    time.sleep(0.1)
    assert (
        broker.publishes == [] and broker.connects[0]["user"] == "anna" and broker.disconnects == 1
    )


def test_the_check_of_an_unreachable_broker_fails() -> None:
    refused = adapter().validate_config({"host": "127.0.0.1", "port": closed_port()})
    with pytest.raises(IntegrationError):
        adapter().check(refused, {}, timeout=TIMEOUT)


# ----------------------------------------------------------------------------- TLS


class FakeContext:
    def __init__(self, verify: bool, fail: bool = False) -> None:
        self.verify, self.fail, self.hostnames = verify, fail, []

    def wrap_socket(self, raw: socket.socket, server_hostname: str) -> socket.socket:
        self.hostnames.append(server_hostname)
        if self.fail:
            raise ssl.SSLCertVerificationError("certificate verify failed")
        return raw


def test_tls_wraps_the_connection_with_the_chosen_verification(broker: Broker) -> None:
    created: list[FakeContext] = []

    def factory(verify: bool) -> Any:
        created.append(FakeContext(verify))
        return created[-1]

    tls = MqttAdapter(context_factory=factory)
    cfg = tls.validate_config({"host": "127.0.0.1", "port": broker.port, "use_tls": True})
    tls.execute(cfg, {}, publish(qos="0"), timeout=TIMEOUT)
    assert created[0].verify is True and created[0].hostnames == ["127.0.0.1"]
    off = tls.validate_config(
        {"host": "127.0.0.1", "port": broker.port, "use_tls": True, "verify_tls": False}
    )
    tls.execute(off, {}, publish(qos="0"), timeout=TIMEOUT)
    assert created[1].verify is False


def test_without_tls_no_context_is_created(broker: Broker) -> None:
    def factory(verify: bool) -> Any:
        raise AssertionError("TLS was not requested")

    MqttAdapter(context_factory=factory).execute(
        config(broker), {}, publish(qos="0"), timeout=TIMEOUT
    )


def test_a_failed_tls_handshake_is_a_permanent_configuration_error(broker: Broker) -> None:
    tls = MqttAdapter(context_factory=lambda verify: FakeContext(verify, fail=True))
    cfg = tls.validate_config({"host": "127.0.0.1", "port": broker.port, "use_tls": True})
    with pytest.raises(IntegrationError) as info:
        tls.execute(cfg, {}, publish(), timeout=TIMEOUT)
    assert not isinstance(info.value, IntegrationConnectionError)
    assert "Zertifikat" in info.value.user_message and broker.publishes == []


# ---------------------------------------------------------- shipped and end to end


def test_the_mqtt_adapter_ships_with_the_program() -> None:
    adapters = default_adapters()
    assert "mqtt" in adapters and "webhook" in adapters
    assert [f.name for f in adapters["mqtt"].spec.config_fields if f.secret] == ["password"]


def test_a_queued_action_is_published_through_the_service(broker: Broker, tmp_path: Path) -> None:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    service = IntegrationService(
        storage, SecretStore(tmp_path / "secrets.json"), {"mqtt": MqttAdapter()}
    )
    connection = service.create(
        "mqtt",
        "Broker",
        {"host": "127.0.0.1", "port": broker.port, "username": "anna", "password": "pw-1"},
    )
    job = IntegrationJob(
        "evt-1",
        connection.integration.id,
        "Lampe",
        {"action": "publish", "topic": "licht/an", "payload": "ON", "qos": "1", "retain": False},
        expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )
    with storage.transaction() as repos:
        repos.jobs.enqueue(job)
    assert service.process_due() == 1
    assert broker.publishes[0]["topic"] == "licht/an" and broker.connects[0]["password"] == "pw-1"
    with storage.read() as repos:
        done = repos.jobs.get(job.id)
    assert done is not None and done.status is JobStatus.DONE
