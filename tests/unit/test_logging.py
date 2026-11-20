"""Tests for central logging: redaction, configuration, rotation and step tracing."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from octaledger.core import logging as ol_logging
from octaledger.core.errors import ConfigurationError
from octaledger.core.logging import (
    LOG_FILE_NAME,
    REDACTED,
    MemoryLogHandler,
    RedactingFormatter,
    clear_registered_secrets,
    configure_logging,
    log_step,
    parse_level,
    recent_log_lines,
    redact,
    register_secret,
    shutdown_logging,
)

logger = logging.getLogger("octaledger.tests.logging")


@pytest.fixture(autouse=True)
def _clean_logging() -> Iterator[None]:
    """Reset global logging state around every test."""
    clear_registered_secrets()
    yield
    shutdown_logging()
    clear_registered_secrets()


# --------------------------------------------------------------------------- redaction


@pytest.mark.parametrize(
    "text, leaked",
    [
        ("token=abc123", "abc123"),
        ("Token: abc123", "abc123"),
        ('{"token": "abc123"}', "abc123"),
        ("password=hunter2 user=x", "hunter2"),
        ("Authorization: Bearer abc.def-ghi", "abc.def-ghi"),
        ("api_key=XYZ789", "XYZ789"),
        ("api-key: XYZ789", "XYZ789"),
        ("secret = s3cr3t!", "s3cr3t!"),
    ],
)
def test_redact_masks_secret_values(text: str, leaked: str) -> None:
    result = redact(text)
    assert leaked not in result
    assert REDACTED in result


def test_redact_keeps_prose_without_separator() -> None:
    # No ':' or '=' follows the keyword, so nothing must be masked.
    assert redact("invalid token provided") == "invalid token provided"


def test_redact_keeps_key_name_for_readability() -> None:
    assert redact("token=abc") == f"token={REDACTED}"
    assert redact("Authorization: Bearer abc") == f"Authorization: Bearer {REDACTED}"


def test_redact_shortens_bluetooth_address() -> None:
    assert redact("device AA:BB:CC:DD:EE:FF found") == "device **:**:**:**:EE:FF found"
    assert redact("dev aa-bb-cc-dd-ee-ff") == "dev **:**:**:**:ee-ff"


def test_redact_keeps_uuids() -> None:
    uuid = "c7e70010-c847-11e6-8175-8c89a55d403c"
    assert redact(f"service {uuid}") == f"service {uuid}"


def test_registered_secret_masked_without_pattern() -> None:
    register_secret("plain-secret-value")
    assert redact("leak plain-secret-value here") == f"leak {REDACTED} here"


def test_register_empty_secret_is_ignored() -> None:
    register_secret("")
    assert redact("nothing to hide") == "nothing to hide"


def test_longest_registered_secret_masked_first() -> None:
    register_secret("abc")
    register_secret("abcdef")
    assert redact("x abcdef y") == f"x {REDACTED} y"


def test_formatter_redacts_arguments_and_traceback() -> None:
    register_secret("tok-123")
    formatter = RedactingFormatter()
    try:
        raise RuntimeError("failed with tok-123")
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            "octaledger.x", logging.ERROR, __file__, 1, "value=%s", ("tok-123",), sys.exc_info()
        )
    formatted = formatter.format(record)
    assert "tok-123" not in formatted
    assert REDACTED in formatted
    assert "RuntimeError" in formatted  # traceback still present, only secret masked


def test_formatter_uses_utc_timestamp_with_z() -> None:
    record = logging.LogRecord("octaledger.x", logging.INFO, __file__, 1, "hi", None, None)
    formatted = RedactingFormatter().format(record)
    assert formatted.split(" ")[0].endswith("Z")
    assert "INFO" in formatted and "hi" in formatted


# ------------------------------------------------------------------------ parse_level


@pytest.mark.parametrize(
    "value, expected",
    [("debug", logging.DEBUG), (" Info ", logging.INFO), ("ERROR", logging.ERROR), (10, 10)],
)
def test_parse_level_accepts(value: str | int, expected: int) -> None:
    assert parse_level(value) == expected


@pytest.mark.parametrize("value", ["loud", "", True])
def test_parse_level_rejects(value: str | bool) -> None:
    with pytest.raises(ConfigurationError) as info:
        parse_level(value)
    assert info.value.error_code == "OL-CONFIG-001"


# ------------------------------------------------------------------ configure_logging


def test_configure_logs_to_file_and_memory(tmp_path: Path) -> None:
    configure_logging(level="DEBUG", log_dir=tmp_path, console=False)
    logger.info("hello file")
    shutdown_logging()  # flush + release file handle
    content = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "hello file" in content


def test_memory_buffer_receives_lines() -> None:
    configure_logging(level="INFO", console=False)
    logger.info("buffered line")
    assert any("buffered line" in line for line in recent_log_lines())


def test_level_filters_messages() -> None:
    configure_logging(level="WARNING", console=False)
    logger.info("hidden")
    logger.warning("visible")
    lines = "\n".join(recent_log_lines())
    assert "hidden" not in lines and "visible" in lines


def test_reconfigure_does_not_duplicate_handlers() -> None:
    root = logging.getLogger("octaledger")
    configure_logging(console=False)
    first = len(root.handlers)
    configure_logging(console=False)
    configure_logging(console=False)
    assert len(root.handlers) == first


def test_foreign_handlers_are_preserved() -> None:
    root = logging.getLogger("octaledger")
    foreign = logging.NullHandler()
    root.addHandler(foreign)
    try:
        configure_logging(console=False)
        configure_logging(console=False)
        assert foreign in root.handlers
    finally:
        root.removeHandler(foreign)


def test_secret_never_reaches_log_file(tmp_path: Path) -> None:
    register_secret("super-token-42")
    configure_logging(log_dir=tmp_path, console=False)
    logger.error("connection with super-token-42 failed, password=pw1")
    shutdown_logging()
    content = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "super-token-42" not in content
    assert "pw1" not in content


def test_unwritable_log_dir_degrades_gracefully(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    # A path *below a regular file* can never be created as a directory.
    configure_logging(log_dir=blocker / "logs", console=False)
    assert any("File logging disabled" in line for line in recent_log_lines())
    logger.info("still works")
    assert any("still works" in line for line in recent_log_lines())


@pytest.mark.parametrize("kwargs", [{"max_bytes": 0}, {"backup_count": -1}])
def test_invalid_rotation_parameters_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises(ConfigurationError):
        configure_logging(console=False, **kwargs)


def test_invalid_level_rejected() -> None:
    with pytest.raises(ConfigurationError):
        configure_logging(level="nope", console=False)


def test_rotation_creates_backup_files(tmp_path: Path) -> None:
    configure_logging(level="DEBUG", log_dir=tmp_path, console=False, max_bytes=500, backup_count=2)
    for i in range(60):
        logger.info("rotating line number %03d with some padding text", i)
    shutdown_logging()
    names = sorted(p.name for p in tmp_path.iterdir())
    assert LOG_FILE_NAME in names
    assert f"{LOG_FILE_NAME}.1" in names


def test_recent_log_lines_empty_when_disabled() -> None:
    configure_logging(console=False, memory_capacity=None)
    logger.info("nobody listens")
    assert recent_log_lines() == []


def test_memory_handler_is_bounded() -> None:
    handler = MemoryLogHandler(capacity=3)
    handler.setFormatter(logging.Formatter("%(message)s"))
    for i in range(10):
        handler.emit(logging.LogRecord("x", logging.INFO, __file__, 1, f"m{i}", None, None))
    assert handler.lines() == ["m7", "m8", "m9"]


def test_memory_handler_rejects_bad_capacity() -> None:
    with pytest.raises(ConfigurationError):
        MemoryLogHandler(capacity=0)


# ---------------------------------------------------------------------------- log_step


def test_log_step_logs_start_and_done() -> None:
    configure_logging(level="DEBUG", console=False)
    with log_step(logger, "open thing", path="x.db"):
        pass
    lines = "\n".join(recent_log_lines())
    assert "Step start: open thing (path=x.db)" in lines
    assert "Step done: open thing (path=x.db)" in lines


def test_log_step_logs_failure_and_reraises() -> None:
    configure_logging(level="DEBUG", console=False)
    with pytest.raises(KeyError):
        with log_step(logger, "explode"):
            raise KeyError("boom")
    lines = "\n".join(recent_log_lines())
    assert "Step failed: explode" in lines
    assert "KeyError" in lines  # traceback included


def test_log_step_masks_secret_context() -> None:
    configure_logging(level="DEBUG", console=False)
    with log_step(logger, "login", token="abc123"):
        pass
    assert "abc123" not in "\n".join(recent_log_lines())


def test_module_exposes_expected_public_names() -> None:
    # Guards against accidental removal of the public API used by other layers.
    for name in ("configure_logging", "log_step", "redact", "register_secret"):
        assert hasattr(ol_logging, name)
