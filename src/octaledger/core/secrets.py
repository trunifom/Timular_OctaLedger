"""Storage for secrets of integrations (tokens, passwords) - separate from every other data.

Responsibility
--------------
An integration needs credentials (a Home Assistant token, an MQTT password, a Hue application
key). They must never end up where ordinary data goes, so they live in **one small file in the
user profile** and nowhere else:

* not in the SQLite database and therefore **not in a backup** (restoring on another computer
  means entering the credentials again - a deliberate trade-off),
* not in any API answer (the API only reports *which* secrets are set),
* not in the log: every value is registered with :func:`~octaledger.core.logging.register_secret`
  the moment it is stored or loaded, so any log line containing it is masked.

File: ``secrets.json`` next to the database, written atomically with
:mod:`octaledger.core.fileio`. On POSIX systems the file is made readable for the owner only; on
Windows the user profile folder is already private to the user.

Limits: the file is **not encrypted** (anyone who can read the user's profile can read it, just
like the API token file). Encryption with the Windows credential vault is a possible later step.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from octaledger.core.errors import StorageError
from octaledger.core.fileio import atomic_write_text, read_text_limited
from octaledger.core.logging import register_secret

logger = logging.getLogger(__name__)

SECRETS_FILE_NAME: Final = "secrets.json"
_FORMAT_VERSION: Final = 1
_MAX_BYTES: Final = 1024 * 1024
_MAX_VALUE_LENGTH: Final = 2000


class SecretStore:
    """Thread-safe store of ``owner id -> {secret name -> value}``.

    The owner is the id of an integration. All methods are safe to call from the API threads
    and the dispatcher thread at the same time.
    """

    def __init__(self, path: Path) -> None:
        """Bind to ``path`` (the file is created on the first write)."""
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, str]] = {}
        self._load()

    # ------------------------------------------------------------------ persistence

    def _load(self) -> None:
        if not self._path.exists():
            return
        text = read_text_limited(self._path, max_bytes=_MAX_BYTES, error_cls=StorageError)
        try:
            document = json.loads(text)
            raw = document["secrets"]
            if document.get("version") != _FORMAT_VERSION or not isinstance(raw, dict):
                raise ValueError("unexpected structure")
            data = {
                str(owner): {str(name): str(value) for name, value in values.items()}
                for owner, values in raw.items()
            }
        except (ValueError, KeyError, AttributeError, TypeError) as exc:
            # Never include the file content in the message: it holds the secrets.
            raise StorageError(
                f"The secrets file {self._path.name} is unreadable: {type(exc).__name__}",
                user_message=(
                    "Die Datei mit den Zugangsdaten ist beschädigt. Löschen Sie „secrets.json“ "
                    "im Datenordner und geben Sie die Zugangsdaten Ihrer Verbindungen neu ein."
                ),
                details={"path": str(self._path)},
            ) from exc
        self._data = data
        for values in data.values():
            for value in values.values():
                register_secret(value)

    def _save(self) -> None:
        document = {"version": _FORMAT_VERSION, "secrets": self._data}
        atomic_write_text(
            self._path,
            json.dumps(document, ensure_ascii=False, indent=1),
            error_cls=StorageError,
        )
        try:
            os.chmod(self._path, 0o600)  # owner only where the platform supports it
        except OSError:
            logger.debug("Could not restrict the permissions of the secrets file", exc_info=True)

    # ------------------------------------------------------------------------- access

    def names(self, owner_id: str) -> tuple[str, ...]:
        """Names of the secrets stored for ``owner_id`` (never their values)."""
        with self._lock:
            return tuple(sorted(self._data.get(owner_id, {})))

    def get(self, owner_id: str) -> dict[str, str]:
        """Return a copy of all secrets of ``owner_id`` (empty if none)."""
        with self._lock:
            return dict(self._data.get(owner_id, {}))

    def update(self, owner_id: str, values: Mapping[str, str]) -> None:
        """Set the given secrets of ``owner_id`` (others are kept); an empty value removes one.

        Raises:
            StorageError: If a value is too long or the file cannot be written; the previous
                content stays intact in that case.
        """
        for name, value in values.items():
            if len(value) > _MAX_VALUE_LENGTH:
                raise StorageError(
                    f"Secret {name!r} is longer than {_MAX_VALUE_LENGTH} characters",
                    user_message="Ein Zugangsdatum ist zu lang.",
                )
        with self._lock:
            merged = dict(self._data.get(owner_id, {}))
            for name, value in values.items():
                if value:
                    merged[name] = value
                    register_secret(value)
                else:
                    merged.pop(name, None)
            candidate = {**self._data, owner_id: merged}
            if not merged:
                del candidate[owner_id]
            previous, self._data = self._data, candidate
            try:
                self._save()
            except StorageError:
                self._data = previous  # keep memory and file consistent
                raise

    def delete(self, owner_id: str) -> None:
        """Forget all secrets of ``owner_id`` (no error if there were none)."""
        with self._lock:
            if owner_id not in self._data:
                return
            previous = self._data
            self._data = {k: v for k, v in previous.items() if k != owner_id}
            try:
                self._save()
            except StorageError:
                self._data = previous
                raise
