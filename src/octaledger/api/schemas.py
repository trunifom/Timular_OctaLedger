"""Versioned request and response schemas.

Requests are strict pydantic models (``extra="forbid"``: unknown fields are an error, so typos
are noticed). Responses are built by small functions into plain dictionaries with stable keys;
every timestamp is ISO-8601 UTC and every duration is an integer number of **seconds**, so any
client (the Streamlit dashboard, scripts) can consume them without knowing internal types.

The API version is part of every URL (``/api/v1``) and reported by ``/api/v1/health``. Breaking
changes require a new version prefix.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from octaledger.agent.supervisor import DeviceStatus
from octaledger.application.device_service import DeviceInfo
from octaledger.application.ics_import import IcsPreview
from octaledger.application.integration_service import IntegrationInfo, JobInfo
from octaledger.application.reporting_service import (
    Balance,
    JournalEntry,
    ProjectBudget,
    Report,
    Share,
)
from octaledger.application.tracking_service import TrackingStatus
from octaledger.domain.attention import AttentionItem
from octaledger.domain.device_identity import badge, color_name
from octaledger.domain.models import (
    FACE_NUMBERS,
    Activity,
    FaceAction,
    Project,
    Session,
)
from octaledger.domain.music_source import MusicSource
from octaledger.domain.schedule import Absence, WorkSchedule
from octaledger.domain.steps import ActionStep
from octaledger.domain.tags import ProjectBilling, Tag
from octaledger.infrastructure.ble.scanner import ScanResult
from octaledger.infrastructure.integrations.base import AdapterSpec, FieldSpec

API_VERSION: Final = 1
API_PREFIX: Final = f"/api/v{API_VERSION}"


class _Strict(BaseModel):
    """Base for request bodies: reject unknown fields."""

    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------------------ requests


class DeviceCreate(_Strict):
    """Register a tracker."""

    alias: str = Field(max_length=200)
    platform_address: str | None = Field(default=None, max_length=200)


class AddressBody(_Strict):
    """Bluetooth address of a device (as found by a scan)."""

    platform_address: str = Field(min_length=1, max_length=200)


class DeviceRename(_Strict):
    """Change a tracker's alias and/or identity colour (at least one of them)."""

    alias: str | None = Field(default=None, max_length=200)
    color: str | None = Field(default=None, max_length=7)


class FaceAssign(_Strict):
    """Assign an activity (and project) to a face."""

    activity_id: str | None = None
    project_id: str | None = None


class IntegrationCreate(_Strict):
    """Create a connection (settings and secrets together; secrets are stored separately)."""

    kind: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    values: dict[str, Any] = Field(default_factory=dict)


class IntegrationUpdate(_Strict):
    """Change a connection; blank secrets keep the stored value."""

    name: str | None = Field(default=None, max_length=200)
    values: dict[str, Any] | None = None
    enabled: bool | None = None


class ProbeBody(_Strict):
    """Run one action right now (\"try it\")."""

    params: dict[str, Any]


class ModeBody(_Strict):
    """Switch a tracker between time recording and control."""

    mode: str = Field(min_length=1, max_length=20)


class ConditionBody(_Strict):
    """When a step may run: a time window (HH:MM, may span midnight) and/or weekdays."""

    start: str = Field(default="", max_length=5)
    end: str = Field(default="", max_length=5)
    weekdays: str = Field(default="", max_length=20)


class StepBody(_Strict):
    """One step of a face's chain."""

    integration_id: str = Field(min_length=1, max_length=64)
    label: str = Field(max_length=200)
    params: dict[str, Any]
    delay_ms: int = Field(default=0, ge=0, le=300_000)
    continue_on_error: bool = False
    enabled: bool = True
    condition: ConditionBody | None = None


class ActionAssign(_Strict):
    """Give a face one action of a connection, or a chain of ``steps``."""

    integration_id: str | None = Field(default=None, min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=200)
    params: dict[str, Any] | None = None
    steps: list[StepBody] | None = Field(default=None, min_length=1, max_length=10)


