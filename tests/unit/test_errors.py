"""Tests for the error hierarchy and its stable error codes."""

import pytest

from octaledger.core import errors
from octaledger.core.errors import (
    ERROR_CODE_PATTERN,
    ERROR_REGISTRY,
    ConfigurationError,
    OctaLedgerError,
    ProtocolError,
    StorageError,
    ValidationError,
)


def _concrete_classes() -> list[type[OctaLedgerError]]:
    """Return every error class defined in the module (base class included)."""
    return [
        obj
        for obj in vars(errors).values()
        if isinstance(obj, type) and issubclass(obj, OctaLedgerError)
    ]


def test_every_class_has_well_formed_unique_code() -> None:
    codes = [cls.code for cls in _concrete_classes()]
    assert all(ERROR_CODE_PATTERN.match(code) for code in codes)
    assert len(codes) == len(set(codes)), "error codes must be unique"


def test_registry_contains_all_classes() -> None:
    for cls in _concrete_classes():
        assert ERROR_REGISTRY[cls.code] is cls


def test_str_contains_code_and_technical_message() -> None:
    error = StorageError("disk full")
    assert str(error) == "[OL-STORAGE-001] disk full"


def test_user_message_falls_back_to_class_default() -> None:
    error = ConfigurationError("bad toml")
    assert error.user_message == ConfigurationError.default_user_message


def test_custom_user_message_is_used() -> None:
    error = ConfigurationError("bad toml", user_message="Eigene Meldung")
    assert error.user_message == "Eigene Meldung"
    assert error.message == "bad toml"


def test_details_are_copied() -> None:
    details = {"field": "alias"}
    error = ValidationError("bad", details=details)
    details["field"] = "changed"
    assert error.details == {"field": "alias"}


def test_to_dict_is_json_friendly() -> None:
    error = StorageError("boom", details={"path": "x.db"})
    assert error.to_dict() == {
        "code": "OL-STORAGE-001",
        "message": StorageError.default_user_message,
        "technical_message": "boom",
        "details": {"path": "x.db"},
    }


def test_instance_code_override() -> None:
    error = StorageError("boom", code="OL-STORAGE-099")
    assert error.error_code == "OL-STORAGE-099"
    assert "OL-STORAGE-099" in str(error)


def test_malformed_instance_code_rejected() -> None:
    with pytest.raises(ValueError):
        StorageError("boom", code="bad code")


def test_validation_error_is_value_error() -> None:
    # Backwards compatibility: callers catching ValueError must keep working.
    with pytest.raises(ValueError):
        raise ValidationError("bad input")


def test_protocol_error_is_validation_error() -> None:
    assert issubclass(ProtocolError, ValidationError)


def test_duplicate_code_in_subclass_is_rejected() -> None:
    with pytest.raises(TypeError, match="already used"):

        class _Duplicate(OctaLedgerError):
            code = StorageError.code


def test_malformed_code_in_subclass_is_rejected() -> None:
    with pytest.raises(TypeError, match="malformed"):

        class _Malformed(OctaLedgerError):
            code = "nope"


def test_cause_is_preserved_with_raise_from() -> None:
    original = OSError("no space")
    try:
        try:
            raise original
        except OSError as exc:
            raise StorageError("write failed") from exc
    except StorageError as wrapped:
        assert wrapped.__cause__ is original
