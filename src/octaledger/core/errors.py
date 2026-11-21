"""Exception hierarchy with stable error codes.

Responsibility
--------------
Every failure that OctaLedger raises *deliberately* is an :class:`OctaLedgerError`.
Each concrete class carries

* a **stable error code** (``OL-<AREA>-<NNN>``) that never changes once released, so
  that users, logs, bug reports and documentation can refer to the same failure, and
* a **user message** written in plain German that the GUI may show unchanged, while the
  technical ``message`` (English) is meant for logs and developers.

Third-party failures (``sqlite3``, ``OSError``, Bleak, JSON ...) must be caught at the
system boundary and translated into one of these classes with ``raise ... from exc`` so
that the original cause is preserved in the traceback and never silently swallowed.

Design notes
------------
* :class:`ValidationError` additionally derives from :class:`ValueError`. Plain Python
  callers (and older tests) that expect ``ValueError`` for invalid input keep working.
* All subclasses are registered automatically in :data:`ERROR_REGISTRY` so that tests
  and documentation generators can verify that codes are unique and well-formed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, ClassVar

#: Pattern every error code must follow, e.g. ``OL-STORAGE-001``.
ERROR_CODE_PATTERN = re.compile(r"^OL-[A-Z]+-\d{3}$")

#: Registry of every error class by its default code (filled by ``__init_subclass__``).
ERROR_REGISTRY: dict[str, type[OctaLedgerError]] = {}


class OctaLedgerError(Exception):
    """Base class of all deliberate OctaLedger failures.

    Attributes:
        code: Stable machine-readable error code (class default, overridable per
            instance for finer granularity inside one family).
        default_user_message: German text shown to end users when no specific one is
            supplied.
        message: Technical English description for logs and developers.
        user_message: German, user-friendly description (no stack traces, no jargon).
        details: Optional structured context (ids, field names ...). Must never
            contain secrets such as API tokens.
    """

    #: Default stable code of the class; every concrete subclass must override it.
    code: ClassVar[str] = "OL-GENERIC-000"
    #: Default German user message of the class.
    default_user_message: ClassVar[str] = (
        "Ein unerwarteter Fehler ist aufgetreten. Details stehen im Logfile."
    )

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        details: Mapping[str, Any] | None = None,
        code: str | None = None,
    ) -> None:
        """Create the error.

        Args:
            message: Technical English description for logs.
            user_message: Optional German message for end users; falls back to the
                class default.
            details: Optional structured context for diagnostics.
            code: Optional per-instance code override. Must match
                :data:`ERROR_CODE_PATTERN`.

        Raises:
            ValueError: If ``code`` does not match the code pattern. (A plain
                ``ValueError`` is used on purpose to avoid recursive error creation.)
        """
        super().__init__(message)
        if code is not None and not ERROR_CODE_PATTERN.match(code):
            raise ValueError(f"Malformed error code: {code!r}")
        self.message = message
        self.user_message = user_message or self.default_user_message
        # Copy into a fresh dict so later mutation by the caller cannot alter us.
        self.details: dict[str, Any] = dict(details) if details else {}
        self._code = code

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Register each subclass and enforce unique, well-formed codes."""
        super().__init_subclass__(**kwargs)
        if not ERROR_CODE_PATTERN.match(cls.code):
            raise TypeError(f"{cls.__name__} has a malformed error code: {cls.code!r}")
        if cls.code in ERROR_REGISTRY:
            other = ERROR_REGISTRY[cls.code].__name__
            raise TypeError(f"Error code {cls.code} of {cls.__name__} already used by {other}")
        ERROR_REGISTRY[cls.code] = cls

    @property
    def error_code(self) -> str:
        """Return the effective code (instance override or class default)."""
        return self._code or self.code

    def __str__(self) -> str:
        """Render ``[CODE] technical message`` for logs and tracebacks."""
        return f"[{self.error_code}] {self.message}"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation for the API and the GUI."""
        return {
            "code": self.error_code,
            "message": self.user_message,
            "technical_message": self.message,
            "details": dict(self.details),
        }


# The base class itself is registered manually (``__init_subclass__`` only fires for
# subclasses) so that the registry is complete.
ERROR_REGISTRY[OctaLedgerError.code] = OctaLedgerError


class ConfigurationError(OctaLedgerError):
    """Settings are missing, unreadable or invalid."""

    code = "OL-CONFIG-001"
    default_user_message = "Die Einstellungen sind ungültig oder konnten nicht gelesen werden."


class ValidationError(OctaLedgerError, ValueError):
    """Input data violates a documented rule (also a plain ``ValueError``)."""

    code = "OL-VALID-001"
    default_user_message = "Die Eingabe ist ungültig. Bitte prüfen Sie Ihre Angaben."


class NotFoundError(OctaLedgerError):
    """A requested entity does not exist."""

    code = "OL-STATE-001"
    default_user_message = "Der gewünschte Eintrag wurde nicht gefunden."


class ConflictError(OctaLedgerError):
    """The request conflicts with current data, e.g. a duplicate or overlapping entry."""

    code = "OL-STATE-002"
    default_user_message = "Die Aktion steht im Widerspruch zu bestehenden Daten."


class InvalidStateError(OctaLedgerError):
    """The operation is not allowed in the current state (e.g. stop without session)."""

    code = "OL-STATE-003"
    default_user_message = "Diese Aktion ist im aktuellen Zustand nicht möglich."


class StorageError(OctaLedgerError):
    """The database could not be opened, read or written."""

    code = "OL-STORAGE-001"
    default_user_message = "Die lokale Datenbank konnte nicht gelesen oder geschrieben werden."


class MigrationError(OctaLedgerError):
    """A database schema migration failed or the schema is newer than the program."""

    code = "OL-STORAGE-002"
    default_user_message = (
        "Die Datenbank konnte nicht auf die aktuelle Version gebracht werden. "
        "Ihre Daten wurden nicht verändert."
    )


class DataIntegrityError(OctaLedgerError):
    """Stored or imported data is inconsistent or corrupt."""

    code = "OL-STORAGE-003"
    default_user_message = "Die Daten sind beschädigt oder widersprüchlich."


class ExportError(OctaLedgerError):
    """Writing an export or backup file failed."""

    code = "OL-DATA-001"
    default_user_message = "Der Export konnte nicht geschrieben werden."


class ImportDataError(OctaLedgerError):
    """Reading or validating an import or restore file failed."""

    code = "OL-DATA-002"
    default_user_message = (
        "Die Datei konnte nicht importiert werden. Es wurden keine Daten verändert."
    )


class ProtocolError(ValidationError):
    """A BLE payload does not match the expected protocol."""

    code = "OL-BLE-001"
    default_user_message = "Der Tracker hat unerwartete Daten gesendet."


class BleConnectionError(OctaLedgerError):
    """Scanning, connecting or subscribing to a tracker failed."""

    code = "OL-BLE-002"
    default_user_message = (
        "Die Bluetooth-Verbindung zum Tracker ist fehlgeschlagen. "
        "Bitte prüfen Sie Bluetooth und die Entfernung zum Tracker."
    )


class UnsupportedDeviceError(OctaLedgerError):
    """The device does not expose the expected service or characteristic."""

    code = "OL-BLE-003"
    default_user_message = "Dieses Gerät wird nicht unterstützt oder wurde nicht erkannt."


class AuthenticationError(OctaLedgerError):
    """API token missing or wrong."""

    code = "OL-API-001"
    default_user_message = "Die Anmeldung an der lokalen Schnittstelle ist fehlgeschlagen."


class ApiUnavailableError(OctaLedgerError):
    """The local API could not be reached."""

    code = "OL-API-002"
    default_user_message = (
        "Der OctaLedger-Agent ist nicht erreichbar. Bitte starten Sie den Agenten."
    )


class ForbiddenOriginError(OctaLedgerError):
    """Request rejected by host/origin validation."""

    code = "OL-API-003"
    default_user_message = "Die Anfrage wurde aus Sicherheitsgründen abgelehnt."


class IntegrationError(OctaLedgerError):
    """An action could not be carried out (the target refused it or the outcome is unknown).

    Not retried automatically: repeating an action of unknown outcome could switch a light twice.
    """

    code = "OL-INTEG-001"
    default_user_message = "Die Aktion konnte nicht ausgeführt werden."


class IntegrationConnectionError(IntegrationError):
    """The target could not be reached and the request certainly had no effect (retried)."""

    code = "OL-INTEG-002"
    default_user_message = "Das Ziel ist nicht erreichbar. Bitte Adresse und Netzwerk prüfen."
