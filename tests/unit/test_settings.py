"""Tests for application paths and validated settings (load, save, overrides)."""

import dataclasses
from pathlib import Path

import pytest

from octaledger.core.errors import ConfigurationError, StorageError
from octaledger.core.settings import (
    ENV_DATA_DIR,
    ENV_HOST,
    ENV_PORT,
    AgentSettings,
    AppPaths,
    BaselinePolicy,
    DisplaySettings,
    FontSize,
    LoggingSettings,
    Settings,
    Theme,
    TrackingSettings,
    apply_env_overrides,
    ensure_directories,
    load_settings,
    resolve_paths,
    save_settings,
    settings_from_mapping,
    settings_to_mapping,
    settings_to_toml,
)

# ---------------------------------------------------------------------------------- paths


def test_explicit_root_wins_over_env(tmp_path: Path) -> None:
    paths = resolve_paths(tmp_path / "explicit", {ENV_DATA_DIR: str(tmp_path / "env")})
    assert paths.root == (tmp_path / "explicit").resolve()


def test_env_root_used_when_no_argument(tmp_path: Path) -> None:
    paths = resolve_paths(environ={ENV_DATA_DIR: str(tmp_path / "env")})
    assert paths.root == (tmp_path / "env").resolve()


def test_blank_env_is_treated_as_unset() -> None:
    paths = resolve_paths(environ={ENV_DATA_DIR: "   "})
    assert "OctaLedger" in str(paths.root)  # platformdirs default


def test_default_root_is_in_user_profile_not_project() -> None:
    paths = resolve_paths(environ={})
    assert "OctaLedger" in paths.root.parts[-1]
    assert not str(paths.root).startswith(str(Path.cwd()))


def test_root_that_is_a_file_is_rejected(tmp_path: Path) -> None:
    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        resolve_paths(file_path)


def test_derived_paths_layout(tmp_path: Path) -> None:
    paths = AppPaths(root=tmp_path)
    assert paths.database_file == tmp_path / "data" / "octaledger.sqlite3"
    assert paths.settings_file == tmp_path / "settings.toml"
    assert {p.name for p in paths.all_dirs()} == {
        tmp_path.name,
        "data",
        "logs",
        "backups",
        "exports",
    }


def test_ensure_directories_is_idempotent(tmp_path: Path) -> None:
    paths = AppPaths(root=tmp_path / "root")
    ensure_directories(paths)
    ensure_directories(paths)
    assert all(d.is_dir() for d in paths.all_dirs())


def test_ensure_directories_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(StorageError):
        ensure_directories(AppPaths(root=blocker / "root"))


# ------------------------------------------------------------------------------- defaults


def test_defaults_match_documented_values() -> None:
    settings = Settings()
    assert settings.agent.host == "127.0.0.1" and settings.agent.port == 8765
    assert settings.tracking.debounce_ms == 300
    assert settings.tracking.baseline_policy is BaselinePolicy.OBSERVE_ONLY
    assert settings.display.theme is Theme.LIGHT
    assert settings.display.font_size is FontSize.NORMAL
    assert settings.display.timezone == "UTC"
    assert settings.logging.level == "INFO"


def test_settings_are_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        Settings().agent.port = 1  # type: ignore[misc]


def test_replace_revalidates() -> None:
    settings = Settings()
    updated = dataclasses.replace(settings.display, theme=Theme.DARK)
    assert updated.theme is Theme.DARK
    with pytest.raises(ConfigurationError):
        dataclasses.replace(settings.display, timezone="Mars/Olympus")


# ------------------------------------------------------------------------------ validation


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.org", "", "::"])
def test_non_loopback_host_rejected(host: str) -> None:
    with pytest.raises(ConfigurationError) as info:
        AgentSettings(host=host)
    assert info.value.details["key"] == "host"


@pytest.mark.parametrize("host", ["127.0.0.1", "LOCALHOST", " ::1 "])
def test_loopback_host_accepted_and_normalised(host: str) -> None:
    assert AgentSettings(host=host).host == host.strip().lower()