class CatalogCreate(_Strict):
    """Create an activity or project."""

    name: str = Field(max_length=200)
    color: str | None = Field(default=None, max_length=20)


class CatalogUpdate(_Strict):
    """Rename and/or recolour an activity or project."""

    name: str | None = Field(default=None, max_length=200)
    color: str | None = Field(default=None, max_length=20)


class ArchiveBody(_Strict):
    """Archive (default) or restore an activity/project."""

    archived: bool = True


class StartBody(_Strict):
    """Start a manual session."""

    activity_id: str
    project_id: str | None = None
    note: str | None = Field(default=None, max_length=5000)


class ManualSession(_Strict):
    """Add a back-dated, finished session."""

    activity_id: str
    start: datetime
    end: datetime
    project_id: str | None = None
    note: str | None = Field(default=None, max_length=5000)


class CorrectBody(_Strict):
    """Correct a session (allowed fields are checked by the service)."""

    changes: dict[str, Any]
    reason: str = Field(max_length=2000)


class SplitBody(_Strict):
    """Split a session at a time."""

    at: datetime
    reason: str = Field(max_length=2000)


class ReasonBody(_Strict):
    """A bare reason (deleting a session)."""

    reason: str = Field(max_length=2000)


class ScanBody(_Strict):
    """Scan for BLE devices."""

    seconds: float = 5.0


class ExportCsvBody(_Strict):
    """CSV export options."""

    tz: str = "UTC"
    delimiter: str = ";"
    start: datetime | None = None
    end: datetime | None = None


class RestoreInspectBody(_Strict):
    """Backup content to validate (no change)."""

    content: str


class RestoreBody(_Strict):
    """Backup content to restore; ``confirm`` must be true (deliberate, destructive action)."""

    content: str
    confirm: bool = False


class AttentionResolve(_Strict):
    """Answer to a question of the attention centre (for a gap: keep, discard or assign)."""

    action: str = Field(min_length=1, max_length=40)
    activity_id: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    until: datetime | None = None


class RenderBody(_Strict):
    """Render a printable report for a period of local days."""

    first: date
    last: date
    format: str = Field(default="html", max_length=10)
    tz: str | None = Field(default=None, max_length=60)


class IcsPreviewBody(_Strict):
    """A calendar file (text) and the period to read from it."""

    content: str = Field(max_length=2_100_000)
    first: date
    last: date
    tz: str | None = Field(default=None, max_length=60)


class IcsEntryBody(_Strict):
    """One confirmed appointment with the chosen activity."""

    start: datetime
    end: datetime
    activity_id: str = Field(max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class IcsApplyBody(_Strict):
    """The confirmed appointments to book (all or nothing)."""

    entries: list[IcsEntryBody] = Field(max_length=200)


class ParseBody(_Strict):
    """A pasted music link to recognise."""

    text: str = Field(max_length=2100)


class MusicSettingsBody(_Strict):
    """Behaviour of a music cube."""

    base_action: str = Field(default="stop", max_length=10)
    stop_delay_ms: int = Field(default=0, ge=0, le=60_000)
    default_volume: int = Field(default=50, ge=0, le=100)


class MusicTitleBody(_Strict):
    """A title for a face, from a pasted link, played on a connection."""

    integration_id: str = Field(min_length=1, max_length=64)
    link: str = Field(max_length=2100)
    label: str = Field(max_length=200)
    volume: int | None = Field(default=None, ge=0, le=100)
    options: dict[str, str] = Field(default_factory=dict)


class FindBody(_Strict):
    """Search for the target on the network (``online`` also asks an internet service)."""

    online: bool = False


class TagCreate(_Strict):
    """A new tag."""

    name: str = Field(max_length=100)
    color: str | None = Field(default=None, max_length=7)


class TagUpdate(_Strict):
    """Rename or recolour a tag."""

    name: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=7)


