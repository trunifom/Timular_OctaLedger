"""Central logging configuration with secret redaction and step tracing.

Responsibility
--------------
* Configure the ``octaledger`` logger tree **once**, in one place (console, rotating
  file, optional in-memory ring buffer for diagnostics).
* Guarantee that secrets never reach a log sink: API tokens, passwords, authorization
  headers and (partially) Bluetooth addresses are masked by :class:`RedactingFormatter`,
  which also covers formatted tracebacks.
* Offer :func:`log_step`, a small context manager that traces a program step (start,
  duration, failure) at DEBUG level so that program flow can be followed when needed.

Conventions (see ``CLAUDE.md``)
-------------------------------
Library modules call ``logging.getLogger(__name__)`` and never configure handlers.
Only entry points (CLI, agent, dashboard) call :func:`configure_logging`.

Levels: DEBUG = program steps, INFO = state changes, WARNING = tolerated deviation,
ERROR = failed operation, CRITICAL = process unusable.

Note: this module is named ``logging`` inside the ``octaledger.core`` package. Absolute
imports (the default in Python 3) make ``import logging`` below resolve to the standard
library, not to this file.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

from octaledger.core.errors import ConfigurationError

#: Name of the root logger of the whole application.
ROOT_LOGGER_NAME: Final = "octaledger"
#: File name of the rotating log file inside the log directory.
LOG_FILE_NAME: Final = "octaledger.log"
#: Default rotation size (bytes) and number of kept rotated files.
DEFAULT_MAX_BYTES: Final = 1_000_000
DEFAULT_BACKUP_COUNT: Final = 5
#: Default capacity of the in-memory diagnostic buffer (number of lines).
DEFAULT_MEMORY_CAPACITY: Final = 500
#: Replacement text for masked secrets.
REDACTED: Final = "***"

#: Marker attribute set on handlers we installed, so reconfiguration can remove exactly
#: those and never touch handlers owned by someone else (e.g. pytest's caplog).
_OWNED_ATTR: Final = "_octaledger_owned"

_LEVELS: Final[dict[str, int]] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# ``token=abc``, ``"password": "abc"``, ``Authorization: Bearer abc`` ...
# A ``:`` or ``=`` separator is required, otherwise harmless prose such as
# "invalid token provided" would be masked as well.
_SECRET_PATTERN: Final = re.compile(
    r"""(?ix)
    (?P<key>token|password|passwd|secret|authorization|api[_-]?key)
    (?P<sep>["']?\s*[:=]\s*["']?)
    (?P<bearer>bearer\s+)?
    (?P<value>[^\s,;"'}]+)
    """
)

# Bluetooth MAC addresses such as ``AA:BB:CC:DD:EE:FF`` or ``AA-BB-...``.
_MAC_PATTERN: Final = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){4}([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})\b")

_secrets_lock = threading.Lock()
_registered_secrets: set[str] = set()


def register_secret(secret: str) -> None:
    """Register an exact secret value (e.g. the API token) to be masked everywhere.

    Pattern based masking only recognises ``key=value`` shapes. A registered secret is
    masked even when it appears alone in a message.

    Args:
        secret: The secret text. Empty strings are ignored.
    """
    if not secret:
        return
    with _secrets_lock:
        _registered_secrets.add(secret)


def clear_registered_secrets() -> None:
    """Forget all registered secrets (used by tests and on shutdown)."""
    with _secrets_lock:
        _registered_secrets.clear()


def redact(text: str) -> str:
    """Mask secrets and shorten Bluetooth addresses in ``text``.

    Args:
        text: Arbitrary log text, possibly multi-line (tracebacks).

    Returns:
        The text with tokens/passwords replaced by ``***`` and only the last two octets
        of Bluetooth addresses kept (``**:**:**:**:EE:FF``).
    """
    with _secrets_lock:
        # Longest first so that a secret containing another secret is masked fully.
        secrets = sorted(_registered_secrets, key=len, reverse=True)
    for secret in secrets:
        text = text.replace(secret, REDACTED)

    def _mask_secret(match: re.Match[str]) -> str:
        return f"{match['key']}{match['sep']}{match['bearer'] or ''}{REDACTED}"

    text = _SECRET_PATTERN.sub(_mask_secret, text)
    return _MAC_PATTERN.sub(lambda m: f"**:**:**:**:{m.group(1)}", text)


class RedactingFormatter(logging.Formatter):
    """Formatter that masks secrets in the *final* text, tracebacks included.

    Redacting the fully formatted record (instead of ``record.msg``) also protects
    secrets that only appear in ``%`` arguments or in exception messages.
    """

    def __init__(self) -> None:
        """Use a UTC ISO-like timestamp so logs are comparable across timezones."""
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s %(name)s [%(threadName)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        self.converter = time.gmtime

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """Append milliseconds and the ``Z`` (UTC) suffix to the timestamp."""
        base = super().formatTime(record, datefmt)
        return f"{base}.{int(record.msecs):03d}Z"

    def format(self, record: logging.LogRecord) -> str:
        """Return the redacted, fully formatted record."""
        return redact(super().format(record))


class MemoryLogHandler(logging.Handler):
    """Keep the most recent formatted log lines in memory (ring buffer).

    Used for the diagnostics page and the anonymised diagnostics export. The buffer is
    bounded, so it can never grow without limit.
    """

    def __init__(self, capacity: int = DEFAULT_MEMORY_CAPACITY) -> None:
        """Create the handler.

        Args:
            capacity: Maximum number of retained lines (must be positive).

        Raises:
            ConfigurationError: If ``capacity`` is not positive.
        """
        super().__init__()
        if capacity <= 0:
            raise ConfigurationError(
                "Memory log capacity must be positive", details={"capacity": capacity}
            )
        self._lines: deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        """Format and store one record; never raise into the application."""
        try:
            self._lines.append(self.format(record))
        except Exception:  # noqa: BLE001 - logging must never break the program
            self.handleError(record)

    def lines(self) -> list[str]:
        """Return a snapshot of the retained lines, oldest first."""
        return list(self._lines)


def parse_level(level: str | int) -> int:
    """Convert a level name or number into a ``logging`` level.

    Args:
        level: ``"DEBUG"``..``"CRITICAL"`` (case-insensitive) or a numeric level.

    Returns:
        The numeric level.

    Raises:
        ConfigurationError: If the level is unknown.
    """
    if isinstance(level, int) and not isinstance(level, bool):
        return level
    if isinstance(level, str) and level.strip().upper() in _LEVELS:
        return _LEVELS[level.strip().upper()]
    raise ConfigurationError(
        f"Unknown log level: {level!r}",
        user_message="Die Protokollstufe ist ungültig. Erlaubt: DEBUG, INFO, WARNING, ERROR.",
        details={"level": str(level)},
    )


def _remove_owned_handlers(logger: logging.Logger) -> None:
    """Close and detach every handler previously installed by this module."""
    for handler in list(logger.handlers):
        if getattr(handler, _OWNED_ATTR, False):
            logger.removeHandler(handler)
            handler.close()


def _own(handler: logging.Handler) -> logging.Handler:
    """Tag ``handler`` as owned by this module and attach the redacting formatter."""
    setattr(handler, _OWNED_ATTR, True)
    handler.setFormatter(RedactingFormatter())
    return handler


def configure_logging(
    *,
    level: str | int = "INFO",
    log_dir: Path | None = None,
    console: bool = True,
    memory_capacity: int | None = DEFAULT_MEMORY_CAPACITY,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """Configure the ``octaledger`` logger tree. Safe to call repeatedly.

    Previously installed OctaLedger handlers are replaced, so repeated calls (for
    example on every Streamlit rerun) never produce duplicate lines.

    A problem with the log *file* (unwritable directory, full disk) must not stop the
    application: it is reported as a WARNING on the remaining sinks and logging
    continues without the file.

    Args:
        level: Minimum level (name or number).
        log_dir: Directory for the rotating log file; ``None`` disables file logging.
        console: Also log to ``stderr``.
        memory_capacity: Size of the diagnostic ring buffer; ``None`` disables it.
        max_bytes: Rotation threshold of the log file in bytes.
        backup_count: Number of rotated files to keep.

    Returns:
        The configured ``octaledger`` logger.

    Raises:
        ConfigurationError: If the level or a numeric parameter is invalid.
    """
    numeric_level = parse_level(level)
    if max_bytes <= 0 or backup_count < 0:
        raise ConfigurationError(
            "Invalid log rotation parameters",
            details={"max_bytes": max_bytes, "backup_count": backup_count},
        )

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    _remove_owned_handlers(logger)
    logger.setLevel(numeric_level)
    # Do not pass records to the root logger: avoids duplicates when an application
    # (or pytest) configured root handlers of its own.
    logger.propagate = False

    if console:
        logger.addHandler(_own(logging.StreamHandler()))
    if memory_capacity is not None:
        logger.addHandler(_own(MemoryLogHandler(memory_capacity)))

    file_error: OSError | None = None
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_dir / LOG_FILE_NAME,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            logger.addHandler(_own(file_handler))
        except OSError as exc:
            file_error = exc

    if file_error is not None:
        logger.warning(
            "File logging disabled, cannot use log directory %s: %s", log_dir, file_error
        )
    logger.debug(
        "Logging configured (level=%s, file=%s)",
        logging.getLevelName(numeric_level),
        file_error is None and log_dir is not None,
    )
    return logger


def shutdown_logging() -> None:
    """Detach and close all handlers installed by :func:`configure_logging`.

    Releases the log file (required on Windows before deleting it) and is called when
    the process ends.
    """
    _remove_owned_handlers(logging.getLogger(ROOT_LOGGER_NAME))


def recent_log_lines() -> list[str]:
    """Return the diagnostic ring buffer (oldest first), or ``[]`` when disabled."""
    for handler in logging.getLogger(ROOT_LOGGER_NAME).handlers:
        if isinstance(handler, MemoryLogHandler):
            return handler.lines()
    return []


@contextmanager
def log_step(logger: logging.Logger, step: str, **context: Any) -> Iterator[None]:
    """Trace one program step: start, success with duration, or failure.

    Emits ``DEBUG`` on start and success and ``ERROR`` (with traceback) on failure. The
    exception is always re-raised unchanged, so tracing never alters behaviour.

    Args:
        logger: Logger of the calling module.
        step: Short human-readable description, e.g. ``"open database"``.
        **context: Extra ``key=value`` pairs appended to every line. Must not contain
            secrets (they are masked anyway, but keep them out on principle).

    Example:
        >>> with log_step(logger, "open database", path=str(db_path)):
        ...     connection = open_database(db_path)
    """
    extras = " ".join(f"{key}={value}" for key, value in context.items())
    suffix = f" ({extras})" if extras else ""
    started = time.perf_counter()
    logger.debug("Step start: %s%s", step, suffix)
    try:
        yield
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.exception("Step failed: %s%s after %.1f ms", step, suffix, elapsed_ms)
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.debug("Step done: %s%s in %.1f ms", step, suffix, elapsed_ms)
