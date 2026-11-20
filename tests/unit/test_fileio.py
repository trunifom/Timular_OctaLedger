"""Tests for atomic writes and size-limited reads."""

import os
from pathlib import Path

import pytest

from octaledger.core import fileio
from octaledger.core.errors import ExportError, ImportDataError, StorageError
from octaledger.core.fileio import (
    atomic_write_bytes,
    atomic_write_text,
    read_bytes_limited,
    read_text_limited,
)


def _leftover_temp_files(directory: Path) -> list[str]:
    """Return names of orphaned temporary files in ``directory``."""
    return [p.name for p in directory.iterdir() if p.name.endswith(".tmp")]


# ------------------------------------------------------------------------------- writes


def test_write_creates_file_and_parent(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "file.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_write_replaces_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert _leftover_temp_files(tmp_path) == []


def test_write_bytes_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "data.bin"
    atomic_write_bytes(target, b"\x00\x01\xff")
    assert target.read_bytes() == b"\x00\x01\xff"


def test_text_encoding_with_bom(tmp_path: Path) -> None:
    target = tmp_path / "excel.csv"
    atomic_write_text(target, "a;b\r\n", encoding="utf-8-sig")
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    # Newlines are written exactly as given (no translation to the OS default).
    assert target.read_bytes().endswith(b"a;b\r\n")


def test_unencodable_text_raises_given_error(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        atomic_write_text(tmp_path / "x.txt", "ü", encoding="ascii", error_cls=ExportError)
    assert not (tmp_path / "x.txt").exists()


def test_unknown_encoding_raises(tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        atomic_write_text(tmp_path / "x.txt", "a", encoding="no-such-encoding")


def test_failed_replace_keeps_old_file_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "keep.txt"
    target.write_text("original", encoding="utf-8")

    def broken_replace(src: str, dst: Path) -> None:
        raise OSError("disk exploded")

    monkeypatch.setattr(fileio.os, "replace", broken_replace)
    with pytest.raises(StorageError) as info:
        atomic_write_text(target, "new content")
    assert isinstance(info.value.__cause__, OSError)
    assert target.read_text(encoding="utf-8") == "original"  # old version intact
    assert _leftover_temp_files(tmp_path) == []  # no orphan


def test_write_to_directory_path_fails_with_error_class(tmp_path: Path) -> None:
    directory = tmp_path / "dir"
    directory.mkdir()
    with pytest.raises(ExportError) as info:
        atomic_write_text(directory, "x", error_cls=ExportError)
    assert info.value.error_code == "OL-DATA-001"
    assert _leftover_temp_files(tmp_path) == []


def test_write_below_regular_file_fails(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(StorageError):
        atomic_write_text(blocker / "child.txt", "x")


def test_error_contains_user_message_and_path(tmp_path: Path) -> None:
    directory = tmp_path / "dir"
    directory.mkdir()
    with pytest.raises(StorageError) as info:
        atomic_write_text(directory, "x")
    assert "dir" in info.value.user_message
    assert info.value.details["path"] == str(directory)


# -------------------------------------------------------------------------------- reads


def test_read_bytes_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "f.bin"
    target.write_bytes(b"abc")
    assert read_bytes_limited(target) == b"abc"


def test_read_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ImportDataError) as info:
        read_bytes_limited(tmp_path / "missing.json")
    assert info.value.error_code == "OL-DATA-002"
    assert "missing.json" in info.value.user_message


def test_read_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ImportDataError):
        read_bytes_limited(tmp_path)


def test_read_too_large_is_rejected_before_reading(tmp_path: Path) -> None:
    target = tmp_path / "big.bin"
    target.write_bytes(b"x" * 11)
    with pytest.raises(ImportDataError) as info:
        read_bytes_limited(target, max_bytes=10)
    assert info.value.details["size"] == 11


def test_read_exactly_at_limit_is_allowed(tmp_path: Path) -> None:
    target = tmp_path / "ok.bin"
    target.write_bytes(b"x" * 10)
    assert read_bytes_limited(target, max_bytes=10) == b"x" * 10


def test_read_detects_file_growth_after_stat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "grow.bin"
    target.write_bytes(b"x" * 20)
    real_stat = Path.stat

    def lying_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:
        # Pretend the file is small although it already contains 20 bytes.
        result = real_stat(self, *args, **kwargs)  # type: ignore[arg-type]
        if self == target:
            return os.stat_result((result.st_mode, 0, 0, 1, 0, 0, 5, 0, 0, 0))
        return result

    monkeypatch.setattr(Path, "stat", lying_stat)
    with pytest.raises(ImportDataError):
        read_bytes_limited(target, max_bytes=10)


def test_read_text_decodes_utf8_with_bom(tmp_path: Path) -> None:
    target = tmp_path / "t.csv"
    target.write_bytes("﻿äöü".encode())
    assert read_text_limited(target, encoding="utf-8-sig") == "äöü"


def test_read_text_invalid_encoding(tmp_path: Path) -> None:
    target = tmp_path / "bad.txt"
    target.write_bytes(b"\xff\xfe\xfa")
    with pytest.raises(ImportDataError) as info:
        read_text_limited(target)
    assert isinstance(info.value.__cause__, UnicodeDecodeError)


def test_read_text_propagates_size_limit(tmp_path: Path) -> None:
    target = tmp_path / "t.txt"
    target.write_text("hello world", encoding="utf-8")
    with pytest.raises(ImportDataError):
        read_text_limited(target, max_bytes=3)