class TagIds(_Strict):
    """A list of tag ids (replaces the current tags)."""

    tag_ids: list[str] = Field(max_length=100)


class ActivityDefaults(_Strict):
    """Default tags and note template of an activity."""

    tag_ids: list[str] = Field(default_factory=list, max_length=100)
    note_template: str | None = Field(default=None, max_length=500)


class BillingBody(_Strict):
    """Budget (minutes), hourly rate (cents) and billable flag of a project."""

    budget_minutes: int | None = Field(default=None, ge=1, le=6_000_000)
    hourly_rate_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    billable: bool = False


class ScheduleBody(_Strict):
    """The target minutes per weekday (Monday first), valid from a date."""

    valid_from: date
    minutes: list[int] = Field(min_length=7, max_length=7)


class AbsenceCreate(_Strict):
    """A period of absence (both dates inclusive)."""

    start: date
    end: date
    kind: str = Field(max_length=40)
    target_minutes: int | None = Field(default=None, ge=0, le=1440)
    note: str | None = Field(default=None, max_length=500)


class AutostartBody(_Strict):
    """Switch "start with Windows" on or off."""

    enabled: bool


class ButtonBody(_Strict):
    """The action of a button press (``none`` clears it)."""

    action: str = Field(min_length=1, max_length=40)


class EntriesRange(_Strict):
    """A period of entries (both ends optional; the end is exclusive)."""

    start: datetime | None = None
    end: datetime | None = None


class EntriesDelete(EntriesRange):
    """Delete the entries of a period; ``expected_count`` is the number the user was shown."""

    expected_count: int = Field(ge=0)
    include_events: bool = False


class DeviceRemove(_Strict):
    """Remove a cube; ``delete_data`` also deletes everything recorded with it."""

    delete_data: bool = False


class ResetBody(_Strict):
    """Factory reset: the confirmation text must be typed exactly."""

    confirm_text: str
    reset_settings: bool = True


class SettingsReset(_Strict):
    """Restore default settings: one section, or all when ``section`` is omitted."""

    section: str | None = Field(default=None, max_length=40)


class SettingsBody(_Strict):
    """Full or partial settings as nested sections (validated like the settings file)."""

    settings: dict[str, dict[str, Any]]


# ----------------------------------------------------------------------------- responses


def iso(value: datetime | None) -> str | None:
    """ISO-8601 text of a UTC datetime (``None`` stays ``None``)."""
    return None if value is None else value.isoformat()


def seconds(value: timedelta) -> int:
    """Whole seconds of a duration."""
    return int(value.total_seconds())


def session_out(session: Session, now: datetime | None = None) -> dict[str, Any]:
    """Serialise a session (a running one is measured up to ``now``)."""
    return {
        "id": session.id,
        "activity_id": session.activity_id,
        "project_id": session.project_id,
        "device_id": session.device_id,
        "started_at": iso(session.started_at),
        "ended_at": iso(session.ended_at),
        "running": session.is_running,
        "duration_seconds": seconds(session.duration(now)),
        "source": session.source.value,
        "quality": session.quality.value,
        "note": session.note,
        "revision": session.revision,
    }


def activity_out(item: Activity | Project) -> dict[str, Any]:
    """Serialise an activity or project."""
    return {"id": item.id, "name": item.name, "color": item.color, "archived": item.archived}


def device_status_out(status: DeviceStatus | None) -> dict[str, Any] | None:
    """Serialise the live connection status of a device (``None`` if never started)."""
    if status is None:
        return None
    return {
        "state": status.state.value,
        "connection_id": status.connection_id,
        "attempt": status.attempt,
        "last_error": status.last_error,
        "last_value": status.last_value,
        "last_event_at": iso(status.last_event_at),
        "battery_percent": status.battery_percent,
        "dropped_values": status.dropped_values,
        "duplicates_ignored": status.duplicates_ignored,
    }