@pytest.mark.parametrize("port", [0, 80, 1023, 65536, -1, True, "8765", 1.5])
def test_invalid_port_rejected(port: object) -> None:
    with pytest.raises(ConfigurationError):
        AgentSettings(port=port)  # type: ignore[arg-type]


@pytest.mark.parametrize("port", [1024, 8765, 65535])
def test_valid_port_accepted(port: int) -> None:
    assert AgentSettings(port=port).port == port


@pytest.mark.parametrize("value", [-1, 10_001, "300", None, False])
def test_invalid_debounce_rejected(value: object) -> None:
    with pytest.raises(ConfigurationError):
        TrackingSettings(debounce_ms=value)  # type: ignore[arg-type]


def test_enum_strings_are_coerced_and_invalid_rejected() -> None:
    tracking = TrackingSettings(baseline_policy="adopt_current")  # type: ignore[arg-type]
    assert tracking.baseline_policy is BaselinePolicy.ADOPT_CURRENT
    with pytest.raises(ConfigurationError) as info:
        TrackingSettings(baseline_policy="guess")  # type: ignore[arg-type]
    assert "observe_only" in info.value.user_message  # lists allowed values


@pytest.mark.parametrize("tz", ["Europe/Zurich", "UTC", "America/New_York"])
def test_valid_timezone(tz: str) -> None:
    assert DisplaySettings(timezone=tz).timezone == tz


@pytest.mark.parametrize("tz", ["", "Mars/Olympus", "../etc/passwd", 5])
def test_invalid_timezone(tz: object) -> None:
    with pytest.raises(ConfigurationError):
        DisplaySettings(timezone=tz)  # type: ignore[arg-type]


def test_unsupported_language_rejected() -> None:
    with pytest.raises(ConfigurationError):
        DisplaySettings(language="xx")


def test_logging_level_normalised_and_validated() -> None:
    assert LoggingSettings(level="debug").level == "DEBUG"
    with pytest.raises(ConfigurationError):
        LoggingSettings(level="loud")


@pytest.mark.parametrize("kwargs", [{"max_bytes": 5}, {"backup_count": -1}, {"backup_count": 51}])
def test_invalid_logging_rotation(kwargs: dict[str, int]) -> None:
    with pytest.raises(ConfigurationError):
        LoggingSettings(**kwargs)


# --------------------------------------------------------------------------- from mapping


def test_empty_mapping_gives_defaults() -> None:
    assert settings_from_mapping({}) == Settings()


def test_partial_mapping_keeps_other_defaults() -> None:
    settings = settings_from_mapping({"display": {"theme": "dark"}})
    assert settings.display.theme is Theme.DARK
    assert settings.display.font_size is FontSize.NORMAL
    assert settings.agent == AgentSettings()


def test_unknown_section_rejected() -> None:
    with pytest.raises(ConfigurationError) as info:
        settings_from_mapping({"agnet": {}})
    assert "agnet" in info.value.user_message


def test_unknown_key_rejected_with_hint() -> None:
    with pytest.raises(ConfigurationError) as info:
        settings_from_mapping({"agent": {"prot": 1}})
    assert "prot" in info.value.user_message and "port" in info.value.user_message


def test_section_must_be_table() -> None:
    with pytest.raises(ConfigurationError):
        settings_from_mapping({"agent": 5})


def test_mapping_roundtrip() -> None:
    original = Settings(display=DisplaySettings(timezone="Europe/Zurich", theme=Theme.DARK))
    assert settings_from_mapping(settings_to_mapping(original)) == original


# --------------------------------------------------------------------------- env overrides


def test_env_overrides_host_and_port() -> None:
    result = apply_env_overrides(Settings(), {ENV_HOST: "localhost", ENV_PORT: "9000"})
    assert result.agent == AgentSettings(host="localhost", port=9000)


def test_env_without_values_returns_same_object() -> None:
    settings = Settings()
    assert apply_env_overrides(settings, {}) is settings


def test_env_invalid_port_text() -> None:
    with pytest.raises(ConfigurationError):
        apply_env_overrides(Settings(), {ENV_PORT: "abc"})


def test_env_non_loopback_host_rejected() -> None:
    with pytest.raises(ConfigurationError):
        apply_env_overrides(Settings(), {ENV_HOST: "0.0.0.0"})


