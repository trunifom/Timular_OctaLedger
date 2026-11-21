"""Tests for the Hue adapter against a local fake of the bridge interface (plain HTTP).

The fake imitates pairing (v1 ``/api``) and the CLIP v2 resources used here. Certificate pinning is
tested at its seams (fingerprint, pool manager configuration, refusal without a fingerprint): a
real TLS handshake with a certificate is not exercised.
"""

import json
import socket
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
from octaledger.infrastructure.integrations.hue import (
    HueAdapter,
    PinnedAdapter,
    fingerprint_of,
    pinned_session,
)
from octaledger.infrastructure.integrations.registry import default_adapters
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

TIMEOUT = 2.0
KEY = "hue-anwendungsschluessel-123"
LAMP = "11111111-1111-4111-8111-111111111111"
LAMP2 = "22222222-2222-4222-8222-222222222222"
GROUP = "33333333-3333-4333-8333-333333333333"
SCENE = "44444444-4444-4444-8444-444444444444"


class FakeBridge:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.button_pressed = True
        self.states = {LAMP: True}
        self.errors: list[dict[str, str]] = []
        self.fail_with: int | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self, status: int, payload: Any) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _resources(self, kind: str) -> Any:
                data: dict[str, list[dict[str, Any]]] = {
                    "light": [
                        {"id": LAMP, "metadata": {"name": "Schreibtisch"}},
                        {"id": LAMP2, "metadata": {"name": "Ambiente"}},
                        {"metadata": {"name": "ohne Kennung"}},
                    ],
                    "room": [
                        {
                            "id": "room-1",
                            "metadata": {"name": "Büro"},
                            "services": [
                                {"rtype": "device", "rid": "x"},
                                {"rtype": "grouped_light", "rid": GROUP},
                            ],
                        },
                        {"id": "room-2", "metadata": {"name": "Ohne Gruppe"}, "services": []},
                    ],
                    "scene": [{"id": SCENE, "metadata": {"name": "Abend"}}],
                    "bridge": [{"bridge_id": "ABCD1234"}],
                }
                return {"errors": [], "data": data.get(kind, [])}

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                outer.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "key": self.headers.get("hue-application-key"),
                        "body": body,
                    }
                )
                if self.path == "/api" and self.command == "POST":
                    if not outer.button_pressed:
                        return self._answer(
                            200,
                            [{"error": {"type": 101, "description": "link button not pressed"}}],
                        )
                    return self._answer(200, [{"success": {"username": KEY, "clientkey": "x"}}])
                if self.headers.get("hue-application-key") != KEY:
                    return self._answer(403, {"errors": [{"description": "unauthorized"}]})
                if outer.fail_with:
                    return self._answer(outer.fail_with, {})
                parts = self.path.strip("/").split("/")
                if len(parts) >= 4 and parts[:3] == ["clip", "v2", "resource"]:
                    kind = parts[3]
                    identifier = parts[4] if len(parts) > 4 else None
                    if self.command == "GET" and identifier is None:
                        return self._answer(200, self._resources(kind))
                    if self.command == "GET" and kind == "light" and identifier in outer.states:
                        return self._answer(
                            200, {"errors": [], "data": [{"on": {"on": outer.states[identifier]}}]}
                        )
                    if self.command == "PUT":
                        if identifier in (LAMP, LAMP2, GROUP, SCENE):
                            if body and "on" in body and identifier in outer.states:
                                outer.states[identifier] = body["on"]["on"]
                            return self._answer(200, {"errors": outer.errors, "data": []})
                return self._answer(404, {"errors": [{"description": "not found"}]})

            do_GET = do_POST = do_PUT = _handle  # noqa: N815

            def log_message(self, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.host = f"127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def bridge() -> Iterator[FakeBridge]:
    instance = FakeBridge()
    yield instance
    instance.close()


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear_registered_secrets()


SECRETS = {"app_key": KEY}


def adapter() -> HueAdapter:
    return HueAdapter(scheme="http")  # a local fake over plain HTTP


def config(bridge: FakeBridge) -> dict[str, Any]:
    return adapter().validate_config({"host": bridge.host})


def action(kind: str, **fields: Any) -> dict[str, Any]:
    return adapter().validate_action({"action": kind, **fields})


def closed_host() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return f"127.0.0.1:{probe.getsockname()[1]}"


# ------------------------------------------------------------------------ validation


@pytest.mark.parametrize("host", ["192.168.1.5", "hue.local", "hue-bridge", "192.168.1.5:8443"])
def test_plain_hosts_are_accepted(host: str) -> None:
    assert adapter().validate_config({"host": host})["host"] == host


@pytest.mark.parametrize(
    "host", ["https://192.168.1.5", "192.168.1.5/clip", "hue bridge", "-x", ""]
)
def test_hosts_with_scheme_path_or_spaces_are_rejected(host: str) -> None:
    with pytest.raises(ValidationError):
        adapter().validate_config({"host": host})


def test_the_fingerprint_is_normalised_and_checked() -> None:
    raw = "ab:cd:" + "ef" * 30
    cleaned = adapter().validate_config({"host": "h", "fingerprint": raw})["fingerprint"]
    assert cleaned == ("ABCD" + "EF" * 30) and len(cleaned) == 64
    for bad in ("zz" * 32, "abcd", "ab" * 33):
        with pytest.raises(ValidationError):
            adapter().validate_config({"host": "h", "fingerprint": bad})


def test_the_application_key_is_a_secret_and_not_a_setting() -> None:
    cleaned = adapter().validate_config({"host": "h", "app_key": "geheim"})
    assert "app_key" not in cleaned
    assert [f.name for f in adapter().spec.config_fields if f.secret] == ["app_key"]
    assert not any(f.required for f in adapter().spec.config_fields if f.secret)  # pairing sets it


@pytest.mark.parametrize("bad", ["", "abc", "../x", LAMP + "/x", LAMP[:-1], "g" * 36])
def test_identifiers_must_be_real_uuids_because_they_become_path_parts(bad: str) -> None:
    with pytest.raises(ValidationError):
        action("light", light_id=bad)
    with pytest.raises(ValidationError):
        action("scene", scene_id=bad)


def test_action_rules() -> None:
    assert action("light", light_id=LAMP)["state"] == "on"
    assert action("room", group_id=GROUP, state="toggle")["state"] == "toggle"
    for bad in (
        {"light_id": LAMP, "state": "off", "brightness": 40},
        {"light_id": LAMP, "state": "toggle", "warmth_k": 2700},
        {"light_id": LAMP, "brightness": 0},
        {"light_id": LAMP, "brightness": 101},
        {"light_id": LAMP, "warmth_k": 1000},
        {"light_id": LAMP, "state": "dim"},
        {"light_id": LAMP, "farbe": "rot"},
    ):
        with pytest.raises(ValidationError):
            action("light", **bad)


# --------------------------------------------------------------------------- pairing


def test_pairing_without_the_button_explains_what_to_do(bridge: FakeBridge) -> None:
    bridge.button_pressed = False
    with pytest.raises(IntegrationError) as info:
        adapter().pair(config(bridge), timeout=TIMEOUT)
    assert "Knopf" in info.value.user_message and "30 Sekunden" in info.value.user_message
    assert not isinstance(info.value, IntegrationConnectionError)


def test_pairing_returns_the_key_as_a_secret(bridge: FakeBridge) -> None:
    result = adapter().pair(config(bridge), timeout=TIMEOUT)
    assert result.secrets == {"app_key": KEY} and result.config == {}  # no pin over plain http
    assert KEY not in result.message
    seen = bridge.requests[0]
    assert (seen["method"], seen["path"]) == ("POST", "/api")
    assert seen["body"] == {"devicetype": "octaledger#pc", "generateclientkey": True}


def test_pairing_with_pinning_remembers_the_certificate_fingerprint(bridge: FakeBridge) -> None:
    calls: list[tuple[str, int]] = []

    def fetch(host: str, port: int, timeout: float) -> str:
        calls.append((host, port))
        return "AB" * 32

    pinned = HueAdapter(scheme="http", pin=True, fetch_certificate=fetch)  # transport: local fake
    result = pinned.pair({"host": bridge.host}, timeout=TIMEOUT)
    assert result.secrets == {"app_key": KEY}
    assert result.config == {"fingerprint": "AB" * 32}  # stored with the connection (not secret)
    assert calls == [("127.0.0.1", int(bridge.host.split(":")[1]))]


def test_a_bridge_that_cannot_be_reached_for_pairing_is_retried_later() -> None:
    def refuse(host: str, port: int, timeout: float) -> str:
        raise ConnectionRefusedError("nope")

    tls = HueAdapter(scheme="https", fetch_certificate=refuse)
    with pytest.raises(IntegrationConnectionError) as info:
        tls.pair({"host": "192.168.1.5"}, timeout=TIMEOUT)
    assert "nimmt kein Gerät" in info.value.user_message


def test_pairing_with_a_confused_answer_fails_clearly(bridge: FakeBridge) -> None:
    bridge.fail_with = None
    other = adapter().validate_config({"host": bridge.host})
    other["host"] = bridge.host + "/x"  # a path the fake does not know: HTTP 404
    with pytest.raises(IntegrationError) as info:
        adapter().pair(other, timeout=TIMEOUT)
    assert "Koppeln" in info.value.user_message


# ----------------------------------------------------------------- certificate pinning


def test_the_fingerprint_is_the_sha256_of_the_der_certificate() -> None:
    assert fingerprint_of(b"abc") == (
        "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD"
    )


def test_a_pinned_session_asserts_the_fingerprint_on_https_only() -> None:
    pin = "AB" * 32
    session = pinned_session(pin)
    adapter_for_https = session.get_adapter("https://192.168.1.5")
    assert isinstance(adapter_for_https, PinnedAdapter)
    assert adapter_for_https.poolmanager.connection_pool_kw["assert_fingerprint"] == pin
    assert adapter_for_https.poolmanager.connection_pool_kw["assert_hostname"] is False
    assert not isinstance(session.get_adapter("http://192.168.1.5"), PinnedAdapter)
    assert session.trust_env is False
    assert not isinstance(pinned_session(None).get_adapter("https://x"), PinnedAdapter)


def test_nothing_is_sent_over_https_without_a_stored_fingerprint() -> None:
    sent: list[str] = []

    def spy(fingerprint: str | None) -> Any:
        sent.append("session created")
        return pinned_session(fingerprint)

    tls = HueAdapter(scheme="https", session_for=spy)
    cfg = tls.validate_config({"host": "192.168.1.5"})
    for call in (
        lambda: tls.check(cfg, SECRETS, timeout=TIMEOUT),
        lambda: tls.execute(cfg, SECRETS, action("light", light_id=LAMP), timeout=TIMEOUT),
        lambda: tls.discover(cfg, SECRETS, timeout=TIMEOUT),
    ):
        with pytest.raises(IntegrationError) as info:
            call()
        assert "koppeln" in info.value.user_message.lower()
    assert sent == []  # no request, not even a session, without a pin


# ---------------------------------------------------------------------------- check


def test_check_needs_pairing_first(bridge: FakeBridge) -> None:
    with pytest.raises(IntegrationError) as info:
        adapter().check(config(bridge), {}, timeout=TIMEOUT)
    assert "gekoppelt" in info.value.user_message and bridge.requests == []


def test_check_reads_the_bridge_without_changing_anything(bridge: FakeBridge) -> None:
    message = adapter().check(config(bridge), SECRETS, timeout=TIMEOUT)
    assert "erreichbar" in message and "ABCD1234" in message
    assert [(r["method"], r["path"]) for r in bridge.requests] == [
        ("GET", "/clip/v2/resource/bridge")
    ]


def test_a_rejected_key_asks_for_pairing_again_without_naming_the_key(bridge: FakeBridge) -> None:
    with pytest.raises(IntegrationError) as info:
        adapter().check(config(bridge), {"app_key": "falsch"}, timeout=TIMEOUT)
    assert "erneut koppeln" in info.value.user_message
    assert "falsch" not in info.value.user_message and "falsch" not in info.value.message


# -------------------------------------------------------------------------- switching


def test_a_lamp_is_switched_on_with_brightness_and_warmth(bridge: FakeBridge) -> None:
    adapter().execute(
        config(bridge),
        SECRETS,
        action("light", light_id=LAMP, brightness=40, warmth_k=2700),
        timeout=TIMEOUT,
    )
    (seen,) = bridge.requests
    assert (seen["method"], seen["path"], seen["key"]) == (
        "PUT",
        f"/clip/v2/resource/light/{LAMP}",
        KEY,
    )
    assert seen["body"] == {
        "on": {"on": True},
        "dimming": {"brightness": 40.0},
        "color_temperature": {"mirek": 370},
    }


@pytest.mark.parametrize(("kelvin", "mirek"), [(2000, 500), (6500, 154), (2700, 370)])
def test_warmth_is_converted_to_mirek_within_the_bridge_range(
    bridge: FakeBridge, kelvin: int, mirek: int
) -> None:
    adapter().execute(
        config(bridge), SECRETS, action("light", light_id=LAMP, warmth_k=kelvin), timeout=TIMEOUT
    )
    assert bridge.requests[0]["body"]["color_temperature"] == {"mirek": mirek}


def test_switching_off_sends_nothing_else(bridge: FakeBridge) -> None:
    message = adapter().execute(
        config(bridge), SECRETS, action("light", light_id=LAMP, state="off"), timeout=TIMEOUT
    )
    assert bridge.requests[0]["body"] == {"on": {"on": False}} and message == "Ausgeschaltet."


def test_toggle_reads_the_state_first_and_flips_it(bridge: FakeBridge) -> None:
    toggle = action("light", light_id=LAMP, state="toggle")
    adapter().execute(config(bridge), SECRETS, toggle, timeout=TIMEOUT)
    assert bridge.states[LAMP] is False  # it was on
    adapter().execute(config(bridge), SECRETS, toggle, timeout=TIMEOUT)
    assert bridge.states[LAMP] is True
    assert [r["method"] for r in bridge.requests] == ["GET", "PUT", "GET", "PUT"]


def test_a_room_uses_the_group_resource_and_a_scene_is_recalled(bridge: FakeBridge) -> None:
    adapter().execute(
        config(bridge), SECRETS, action("room", group_id=GROUP, state="off"), timeout=TIMEOUT
    )
    assert bridge.requests[0]["path"] == f"/clip/v2/resource/grouped_light/{GROUP}"
    message = adapter().execute(
        config(bridge), SECRETS, action("scene", scene_id=SCENE), timeout=TIMEOUT
    )
    assert bridge.requests[1]["path"] == f"/clip/v2/resource/scene/{SCENE}"
    assert bridge.requests[1]["body"] == {"recall": {"action": "active"}}
    assert message == "Szene aktiviert."


def test_errors_reported_by_the_bridge_inside_a_200_answer_are_not_swallowed(
    bridge: FakeBridge,
) -> None:
    bridge.errors = [{"description": "device (light) is unreachable"}]
    with pytest.raises(IntegrationError) as info:
        adapter().execute(config(bridge), SECRETS, action("light", light_id=LAMP), timeout=TIMEOUT)
    assert "unreachable" in info.value.user_message


def test_an_unknown_lamp_is_reported_clearly(bridge: FakeBridge) -> None:
    unknown = "99999999-9999-4999-8999-999999999999"
    with pytest.raises(IntegrationError) as info:
        adapter().execute(
            config(bridge), SECRETS, action("light", light_id=unknown), timeout=TIMEOUT
        )
    assert "kennt diese Lampe" in info.value.user_message


@pytest.mark.parametrize("status", [500, 503])
def test_other_failure_answers_are_permanent(bridge: FakeBridge, status: int) -> None:
    bridge.fail_with = status
    with pytest.raises(IntegrationError) as info:
        adapter().execute(config(bridge), SECRETS, action("light", light_id=LAMP), timeout=TIMEOUT)
    assert not isinstance(info.value, IntegrationConnectionError)
    assert f"HTTP {status}" in info.value.user_message and len(bridge.requests) == 1


def test_an_unreachable_bridge_is_retried_later() -> None:
    cfg = adapter().validate_config({"host": closed_host()})
    with pytest.raises(IntegrationConnectionError):
        adapter().execute(cfg, SECRETS, action("light", light_id=LAMP), timeout=TIMEOUT)


# ------------------------------------------------------------------------- discovery


def test_discovery_lists_lamps_rooms_and_scenes_by_name(bridge: FakeBridge) -> None:
    found = adapter().discover(config(bridge), SECRETS, timeout=TIMEOUT)
    assert found["lights"] == [
        {"id": LAMP2, "name": "Ambiente"},
        {"id": LAMP, "name": "Schreibtisch"},
    ]  # sorted by name; the entry without an id is skipped
    assert found["rooms"] == [{"id": GROUP, "name": "Büro"}]  # the id of the lamp *group*
    assert found["scenes"] == [{"id": SCENE, "name": "Abend"}]


def test_discovery_needs_a_valid_key(bridge: FakeBridge) -> None:
    with pytest.raises(IntegrationError):
        adapter().discover(config(bridge), {"app_key": "falsch"}, timeout=TIMEOUT)


# ---------------------------------------------------------- shipped and end to end


def test_the_adapter_ships_with_the_program() -> None:
    spec = default_adapters()["hue"].spec
    assert spec.can_pair and spec.can_discover and spec.pair_help
    assert not spec.action("light").idempotent and spec.action("scene").idempotent
    # every identifier field is filled from what discovery found, so nobody has to type a UUID
    sources = {
        field.name: field.choices_from
        for action in spec.actions
        for field in action.fields
        if field.name.endswith("_id")
    }
    assert sources == {
        "light_id": ("lights",),
        "group_id": ("rooms",),
        "scene_id": ("scenes",),
    }


def test_pairing_and_switching_through_the_service(bridge: FakeBridge, tmp_path: Path) -> None:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    secrets = SecretStore(tmp_path / "secrets.json")
    service = IntegrationService(storage, secrets, {"hue": adapter()})
    created = service.create("hue", "Wohnung", {"host": bridge.host})  # no key needed yet
    integration_id = created.integration.id
    assert created.secrets_set == ()
    assert service.pair(integration_id) == "Mit der Hue Bridge gekoppelt."
    assert secrets.get(integration_id) == {"app_key": KEY}
    assert KEY not in repr(service.get(integration_id))  # only the name of the secret is visible
    assert service.discover(integration_id)["lights"][0]["name"] == "Ambiente"
    job = IntegrationJob(
        "evt-1",
        integration_id,
        "Schreibtisch",
        {"action": "light", "light_id": LAMP, "state": "off"},
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    with storage.transaction() as repos:
        repos.jobs.enqueue(job)
    assert service.process_due() == 1
    assert bridge.states[LAMP] is False
    with storage.read() as repos:
        done = repos.jobs.get(job.id)
    assert done is not None and done.status is JobStatus.DONE
