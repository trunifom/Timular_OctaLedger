"""Domain data models: devices, activities, projects, events, sessions, corrections.

Responsibility
--------------
Pure value objects without any knowledge of BLE, SQL, HTTP or Streamlit. Every model

* is **immutable** (``frozen=True``; use :func:`dataclasses.replace` to derive changes),
* **validates itself** in ``__post_init__`` and raises
  :class:`~octaledger.core.errors.ValidationError` on invalid data, so an inconsistent
  object can never exist (this also protects imports and the database layer), and
* stores every timestamp as **timezone-aware UTC**.

Identifiers are random UUID4 strings created by :func:`new_id`. A Bluetooth address is
*not* an identity: it is only an optional platform hint (``Device.platform_address``)
because addresses may change or be randomised.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from octaledger.core.errors import ValidationError
from octaledger.domain.time_rules import ensure_utc, interval_duration, utc_now

#: Face numbers of the eight-sided tracker (technical numbers as reported by the device).
FACE_NUMBERS: Final = tuple(range(1, 9))
#: Limits for user-provided text (names, notes) to keep storage and GUI sane.
MAX_NAME_LENGTH: Final = 100
MAX_NOTE_LENGTH: Final = 2000
MAX_REASON_LENGTH: Final = 500

_COLOR_PATTERN: Final = re.compile(r"^#[0-9A-Fa-f]{6}$")
#: Default colour used when none is chosen (neutral blue-grey).
DEFAULT_COLOR: Final = "#5B7C99"


def new_id() -> str:
    """Return a new random identifier (UUID4, canonical hyphenated string)."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------- enumerations


class EventKind(StrEnum):
    """Kind of a raw event observed from a tracker (kept separate on purpose)."""

    #: First value read after connecting; never starts a session by itself.
    BASELINE = "baseline"
    #: A real change to a face 1..8.
    FACE_CHANGE = "face_change"
    #: Neutral value 0 (no stable face).
    NEUTRAL = "neutral"
    #: Connection lost.
    DISCONNECT = "disconnect"
    #: Connection re-established.
    RECONNECT = "reconnect"
    #: Packet that failed validation (kept for diagnostics, never creates a session).
    INVALID = "invalid"


class SessionSource(StrEnum):
    """Where a session came from."""

    DEVICE = "device"
    MANUAL = "manual"


class Quality(StrEnum):
    """Reliability of a session's time span."""

    CONFIRMED = "confirmed"
    #: Part of the span is unknown (e.g. connection loss); the user should confirm.
    UNCERTAIN = "uncertain"


# ------------------------------------------------------------------------ field validators


def _clean_text(value: object, field_name: str, *, max_length: int, required: bool) -> str:
    """Validate and strip a text field.

    Raises:
        ValidationError: If not a string, empty while required, or too long.
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be text", details={"field": field_name})
    text = value.strip()
    if required and not text:
        raise ValidationError(
            f"{field_name} must not be empty",
            user_message=f"Das Feld „{field_name}“ darf nicht leer sein.",
            details={"field": field_name},
        )
    if len(text) > max_length:
        raise ValidationError(
            f"{field_name} longer than {max_length} characters",
            user_message=f"Das Feld „{field_name}“ ist zu lang (maximal {max_length} Zeichen).",
            details={"field": field_name, "max_length": max_length},
        )
    return text


def _optional_text(value: str | None, field_name: str, max_length: int) -> str | None:
    """Validate an optional text field; blank text becomes ``None``."""
    if value is None:
        return None
    text = _clean_text(value, field_name, max_length=max_length, required=False)
    return text or None


def _check_id(value: object, field_name: str) -> str:
    """Validate that ``value`` is a non-empty identifier string."""
    return _clean_text(value, field_name, max_length=64, required=True)


def _check_color(value: object) -> str:
    """Validate a ``#RRGGBB`` colour and normalise it to upper case."""
    if not isinstance(value, str) or not _COLOR_PATTERN.match(value):
        raise ValidationError(
            f"Invalid colour {value!r}",
            user_message="Die Farbe muss im Format #RRGGBB angegeben werden.",
            details={"field": "color"},
        )
    return value.upper()


def _check_face(value: object) -> int:
    """Validate a face number ``1..8`` (``bool`` is rejected)."""
    if isinstance(value, bool) or not isinstance(value, int) or value not in FACE_NUMBERS:
        raise ValidationError(
            f"Face must be 1..8, got {value!r}",
            user_message="Die Seite muss eine Zahl von 1 bis 8 sein.",
            details={"field": "face"},
        )
    return value


# -------------------------------------------------------------------------------- devices