def live_out(
    info: DeviceInfo,
    status: DeviceStatus | None,
    activities: dict[str, Activity],
    projects: dict[str, Project],
    tracking: dict[str, Any],
) -> dict[str, Any]:
    """Serialise the live view of one cube: position, debounce state, history and effect.

    Args:
        info: The device with its calibration.
        status: Live worker status (``None`` while the device was never started).
        activities: All activities by id (names/colours of the assigned faces).
        projects: All projects by id.
        tracking: The serialised tracking status (what runs now because of the cube).
    """

    def named(item: Activity | Project | None) -> dict[str, Any] | None:
        """Short ``{id, name, colour}`` description of an activity/project, or ``None``."""
        return None if item is None else {"id": item.id, "name": item.name, "color": item.color}

    faces: dict[str, Any] = {}
    for face in FACE_NUMBERS:
        mapping = info.mappings.get(face)
        action = info.actions.get(face)
        faces[str(face)] = {
            "action": None if action is None else {"label": action.label},
            "activity": (
                named(activities.get(mapping.activity_id))
                if mapping and mapping.activity_id
                else None
            ),
            "project": (
                named(projects.get(mapping.project_id)) if mapping and mapping.project_id else None
            ),
        }
    live = device_status_out(status)
    return {
        "device_id": info.device.id,
        "alias": info.device.alias,
        "is_active": info.is_active,
        "mode": info.device.mode.value,
        "state": live["state"] if live else None,
        "raw_value": status.raw_value if status else None,
        "raw_at": iso(status.raw_at) if status else None,
        "committed_value": status.last_value if status else None,
        "pending_value": status.pending_value if status else None,
        "debounce_ms": status.debounce_ms if status else 0,
        "battery_percent": status.battery_percent if status else None,
        "faces": faces,
        "recent": [
            {"at": iso(event.at), "kind": event.kind, "value": event.value}
            for event in reversed(status.recent if status else ())
        ],
        "tracking": tracking,
    }


def action_out(action: FaceAction) -> dict[str, Any]:
    """Serialise the action of a face."""
    return {
        "integration_id": action.integration_id,
        "label": action.label,
        "params": dict(action.params),
        "revision": action.revision,
    }


def field_out(spec: FieldSpec) -> dict[str, Any]:
    """Serialise one form field of an adapter description."""
    return {
        "name": spec.name,
        "label": spec.label,
        "kind": spec.kind,
        "required": spec.required,
        "help": spec.help,
        "default": spec.default,
        "placeholder": spec.placeholder,
        "choices": [{"value": value, "label": label} for value, label in spec.choices],
        "minimum": spec.minimum,
        "maximum": spec.maximum,
        "choices_from": list(spec.choices_from),
        "advanced": spec.advanced,
    }


def adapter_out(spec: AdapterSpec) -> dict[str, Any]:
    """Serialise an adapter's self-description (the dashboard renders forms from it)."""
    return {
        "kind": spec.kind,
        "title": spec.title,
        "description": spec.description,
        "config_fields": [field_out(f) for f in spec.config_fields],
        "actions": [
            {
                "id": a.id,
                "label": a.label,
                "description": a.description,
                "idempotent": a.idempotent,
                "fields": [field_out(f) for f in a.fields],
            }
            for a in spec.actions
        ],
        "can_pair": spec.can_pair,
        "pair_help": spec.pair_help,
        "can_discover": spec.can_discover,
        "can_find": spec.can_find,
        "music_capable": spec.music_capable,
        "presets": [
            {
                "id": p.id,
                "label": p.label,
                "action": p.action,
                "description": p.description,
                "params": dict(p.params),
                "verified": p.verified,
            }
            for p in spec.presets
        ],
        "find_help": spec.find_help,
        "setup_guide": spec.setup_guide,
    }


