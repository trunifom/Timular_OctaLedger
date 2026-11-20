"""Tests for API token handling and host/origin validation."""

import os
import stat
from pathlib import Path

import pytest

from octaledger.api.security import (
    ENV_TOKEN,
    MIN_TOKEN_LENGTH,
    TOKEN_FILE_NAME,
    check_request_origin,
    generate_token,
    is_allowed_host,
    is_allowed_origin,
    load_or_create_token,
    parse_bearer,
    validate_token_format,
    verify_token,
)
from octaledger.core.errors import (
    AuthenticationError,
    ConfigurationError,
    ForbiddenOriginError,
)
from octaledger.core.logging import clear_registered_secrets, redact

PORT = 8765


@pytest.fixture(autouse=True)
def _reset_secrets() -> None:
    clear_registered_secrets()


# ----------------------------------------------------------------------------- token


def test_generated_tokens_are_long_random_and_valid() -> None:
    first, second = generate_token(), generate_token()
    assert first != second and len(first) >= MIN_TOKEN_LENGTH
    assert validate_token_format(first) == first


@pytest.mark.parametrize(
    "token", ["", "short", "x" * 31, "x" * 257, "has space " * 5, "ümlaut" * 10, "a;b" * 20]
)
def test_invalid_token_formats(token: str) -> None:
    with pytest.raises(ConfigurationError):
        validate_token_format(token)


def test_token_is_created_once_and_reused(tmp_path: Path) -> None:
    path = tmp_path / TOKEN_FILE_NAME
    first = load_or_create_token(path, {})
    assert path.read_text(encoding="utf-8").strip() == first
    assert load_or_create_token(path, {}) == first  # same token on the next start


def test_token_file_gets_restricted_permissions_on_posix(tmp_path: Path) -> None:
    path = tmp_path / TOKEN_FILE_NAME
    load_or_create_token(path, {})
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_environment_token_overrides_file_and_creates_nothing(tmp_path: Path) -> None:
    path = tmp_path / TOKEN_FILE_NAME
    token = "e" * 40
    assert load_or_create_token(path, {ENV_TOKEN: f"  {token} "}) == token
    assert not path.exists()


def test_invalid_environment_or_file_token_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        load_or_create_token(tmp_path / "t", {ENV_TOKEN: "short"})
    bad = tmp_path / "bad"
    bad.write_text("tiny", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_or_create_token(bad, {})
    huge = tmp_path / "huge"
    huge.write_text("x" * 5000, encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_or_create_token(huge, {})


def test_token_is_registered_for_log_redaction(tmp_path: Path) -> None:
    token = load_or_create_token(tmp_path / TOKEN_FILE_NAME, {})
    assert token not in redact(f"leaked {token} here")
    assert "***" in redact(f"leaked {token} here")


# -------------------------------------------------------------------------- verification


def test_verify_accepts_exact_token_only() -> None:
    token = generate_token()
    verify_token(token, token)
    for wrong in (None, "", token + "x", token[:-1], token.upper()):
        with pytest.raises(AuthenticationError) as info:
            verify_token(wrong, token)
        assert info.value.error_code == "OL-API-001"
        assert token not in str(info.value)  # the message never leaks the secret


@pytest.mark.parametrize(
    "header, expected",
    [
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("  BEARER   abc  ", "abc"),
        ("Basic abc", None),
        ("Bearer", None),
        ("Bearer ", None),
        ("abc", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_bearer(header: str | None, expected: str | None) -> None:
    assert parse_bearer(header) == expected


# ---------------------------------------------------------------------------- host header


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1:8765", "localhost:8765", "LOCALHOST:8765", "[::1]:8765", " 127.0.0.1:8765 "],
)
def test_allowed_hosts(host: str) -> None:
    assert is_allowed_host(host, PORT)


@pytest.mark.parametrize(
    "host",
    [
        None,
        "",
        "127.0.0.1",  # no port
        "127.0.0.1:80",
        "127.0.0.1:8766",
        "evil.example:8765",  # DNS rebinding: foreign name resolving to 127.0.0.1
        "localhost.evil.example:8765",
        "127.0.0.1.evil.example:8765",
        "0.0.0.0:8765",
        "[::1]",
        "[::1",
        "[::1]8765",
        "[::2]:8765",
        "192.168.0.5:8765",
    ],
)
def test_rejected_hosts(host: str | None) -> None:
    assert not is_allowed_host(host, PORT)


# -------------------------------------------------------------------------- origin header


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "http://127.0.0.1:8501",
        "http://localhost:8501",
        "https://localhost",
        "http://[::1]:8501",
    ],
)
def test_allowed_origins(origin: str | None) -> None:
    assert is_allowed_origin(origin)


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "",
        "http://evil.example",
        "https://example.com:8765",
        "http://localhost.evil.example",
        "http://127.0.0.1.evil.example",
        "file:///etc/passwd",
        "ftp://localhost",
        "http://localhost:99999",
        "javascript:alert(1)",
        "http://user@evil.example",
    ],
)
def test_rejected_origins(origin: str) -> None:
    assert not is_allowed_origin(origin)


def test_check_request_origin_raises_with_reason() -> None:
    check_request_origin("127.0.0.1:8765", None, PORT)  # fine
    check_request_origin("localhost:8765", "http://localhost:8501", PORT)
    with pytest.raises(ForbiddenOriginError) as host_error:
        check_request_origin("evil.example:8765", None, PORT)
    assert (
        host_error.value.details["reason"] == "host" and host_error.value.error_code == "OL-API-003"
    )
    with pytest.raises(ForbiddenOriginError) as origin_error:
        check_request_origin("127.0.0.1:8765", "http://evil.example", PORT)
    assert origin_error.value.details["reason"] == "origin"