@dataclass(frozen=True, slots=True)
class Device:
    """A registered tracker.

    Attributes:
        id: Internal stable identifier (never the Bluetooth address).
        alias: User-chosen display name, e.g. "Tracker Büro".
        platform_address: Optional OS-specific Bluetooth address/identifier used to
            reconnect. May change over time; treated as a hint only.
        model: Optional model description reported by the device.
        firmware: Optional firmware version reported by the device.
        created_at: Registration time (UTC).
    """

    alias: str
    id: str = field(default_factory=new_id)
    platform_address: str | None = None
    model: str | None = None
    firmware: str | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        """Validate and normalise all fields."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        object.__setattr__(
            self,
            "alias",
            _clean_text(self.alias, "Alias", max_length=MAX_NAME_LENGTH, required=True),
        )
        object.__setattr__(
            self, "platform_address", _optional_text(self.platform_address, "address", 200)
        )
        object.__setattr__(self, "model", _optional_text(self.model, "model", MAX_NAME_LENGTH))
        object.__setattr__(self, "firmware", _optional_text(self.firmware, "firmware", 50))
        object.__setattr__(self, "created_at", ensure_utc(self.created_at, name="created_at"))


# ------------------------------------------------------------- activities and projects


@dataclass(frozen=True, slots=True)
class Activity:
    """A kind of work that can be assigned to a tracker face (e.g. "Meeting")."""

    name: str
    id: str = field(default_factory=new_id)
    color: str = DEFAULT_COLOR
    archived: bool = False

    def __post_init__(self) -> None:
        """Validate name, id and colour."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        object.__setattr__(
            self, "name", _clean_text(self.name, "Name", max_length=MAX_NAME_LENGTH, required=True)
        )
        object.__setattr__(self, "color", _check_color(self.color))