def integration_out(info: IntegrationInfo) -> dict[str, Any]:
    """Serialise a connection: settings and the *names* of stored secrets, never their values."""
    integration = info.integration
    return {
        "id": integration.id,
        "kind": integration.kind,
        "name": integration.name,
        "config": dict(integration.config),
        "enabled": integration.enabled,
        "secrets_set": list(info.secrets_set),
        "created_at": iso(integration.created_at),
    }


def step_out(step: ActionStep) -> dict[str, Any]:
    """Serialise one step of a chain."""
    return {
        "position": step.position,
        "integration_id": step.integration_id,
        "label": step.label,
        "params": dict(step.params),
        "delay_ms": step.delay_ms,
        "continue_on_error": step.continue_on_error,
        "enabled": step.enabled,
        "condition": None if step.condition is None else step.condition.to_json(),
    }


def job_out(info: JobInfo) -> dict[str, Any]:
    """Serialise one entry of the action history."""
    job = info.job
    return {
        "id": job.id,
        "integration": info.integration_name,
        "label": job.label,
        "face": job.face,
        "step": job.step + 1,
        "status": job.status.value,
        "attempts": job.attempts,
        "error": job.last_error,
        "created_at": iso(job.created_at),
        "finished_at": iso(job.finished_at),
    }


def device_out(info: DeviceInfo, status: DeviceStatus | None = None) -> dict[str, Any]:
    """Serialise a device with calibration and optional live status."""
    device = info.device
    return {
        "id": device.id,
        "alias": device.alias,
        "number": info.number,
        "color": info.color,
        "color_name": color_name(info.color),
        "badge": badge(info.number),
        "has_address": device.platform_address is not None,
        "model": device.model,
        "firmware": device.firmware,
        "created_at": iso(device.created_at),
        "is_active": info.is_active,
        "mode": device.mode.value,
        "configured_faces": info.configured_faces,
        "fully_calibrated": info.is_fully_calibrated,
        "actions": {str(face): action_out(action) for face, action in sorted(info.actions.items())},
        "faces": {
            str(face): {
                "activity_id": mapping.activity_id,
                "project_id": mapping.project_id,
                "revision": mapping.revision,
            }
            for face, mapping in sorted(info.mappings.items())
        },
        "status": device_status_out(status),
    }


def tracking_status_out(status: TrackingStatus, now: datetime) -> dict[str, Any]:
    """Serialise the overview snapshot."""
    return {
        "running": session_out(status.running, now) if status.running else None,
        "activity": activity_out(status.activity) if status.activity else None,
        "project": activity_out(status.project) if status.project else None,
        "elapsed_seconds": seconds(status.elapsed),
        "paused": status.paused,
        "active_device_id": status.active_device_id,
        "uncertain_count": status.uncertain_count,
    }


def ics_preview_out(preview: IcsPreview) -> dict[str, Any]:
    """Serialise the proposals of a calendar import."""
    return {
        "proposals": [
            {
                "index": p.index,
                "start": iso(p.start),
                "end": iso(p.end),
                "title": p.title,
                "overlaps": p.overlaps,
            }
            for p in preview.proposals
        ],
        "skipped": dict(preview.skipped),
    }


def source_out(source: MusicSource) -> dict[str, Any]:
    """Serialise a recognised music source."""
    return {
        "kind": source.kind.value,
        "uri": source.uri,
        "description": source.description,
        "ref": source.ref,
    }


def tag_out(tag: Tag) -> dict[str, Any]:
    """Serialise a tag."""
    return {"id": tag.id, "name": tag.name, "color": tag.color}


def billing_out(billing: ProjectBilling) -> dict[str, Any]:
    """Serialise budget, rate and billable flag."""
    return {
        "project_id": billing.project_id,
        "budget_minutes": billing.budget_minutes,
        "hourly_rate_cents": billing.hourly_rate_cents,
        "billable": billing.billable,
    }


