"""Unit tests for the dashboard API client with a fake HTTP session (no network)."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import requests

from octaledger.core.errors import (
    ERROR_CODE_PATTERN,
    ApiUnavailableError,
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
    OctaLedgerError,
    ValidationError,
)
from octaledger.core.logging import clear_registered_secrets
from octaledger.core.settings import AgentSettings
from octaledger.dashboard_client.client import ApiClient, error_from_response, read_token

TOKEN = "k" * 43
BASE = "http://127.0.0.1:8765"
T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


class FakeResponse:
    def __init__(self, status: int = 200, payload: Any = None, *, bad_json: bool = False) -> None:
        self.status_code = status
        self._payload = payload
        self._bad_json = bad_json

    def json(self) -> Any:
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, *responses: FakeResponse | Exception) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self.responses.pop(0) if self.responses else FakeResponse(200, {})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client_with(*responses: FakeResponse | Exception) -> tuple[ApiClient, FakeSession]:
    session = FakeSession(*responses)
    return ApiClient(BASE, TOKEN, session=session), session  # type: ignore[arg-type]


# -------------------------------------------------------------------------- construction


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.example:8765",
        "http://192.168.1.5:8765",
        "https://127.0.0.1:8765",  # the API speaks plain http on loopback
        "http://127.0.0.1",  # no port
        "ftp://127.0.0.1:8765",
        "http://localhost.evil.com:8765",
        "127.0.0.1:8765",
    ],
)
def test_token_is_never_sent_to_non_loopback_urls(url: str) -> None:
    with pytest.raises(ConfigurationError):
        ApiClient(url, TOKEN)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8765", "http://localhost:9000", "http://[::1]:8765"]
)
def test_loopback_urls_are_accepted(url: str) -> None:
    ApiClient(url, TOKEN)


def test_malformed_token_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        ApiClient(BASE, "short")


def test_from_settings_builds_url_and_reads_token_file(tmp_path: Path) -> None:
    (tmp_path / "api_token").write_text(TOKEN + "\n", encoding="utf-8")
    client = ApiClient.from_settings(AgentSettings(host="localhost", port=9001), tmp_path)
    assert client._base == "http://localhost:9001"
    ipv6 = ApiClient.from_settings(AgentSettings(host="::1", port=9001), tmp_path)
    assert ipv6._base == "http://[::1]:9001"


def test_read_token_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as missing:
        read_token(tmp_path / "api_token")
    assert "Agenten" in missing.value.user_message  # tells the user to start the agent
    (tmp_path / "api_token").write_text("tiny", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        read_token(tmp_path / "api_token")


# ---------------------------------------------------------------------------- transport


def test_request_carries_token_only_in_header_and_uses_timeouts() -> None:
    client, session = client_with(FakeResponse(200, {"running": None}))
    assert client.status() == {"running": None}
    call = session.calls[0]
    assert call["method"] == "GET" and call["url"] == f"{BASE}/api/v1/status"
    assert call["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert TOKEN not in call["url"] and call["timeout"] == (3.0, 30.0)


def test_health_is_sent_without_credentials() -> None:
    client, session = client_with(FakeResponse(200, {"status": "ok"}))
    assert client.health()["status"] == "ok"
    assert session.calls[0]["headers"] == {}


def test_none_parameters_are_dropped_and_bool_flags_forwarded() -> None:
    client, session = client_with(FakeResponse(200, []), FakeResponse(200, []))
    client.list_items("activities")
    client.list_items("projects", include_archived=True)
    assert session.calls[0]["params"] is None
    assert session.calls[1]["params"] == {"include_archived": True}


def test_204_returns_none() -> None:
    client, _ = client_with(FakeResponse(204))
    assert client.remove_device("d1") is None


@pytest.mark.parametrize(
    "exc", [requests.ConnectionError("refused http://x?token=SECRET"), requests.Timeout("slow")]
)
def test_connection_problems_become_api_unavailable_without_leaking_details(exc: Exception) -> None:
    client, _ = client_with(exc)
    with pytest.raises(ApiUnavailableError) as info:
        client.status()
    assert info.value.error_code == "OL-API-002" and "SECRET" not in str(info.value)
    assert info.value.__cause__ is exc


def test_other_request_exceptions_are_also_unavailable() -> None:
    client, _ = client_with(requests.exceptions.InvalidURL("bad"))
    with pytest.raises(ApiUnavailableError):
        client.status()


def test_is_agent_running_never_raises() -> None:
    assert client_with(FakeResponse(200, {"status": "ok"}))[0].is_agent_running()
    assert not client_with(requests.ConnectionError("down"))[0].is_agent_running()
    assert not client_with(FakeResponse(200, {"status": "starting"}))[0].is_agent_running()
    assert not client_with(FakeResponse(403, {"error": {"code": "OL-API-003", "message": "x"}}))[
        0
    ].is_agent_running()


# ------------------------------------------------------------------------ error mapping


@pytest.mark.parametrize(
    "status, code, expected",
    [
        (401, "OL-API-001", AuthenticationError),
        (404, "OL-STATE-001", NotFoundError),
        (409, "OL-STATE-002", ConflictError),
        (422, "OL-VALID-001", ValidationError),
    ],
)
def test_api_errors_are_rebuilt_as_the_matching_exception(
    status: int, code: str, expected: type[OctaLedgerError]
) -> None:
    payload = {
        "error": {
            "code": code,
            "message": "Deutsch",
            "technical_message": "english",
            "details": {"field": "x"},
        }
    }
    client, _ = client_with(FakeResponse(status, payload))
    with pytest.raises(expected) as info:
        client.status()
    assert info.value.user_message == "Deutsch" and info.value.message == "english"
    assert info.value.details == {"field": "x"} and info.value.error_code == code


def test_unknown_code_keeps_the_code_but_is_a_generic_error() -> None:
    error = error_from_response(500, {"error": {"code": "OL-FUTURE-042", "message": "Neu"}})
    assert type(error) is OctaLedgerError and error.error_code == "OL-FUTURE-042"
    assert error.user_message == "Neu"


@pytest.mark.parametrize(
    "payload",
    [None, [], "text", {"error": "flat"}, {"error": {"code": "garbage code", "message": "m"}}, {}],
)
def test_malformed_error_bodies_never_crash(payload: Any) -> None:
    error = error_from_response(502, payload)
    assert isinstance(error, OctaLedgerError)
    assert error.user_message  # always something the GUI can show
    assert ERROR_CODE_PATTERN.match(error.error_code)  # a garbage code is never adopted
    if not (isinstance(payload, dict) and isinstance(payload.get("error"), dict)):
        assert "502" in error.message  # the HTTP status survives when the body is unusable


def test_non_json_error_body_is_reported_with_status() -> None:
    client, _ = client_with(FakeResponse(502, bad_json=True))
    with pytest.raises(OctaLedgerError) as info:
        client.status()
    assert "502" in info.value.user_message


def test_non_json_success_body_returns_none() -> None:
    client, _ = client_with(FakeResponse(200, bad_json=True))
    assert client.status() is None  # type: ignore[func-returns-value]


# ------------------------------------------------------------------------------ methods


def test_methods_build_the_documented_requests() -> None:
    client, session = client_with(*[FakeResponse(200, {}) for _ in range(12)])
    client.register_device("Büro")
    client.assign_face("d1", 3, "a1", None)
    client.set_device_address("d1", "AA:BB")
    client.create_item("projects", "Alpha", "#112233")
    client.archive_item("activities", "a1", False)
    client.start_tracking("a1", note="x")
    client.add_session("a1", T0, T0.replace(hour=9))
    client.correct_session("s1", {"ended_at": T0, "note": "n"}, "Grund")
    client.split_session("s1", T0, "Pause")
    client.delete_session("s1", "Test")
    client.day_report(date(2026, 1, 5), tz="Europe/Zurich", activity_id=None)
    client.restore("{}", confirm=True)
    calls = [
        (c["method"], c["url"].removeprefix(f"{BASE}/api/v1"), c.get("json"), c.get("params"))
        for c in session.calls
    ]
    assert calls[0] == ("POST", "/devices", {"alias": "Büro"}, None)
    assert calls[1] == (
        "PUT",
        "/devices/d1/faces/3",
        {"activity_id": "a1", "project_id": None},
        None,
    )
    assert calls[2][2] == {"platform_address": "AA:BB"}
    assert calls[3][:2] == ("POST", "/projects") and calls[4][2] == {"archived": False}
    assert calls[6][2]["start"] == "2026-01-05T08:00:00+00:00"
    assert calls[7][2] == {
        "changes": {"ended_at": "2026-01-05T08:00:00+00:00", "note": "n"},
        "reason": "Grund",
    }
    assert calls[9][:2] == ("POST", "/sessions/s1/delete")  # deletion is a POST with a body
    assert calls[10][3] == {"day": "2026-01-05", "tz": "Europe/Zurich"}  # None filter dropped
    assert calls[11][2] == {"content": "{}", "confirm": True}


def test_invalid_catalog_kind_and_naive_datetimes_are_rejected_locally() -> None:
    client, session = client_with()
    with pytest.raises(ValidationError):
        client.list_items("devices")
    with pytest.raises(ValidationError):
        client.journal(datetime(2026, 1, 5), T0)
    assert session.calls == []  # nothing was sent


def test_logs_and_integrity_unwrap_results() -> None:
    client, _ = client_with(
        FakeResponse(200, {"lines": ["a", "b"]}), FakeResponse(200, {"ok": True, "problems": []})
    )
    assert client.logs(10) == ["a", "b"] and client.integrity()["ok"] is True


def test_token_does_not_survive_in_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    clear_registered_secrets()
    client, _ = client_with(requests.ConnectionError(f"boom {TOKEN}"))
    with caplog.at_level("DEBUG"), pytest.raises(ApiUnavailableError):
        client.status()
    assert TOKEN not in caplog.text
