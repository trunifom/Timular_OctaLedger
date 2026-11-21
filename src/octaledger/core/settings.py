"""Validated configuration and per-user application paths.

Responsibility
--------------
* :class:`AppPaths` / :func:`resolve_paths` decide **where** user data lives. Data never
  lands in the project folder: the default is the per-user data directory of the
  operating system (via ``platformdirs``), overridable with the environment variable
  ``OCTALEDGER_DATA_DIR`` or an explicit argument.
* :class:`Settings` and its sections are **immutable, validated** value objects. They
  validate themselves in ``__post_init__``, so an invalid configuration can neither be
  loaded from a file nor constructed programmatically.
* :func:`load_settings` / :func:`save_settings` read and write ``settings.toml``.
  A missing file means defaults; a broken file is a :class:`ConfigurationError` with a
  precise message (it is never silently ignored). Unknown keys are rejected so typos
  are noticed instead of being dropped.

Security notes
--------------
The API host is restricted to loopback addresses (MVP requirement). The API *token* is
not part of the settings file; it is handled by ``octaledger.api.security``.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import threading
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import platformdirs

from octaledger.core.errors import ConfigurationError, StorageError
from octaledger.core.fileio import atomic_write_text, read_text_limited
from octaledger.core.logging import parse_level

logger = logging.getLogger(__name__)

#: Application name used for the per-user data directory.
APP_NAME: Final = "OctaLedger"
#: Environment variables that override file settings.
ENV_DATA_DIR: Final = "OCTALEDGER_DATA_DIR"
ENV_HOST: Final = "OCTALEDGER_HOST"
ENV_PORT: Final = "OCTALEDGER_PORT"
#: Hosts accepted for the local API in the MVP (loopback only).
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1", "localhost"})
#: Largest accepted settings file (a settings file is tiny; this is only a safety net).
MAX_SETTINGS_BYTES: Final = 1024 * 1024
#: Languages the GUI can display (more are planned, none are advertised before they exist).
SUPPORTED_LANGUAGES: Final = frozenset({"de"})


# ---------------------------------------------------------------------------- enumerations


class BaselinePolicy(StrEnum):
    """What to do with the first orientation read after connecting (the baseline)."""

    #: Only record it; never start a session by itself (default, safest).
    OBSERVE_ONLY = "observe_only"
    #: Treat the current face as an explicit session start ("adopt current side").
    ADOPT_CURRENT = "adopt_current"


class DisconnectPolicy(StrEnum):
    """What to do with the running session when the tracker connection is lost."""

    #: Keep the session but flag the gap as uncertain; the user confirms afterwards.
    MARK_UNCERTAIN = "mark_uncertain"
    #: End the session at the last known good moment.
    STOP_SESSION = "stop_session"
    #: Keep the session running for a grace period; end it at the moment of the loss if the
    #: tracker does not come back in time, then ask the user about the gap.
    GRACE_THEN_STOP = "grace_then_stop"


class NeutralPolicy(StrEnum):
    """How the neutral value ``0`` is treated (not yet validated on real hardware)."""

    #: Only log it as an event (default until hardware tests are done).
    OBSERVE_ONLY = "observe_only"
    #: Interpret neutral as a pause (experimental).
    PAUSE = "pause"


class TrackingMode(StrEnum):
    """How several registered trackers contribute to personal working time."""

    #: One personal active session fed by the selected tracker (MVP).
    SINGLE_ACTIVE_TRACKER = "single_active_tracker"


class Theme(StrEnum):
    """Colour scheme of the dashboard."""

    LIGHT = "light"
    DARK = "dark"


class FontSize(StrEnum):
    """Font size step of the dashboard (two steps, as required)."""

    NORMAL = "normal"
    LARGE = "large"


# ------------------------------------------------------------------------ validation helpers


def _fail(section: str, key: str, problem: str, value: object) -> ConfigurationError:
    """Build a uniform, user-readable configuration error."""
    return ConfigurationError(
        f"Invalid setting [{section}] {key}: {problem} (got {value!r})",
        user_message=f"Einstellung „{key}“ im Abschnitt „{section}“ ist ungültig: {problem}.",
        details={"section": section, "key": key},
    )


def _check_int(section: str, key: str, value: object, low: int, high: int) -> int:
    """Validate an integer within ``low..high`` (``bool`` is not accepted)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(section, key, "ganze Zahl erwartet", value)
    if not low <= value <= high:
        raise _fail(section, key, f"erlaubt sind {low} bis {high}", value)
    return value