@dataclass(frozen=True, slots=True)
class Project:
    """A project that time can be booked to (optional dimension next to the activity)."""

    name: str
    id: str = field(default_factory=new_id)
    color: str = DEFAULT_COLOR
    archived: bool = False

    def __post_init__(self) -> None:
        """Validate name, id and colour."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        object.__setattr__(
            self, "name", _clean_text(self.name, "Name", max_length=MAX_NAME_LENGTH, required=True)
        )
        object.__setattr__(self, "color", _check_color(self.color))


@dataclass(frozen=True, slots=True)
class FaceMapping:
    """Assignment of one technical face of one device to an activity (and project).

    ``revision`` increases with every change so that past sessions stay explainable.
    A mapping without activity means "face not configured yet".
    """

    device_id: str
    face: int
    activity_id: str | None = None
    project_id: str | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        """Validate ids, face number and revision."""
        object.__setattr__(self, "device_id", _check_id(self.device_id, "device_id"))
        object.__setattr__(self, "face", _check_face(self.face))
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise ValidationError("revision must be a positive integer")


# ------------------------------------------------------------------------------ raw events


@dataclass(frozen=True, slots=True)
class RawEvent:
    """One observation from a tracker, stored unmodified for audit purposes.

    Attributes:
        device_id: The device that produced it.
        kind: What kind of observation this is.
        received_at: Reception time (UTC).
        sequence: Per-connection running number (detects gaps and duplicates).
        connection_id: Identifier of the connection cycle (late results of old cycles
            are recognised by it).
        raw_value: The decoded value ``0..8`` or ``None`` for non-value events.
        detail: Optional diagnostic text (e.g. why a packet was invalid).
    """

    device_id: str
    kind: EventKind
    sequence: int
    connection_id: str
    received_at: datetime = field(default_factory=utc_now)
    raw_value: int | None = None
    detail: str | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Validate the event and its consistency with its kind."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        object.__setattr__(self, "device_id", _check_id(self.device_id, "device_id"))
        object.__setattr__(self, "connection_id", _check_id(self.connection_id, "connection_id"))
        object.__setattr__(self, "kind", EventKind(self.kind))
        object.__setattr__(self, "received_at", ensure_utc(self.received_at, name="received_at"))
        object.__setattr__(self, "detail", _optional_text(self.detail, "detail", MAX_NOTE_LENGTH))
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValidationError("sequence must be a non-negative integer")
        if self.raw_value is not None and (
            isinstance(self.raw_value, bool)
            or not isinstance(self.raw_value, int)
            or not 0 <= self.raw_value <= 8
        ):
            raise ValidationError(f"raw_value must be 0..8, got {self.raw_value!r}")
        # Consistency: events that carry a face value must have one, others must not.
        needs_value = self.kind in (EventKind.BASELINE, EventKind.FACE_CHANGE, EventKind.NEUTRAL)
        if needs_value and self.raw_value is None:
            raise ValidationError(f"{self.kind.value} event requires raw_value")
        if not needs_value and self.raw_value is not None:
            raise ValidationError(f"{self.kind.value} event must not carry raw_value")
        if self.kind is EventKind.NEUTRAL and self.raw_value != 0:
            raise ValidationError("neutral event must carry raw_value 0")
        if self.kind is EventKind.FACE_CHANGE and self.raw_value == 0:
            raise ValidationError("face_change event must carry a face 1..8")


# -------------------------------------------------------------------------------- sessions


@dataclass(frozen=True, slots=True)
class Session:
    """A time span spent on an activity.

    A session with ``ended_at is None`` is *running*. Sessions never overlap for one
    person (MVP rule, enforced by the tracking service and the database layer).

    Attributes:
        activity_id: What was done.
        started_at: Start (UTC).
        ended_at: End (UTC) or ``None`` while running.
        project_id: Optional project.
        device_id: Tracker that produced it; ``None`` for manual sessions.
        source: ``device`` or ``manual``.
        quality: ``confirmed`` or ``uncertain`` (e.g. after a connection loss).
        note: Optional free text.
        revision: Increases with every correction (audit trail lives in ``Correction``).
    """

    activity_id: str
    started_at: datetime
    ended_at: datetime | None = None
    project_id: str | None = None
    device_id: str | None = None
    source: SessionSource = SessionSource.MANUAL
    quality: Quality = Quality.CONFIRMED
    note: str | None = None
    revision: int = 1
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Validate ids, enums, timestamps and the interval."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        object.__setattr__(self, "activity_id", _check_id(self.activity_id, "activity_id"))
        if self.project_id is not None:
            object.__setattr__(self, "project_id", _check_id(self.project_id, "project_id"))
        if self.device_id is not None:
            object.__setattr__(self, "device_id", _check_id(self.device_id, "device_id"))
        object.__setattr__(self, "source", SessionSource(self.source))
        object.__setattr__(self, "quality", Quality(self.quality))
        object.__setattr__(self, "note", _optional_text(self.note, "Notiz", MAX_NOTE_LENGTH))
        object.__setattr__(self, "started_at", ensure_utc(self.started_at, name="started_at"))
        if self.ended_at is not None:
            object.__setattr__(self, "ended_at", ensure_utc(self.ended_at, name="ended_at"))
            # Raises ValidationError if the end precedes the start.
            interval_duration(self.started_at, self.ended_at)
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise ValidationError("revision must be a positive integer")
        if self.source is SessionSource.DEVICE and self.device_id is None:
            raise ValidationError("a device session requires device_id")

    @property
    def is_running(self) -> bool:
        """``True`` while the session has no end."""
        return self.ended_at is None

    def duration(self, now: datetime | None = None) -> timedelta:
        """Return the elapsed time; a running session is measured up to ``now``.

        Args:
            now: Reference time for running sessions (defaults to the current time).
        """
        end = self.ended_at if self.ended_at is not None else (now or utc_now())
        return interval_duration(self.started_at, end)


@dataclass(frozen=True, slots=True)
class Correction:
    """Audit record of one change to a session; originals are never overwritten silently.

    Attributes:
        session_id: The corrected session.
        field_name: Which field changed (e.g. ``started_at``, ``activity_id``).
        old_value: Previous value as text (``None`` if the field was empty).
        new_value: New value as text.
        reason: Why the change was made (required).
        corrected_at: When the change was made (UTC).
        revision: Session revision created by this correction.
    """

    session_id: str
    field_name: str
    new_value: str | None
    reason: str
    old_value: str | None = None
    revision: int = 2
    corrected_at: datetime = field(default_factory=utc_now)
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Validate ids, texts, timestamp and revision."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        object.__setattr__(self, "session_id", _check_id(self.session_id, "session_id"))
        object.__setattr__(
            self, "field_name", _clean_text(self.field_name, "field", max_length=50, required=True)
        )
        object.__setattr__(
            self,
            "reason",
            _clean_text(self.reason, "Grund", max_length=MAX_REASON_LENGTH, required=True),
        )
        object.__setattr__(
            self, "old_value", _optional_text(self.old_value, "old", MAX_NOTE_LENGTH)
        )
        object.__setattr__(
            self, "new_value", _optional_text(self.new_value, "new", MAX_NOTE_LENGTH)
        )
        object.__setattr__(self, "corrected_at", ensure_utc(self.corrected_at, name="corrected_at"))
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 2
        ):
            raise ValidationError("a correction creates revision 2 or higher")
