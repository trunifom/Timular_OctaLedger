"""Tests for domain models: validation, normalisation and invariants."""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from octaledger.core.errors import ValidationError
from octaledger.domain.models import (
    DEFAULT_COLOR,
    MAX_NAME_LENGTH,
    Activity,
    Correction,
    Device,
    EventKind,
    FaceMapping,
    Project,
    Quality,
    RawEvent,
    Session,
    SessionSource,
    new_id,
)
from octaledger.domain.time_rules import ensure_utc, utc_now

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)


def _event(kind: EventKind, value: int | None, **kwargs: object) -> RawEvent:
    return RawEvent(
        device_id="d1",
        kind=kind,
        sequence=0,
        connection_id="c1",
        raw_value=value,
        **kwargs,  # type: ignore[arg-type]
    )


# ------------------------------------------------------------------------------ helpers


def test_new_id_is_unique_uuid() -> None:
    first, second = new_id(), new_id()
    assert first != second
    assert str(uuid.UUID(first)) == first


def test_utc_now_is_aware_utc() -> None:
    assert utc_now().utcoffset() == timedelta(0)


def test_ensure_utc_converts_offsets() -> None:
    plus_two = timezone(timedelta(hours=2))
    result = ensure_utc(datetime(2026, 1, 1, 12, tzinfo=plus_two))
    assert result == datetime(2026, 1, 1, 10, tzinfo=UTC)
    assert result.utcoffset() == timedelta(0)


def test_ensure_utc_rejects_naive_and_non_datetime() -> None:
    with pytest.raises(ValidationError):
        ensure_utc(datetime(2026, 1, 1))
    with pytest.raises(ValidationError):
        ensure_utc("2026-01-01")  # type: ignore[arg-type]


# ------------------------------------------------------------------------------ devices


def test_device_defaults_and_normalisation() -> None:
    device = Device(alias="  Büro  ", model=" ", firmware=" 1.2 ")
    assert device.alias == "Büro"
    assert device.model is None  # blank -> None
    assert device.firmware == "1.2"
    assert device.created_at.utcoffset() == timedelta(0)
    uuid.UUID(device.id)


@pytest.mark.parametrize("alias", ["", "   ", "x" * (MAX_NAME_LENGTH + 1), None, 5])
def test_device_alias_invalid(alias: object) -> None:
    with pytest.raises(ValidationError):
        Device(alias=alias)  # type: ignore[arg-type]


def test_device_rejects_naive_created_at() -> None:
    with pytest.raises(ValidationError):
        Device(alias="a", created_at=datetime(2026, 1, 1))


def test_models_are_immutable_but_replaceable() -> None:
    device = Device(alias="a")
    with pytest.raises(dataclasses.FrozenInstanceError):
        device.alias = "b"  # type: ignore[misc]
    assert dataclasses.replace(device, alias="b").alias == "b"
    with pytest.raises(ValidationError):  # replace re-validates
        dataclasses.replace(device, alias="")


# ------------------------------------------------------------- activities and projects


@pytest.mark.parametrize("cls", [Activity, Project])
def test_activity_and_project_defaults(cls: type[Activity] | type[Project]) -> None:
    item = cls(name=" Meeting ")
    assert item.name == "Meeting"
    assert item.color == DEFAULT_COLOR
    assert item.archived is False


@pytest.mark.parametrize("cls", [Activity, Project])
@pytest.mark.parametrize("color", ["red", "#12345", "#GGGGGG", "123456", "", None])
def test_invalid_colour(cls: type[Activity] | type[Project], color: object) -> None:
    with pytest.raises(ValidationError):
        cls(name="x", color=color)  # type: ignore[arg-type]


@pytest.mark.parametrize("cls", [Activity, Project])
def test_colour_is_normalised_to_upper_case(cls: type[Activity] | type[Project]) -> None:
    assert cls(name="x", color="#aabbcc").color == "#AABBCC"


@pytest.mark.parametrize("cls", [Activity, Project])
def test_empty_name_rejected(cls: type[Activity] | type[Project]) -> None:
    with pytest.raises(ValidationError) as info:
        cls(name=" ")
    assert info.value.error_code == "OL-VALID-001"


# ---------------------------------------------------------------------------- face mapping


@pytest.mark.parametrize("face", range(1, 9))
def test_valid_faces(face: int) -> None:
    assert FaceMapping(device_id="d1", face=face).face == face


@pytest.mark.parametrize("face", [0, 9, -1, True, "1", 1.0])
def test_invalid_faces(face: object) -> None:
    with pytest.raises(ValidationError):
        FaceMapping(device_id="d1", face=face)  # type: ignore[arg-type]


@pytest.mark.parametrize("revision", [0, -1, True])
def test_invalid_mapping_revision(revision: int) -> None:
    with pytest.raises(ValidationError):
        FaceMapping(device_id="d1", face=1, revision=revision)


# ------------------------------------------------------------------------------ raw events


