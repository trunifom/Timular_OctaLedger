"""Tests for the secret store: separate file, no leaks, atomic and consistent."""

import json
import logging
import os
import stat
from pathlib import Path

import pytest

from octaledger.core.errors import StorageError
from octaledger.core.logging import clear_registered_secrets, redact
from octaledger.core.secrets import SecretStore


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear_registered_secrets()


def test_values_survive_a_restart_and_names_never_show_values(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    store = SecretStore(path)
    store.update("hue-1", {"app_key": "geheim-123", "other": "x"})
    store.update("mqtt-1", {"password": "pw"})
    reopened = SecretStore(path)
    assert reopened.get("hue-1") == {"app_key": "geheim-123", "other": "x"}
    assert reopened.names("hue-1") == ("app_key", "other")
    assert "geheim-123" not in repr(reopened.names("hue-1"))
    assert reopened.get("ghost") == {} and reopened.names("ghost") == ()


def test_update_merges_and_an_empty_value_removes_one_secret(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "secrets.json")
    store.update("a", {"one": "1", "two": "2"})
    store.update("a", {"two": "22", "three": "3"})
    assert store.get("a") == {"one": "1", "two": "22", "three": "3"}
    store.update("a", {"one": ""})
    assert store.names("a") == ("three", "two")
    store.update("a", {"two": "", "three": ""})
    assert store.names("a") == ()
    assert json.loads((tmp_path / "secrets.json").read_text(encoding="utf-8"))["secrets"] == {}


def test_delete_forgets_everything_of_an_owner(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "secrets.json")
    store.update("a", {"k": "v"})
    store.update("b", {"k": "w"})
    store.delete("a")
    store.delete("ghost")  # no error
    assert SecretStore(tmp_path / "secrets.json").get("a") == {}
    assert SecretStore(tmp_path / "secrets.json").get("b") == {"k": "w"}


def test_get_returns_a_copy(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "secrets.json")
    store.update("a", {"k": "v"})
    store.get("a")["k"] = "changed"
    assert store.get("a") == {"k": "v"}


def test_stored_and_loaded_secrets_are_masked_in_log_text(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    SecretStore(path).update("a", {"token": "super-geheimer-wert"})
    clear_registered_secrets()  # a new process: nothing registered yet
    assert "super-geheimer-wert" in redact("x super-geheimer-wert y")
    SecretStore(path)  # loading registers the values again
    assert "super-geheimer-wert" not in redact("Fehler bei super-geheimer-wert")


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_the_file_is_readable_by_the_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    SecretStore(path).update("a", {"k": "v"})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"version": 1}',
        '{"version": 9, "secrets": {}}',
        '{"version": 1, "secrets": 5}',
    ],
)
def test_a_damaged_file_gives_a_clear_error_without_leaking_its_content(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "secrets.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(StorageError) as info:
        SecretStore(path)
    assert "secrets.json" in info.value.user_message
    assert content not in info.value.message


def test_a_failed_write_leaves_memory_and_file_consistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "secrets.json"
    store = SecretStore(path)
    store.update("a", {"k": "v"})

    def broken(*_args: object, **_kwargs: object) -> None:
        raise StorageError("disk full")

    monkeypatch.setattr("octaledger.core.secrets.atomic_write_text", broken)
    with pytest.raises(StorageError):
        store.update("a", {"k": "new", "x": "y"})
    with pytest.raises(StorageError):
        store.delete("a")
    assert store.get("a") == {"k": "v"}  # memory did not move ahead of the file
    monkeypatch.undo()
    assert SecretStore(path).get("a") == {"k": "v"}


def test_overlong_values_are_rejected(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "secrets.json")
    with pytest.raises(StorageError):
        store.update("a", {"k": "x" * 3000})
    assert store.names("a") == ()


def test_log_lines_from_the_store_do_not_contain_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        store = SecretStore(tmp_path / "secrets.json")
        store.update("a", {"k": "wert-der-nie-im-log-stehen-darf"})
        store.delete("a")
    assert "wert-der-nie-im-log-stehen-darf" not in caplog.text