def budget_out(item: ProjectBudget) -> dict[str, Any]:
    """Serialise the budget use of a project (the amount is computed, in cents)."""
    return {
        "project_id": item.project_id,
        "name": item.name,
        "color": item.color,
        "used_seconds": seconds(item.used),
        "budget_minutes": item.budget_minutes,
        "fraction": None if item.fraction is None else round(item.fraction, 4),
        "hourly_rate_cents": item.hourly_rate_cents,
        "amount_cents": item.amount_cents,
        "billable": item.billable,
    }


def schedule_out(schedule: WorkSchedule) -> dict[str, Any]:
    """Serialise one schedule version."""
    return {"valid_from": schedule.valid_from.isoformat(), "minutes": list(schedule.minutes)}


def absence_out(absence: Absence) -> dict[str, Any]:
    """Serialise an absence."""
    return {
        "id": absence.id,
        "start": absence.start.isoformat(),
        "end": absence.end.isoformat(),
        "kind": absence.kind.value,
        "target_minutes": absence.target_minutes,
        "note": absence.note,
    }


def balance_out(balance: Balance) -> dict[str, Any]:
    """Serialise the target/actual comparison (durations in seconds)."""
    return {
        "has_schedule": balance.has_schedule,
        "includes_running": balance.includes_running,
        "target_seconds": seconds(balance.target),
        "actual_seconds": seconds(balance.actual),
        "difference_seconds": seconds(balance.difference),
        "days": [
            {
                "day": d.day.isoformat(),
                "target_seconds": seconds(d.target),
                "actual_seconds": seconds(d.actual),
                "difference_seconds": seconds(d.difference),
                "balance_seconds": seconds(d.balance),
                "reason": d.reason,
            }
            for d in balance.days
        ],
    }


def attention_out(item: AttentionItem) -> dict[str, Any]:
    """Serialise an attention item."""
    return {
        "id": item.id,
        "kind": item.kind.value,
        "status": item.status.value,
        "created_at": iso(item.created_at),
        "resolved_at": iso(item.resolved_at) if item.resolved_at else None,
        "resolution": item.resolution,
        "session_id": item.session_id,
        "payload": item.payload,
    }


def share_out(share: Share) -> dict[str, Any]:
    """Serialise an activity/project share."""
    return {
        "id": share.id,
        "name": share.name,
        "color": share.color,
        "seconds": seconds(share.duration),
        "uncertain_seconds": seconds(share.uncertain),
        "fraction": round(share.fraction, 6),
    }


def report_out(report: Report) -> dict[str, Any]:
    """Serialise a report."""
    return {
        "window": [iso(report.window[0]), iso(report.window[1])],
        "timezone": report.timezone,
        "daily": [
            {
                "day": day.day.isoformat(),
                "device_seconds": seconds(day.device_time),
                "personal_seconds": seconds(day.personal_time),
                "uncertain_seconds": seconds(day.uncertain_time),
            }
            for day in report.daily
        ],
        "by_activity": [share_out(s) for s in report.by_activity],
        "by_project": [share_out(s) for s in report.by_project],
        "device_seconds": seconds(report.device_time),
        "personal_seconds": seconds(report.personal_time),
        "overlap_seconds": seconds(report.overlap_time),
        "uncertain_seconds": seconds(report.uncertain_time),
        "session_count": report.session_count,
        "includes_running": report.includes_running,
    }


def journal_out(entry: JournalEntry, now: datetime) -> dict[str, Any]:
    """Serialise one journal row."""
    data = session_out(entry.session, now)
    data.update(
        activity_name=entry.activity_name,
        project_name=entry.project_name,
        device_alias=entry.device_alias,
        tags=list(entry.tags),
        billable=entry.billable,
        amount_cents=entry.amount_cents,
    )
    return data


def scan_out(result: ScanResult) -> dict[str, Any]:
    """Serialise a scan result."""
    return {
        "address": result.address,
        "name": result.name,
        "rssi": result.rssi,
        "is_candidate": result.is_candidate,
        "looks_like_tracker": result.looks_like_tracker,
        "label": result.label,
    }