def _check_enum[E: StrEnum](section: str, key: str, value: object, enum_cls: type[E]) -> E:
    """Validate that ``value`` is a member (or the value) of ``enum_cls``."""
    allowed = ", ".join(member.value for member in enum_cls)
    # Non-strings (numbers, None ...) can never be valid enum values.
    if not isinstance(value, str):
        raise _fail(section, key, f"erlaubt sind: {allowed}", value)
    try:
        return enum_cls(value)
    except ValueError:
        raise _fail(section, key, f"erlaubt sind: {allowed}", value) from None


def _check_timezone(value: object) -> str:
    """Validate an IANA timezone name (e.g. ``Europe/Zurich``)."""
    if not isinstance(value, str) or not value:
        raise _fail("display", "timezone", "IANA-Zeitzonenname erwartet", value)
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise _fail(
            "display", "timezone", "unbekannte Zeitzone (z. B. Europe/Zurich)", value
        ) from None
    return value


# --------------------------------------------------------------------------- settings classes


@dataclass(frozen=True, slots=True)
class AgentSettings:
    """Where the local agent API listens (loopback only)."""

    host: str = "127.0.0.1"
    port: int = 8765
    #: Scan briefly for the cube before connecting (Windows connects more reliably).
    scan_before_connect: bool = True
    #: Seconds the pre-connect scan may take.
    scan_timeout_seconds: int = 8

    def __post_init__(self) -> None:
        """Validate host (loopback only), port range and the pre-connect scan."""
        host = self.host.strip().lower() if isinstance(self.host, str) else self.host
        if host not in LOOPBACK_HOSTS:
            raise _fail(
                "agent",
                "host",
                "nur lokale Adressen sind erlaubt (127.0.0.1, ::1, localhost)",
                self.host,
            )
        object.__setattr__(self, "host", host)  # normalised form
        _check_int("agent", "port", self.port, 1024, 65535)
        if not isinstance(self.scan_before_connect, bool):
            raise _fail(
                "agent",
                "scan_before_connect",
                "wahr oder falsch erwartet",
                self.scan_before_connect,
            )
        _check_int("agent", "scan_timeout_seconds", self.scan_timeout_seconds, 2, 30)


@dataclass(frozen=True, slots=True)
class TrackingSettings:
    """Rules for turning orientation events into sessions."""

    debounce_ms: int = 300
    baseline_policy: BaselinePolicy = BaselinePolicy.OBSERVE_ONLY
    disconnect_policy: DisconnectPolicy = DisconnectPolicy.GRACE_THEN_STOP
    #: Grace period (seconds) of ``grace_then_stop``; 0 behaves like ``stop_session``.
    disconnect_grace_seconds: int = 300
    neutral_policy: NeutralPolicy = NeutralPolicy.OBSERVE_ONLY
    mode: TrackingMode = TrackingMode.SINGLE_ACTIVE_TRACKER

    def __post_init__(self) -> None:
        """Validate ranges and coerce strings to enum members."""
        _check_int("tracking", "debounce_ms", self.debounce_ms, 0, 10_000)
        _check_int("tracking", "disconnect_grace_seconds", self.disconnect_grace_seconds, 0, 3600)
        object.__setattr__(
            self,
            "baseline_policy",
            _check_enum("tracking", "baseline_policy", self.baseline_policy, BaselinePolicy),
        )
        object.__setattr__(
            self,
            "disconnect_policy",
            _check_enum("tracking", "disconnect_policy", self.disconnect_policy, DisconnectPolicy),
        )
        object.__setattr__(
            self,
            "neutral_policy",
            _check_enum("tracking", "neutral_policy", self.neutral_policy, NeutralPolicy),
        )
        object.__setattr__(self, "mode", _check_enum("tracking", "mode", self.mode, TrackingMode))


