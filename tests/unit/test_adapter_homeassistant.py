"""Tests for the Home Assistant adapter against a local fake of its REST interface.

The fake imitates the parts used here (API root, service calls, state list, bearer token). It
cannot prove behaviour with a real Home Assistant (versions and error texts may differ).
"""

import json
import socket
import threading
import time
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
from octaledger.infrastructure.integrations.homeassistant import HomeAssistantAdapter
from octaledger.infrastructure.integrations.httpio import (
    MAX_BODY_BYTES,
    new_session,
    read_limited,
)
from octaledger.infrastructure.integrations.registry import default_adapters
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

TIMEOUT = 2.0
TOKEN = "gutes-token-123"

STATES = [
    {"entity_id": "light.schreibtisch", "attributes": {"friendly_name": "Schreibtischlampe"}},
    {"entity_id": "light.bad", "attributes": {"friendly_name": "Badezimmer"}},
    {"entity_id": "switch.radio", "attributes": {}},
    {"entity_id": "scene.abend", "attributes": {"friendly_name": "Abend"}},
    {"entity_id": "sensor.temperatur", "attributes": {"friendly_name": "Temperatur"}},
    {"entity_id": "kaputt-ohne-punkt", "attributes": {}},
    "kein-objekt",
]


class FakeHomeAssistant:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.states: Any = STATES
        self.unknown_services = {"nope/gibtsnicht"}
        self.fail_with: int | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self, status: int, payload: Any = None) -> None:
                body = json.dumps(payload if payload is not None else {}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8") if length else ""
                outer.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "auth": self.headers.get("Authorization"),
                        "body": json.loads(body) if body else None,
                    }
                )
                if self.path.startswith("/slow"):
                    time.sleep(1.0)
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._answer(401, {"message": "unauthorized"})
                if outer.fail_with:
                    return self._answer(outer.fail_with)
                if self.path == "/api/" and self.command == "GET":
                    return self._answer(200, {"message": "API running."})
                if self.path == "/api/states":
                    return self._answer(200, outer.states)
                if self.path.startswith("/api/services/"):
                    service = self.path.removeprefix("/api/services/")
                    if service in outer.unknown_services:
                        return self._answer(404, {"message": "not found"})
                    return self._answer(200, [])
                if self.path.startswith("/moved"):
                    self.send_response(302)
                    self.send_header("Location", "http://127.0.0.1:1/x")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                return self._answer(404)

            do_GET = do_POST = _handle  # noqa: N815

            def log_message(self, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def ha() -> Iterator[FakeHomeAssistant]:
    instance = FakeHomeAssistant()
    yield instance
    instance.close()


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear_registered_secrets()


SECRETS = {"token": TOKEN}


def adapter() -> HomeAssistantAdapter:
    return HomeAssistantAdapter()


def config(ha: FakeHomeAssistant) -> dict[str, Any]:
    return adapter().validate_config({"base_url": ha.url})


def action(kind: str, **fields: Any) -> dict[str, Any]:
    return adapter().validate_action({"action": kind, **fields})


def closed_port_url() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{probe.getsockname()[1]}"


# ------------------------------------------------------------------------ validation


def test_the_token_is_a_secret_and_the_address_is_checked() -> None:
    cleaned = adapter().validate_config(
        {"base_url": "http://homeassistant.local:8123/", "token": "geheim"}
    )
    assert cleaned["base_url"] == "http://homeassistant.local:8123" and "token" not in cleaned
    spec = adapter().spec
    assert [f.name for f in spec.config_fields if f.secret] == ["token"]
    for bad in ("homeassistant.local", "ftp://x", "http://u:p@h", "http://h/?a=1"):
        with pytest.raises(ValidationError):
            adapter().validate_config({"base_url": bad})


@pytest.mark.parametrize(
    "entity", ["light", "Light.Desk", "light.desk lamp", "light/../x", "a.b.c", ""]
)
def test_malformed_entity_ids_are_rejected(entity: str) -> None:
    with pytest.raises(ValidationError):
        action("turn_off", entity_id=entity)


def test_scenes_and_scripts_must_name_a_scene_or_a_script() -> None:
    assert action("scene", entity_id="scene.abend")["entity_id"] == "scene.abend"
    assert action("script", entity_id="script.feierabend")["entity_id"] == "script.feierabend"
    for kind, entity in (("scene", "light.desk"), ("script", "scene.abend")):
        with pytest.raises(ValidationError):
            action(kind, entity_id=entity)


def test_brightness_only_for_lamps_and_within_range() -> None:
    assert action("turn_on", entity_id="light.desk", brightness=40)["brightness"] == 40
    for fields in (
        {"entity_id": "switch.radio", "brightness": 40},
        {"entity_id": "light.desk", "brightness": 0},
        {"entity_id": "light.desk", "brightness": 101},
    ):
        with pytest.raises(ValidationError):
            action("turn_on", **fields)


@pytest.mark.parametrize("name", ["../x", "Light", "a b", "a.b", "", "a/b"])
def test_domain_and_service_cannot_reshape_the_request_path(name: str) -> None:
    with pytest.raises(ValidationError):
        action("service", domain=name, service="turn_on")
    with pytest.raises(ValidationError):
        action("service", domain="light", service=name)


def test_generic_service_data_must_be_a_json_object() -> None:
    assert (
        action("service", domain="light", service="turn_on", data='{"a": 1}')["data"] == '{"a": 1}'
    )
    for bad in ("{kein json", "[1, 2]", "5"):
        with pytest.raises(ValidationError):
            action("service", domain="light", service="turn_on", data=bad)


def test_unknown_fields_and_actions_are_rejected() -> None:
    with pytest.raises(ValidationError):
        action("turn_on", entity_id="light.desk", zusatz="x")
    with pytest.raises(ValidationError):
        adapter().validate_action({"action": "format_disk"})


# ----------------------------------------------------------------------- calling


@pytest.mark.parametrize(
    ("fields", "path", "body"),
    [
        (
            {"action": "turn_on", "entity_id": "switch.radio"},
            "homeassistant/turn_on",
            {"entity_id": "switch.radio"},
        ),
        (
            {"action": "turn_on", "entity_id": "light.desk", "brightness": 40},
            "light/turn_on",
            {"entity_id": "light.desk", "brightness_pct": 40},
        ),
        (
            {"action": "turn_off", "entity_id": "light.desk"},
            "homeassistant/turn_off",
            {"entity_id": "light.desk"},
        ),
        (
            {"action": "toggle", "entity_id": "light.desk"},
            "homeassistant/toggle",
            {"entity_id": "light.desk"},
        ),
        (
            {"action": "scene", "entity_id": "scene.abend"},
            "scene/turn_on",
            {"entity_id": "scene.abend"},
        ),
        (
            {"action": "script", "entity_id": "script.s"},
            "script/turn_on",
            {"entity_id": "script.s"},
        ),
        (
            {
                "action": "service",
                "domain": "climate",
                "service": "set_temperature",
                "entity_id": "climate.bad",
                "data": '{"temperature": 21}',
            },
            "climate/set_temperature",
            {"temperature": 21, "entity_id": "climate.bad"},
        ),
        ({"action": "service", "domain": "notify", "service": "mobile"}, "notify/mobile", {}),
    ],
)
def test_every_action_calls_the_matching_service(
    ha: FakeHomeAssistant, fields: dict[str, Any], path: str, body: dict[str, Any]
) -> None:
    message = adapter().execute(
        config(ha), SECRETS, adapter().validate_action(fields), timeout=TIMEOUT
    )
    (seen,) = ha.requests
    assert (seen["method"], seen["path"], seen["body"]) == ("POST", f"/api/services/{path}", body)
    assert seen["auth"] == f"Bearer {TOKEN}"
    assert path.replace("/", ".") in message and TOKEN not in message


def test_without_a_token_nothing_is_sent(ha: FakeHomeAssistant) -> None:
    with pytest.raises(IntegrationError) as info:
        adapter().execute(config(ha), {}, action("toggle", entity_id="light.desk"), timeout=TIMEOUT)
    assert "Zugriffstoken" in info.value.user_message and ha.requests == []


def test_a_rejected_token_points_to_creating_a_new_one(ha: FakeHomeAssistant) -> None:
    with pytest.raises(IntegrationError) as info:
        adapter().execute(
            config(ha),
            {"token": "falsch"},
            action("toggle", entity_id="light.desk"),
            timeout=TIMEOUT,
        )
    assert "lehnt das Zugriffstoken ab" in info.value.user_message
    assert "falsch" not in info.value.user_message and "falsch" not in info.value.message


def test_an_unknown_service_is_reported_clearly(ha: FakeHomeAssistant) -> None:
    with pytest.raises(IntegrationError) as info:
        adapter().execute(
            config(ha),
            SECRETS,
            action("service", domain="nope", service="gibtsnicht"),
            timeout=TIMEOUT,
        )
    assert "kennt diesen Dienst nicht" in info.value.user_message
    assert not isinstance(info.value, IntegrationConnectionError)


def test_an_error_answer_is_permanent(ha: FakeHomeAssistant) -> None:
    ha.fail_with = 500
    with pytest.raises(IntegrationError) as info:
        adapter().execute(
            config(ha), SECRETS, action("toggle", entity_id="light.desk"), timeout=TIMEOUT
        )
    assert (
        not isinstance(info.value, IntegrationConnectionError)
        and "HTTP 500" in info.value.user_message
    )
    assert len(ha.requests) == 1


def test_an_unreachable_home_assistant_is_retried_later() -> None:
    cfg = adapter().validate_config({"base_url": closed_port_url()})
    with pytest.raises(IntegrationConnectionError):
        adapter().execute(cfg, SECRETS, action("toggle", entity_id="light.desk"), timeout=TIMEOUT)


def test_a_timeout_after_sending_is_not_retried(ha: FakeHomeAssistant) -> None:
    cfg = adapter().validate_config({"base_url": ha.url + "/slow"})
    with pytest.raises(IntegrationError) as info:
        adapter().execute(cfg, SECRETS, action("toggle", entity_id="light.desk"), timeout=0.3)
    assert not isinstance(info.value, IntegrationConnectionError)
    assert "möglicherweise ausgeführt" in info.value.user_message


def test_redirects_are_not_followed(ha: FakeHomeAssistant) -> None:
    moved = adapter().validate_config({"base_url": ha.url + "/moved"})  # the fake redirects these
    with pytest.raises(IntegrationError) as info:
        adapter().check(moved, SECRETS, timeout=TIMEOUT)
    assert "leitet weiter" in info.value.user_message
    assert [r["path"] for r in ha.requests] == ["/moved/api/"]  # nothing else was contacted


# ----------------------------------------------------------------------------- check


def test_check_confirms_the_address_and_the_token(ha: FakeHomeAssistant) -> None:
    assert "Zugriffstoken wird akzeptiert" in adapter().check(config(ha), SECRETS, timeout=TIMEOUT)
    assert [(r["method"], r["path"]) for r in ha.requests] == [("GET", "/api/")]  # no side effect


def test_check_with_a_wrong_token_fails(ha: FakeHomeAssistant) -> None:
    with pytest.raises(IntegrationError) as info:
        adapter().check(config(ha), {"token": "falsch"}, timeout=TIMEOUT)
    assert "Zugriffstoken" in info.value.user_message


def test_check_of_an_unreachable_target_fails() -> None:
    cfg = adapter().validate_config({"base_url": closed_port_url()})
    with pytest.raises(IntegrationError):
        adapter().check(cfg, SECRETS, timeout=TIMEOUT)


# -------------------------------------------------------------------------- discovery


def test_discovery_lists_the_devices_to_choose_from(ha: FakeHomeAssistant) -> None:
    found = adapter().discover(config(ha), SECRETS, timeout=TIMEOUT)
    assert found["light"] == [
        {"id": "light.bad", "name": "Badezimmer"},
        {"id": "light.schreibtisch", "name": "Schreibtischlampe"},
    ]  # sorted by the friendly name
    assert found["switch"] == [{"id": "switch.radio", "name": "switch.radio"}]  # no friendly name
    assert found["scene"] == [{"id": "scene.abend", "name": "Abend"}]
    assert (
        "sensor" not in found and "script" not in found
    )  # only what can be switched; empty omitted


def test_discovery_tolerates_odd_entries_and_caps_the_list(ha: FakeHomeAssistant) -> None:
    ha.states = [
        {"entity_id": f"light.l{n:03d}", "attributes": {"friendly_name": f"Lampe {n:03d}"}}
        for n in range(500)
    ]
    assert len(adapter().discover(config(ha), SECRETS, timeout=TIMEOUT)["light"]) == 200
    ha.states = {"kein": "listenformat"}
    assert adapter().discover(config(ha), SECRETS, timeout=TIMEOUT) == {}


def test_discovery_with_a_wrong_token_fails(ha: FakeHomeAssistant) -> None:
    with pytest.raises(IntegrationError):
        adapter().discover(config(ha), {"token": "falsch"}, timeout=TIMEOUT)


# ---------------------------------------------------------------------------- httpio


def test_the_shared_session_ignores_the_environment() -> None:
    assert new_session().trust_env is False


def test_a_huge_answer_is_cut_off() -> None:
    class Endless:
        closed = False

        def iter_content(self, chunk_size: int) -> Iterator[bytes]:
            while True:
                yield b"x" * chunk_size

        def close(self) -> None:
            self.closed = True

    response = Endless()
    with pytest.raises(IntegrationError):
        read_limited(response, limit=1024 * 1024)  # type: ignore[arg-type]
    assert response.closed and MAX_BODY_BYTES >= 1024 * 1024


# ---------------------------------------------------------- shipped and end to end


def test_the_adapter_ships_with_the_program() -> None:
    adapters = default_adapters()
    assert "homeassistant" in adapters and adapters["homeassistant"].spec.can_discover
    spec = adapters["homeassistant"].spec
    assert spec.action("turn_on").idempotent and not spec.action("toggle").idempotent
    assert "light" in spec.action("turn_on").fields[0].choices_from
    assert spec.action("scene").fields[0].choices_from == ("scene",)
    assert spec.action("script").fields[0].choices_from == ("script",)


def test_a_queued_action_reaches_home_assistant_through_the_service(
    ha: FakeHomeAssistant, tmp_path: Path
) -> None:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    service = IntegrationService(
        storage, SecretStore(tmp_path / "secrets.json"), {"homeassistant": HomeAssistantAdapter()}
    )
    connection = service.create("homeassistant", "Zuhause", {"base_url": ha.url, "token": TOKEN})
    assert service.check(connection.integration.id).startswith("Home Assistant ist erreichbar")
    assert service.discover(connection.integration.id)["light"][0]["id"] == "light.bad"
    job = IntegrationJob(
        "evt-1",
        connection.integration.id,
        "Schreibtischlampe",
        {"action": "toggle", "entity_id": "light.schreibtisch"},
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    with storage.transaction() as repos:
        repos.jobs.enqueue(job)
    assert service.process_due() == 1
    sent = [r for r in ha.requests if r["method"] == "POST"]
    assert sent[0]["path"] == "/api/services/homeassistant/toggle"
    assert sent[0]["body"] == {"entity_id": "light.schreibtisch"}
    with storage.read() as repos:
        done = repos.jobs.get(job.id)
    assert done is not None and done.status is JobStatus.DONE
