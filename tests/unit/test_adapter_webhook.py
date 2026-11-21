"""Tests for the webhook adapter against a real local HTTP server (no mocks of the network)."""

import json
import socket
import threading
import time
from collections.abc import Iterator
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
from octaledger.infrastructure.integrations.registry import default_adapters
from octaledger.infrastructure.integrations.webhook import WebhookAdapter
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

TIMEOUT = 2.0


class Target:
    """A tiny HTTP server that records requests and answers as the test programmed."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.answers: dict[str, tuple[int, dict[str, str]]] = {}
        target = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8") if length else ""
                target.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": body,
                    }
                )
                if self.path.startswith("/slow"):
                    time.sleep(1.0)
                status, headers = target.answers.get(self.path.split("?")[0], (200, {}))
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle  # noqa: N815

            def log_message(self, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def target() -> Iterator[Target]:
    instance = Target()
    yield instance
    instance.close()


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear_registered_secrets()


def adapter() -> WebhookAdapter:
    return WebhookAdapter()


def config(target: Target, **extra: Any) -> dict[str, Any]:
    return adapter().validate_config({"base_url": target.url, **extra})


def action(**fields: Any) -> dict[str, Any]:
    return adapter().validate_action({"action": "request", **fields})


def closed_port_url() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{probe.getsockname()[1]}"  # nothing listens there afterwards


# ------------------------------------------------------------------------ validation


@pytest.mark.parametrize(
    "url", ["http://192.168.1.2:1880", "https://example.org", "http://h/prefix/"]
)
def test_plain_http_addresses_are_accepted(url: str) -> None:
    cleaned = adapter().validate_config({"base_url": url})
    assert cleaned["base_url"] == url.rstrip("/") and cleaned["verify_tls"] is True


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://host",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "host-without-scheme",
        "http://user:pw@host",
        "http://host/?token=1",
        "http://host/#x",
        "http://host:99999",
        "http://",
    ],
)
def test_other_addresses_are_rejected_with_a_german_message(url: str) -> None:
    with pytest.raises(ValidationError) as info:
        adapter().validate_config({"base_url": url})
    assert "Basisadresse" in info.value.user_message or "darf nicht leer" in info.value.user_message


def test_the_header_name_is_restricted() -> None:
    cleaned = adapter().validate_config({"base_url": "http://h", "auth_header": "X-Api-Key"})
    assert cleaned["auth_header"] == "X-Api-Key"
    for bad in ("X Key", "X:Key", "Keüy"):
        with pytest.raises(ValidationError):
            adapter().validate_config({"base_url": "http://h", "auth_header": bad})


def test_the_secret_is_not_part_of_the_validated_settings() -> None:
    cleaned = adapter().validate_config({"base_url": "http://h", "auth_value": "Bearer geheim"})
    assert "auth_value" not in cleaned and "geheim" not in repr(cleaned)


def test_action_defaults_and_rules() -> None:
    cleaned = action(path="/an")
    assert cleaned == {
        "action": "request",
        "path": "/an",
        "method": "POST",
        "content_type": "application/json",
    }
    assert action(path="/an?x=1")["path"] == "/an?x=1"  # a query string belongs to the path
    for bad in (
        {"path": "an"},
        {"path": "//evil.example/x"},
        {"path": "/x", "method": "TRACE"},
        {"path": "/x", "body": "{kein json"},
        {"path": "/x", "method": "GET", "body": "{}"},
        {"path": "/x", "zusatz": "1"},
    ):
        with pytest.raises(ValidationError):
            action(**bad)
    assert action(path="/x", body="plain text", content_type="text/plain")["body"] == "plain text"


# ---------------------------------------------------------------------------- sending


def test_the_request_arrives_as_configured(target: Target) -> None:
    message = adapter().execute(
        config(target, auth_header="X-Api-Key"),
        {"auth_value": "geheim-123"},
        action(path="/licht/an", method="PUT", body='{"an": true}'),
        timeout=TIMEOUT,
    )
    (seen,) = target.requests
    assert (seen["method"], seen["path"], seen["body"]) == ("PUT", "/licht/an", '{"an": true}')
    assert seen["headers"]["content-type"] == "application/json"
    assert seen["headers"]["x-api-key"] == "geheim-123"
    assert seen["headers"]["user-agent"] == "OctaLedger"
    assert "geheim-123" not in message and "HTTP 200" in message


def test_without_a_secret_no_authorization_header_is_sent(target: Target) -> None:
    adapter().execute(config(target), {}, action(path="/x", method="GET"), timeout=TIMEOUT)
    assert "authorization" not in target.requests[0]["headers"]
    assert "content-type" not in target.requests[0]["headers"]  # no body, no content type


def test_the_authorization_header_is_the_default(target: Target) -> None:
    adapter().execute(
        config(target), {"auth_value": "Bearer abc"}, action(path="/x"), timeout=TIMEOUT
    )
    assert target.requests[0]["headers"]["authorization"] == "Bearer abc"


def test_a_base_path_prefix_is_kept(target: Target) -> None:
    prefixed = adapter().validate_config({"base_url": target.url + "/api/"})
    adapter().execute(prefixed, {}, action(path="/licht"), timeout=TIMEOUT)
    assert target.requests[0]["path"] == "/api/licht"


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_an_error_answer_is_a_permanent_error(target: Target, status: int) -> None:
    target.answers["/x"] = (status, {})
    with pytest.raises(IntegrationError) as info:
        adapter().execute(config(target), {}, action(path="/x"), timeout=TIMEOUT)
    assert not isinstance(info.value, IntegrationConnectionError)  # an answer is never retried
    assert f"HTTP {status}" in info.value.user_message
    assert len(target.requests) == 1


def test_an_unauthorised_answer_points_to_the_credentials(target: Target) -> None:
    target.answers["/x"] = (401, {})
    with pytest.raises(IntegrationError) as info:
        adapter().execute(config(target), {}, action(path="/x"), timeout=TIMEOUT)
    assert "Zugang" in info.value.user_message


def test_redirects_are_not_followed(target: Target) -> None:
    target.answers["/old"] = (302, {"Location": "http://127.0.0.1:1/elsewhere"})
    with pytest.raises(IntegrationError) as info:
        adapter().execute(config(target), {}, action(path="/old"), timeout=TIMEOUT)
    assert "leitet weiter" in info.value.user_message
    assert [r["path"] for r in target.requests] == ["/old"]  # nothing else was contacted


def test_a_refused_connection_is_retried_later(target: Target) -> None:
    refused = adapter().validate_config({"base_url": closed_port_url()})
    with pytest.raises(IntegrationConnectionError) as info:
        adapter().execute(refused, {}, action(path="/x"), timeout=TIMEOUT)
    assert "nicht erreichbar" in info.value.user_message


def test_an_unknown_host_is_retried_later() -> None:
    unknown = adapter().validate_config({"base_url": "http://gibt-es-nicht.invalid"})
    with pytest.raises(IntegrationConnectionError):
        adapter().execute(unknown, {}, action(path="/x"), timeout=TIMEOUT)


def test_a_timeout_after_sending_is_not_retried(target: Target) -> None:
    """The action may already have happened, so repeating it could do it twice."""
    with pytest.raises(IntegrationError) as info:
        adapter().execute(config(target), {}, action(path="/slow"), timeout=0.3)
    assert not isinstance(info.value, IntegrationConnectionError)
    assert "möglicherweise ausgeführt" in info.value.user_message
    assert len(target.requests) == 1


def test_environment_proxies_are_ignored(target: Target, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    adapter().execute(config(target), {}, action(path="/x"), timeout=TIMEOUT)
    assert len(target.requests) == 1  # went straight to the target, not through the proxy


# ----------------------------------------------------------------------- the check


def test_check_accepts_any_answer_below_500(target: Target) -> None:
    assert "erreichbar (HTTP 200)" in adapter().check(config(target), {}, timeout=TIMEOUT)
    target.answers["/"] = (404, {})
    assert "erreichbar (HTTP 404)" in adapter().check(config(target), {}, timeout=TIMEOUT)
    assert [r["method"] for r in target.requests] == ["GET", "GET"]  # a check changes nothing


@pytest.mark.parametrize(
    ("status", "fragment"), [(401, "lehnt den Zugang"), (503, "einen Fehler (HTTP 503)")]
)
def test_check_reports_a_rejection_or_a_failing_target(
    target: Target, status: int, fragment: str
) -> None:
    target.answers["/"] = (status, {})
    with pytest.raises(IntegrationError) as info:
        adapter().check(config(target), {}, timeout=TIMEOUT)
    assert fragment in info.value.user_message


def test_check_of_an_unreachable_target_fails() -> None:
    unreachable = adapter().validate_config({"base_url": closed_port_url()})
    with pytest.raises(IntegrationError):
        adapter().check(unreachable, {}, timeout=TIMEOUT)


# ------------------------------------------------------------- shipped and end to end


def test_the_webhook_adapter_ships_with_the_program() -> None:
    adapters = default_adapters()
    assert "webhook" in adapters and adapters["webhook"].spec.title.startswith("Webhook")
    spec = adapters["webhook"].spec
    assert spec.action("request").idempotent is False  # the interface warns about repeating it
    assert [f.name for f in spec.config_fields if f.secret] == ["auth_value"]


def test_a_queued_action_reaches_the_target_through_the_service(
    target: Target, tmp_path: Path
) -> None:
    from datetime import datetime, timedelta, timezone

    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    service = IntegrationService(
        storage, SecretStore(tmp_path / "secrets.json"), {"webhook": WebhookAdapter()}
    )
    connection = service.create(
        "webhook", "Node-RED", {"base_url": target.url, "auth_value": "Bearer token-1"}
    )
    now = datetime.now(timezone.utc)
    job = IntegrationJob(
        "evt-1",
        connection.integration.id,
        "Licht an",
        {
            "action": "request",
            "path": "/licht/an",
            "method": "POST",
            "content_type": "application/json",
            "body": '{"an": 1}',
        },
        expires_at=now + timedelta(seconds=30),
    )
    with storage.transaction() as repos:
        repos.jobs.enqueue(job)
    assert service.process_due() == 1
    (seen,) = target.requests
    assert seen["path"] == "/licht/an" and json.loads(seen["body"]) == {"an": 1}
    assert seen["headers"]["authorization"] == "Bearer token-1"
    with storage.read() as repos:
        done = repos.jobs.get(job.id)
    assert done is not None and done.status is JobStatus.DONE