@dataclass(frozen=True, slots=True)
class DisplaySettings:
    """Presentation: language, timezone, colour scheme and font size."""

    language: str = "de"
    #: IANA timezone for *display*; stored times are always UTC. Default is UTC so no
    #: wrong local timezone is guessed; users choose theirs in the settings page.
    timezone: str = "UTC"
    theme: Theme = Theme.LIGHT
    font_size: FontSize = FontSize.NORMAL

    def __post_init__(self) -> None:
        """Validate language and timezone, coerce enum members."""
        if self.language not in SUPPORTED_LANGUAGES:
            raise _fail(
                "display",
                "language",
                f"erlaubt sind: {', '.join(sorted(SUPPORTED_LANGUAGES))}",
                self.language,
            )
        _check_timezone(self.timezone)
        object.__setattr__(self, "theme", _check_enum("display", "theme", self.theme, Theme))
        object.__setattr__(
            self, "font_size", _check_enum("display", "font_size", self.font_size, FontSize)
        )


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    """Log level and rotation of the log file."""

    level: str = "INFO"
    max_bytes: int = 1_000_000
    backup_count: int = 5

    def __post_init__(self) -> None:
        """Validate and normalise the level name."""
        try:
            parse_level(self.level)
        except ConfigurationError:
            raise _fail(
                "logging",
                "level",
                "erlaubt sind: DEBUG, INFO, WARNING, ERROR, CRITICAL",
                self.level,
            ) from None
        object.__setattr__(self, "level", str(self.level).strip().upper())
        _check_int("logging", "max_bytes", self.max_bytes, 10_000, 100 * 1024 * 1024)
        _check_int("logging", "backup_count", self.backup_count, 0, 50)


@dataclass(frozen=True, slots=True)
class NotificationSettings:
    """What the app tells you about on its own (see the attention centre)."""

    #: Warn once when the cube's battery falls below this percentage; 0 switches it off.
    battery_warning_percent: int = 20
    #: Show new questions as Windows toasts (needs the optional ``toast`` package).
    toast: bool = False
    #: No toasts between these times (``HH:MM``, may span midnight); empty = no quiet hours.
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"

    def __post_init__(self) -> None:
        """Validate the values."""
        _check_int("notifications", "battery_warning_percent", self.battery_warning_percent, 0, 90)
        if not isinstance(self.toast, bool):
            raise _fail("notifications", "toast", "wahr oder falsch erwartet", self.toast)
        object.__setattr__(
            self, "quiet_start", _check_clock("notifications", "quiet_start", self.quiet_start)
        )
        object.__setattr__(
            self, "quiet_end", _check_clock("notifications", "quiet_end", self.quiet_end)
        )


@dataclass(frozen=True, slots=True)
class TraySettings:
    """The tray icon next to the clock."""

    #: Show the icon when the optional ``tray`` package is installed.
    enabled: bool = True

    def __post_init__(self) -> None:
        """Validate the value."""
        if not isinstance(self.enabled, bool):
            raise _fail("tray", "enabled", "wahr oder falsch erwartet", self.enabled)


def _check_clock(section: str, key: str, value: object) -> str:
    """Validate ``HH:MM`` (24 h) or the empty text that switches a rule off."""
    if not isinstance(value, str):
        raise _fail(section, key, "Uhrzeit als Text erwartet (z. B. 17:30)", value)
    text = value.strip()
    if not text:
        return ""
    parts = text.split(":")
    if (
        len(parts) != 2
        or not all(p.isdigit() and len(p) in (1, 2) for p in parts)
        or not (0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59)
    ):
        raise _fail(section, key, "Uhrzeit im Format HH:MM erwartet (z. B. 17:30)", value)
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"


