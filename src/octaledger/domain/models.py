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

import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final

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


class DeviceMode(StrEnum):
    """What a tracker is used for (switchable per tracker).

    The two modes never mix on one tracker, so a turn can never both start a time entry and
    switch a light by accident.
    """

    #: Faces are activities; turning the cube records working time (the default).
    TIME = "time"
    #: Faces are actions (switch a light, publish a message ...); no time is recorded.
    CONTROL = "control"


class JobStatus(StrEnum):
    """Life cycle of an integration job (one action waiting to be sent)."""

    PENDING = "pending"
    DONE = "done"
    #: Gave up: a permanent error or the attempts are used up.
    FAILED = "failed"
    #: Dropped on purpose: too late to be useful, or the queue was full.
    EXPIRED = "expired"


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


def _check_mode(value: object) -> DeviceMode:
    """Validate a device mode (accepts the enum or its text value)."""
    try:
        return DeviceMode(str(value))
    except ValueError:
        raise ValidationError(
            f"Invalid device mode {value!r}",
            user_message="Der Modus muss „Zeiterfassung“ oder „Steuerung“ sein.",
            details={"field": "mode"},
        ) from None


#: Upper bound of the JSON text of an integration's settings or an action's parameters.
MAX_JSON_BYTES: Final = 8 * 1024
_KIND_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def _check_json_object(value: object, field_name: str) -> dict[str, Any]:
    """Validate a small JSON object (text keys, JSON-serialisable values, size limit).

    Returns a *copy*, so the caller cannot change the stored value afterwards.

    Raises:
        ValidationError: If it is not an object, not serialisable, or larger than the limit.
    """
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValidationError(
            f"{field_name} must be an object with text keys", details={"field": field_name}
        )
    try:
        text = json.dumps(dict(value), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"{field_name} is not valid JSON data: {exc}", details={"field": field_name}
        ) from exc
    if len(text.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValidationError(
            f"{field_name} larger than {MAX_JSON_BYTES} bytes",
            user_message=f"Die Angaben für „{field_name}“ sind zu umfangreich.",
            details={"field": field_name},
        )
    loaded: dict[str, Any] = json.loads(text)
    return loaded


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
        mode: Whether the faces record time or trigger actions (:class:`DeviceMode`).
    """

    alias: str
    id: str = field(default_factory=new_id)
    platform_address: str | None = None
    model: str | None = None
    firmware: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    mode: DeviceMode = DeviceMode.TIME

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
        object.__setattr__(self, "mode", _check_mode(self.mode))


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


# --------------------------------------------------------------- integrations and actions


@dataclass(frozen=True, slots=True)
class Integration:
    """A configured connection to something that can be controlled (MQTT broker, Hue bridge ...).

    Attributes:
        kind: Which adapter handles it (``webhook``, ``mqtt``, ``homeassistant``, ``hue``).
        name: User-chosen name, unique among integrations (case-insensitive).
        config: Adapter settings **without secrets**. Secrets (tokens, passwords) live in the
            separate secret store and are never part of this object, a backup or an API answer.
        enabled: A disabled integration keeps its settings but sends nothing.
    """

    kind: str
    name: str
    config: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        """Validate and normalise all fields."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        if not isinstance(self.kind, str) or not _KIND_PATTERN.match(self.kind):
            raise ValidationError(
                f"Invalid integration kind {self.kind!r}", details={"field": "kind"}
            )
        object.__setattr__(
            self,
            "name",
            _clean_text(self.name, "Name", max_length=MAX_NAME_LENGTH, required=True),
        )
        object.__setattr__(self, "config", _check_json_object(self.config, "config"))
        if not isinstance(self.enabled, bool):
            raise ValidationError("enabled must be true or false", details={"field": "enabled"})
        object.__setattr__(self, "created_at", ensure_utc(self.created_at, name="created_at"))


@dataclass(frozen=True, slots=True)
class FaceAction:
    """What one face of a tracker in control mode does: one action of one integration.

    ``params`` holds the adapter-specific action (for example ``{"action": "call_service",
    "domain": "light", "service": "toggle", "entity_id": "light.desk"}``). ``label`` is the name
    the user gave the face ("Schreibtischlampe"); it is shown in the live view and the history.
    ``revision`` increases with every change, like :class:`FaceMapping`.
    """

    device_id: str
    face: int
    integration_id: str
    label: str
    params: Mapping[str, Any] = field(default_factory=dict)
    revision: int = 1

    def __post_init__(self) -> None:
        """Validate ids, face, texts and revision."""
        object.__setattr__(self, "device_id", _check_id(self.device_id, "device_id"))
        object.__setattr__(self, "face", _check_face(self.face))
        object.__setattr__(self, "integration_id", _check_id(self.integration_id, "integration_id"))
        object.__setattr__(
            self,
            "label",
            _clean_text(self.label, "Bezeichnung", max_length=MAX_NAME_LENGTH, required=True),
        )
        object.__setattr__(self, "params", _check_json_object(self.params, "params"))
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise ValidationError("revision must be a positive integer")


@dataclass(frozen=True, slots=True)
class IntegrationJob:
    """One action waiting to be sent (the "outbox" entry written together with the raw event).

    Writing the job in the same transaction as the event makes the trigger reliable, and the
    unique ``idempotency_key`` (the id of the raw event) makes a repeated trigger harmless. The
    action is copied into the job (``label``/``params``), so editing the face later does not
    change what an already queued job does. A job is only useful for a short time, hence
    ``expires_at``.
    """

    idempotency_key: str
    integration_id: str
    label: str
    params: Mapping[str, Any]
    expires_at: datetime
    device_id: str | None = None
    face: int | None = None
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    last_error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    next_attempt_at: datetime | None = None
    finished_at: datetime | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Validate and normalise all fields."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        object.__setattr__(
            self, "idempotency_key", _check_id(self.idempotency_key, "idempotency_key")
        )
        object.__setattr__(self, "integration_id", _check_id(self.integration_id, "integration_id"))
        object.__setattr__(
            self,
            "label",
            _clean_text(self.label, "Bezeichnung", max_length=MAX_NAME_LENGTH, required=True),
        )
        object.__setattr__(self, "params", _check_json_object(self.params, "params"))
        if self.face is not None:
            object.__setattr__(self, "face", _check_face(self.face))
        object.__setattr__(self, "status", JobStatus(self.status))
        if (
            isinstance(self.attempts, bool)
            or not isinstance(self.attempts, int)
            or self.attempts < 0
        ):
            raise ValidationError("attempts must be a non-negative integer")
        object.__setattr__(
            self, "last_error", _optional_text(self.last_error, "error", MAX_NOTE_LENGTH)
        )
        object.__setattr__(self, "created_at", ensure_utc(self.created_at, name="created_at"))
        object.__setattr__(self, "expires_at", ensure_utc(self.expires_at, name="expires_at"))
        object.__setattr__(
            self,
            "next_attempt_at",
            self.created_at
            if self.next_attempt_at is None
            else ensure_utc(self.next_attempt_at, name="next_attempt_at"),
        )
        if self.finished_at is not None:
            object.__setattr__(
                self, "finished_at", ensure_utc(self.finished_at, name="finished_at")
            )
