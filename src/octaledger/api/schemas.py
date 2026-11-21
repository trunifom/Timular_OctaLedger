"""Versioned request and response schemas.

Requests are strict pydantic models (``extra="forbid"``: unknown fields are an error, so typos
are noticed). Responses are built by small functions into plain dictionaries with stable keys;
every timestamp is ISO-8601 UTC and every duration is an integer number of **seconds**, so any
client (the Streamlit dashboard, scripts) can consume them without knowing internal types.

The API version is part of every URL (``/api/v1``) and reported by ``/api/v1/health``. Breaking
changes require a new version prefix.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from octaledger.agent.supervisor import DeviceStatus
from octaledger.application.device_service import DeviceInfo
from octaledger.application.integration_service import IntegrationInfo, JobInfo
from octaledger.application.reporting_service import JournalEntry, Report, Share
from octaledger.application.tracking_service import TrackingStatus
from octaledger.domain.models import (
    FACE_NUMBERS,
    Activity,
    FaceAction,
    Project,
    Session,
)
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
    """Change a tracker's alias."""

    alias: str = Field(max_length=200)


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


class ActionAssign(_Strict):
    """Give a face an action of a connection."""

    integration_id: str = Field(min_length=1, max_length=64)
    label: str = Field(max_length=200)
    params: dict[str, Any]


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


def job_out(info: JobInfo) -> dict[str, Any]:
    """Serialise one entry of the action history."""
    job = info.job
    return {
        "id": job.id,
        "integration": info.integration_name,
        "label": job.label,
        "face": job.face,
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