@dataclass(frozen=True, slots=True)
class WorkSettings:
    """The working day: automatic stop, idle detection and reminders (all off by default)."""

    #: Time (``HH:MM``) at which a running entry ends; empty = no automatic stop.
    workday_end: str = ""
    #: Working days as comma-separated ISO weekday numbers (1 = Monday ... 7 = Sunday).
    workdays: str = "1,2,3,4,5"
    #: Ask after this many minutes without keyboard/mouse input; 0 = off.
    idle_minutes: int = 0
    #: Remind from this time (``HH:MM``) if no timer runs on a working day; empty = off.
    reminder_no_timer_after: str = ""
    #: Remind when one entry has been running this many hours; 0 = off.
    reminder_running_hours: int = 0

    def __post_init__(self) -> None:
        """Validate every value and normalise the clock times."""
        object.__setattr__(
            self, "workday_end", _check_clock("work", "workday_end", self.workday_end)
        )
        object.__setattr__(
            self,
            "reminder_no_timer_after",
            _check_clock("work", "reminder_no_timer_after", self.reminder_no_timer_after),
        )
        _check_int("work", "idle_minutes", self.idle_minutes, 0, 480)
        _check_int("work", "reminder_running_hours", self.reminder_running_hours, 0, 24)
        if not isinstance(self.workdays, str):
            raise _fail(
                "work", "workdays", "Wochentage als Text erwartet (z. B. 1,2,3,4,5)", self.workdays
            )
        days = [d.strip() for d in self.workdays.split(",") if d.strip()]
        if not days or not all(d in {"1", "2", "3", "4", "5", "6", "7"} for d in days):
            raise _fail(
                "work",
                "workdays",
                "Zahlen von 1 (Montag) bis 7 (Sonntag), mit Komma getrennt",
                self.workdays,
            )
        object.__setattr__(self, "workdays", ",".join(sorted(set(days))))

    def workday_numbers(self) -> frozenset[int]:
        """The working days as ISO weekday numbers."""
        return frozenset(int(d) for d in self.workdays.split(","))