def test_valid_events_by_kind() -> None:
    assert _event(EventKind.BASELINE, 3).raw_value == 3
    assert _event(EventKind.FACE_CHANGE, 5).raw_value == 5
    assert _event(EventKind.NEUTRAL, 0).raw_value == 0
    assert _event(EventKind.DISCONNECT, None).raw_value is None
    assert _event(EventKind.RECONNECT, None).kind is EventKind.RECONNECT
    assert _event(EventKind.INVALID, None, detail="bad length").detail == "bad length"


@pytest.mark.parametrize(
    "kind, value",
    [
        (EventKind.BASELINE, None),  # value required
        (EventKind.FACE_CHANGE, None),
        (EventKind.NEUTRAL, None),
        (EventKind.NEUTRAL, 3),  # neutral must be 0
        (EventKind.FACE_CHANGE, 0),  # a face change needs a face
        (EventKind.DISCONNECT, 1),  # no value allowed
        (EventKind.INVALID, 0),
        (EventKind.FACE_CHANGE, 9),
        (EventKind.FACE_CHANGE, -1),
        (EventKind.FACE_CHANGE, True),
    ],
)
def test_inconsistent_events_rejected(kind: EventKind, value: int | None) -> None:
    with pytest.raises(ValidationError):
        _event(kind, value)


def test_event_kind_string_is_coerced_and_unknown_rejected() -> None:
    event = RawEvent(device_id="d", kind="baseline", sequence=0, connection_id="c", raw_value=1)  # type: ignore[arg-type]
    assert event.kind is EventKind.BASELINE
    with pytest.raises(ValueError):
        RawEvent(device_id="d", kind="nope", sequence=0, connection_id="c")  # type: ignore[arg-type]


@pytest.mark.parametrize("sequence", [-1, True, "0", 1.5])
def test_invalid_sequence(sequence: object) -> None:
    with pytest.raises(ValidationError):
        RawEvent(
            device_id="d",
            kind=EventKind.DISCONNECT,
            sequence=sequence,
            connection_id="c",  # type: ignore[arg-type]
        )


# -------------------------------------------------------------------------------- sessions


def test_running_session() -> None:
    session = Session(activity_id="a1", started_at=T0)
    assert session.is_running
    assert session.duration(now=T0 + timedelta(minutes=30)) == timedelta(minutes=30)
    assert session.source is SessionSource.MANUAL
    assert session.quality is Quality.CONFIRMED


def test_finished_session_duration_ignores_now() -> None:
    session = Session(activity_id="a1", started_at=T0, ended_at=T0 + timedelta(hours=1))
    assert not session.is_running
    assert session.duration(now=T0 + timedelta(days=9)) == timedelta(hours=1)


def test_session_normalises_timezones() -> None:
    plus_two = timezone(timedelta(hours=2))
    session = Session(activity_id="a", started_at=datetime(2026, 1, 5, 10, tzinfo=plus_two))
    assert session.started_at == T0
    assert session.started_at.tzinfo is UTC


def test_session_rejects_inverted_interval() -> None:
    with pytest.raises(ValidationError):
        Session(activity_id="a", started_at=T0, ended_at=T0 - timedelta(seconds=1))


def test_session_zero_length_allowed() -> None:
    assert Session(activity_id="a", started_at=T0, ended_at=T0).duration() == timedelta(0)


def test_session_rejects_naive_times() -> None:
    with pytest.raises(ValidationError):
        Session(activity_id="a", started_at=datetime(2026, 1, 5))
    with pytest.raises(ValidationError):
        Session(activity_id="a", started_at=T0, ended_at=datetime(2026, 1, 5, 9))


def test_device_session_requires_device() -> None:
    with pytest.raises(ValidationError):
        Session(activity_id="a", started_at=T0, source=SessionSource.DEVICE)
    ok = Session(activity_id="a", started_at=T0, source=SessionSource.DEVICE, device_id="d1")
    assert ok.device_id == "d1"


def test_session_enum_strings_coerced() -> None:
    session = Session(activity_id="a", started_at=T0, quality="uncertain", source="manual")  # type: ignore[arg-type]
    assert session.quality is Quality.UNCERTAIN


def test_session_note_blank_becomes_none_and_long_rejected() -> None:
    assert Session(activity_id="a", started_at=T0, note="  ").note is None
    with pytest.raises(ValidationError):
        Session(activity_id="a", started_at=T0, note="x" * 2001)


def test_session_invalid_revision() -> None:
    with pytest.raises(ValidationError):
        Session(activity_id="a", started_at=T0, revision=0)


# ----------------------------------------------------------------------------- corrections


def test_correction_valid() -> None:
    correction = Correction(
        session_id="s1",
        field_name="started_at",
        new_value="2026-01-05T08:05:00Z",
        reason=" Fehler ",
    )
    assert correction.reason == "Fehler"
    assert correction.revision == 2
    assert correction.old_value is None


@pytest.mark.parametrize("reason", ["", "  ", None])
def test_correction_requires_reason(reason: object) -> None:
    with pytest.raises(ValidationError):
        Correction(session_id="s", field_name="note", new_value="x", reason=reason)  # type: ignore[arg-type]


def test_correction_revision_must_be_two_or_more() -> None:
    with pytest.raises(ValidationError):
        Correction(session_id="s", field_name="note", new_value="x", reason="r", revision=1)