# ---------------------------------------------------------------------- load / save files


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "none.toml", {}) == Settings()


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    original = Settings(
        agent=AgentSettings(port=9001),
        tracking=TrackingSettings(debounce_ms=450, baseline_policy=BaselinePolicy.ADOPT_CURRENT),
        display=DisplaySettings(
            timezone="Europe/Zurich", theme=Theme.DARK, font_size=FontSize.LARGE
        ),
        logging=LoggingSettings(level="DEBUG", backup_count=3),
    )
    save_settings(original, target)
    assert load_settings(target, {}) == original


def test_saved_file_is_readable_text(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    save_settings(Settings(), target)
    text = target.read_text(encoding="utf-8")
    assert "[agent]" in text and 'host = "127.0.0.1"' in text and "port = 8765" in text


def test_load_applies_env_override_after_file(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    save_settings(Settings(agent=AgentSettings(port=9001)), target)
    assert load_settings(target, {ENV_PORT: "9002"}).agent.port == 9002


def test_invalid_toml_is_reported_not_ignored(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    target.write_text("[agent\nport = ", encoding="utf-8")
    with pytest.raises(ConfigurationError) as info:
        load_settings(target, {})
    assert "settings.toml" in info.value.user_message


def test_invalid_value_in_file_reported(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    target.write_text("[agent]\nport = 80\n", encoding="utf-8")
    with pytest.raises(ConfigurationError) as info:
        load_settings(target, {})
    assert info.value.details == {"section": "agent", "key": "port"}


def test_file_with_bom_is_accepted(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    target.write_bytes(b'\xef\xbb\xbf[display]\ntheme = "dark"\n')
    assert load_settings(target, {}).display.theme is Theme.DARK


def test_non_utf8_file_reported(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    target.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ConfigurationError):
        load_settings(target, {})


def test_oversized_file_rejected(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    target.write_text("# " + "x" * (1024 * 1024 + 10), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_settings(target, {})


def test_save_failure_raises_storage_error(tmp_path: Path) -> None:
    directory = tmp_path / "dir"
    directory.mkdir()
    with pytest.raises(StorageError):
        save_settings(Settings(), directory)


def test_toml_text_is_stable(tmp_path: Path) -> None:
    assert settings_to_toml(Settings()) == settings_to_toml(Settings())


@pytest.mark.parametrize("value", [5, None, 1.5, ["observe_only"]])
def test_non_string_enum_value_rejected(value: object) -> None:
    with pytest.raises(ConfigurationError):
        TrackingSettings(baseline_policy=value)  # type: ignore[arg-type]


# ------------------------------------------------------------------------ SettingsStore


def test_store_loads_updates_and_persists(tmp_path: Path) -> None:
    from octaledger.core.settings import SettingsStore

    target = tmp_path / "settings.toml"
    store = SettingsStore(target)
    assert store.settings == Settings()
    changed = dataclasses.replace(
        store.settings, display=DisplaySettings(timezone="Europe/Zurich", theme=Theme.DARK)
    )
    assert store.update(changed) == changed
    assert SettingsStore(target).settings == changed  # survives a restart


def test_store_failed_save_keeps_old_value(tmp_path: Path) -> None:
    from octaledger.core.settings import SettingsStore

    directory = tmp_path / "dir"
    directory.mkdir()
    store = SettingsStore(directory, Settings())  # a directory cannot be written as a file
    with pytest.raises(StorageError):
        store.update(dataclasses.replace(Settings(), display=DisplaySettings(theme=Theme.DARK)))
    assert store.settings == Settings()


def test_store_reload_picks_up_manual_edit(tmp_path: Path) -> None:
    from octaledger.core.settings import SettingsStore

    target = tmp_path / "settings.toml"
    store = SettingsStore(target)
    target.write_text('[display]\ntheme = "dark"\n', encoding="utf-8")
    assert store.reload().display.theme is Theme.DARK and store.settings.display.theme is Theme.DARK
    target.write_text("[display\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        store.reload()
    assert store.settings.display.theme is Theme.DARK  # a broken file does not replace memory
