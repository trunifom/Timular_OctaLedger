"""Safe file input/output primitives (atomic writes, size-limited reads).

Responsibility
--------------
Every place that writes a user-visible file (settings, CSV export, JSON backup) or reads
an untrusted file (import, restore) goes through this module so that the same guarantees
hold everywhere:

* **Atomic writes** - data is first written to a temporary file in the *same directory*,
  flushed and ``fsync``-ed, then moved over the target with :func:`os.replace`, which is
  atomic on Windows and POSIX (retried briefly if Windows reports the target as locked).
  A crash or full disk can therefore never leave a
  half-written target; the previous version stays intact.
* **Bounded reads** - untrusted input is size-limited before it is read, so a huge or
  malicious file cannot exhaust memory.
* **Error translation** - ``OSError`` never leaks out; it is converted to an
  :class:`~octaledger.core.errors.OctaLedgerError` subclass chosen by the caller, with the
  original exception preserved as ``__cause__``.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

from octaledger.core.errors import ImportDataError, OctaLedgerError, StorageError

logger = logging.getLogger(__name__)

#: Default upper bound for untrusted input files (50 MiB).
DEFAULT_MAX_READ_BYTES = 50 * 1024 * 1024

#: Waits (seconds) between attempts to move the temp file over a target that is briefly locked.
_REPLACE_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.4)


def _replace_with_retry(source: str, target: Path) -> None:
    """``os.replace`` that waits briefly while Windows reports the target as in use.

    Windows raises ``PermissionError`` (WinError 5/32) when another handle on the target is open
    for a moment: a reader, a second writer, a virus scanner or an indexer. Such a lock is short,
    so a few short retries almost always succeed; a real permission problem still fails (and is
    reported) after about 0.8 s.
    """
    for delay in _REPLACE_RETRY_DELAYS:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            logger.debug("%s is locked, retrying in %.2f s", target, delay)
            time.sleep(delay)
    os.replace(source, target)  # last attempt: a persistent failure propagates


def atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    error_cls: type[OctaLedgerError] = StorageError,
) -> None:
    """Atomically replace ``path`` with ``data``.

    The parent directory is created when missing. On any failure the temporary file is
    removed and the previous content of ``path`` (if any) is left untouched.

    Args:
        path: Target file.
        data: Complete new content.
        error_cls: Error class raised on failure (e.g. ``ExportError`` for exports).

    Raises:
        OctaLedgerError: An instance of ``error_cls`` wrapping the underlying ``OSError``.
    """
    temp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # The temp file lives next to the target: os.replace is only atomic within one
        # filesystem. delete=False because we move it ourselves.
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temp_name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())  # force data to disk before the swap
        _replace_with_retry(temp_name, path)
        temp_name = None  # ownership transferred to the target path
        logger.debug("Atomically wrote %d bytes to %s", len(data), path)
    except OSError as exc:
        raise error_cls(
            f"Cannot write file {path}: {exc}",
            user_message=(
                f"Die Datei „{path.name}“ konnte nicht gespeichert werden "
                "(Rechte, Speicherplatz oder Pfad prüfen)."
            ),
            details={"path": str(path)},
        ) from exc
    finally:
        if temp_name is not None:
            # Best-effort cleanup of the orphaned temporary file.
            try:
                os.unlink(temp_name)
            except OSError:
                logger.warning("Could not remove temporary file %s", temp_name)


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    error_cls: type[OctaLedgerError] = StorageError,
) -> None:
    """Atomically replace ``path`` with ``text`` encoded as ``encoding``.

    Newlines are written exactly as contained in ``text`` (no translation), so callers
    such as the CSV writer control line endings themselves.

    Args:
        path: Target file.
        text: Complete new content.
        encoding: Text encoding, e.g. ``"utf-8"`` or ``"utf-8-sig"`` (Excel-friendly BOM).
        error_cls: Error class raised on failure.

    Raises:
        OctaLedgerError: An instance of ``error_cls`` if encoding or writing fails.
    """
    try:
        data = text.encode(encoding)
    except (UnicodeEncodeError, LookupError) as exc:
        raise error_cls(
            f"Cannot encode text for {path} as {encoding}: {exc}",
            details={"path": str(path), "encoding": encoding},
        ) from exc
    atomic_write_bytes(path, data, error_cls=error_cls)


def read_bytes_limited(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_READ_BYTES,
    error_cls: type[OctaLedgerError] = ImportDataError,
) -> bytes:
    """Read a regular file, refusing anything larger than ``max_bytes``.

    Args:
        path: File to read.
        max_bytes: Maximum accepted size in bytes.
        error_cls: Error class raised on failure.

    Returns:
        The complete file content.

    Raises:
        OctaLedgerError: An instance of ``error_cls`` if the path is missing, not a
            regular file, too large or unreadable.
    """
    try:
        if not path.is_file():
            raise error_cls(
                f"Not a readable file: {path}",
                user_message=f"Die Datei „{path.name}“ wurde nicht gefunden.",
                details={"path": str(path)},
            )
        size = path.stat().st_size
        if size > max_bytes:
            raise error_cls(
                f"File too large: {size} bytes (limit {max_bytes})",
                user_message=(
                    f"Die Datei „{path.name}“ ist zu groß "
                    f"({size // (1024 * 1024)} MB, erlaubt {max_bytes // (1024 * 1024)} MB)."
                ),
                details={"path": str(path), "size": size, "max_bytes": max_bytes},
            )
        # Read at most max_bytes + 1 so a file that grows after stat() is still caught.
        with path.open("rb") as handle:
            data = handle.read(max_bytes + 1)
    except OSError as exc:
        raise error_cls(
            f"Cannot read file {path}: {exc}",
            user_message=f"Die Datei „{path.name}“ konnte nicht gelesen werden.",
            details={"path": str(path)},
        ) from exc
    if len(data) > max_bytes:
        raise error_cls(
            f"File grew beyond limit while reading: {path}",
            details={"path": str(path), "max_bytes": max_bytes},
        )
    logger.debug("Read %d bytes from %s", len(data), path)
    return data


def read_text_limited(
    path: Path,
    *,
    encoding: str = "utf-8",
    max_bytes: int = DEFAULT_MAX_READ_BYTES,
    error_cls: type[OctaLedgerError] = ImportDataError,
) -> str:
    """Read a text file with a size limit and decode it strictly.

    Args:
        path: File to read.
        encoding: Expected text encoding (a UTF-8 BOM is handled by ``utf-8-sig``).
        max_bytes: Maximum accepted size in bytes.
        error_cls: Error class raised on failure.

    Returns:
        The decoded text.

    Raises:
        OctaLedgerError: An instance of ``error_cls`` on read or decode failure.
    """
    data = read_bytes_limited(path, max_bytes=max_bytes, error_cls=error_cls)
    try:
        return data.decode(encoding)
    except UnicodeDecodeError as exc:
        raise error_cls(
            f"File {path} is not valid {encoding}: {exc}",
            user_message=f"Die Datei „{path.name}“ hat ein ungültiges Textformat.",
            details={"path": str(path), "encoding": encoding},
        ) from exc