@dataclass(frozen=True, slots=True)
class Settings:
    """Complete application configuration (immutable)."""

    agent: AgentSettings = field(default_factory=AgentSettings)
    tracking: TrackingSettings = field(default_factory=TrackingSettings)
    display: DisplaySettings = field(default_factory=DisplaySettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    work: WorkSettings = field(default_factory=WorkSettings)
    tray: TraySettings = field(default_factory=TraySettings)


#: Section name -> settings class, the single source for parsing and serialising.
_SECTIONS: Final[dict[str, type]] = {
    "agent": AgentSettings,
    "tracking": TrackingSettings,
    "display": DisplaySettings,
    "logging": LoggingSettings,
    "notifications": NotificationSettings,
    "work": WorkSettings,
    "tray": TraySettings,
}


# -------------------------------------------------------------------------------- paths


@dataclass(frozen=True, slots=True)
class AppPaths:
    """All per-user locations used by OctaLedger, derived from one root directory."""

    root: Path

    @property
    def data_dir(self) -> Path:
        """Directory holding the SQLite database."""
        return self.root / "data"

    @property
    def logs_dir(self) -> Path:
        """Directory holding rotating log files."""
        return self.root / "logs"

    @property
    def backups_dir(self) -> Path:
        """Directory for automatic and manual backups."""
        return self.root / "backups"

    @property
    def exports_dir(self) -> Path:
        """Default directory for CSV/JSON exports."""
        return self.root / "exports"

    @property
    def database_file(self) -> Path:
        """Path of the SQLite database file."""
        return self.data_dir / "octaledger.sqlite3"

    @property
    def settings_file(self) -> Path:
        """Path of the user settings file."""
        return self.root / "settings.toml"

    def all_dirs(self) -> tuple[Path, ...]:
        """Return every directory that must exist."""
        return (self.root, self.data_dir, self.logs_dir, self.backups_dir, self.exports_dir)


def resolve_paths(root: Path | None = None, environ: Mapping[str, str] | None = None) -> AppPaths:
    """Determine the per-user data root.

    Precedence: explicit ``root`` argument, then ``OCTALEDGER_DATA_DIR``, then the
    operating-system user data directory. Nothing is created here (see
    :func:`ensure_directories`).

    Args:
        root: Explicit root directory.
        environ: Environment mapping (defaults to ``os.environ``; injectable for tests).

    Returns:
        The resolved, absolute :class:`AppPaths`.

    Raises:
        ConfigurationError: If the chosen root exists but is not a directory.
    """
    env = os.environ if environ is None else environ
    if root is not None:
        chosen = root
    elif env.get(ENV_DATA_DIR, "").strip():
        chosen = Path(env[ENV_DATA_DIR].strip())
    else:
        chosen = Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
    resolved = chosen.expanduser().resolve()
    if resolved.exists() and not resolved.is_dir():
        raise ConfigurationError(
            f"Data root exists but is not a directory: {resolved}",
            user_message=f"Der Datenpfad „{resolved}“ ist kein Ordner.",
            details={"path": str(resolved)},
        )
    logger.debug("Resolved data root: %s", resolved)
    return AppPaths(root=resolved)


def ensure_directories(paths: AppPaths) -> None:
    """Create all application directories (idempotent).

    Raises:
        StorageError: If a directory cannot be created.
    """
    for directory in paths.all_dirs():
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(
                f"Cannot create directory {directory}: {exc}",
                user_message=f"Der Ordner „{directory}“ konnte nicht angelegt werden.",
                details={"path": str(directory)},
            ) from exc
    logger.debug("Application directories ready under %s", paths.root)


# ------------------------------------------------------------------------ load and save


def _build_section(name: str, cls: type, raw: object) -> Any:
    """Create one settings section from a TOML table, rejecting unknown keys."""
    if not isinstance(raw, dict):
        raise ConfigurationError(
            f"Section [{name}] must be a table",
            user_message=f"Der Abschnitt „{name}“ in der Einstellungsdatei ist fehlerhaft.",
            details={"section": name},
        )
    allowed = {f.name for f in dataclasses.fields(cls)}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigurationError(
            f"Unknown key(s) in [{name}]: {', '.join(unknown)}",
            user_message=(
                f"Unbekannte Einstellung(en) im Abschnitt „{name}“: {', '.join(unknown)}. "
                f"Erlaubt: {', '.join(sorted(allowed))}."
            ),
            details={"section": name, "unknown": unknown},
        )
    return cls(**raw)


def settings_from_mapping(data: Mapping[str, Any]) -> Settings:
    """Build validated :class:`Settings` from a nested mapping (parsed TOML).

    Missing sections and keys fall back to defaults.

    Raises:
        ConfigurationError: For unknown sections/keys or invalid values.
    """
    unknown = sorted(set(data) - set(_SECTIONS))
    if unknown:
        raise ConfigurationError(
            f"Unknown section(s): {', '.join(unknown)}",
            user_message=(
                f"Unbekannter Abschnitt in der Einstellungsdatei: {', '.join(unknown)}. "
                f"Erlaubt: {', '.join(_SECTIONS)}."
            ),
            details={"unknown": unknown},
        )
    sections = {
        name: _build_section(name, cls, data[name]) if name in data else cls()
        for name, cls in _SECTIONS.items()
    }
    return Settings(**sections)


def settings_to_mapping(settings: Settings) -> dict[str, dict[str, Any]]:
    """Convert settings to a plain nested dict (enums become their string values)."""
    result: dict[str, dict[str, Any]] = {}
    for name in _SECTIONS:
        section = getattr(settings, name)
        result[name] = {
            f.name: (v.value if isinstance(v := getattr(section, f.name), StrEnum) else v)
            for f in dataclasses.fields(section)
        }
    return result


def apply_env_overrides(settings: Settings, environ: Mapping[str, str] | None = None) -> Settings:
    """Apply ``OCTALEDGER_HOST`` / ``OCTALEDGER_PORT`` on top of ``settings``.

    Raises:
        ConfigurationError: If the port is not a number or a value fails validation.
    """
    env = os.environ if environ is None else environ
    host = env.get(ENV_HOST, "").strip() or settings.agent.host
    port: int = settings.agent.port
    raw_port = env.get(ENV_PORT, "").strip()
    if raw_port:
        try:
            port = int(raw_port)
        except ValueError:
            raise _fail(
                "agent", "port", "ganze Zahl erwartet (Umgebungsvariable)", raw_port
            ) from None
    if host == settings.agent.host and port == settings.agent.port:
        return settings
    logger.info("Agent address overridden by environment variables")
    return dataclasses.replace(settings, agent=AgentSettings(host=host, port=port))


def load_settings(settings_file: Path, environ: Mapping[str, str] | None = None) -> Settings:
    """Load settings from ``settings_file`` and apply environment overrides.

    A missing file yields defaults (first start). A file that exists but is unreadable,
    not valid TOML or contains invalid values raises an error - it is never ignored.

    Args:
        settings_file: Path of ``settings.toml``.
        environ: Environment mapping (defaults to ``os.environ``).

    Returns:
        The validated settings.

    Raises:
        ConfigurationError: On read, parse or validation problems.
    """
    if not settings_file.exists():
        logger.info("No settings file at %s, using defaults", settings_file)
        return apply_env_overrides(Settings(), environ)
    text = read_text_limited(
        settings_file,
        encoding="utf-8-sig",
        max_bytes=MAX_SETTINGS_BYTES,
        error_cls=ConfigurationError,
    )
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(
            f"Invalid TOML in {settings_file}: {exc}",
            user_message=(
                f"Die Einstellungsdatei „{settings_file.name}“ ist fehlerhaft ({exc}). "
                "Bitte korrigieren oder löschen (dann gelten die Standardwerte)."
            ),
            details={"path": str(settings_file)},
        ) from exc
    settings = settings_from_mapping(data)
    logger.info("Loaded settings from %s", settings_file)
    return apply_env_overrides(settings, environ)


def _toml_value(value: Any) -> str:
    """Render one scalar as a TOML literal (strings use JSON-compatible escaping)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def settings_to_toml(settings: Settings) -> str:
    """Serialise settings to TOML text (stdlib has no TOML writer)."""
    lines = ["# OctaLedger settings. Edit with care; invalid values stop the program.", ""]
    for name, values in settings_to_mapping(settings).items():
        lines.append(f"[{name}]")
        lines.extend(f"{key} = {_toml_value(value)}" for key, value in values.items())
        lines.append("")
    return "\n".join(lines)


def save_settings(settings: Settings, settings_file: Path) -> None:
    """Atomically write ``settings`` to ``settings_file``.

    Raises:
        StorageError: If the file cannot be written (previous file stays intact).
    """
    atomic_write_text(settings_file, settings_to_toml(settings))
    logger.info("Saved settings to %s", settings_file)


class SettingsStore:
    """Thread-safe holder of the current settings, persisted in ``settings.toml``.

    The API threads and the dashboard-facing code read the settings while the user may change
    them at the same time, so access goes through a lock. ``update`` validates (settings are
    self-validating), writes the file atomically **first** and only then replaces the in-memory
    value, so a failed save never leaves memory and file disagreeing.
    """

    def __init__(self, settings_file: Path, initial: Settings | None = None) -> None:
        """Create the store.

        Args:
            settings_file: Path of ``settings.toml``.
            initial: Starting value; default is loaded from the file (defaults if missing).
        """
        self._file = settings_file
        self._lock = threading.Lock()
        self._settings = initial if initial is not None else load_settings(settings_file)

    @property
    def settings(self) -> Settings:
        """The current settings (immutable snapshot)."""
        with self._lock:
            return self._settings

    def update(self, new: Settings) -> Settings:
        """Persist and activate ``new``.

        Raises:
            StorageError: If the file cannot be written (the old settings stay active).
        """
        with self._lock:
            save_settings(new, self._file)
            self._settings = new
        return new

    def reload(self) -> Settings:
        """Re-read the file (e.g. after manual editing)."""
        loaded = load_settings(self._file)
        with self._lock:
            self._settings = loaded
        return loaded
