"""Validated device, session and reporting endpoints.

Conventions
-----------
* Every path lives under ``/api/v1``. Only ``/health`` is public (it reveals nothing but that
  the agent runs); **everything else requires the bearer token**.
* **No state change through ``GET``**: reads are ``GET``, every change is ``POST``/``PUT``/
  ``PATCH``/``DELETE`` (also the actions that look read-only but have effects, such as scanning
  or exporting a file).
* Handlers are plain ``def`` functions: FastAPI runs them in a thread pool, which is what we
  want for blocking SQLite work. They contain **no business logic** - they call a service,
  convert the result with a function from :mod:`octaledger.api.schemas` and let errors bubble
  up to the central mapping in :mod:`octaledger.api.app`.
"""

from __future__ import annotations

import base64
import logging
from datetime import date, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query

from octaledger import __version__
from octaledger.agent.tray import tray_available
from octaledger.api.context import AppContext
from octaledger.api.schemas import (
    API_VERSION,
    AbsenceCreate,
    ActionAssign,
    ActivityDefaults,
    AddressBody,
    ArchiveBody,
    AttentionResolve,
    AutostartBody,
    BillingBody,
    ButtonBody,
    CatalogCreate,
    CatalogUpdate,
    CorrectBody,
    DeviceCreate,
    DeviceRemove,
    DeviceRename,
    EntriesDelete,
    EntriesRange,
    ExportCsvBody,
    FaceAssign,
    FindBody,
    IcsApplyBody,
    IcsPreviewBody,
    IntegrationCreate,
    IntegrationUpdate,
    ManualSession,
    ModeBody,
    ProbeBody,
    ReasonBody,
    RenderBody,
    ResetBody,
    RestoreBody,
    RestoreInspectBody,
    ScanBody,
    ScheduleBody,
    SettingsBody,
    SettingsReset,
    SplitBody,
    StartBody,
    TagCreate,
    TagIds,
    TagUpdate,
    absence_out,
    activity_out,
    adapter_out,
    attention_out,
    balance_out,
    billing_out,
    budget_out,
    device_out,
    ics_preview_out,
    integration_out,
    iso,
    job_out,
    journal_out,
    live_out,
    report_out,
    scan_out,
    schedule_out,
    session_out,
    tag_out,
    tracking_status_out,
)
from octaledger.api.security import parse_bearer, verify_token
from octaledger.application.data_service import DataService
from octaledger.application.ics_import import IcsEntry, ics_available
from octaledger.application.report_render import (
    build_document,
    pdf_available,
    render_html,
    render_pdf,
)
from octaledger.application.reporting_service import ReportFilter
from octaledger.core.errors import ApiUnavailableError, InvalidStateError, ValidationError
from octaledger.core.settings import (
    Settings,
    settings_from_mapping,
    settings_to_mapping,
)
from octaledger.domain.attention import AttentionKind
from octaledger.domain.models import DeviceMode
from octaledger.domain.time_rules import ensure_utc, local_day_bounds, utc_now
from octaledger.infrastructure.system.holidays_provider import holidays_available
from octaledger.infrastructure.system.toast import toast_available

logger = logging.getLogger(__name__)

#: The text a user must type to confirm a factory reset (also checked by the dashboard).
RESET_CONFIRMATION = "ALLES LÖSCHEN"


def build_router(ctx: AppContext) -> APIRouter:
    """Create the router with all endpoints bound to ``ctx``."""

    def require_auth(authorization: Annotated[str | None, Header()] = None) -> None:
        """Dependency: the request must carry the correct bearer token."""
        verify_token(parse_bearer(authorization), ctx.token)

    public = APIRouter()
    router = APIRouter(dependencies=[Depends(require_auth)])

    def now() -> datetime:
        """Current time in UTC (one place, so tests can see it used consistently)."""
        return utc_now()

    def device_statuses() -> dict[str, Any]:
        """Live status of every started device by device id (empty without an agent)."""
        return {s.device_id: s for s in (ctx.agent.device_statuses() if ctx.agent else [])}

    def require_agent() -> Any:
        """Return the agent control or answer 503 when the API runs without a BLE agent."""
        if ctx.agent is None:
            raise ApiUnavailableError("The BLE agent is not running in this process")
        return ctx.agent

    def require_integrations() -> Any:
        """Return the integration service or answer 503 when control mode is unavailable."""
        if ctx.integrations is None:
            raise ApiUnavailableError("Control mode is not available in this process")
        return ctx.integrations

    # ----------------------------------------------------------------------- health
    @public.get("/health")
    def health() -> dict[str, Any]:
        """Public liveness check (reveals nothing but the versions)."""
        return {"status": "ok", "api_version": API_VERSION, "version": __version__}

    # ------------------------------------------------------------------- overview
    @router.get("/status")
    def status() -> dict[str, Any]:
        """Overview: running session, active tracker, live device states."""
        moment = now()
        live = device_statuses()
        return {
            "tracking": tracking_status_out(ctx.tracking.status(), moment),
            "devices": [
                {
                    "id": info.device.id,
                    "alias": info.device.alias,
                    "is_active": info.is_active,
                    "mode": info.device.mode.value,
                    "live": device_out(info, live.get(info.device.id))["status"],
                }
                for info in ctx.devices.list_devices()
            ],
            "agent_running": ctx.agent is not None,
            "server_time": iso(moment),
        }

    # --------------------------------------------------------------------- devices
    @router.get("/devices")
    def list_devices() -> list[dict[str, Any]]:
        """All devices with calibration and live status."""
        live = device_statuses()
        return [device_out(i, live.get(i.device.id)) for i in ctx.devices.list_devices()]

    @router.post("/devices", status_code=201)
    def register_device(body: DeviceCreate) -> dict[str, Any]:
        """Register a tracker (the first one becomes the active tracker)."""
        device = ctx.devices.register(body.alias, platform_address=body.platform_address)
        return device_out(ctx.devices.get(device.id))

    @router.patch("/devices/{device_id}")
    def rename_device(device_id: str, body: DeviceRename) -> dict[str, Any]:
        """Change a tracker's alias."""
        ctx.devices.rename(device_id, body.alias)
        return device_out(ctx.devices.get(device_id))

    @router.delete("/devices/{device_id}", status_code=204)
    def remove_device(device_id: str) -> None:
        """Remove a device without recorded data."""
        ctx.devices.remove(device_id)

    @router.put("/devices/{device_id}/faces/{face}")
    def assign_face(device_id: str, face: int, body: FaceAssign) -> dict[str, Any]:
        """Assign an activity (and project) to a face 1..8."""
        ctx.devices.assign_face(device_id, face, body.activity_id, body.project_id)
        return device_out(ctx.devices.get(device_id))

    @router.delete("/devices/{device_id}/faces/{face}")
    def clear_face(device_id: str, face: int) -> dict[str, Any]:
        """Remove the assignment of a face."""
        ctx.devices.clear_face(device_id, face)
        return device_out(ctx.devices.get(device_id))

    @router.get("/devices/{device_id}/observed-face")
    def observed_face(device_id: str) -> dict[str, Any]:
        """The face most recently seen from the device (guided calibration)."""
        seen = ctx.devices.last_observed_face(device_id)
        if seen is None:
            return {"face": None}
        return {"face": seen.face, "received_at": iso(seen.received_at), "kind": seen.kind.value}

    @router.get("/devices/{device_id}/live")
    def live_view(device_id: str) -> dict[str, Any]:
        """Live position of the cube, the debounce state, recent movements and their effect."""
        info = ctx.devices.get(device_id)
        activities = {a.id: a for a in ctx.catalog.list_activities(include_archived=True)}
        projects = {p.id: p for p in ctx.catalog.list_projects(include_archived=True)}
        tracking = tracking_status_out(ctx.tracking.status(), now())
        return live_out(info, device_statuses().get(device_id), activities, projects, tracking)

    @router.put("/devices/{device_id}/mode")
    def set_device_mode(device_id: str, body: ModeBody) -> dict[str, Any]:
        """Switch a tracker between time recording (``time``) and control (``control``)."""
        try:
            mode = DeviceMode(body.mode)
        except ValueError:
            raise ValidationError(
                f"Invalid mode {body.mode!r}",
                user_message="Der Modus muss „time“ (Zeit) oder „control“ (Steuerung) sein.",
            ) from None
        ctx.devices.set_mode(device_id, mode)
        return device_out(ctx.devices.get(device_id), device_statuses().get(device_id))

    @router.put("/devices/{device_id}/actions/{face}")
    def assign_action(device_id: str, face: int, body: ActionAssign) -> dict[str, Any]:
        """Give a face an action of a connection (validated by the connection's adapter)."""
        require_integrations().assign_action(
            device_id, face, body.integration_id, body.label, body.params
        )
        return device_out(ctx.devices.get(device_id))

    @router.delete("/devices/{device_id}/actions/{face}")
    def clear_action(device_id: str, face: int) -> dict[str, Any]:
        """Remove the action of a face."""
        require_integrations().clear_action(device_id, face)
        return device_out(ctx.devices.get(device_id))

    @router.post("/devices/{device_id}/activate")
    def activate_device(device_id: str) -> dict[str, Any]:
        """Explicit hand-over: make this tracker the active one."""
        ended = ctx.tracking.handover(device_id)
        return {"ended_session": session_out(ended) if ended else None}

    @router.post("/devices/{device_id}/connect")
    def connect_device(device_id: str) -> dict[str, Any]:
        """Start the Bluetooth connection of a device (needs a stored address)."""
        agent = require_agent()
        info = ctx.devices.get(device_id)
        if info.device.platform_address is None:
            raise ValidationError(
                "Device has no Bluetooth address",
                user_message="Für dieses Gerät ist keine Bluetooth-Adresse gespeichert. "
                "Bitte zuerst per Suche zuordnen.",
            )
        agent.start_device(device_id)
        return {"started": True}

    @router.post("/devices/{device_id}/disconnect")
    def disconnect_device(device_id: str) -> dict[str, Any]:
        """Stop a device on purpose (no reconnect)."""
        ctx.devices.get(device_id)  # 404 for unknown devices
        require_agent().stop_device(device_id)
        return {"stopped": True}

    @router.post("/devices/{device_id}/address")
    def set_device_address(device_id: str, body: AddressBody) -> dict[str, Any]:
        """Store the Bluetooth address found by a scan for a device."""
        ctx.devices.update_hardware_info(device_id, platform_address=body.platform_address)
        return device_out(ctx.devices.get(device_id))

    @router.post("/scan")
    def scan(body: ScanBody) -> list[dict[str, Any]]:
        """Scan for BLE devices (explicit user action; never connects by itself)."""
        return [scan_out(r) for r in require_agent().scan(body.seconds)]

    # ----------------------------------------------------- control mode: connections
    @router.get("/adapters")
    def list_adapters() -> list[dict[str, Any]]:
        """The kinds of connection OctaLedger offers, each with its form description."""
        return [adapter_out(spec) for spec in require_integrations().adapter_specs()]

    @router.get("/integrations")
    def list_integrations() -> list[dict[str, Any]]:
        """All connections (settings and the names of stored secrets, never secret values)."""
        return [integration_out(i) for i in require_integrations().list_integrations()]

    @router.post("/integrations", status_code=201)
    def create_integration(body: IntegrationCreate) -> dict[str, Any]:
        """Create a connection; secrets in ``values`` go to the separate secret store."""
        return integration_out(require_integrations().create(body.kind, body.name, body.values))

    @router.patch("/integrations/{integration_id}")
    def update_integration(integration_id: str, body: IntegrationUpdate) -> dict[str, Any]:
        """Change name, settings, secrets (blank keeps) or the enabled flag."""
        return integration_out(
            require_integrations().update(
                integration_id, name=body.name, values=body.values, enabled=body.enabled
            )
        )

    @router.delete("/integrations/{integration_id}", status_code=204)
    def delete_integration(integration_id: str) -> None:
        """Delete a connection (refused while a face still uses it)."""
        require_integrations().delete(integration_id)

    @router.post("/integrations/{integration_id}/check")
    def check_integration(integration_id: str) -> dict[str, Any]:
        """Test the connection without side effects."""
        return {"message": require_integrations().check(integration_id)}

    @router.post("/integrations/{integration_id}/probe")
    def probe_integration(integration_id: str, body: ProbeBody) -> dict[str, Any]:
        """Run one action right now (\"try it\")."""
        return {"message": require_integrations().probe(integration_id, body.params)}

    @router.post("/integrations/{integration_id}/pair")
    def pair_integration(integration_id: str) -> dict[str, Any]:
        """Run the one-time pairing (for example after pressing the bridge button)."""
        return {"message": require_integrations().pair(integration_id)}

    @router.post("/adapters/{kind}/find")
    def find_targets(kind: str, body: FindBody) -> dict[str, Any]:
        """Look for the target on the network, e.g. a Hue Bridge (``online`` is opt-in)."""
        return {"items": require_integrations().find_targets(kind, online=body.online)}

    @router.post("/integrations/{integration_id}/discover")
    def discover_integration(integration_id: str) -> dict[str, Any]:
        """List lights, scenes ... the target offers to choose from."""
        return {"items": require_integrations().discover(integration_id)}

    @router.get("/jobs")
    def list_jobs(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[dict[str, Any]]:
        """History of sent actions, newest first."""
        return [job_out(j) for j in require_integrations().list_jobs(limit)]

    # ------------------------------------------------------------ activities/projects
    def catalog_routes(kind: str, plural_name: str) -> None:
        """Register the five routes of one catalogue kind (activities or projects)."""
        plural = f"/{plural_name}"
        create = ctx.catalog.create_activity if kind == "activity" else ctx.catalog.create_project
        listing = ctx.catalog.list_activities if kind == "activity" else ctx.catalog.list_projects
        update = ctx.catalog.update_activity if kind == "activity" else ctx.catalog.update_project
        archive = (
            ctx.catalog.archive_activity if kind == "activity" else ctx.catalog.archive_project
        )
        delete = ctx.catalog.delete_activity if kind == "activity" else ctx.catalog.delete_project

        @router.get(plural, name=f"list_{kind}s")
        def list_items(include_archived: bool = False) -> list[dict[str, Any]]:
            """List the items; archived ones only when asked for."""
            return [activity_out(i) for i in listing(include_archived=include_archived)]

        @router.post(plural, status_code=201, name=f"create_{kind}")
        def create_item(body: CatalogCreate) -> dict[str, Any]:
            """Create an item (colour is chosen automatically when omitted)."""
            return activity_out(create(body.name, body.color))

        @router.patch(plural + "/{item_id}", name=f"update_{kind}")
        def update_item(item_id: str, body: CatalogUpdate) -> dict[str, Any]:
            """Rename and/or recolour an item."""
            return activity_out(update(item_id, name=body.name, color=body.color))

        @router.post(plural + "/{item_id}/archive", name=f"archive_{kind}")
        def archive_item(item_id: str, body: ArchiveBody) -> dict[str, Any]:
            """Archive an item, or restore it with ``archived=false``."""
            return activity_out(archive(item_id, body.archived))

        @router.delete(plural + "/{item_id}", status_code=204, name=f"delete_{kind}")
        def delete_item(item_id: str) -> None:
            """Delete an unused item (used ones must be archived instead)."""
            delete(item_id)

    catalog_routes("activity", "activities")
    catalog_routes("project", "projects")

    # --------------------------------------------------------------------- tracking
    @router.post("/tracking/start")
    def start_tracking(body: StartBody) -> dict[str, Any]:
        """Start a manual session now."""
        return session_out(ctx.tracking.start_manual(body.activity_id, body.project_id, body.note))

    @router.post("/tracking/stop")
    def stop_tracking() -> dict[str, Any]:
        """End the running session."""
        return session_out(ctx.tracking.stop())

    @router.post("/tracking/pause")
    def pause_tracking() -> dict[str, Any]:
        """Pause: end the session and remember its activity."""
        return session_out(ctx.tracking.pause())

    @router.post("/tracking/resume")
    def resume_tracking() -> dict[str, Any]:
        """Resume the paused activity."""
        return session_out(ctx.tracking.resume())

    # ---------------------------------------------------------------------- sessions
    @router.get("/sessions")
    def journal(
        start: datetime,
        end: datetime,
        device_id: str | None = None,
        activity_id: str | None = None,
        project_id: str | None = None,
        tag_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Journal: whole sessions overlapping the window, newest first."""
        moment = now()
        flt = ReportFilter(start, end, device_id, activity_id, project_id, tag_id)
        return [journal_out(e, moment) for e in ctx.reports.journal(flt)]

    # ------------------------------------------------------------- tags and billing
    @router.get("/tags")
    def list_tags() -> list[dict[str, Any]]:
        """All tags by name."""
        return [tag_out(t) for t in ctx.tag_service.list_tags()]

    @router.post("/tags", status_code=201)
    def create_tag(body: TagCreate) -> dict[str, Any]:
        """Create a tag (names are unique, case-insensitive)."""
        return tag_out(ctx.tag_service.create_tag(body.name, body.color))

    @router.put("/tags/{tag_id}")
    def update_tag(tag_id: str, body: TagUpdate) -> dict[str, Any]:
        """Rename or recolour a tag."""
        return tag_out(ctx.tag_service.update_tag(tag_id, body.name, body.color))

    @router.delete("/tags/{tag_id}", status_code=204)
    def delete_tag(tag_id: str) -> None:
        """Delete a tag; it disappears from all entries and activities."""
        ctx.tag_service.delete_tag(tag_id)

    @router.put("/sessions/{session_id}/tags")
    def set_session_tags(session_id: str, body: TagIds) -> list[dict[str, Any]]:
        """Replace the tags of an entry."""
        return [tag_out(t) for t in ctx.tag_service.set_session_tags(session_id, body.tag_ids)]

    @router.get("/activities/{activity_id}/defaults")
    def get_activity_defaults(activity_id: str) -> dict[str, Any]:
        """Default tags and note template of an activity."""
        data = ctx.tag_service.get_activity_defaults(activity_id)
        tags: Any = data["tags"]
        return {"tags": [tag_out(t) for t in tags], "note_template": data["note_template"]}

    @router.put("/activities/{activity_id}/defaults")
    def set_activity_defaults(activity_id: str, body: ActivityDefaults) -> dict[str, Any]:
        """Set the tags new entries of the activity get and its note template."""
        ctx.tag_service.set_activity_defaults(activity_id, body.tag_ids, body.note_template)
        return get_activity_defaults(activity_id)

    @router.get("/projects/{project_id}/billing")
    def get_billing(project_id: str) -> dict[str, Any]:
        """Budget, hourly rate and billable flag of a project."""
        return billing_out(ctx.tag_service.get_billing(project_id))

    @router.put("/projects/{project_id}/billing")
    def set_billing(project_id: str, body: BillingBody) -> dict[str, Any]:
        """Set budget (minutes), hourly rate (cents) and billable flag of a project."""
        return billing_out(
            ctx.tag_service.set_billing(
                project_id, body.budget_minutes, body.hourly_rate_cents, body.billable
            )
        )

    @router.get("/reports/budgets")
    def budgets() -> list[dict[str, Any]]:
        """Used time, budget share and amount per project with billing information."""
        return [budget_out(b) for b in ctx.reports.budgets()]

    # ---------------------------------------------------------------------- system
    def autostart_out() -> dict[str, Any]:
        """The autostart state as an API answer."""
        status = ctx.autostart.status()
        return {
            "available": status.available,
            "enabled": status.enabled,
            "current": status.current,
            "command": status.command,
        }

    @router.get("/system/autostart")
    def get_autostart() -> dict[str, Any]:
        """Whether OctaLedger starts with Windows (read from the registry)."""
        return autostart_out()

    @router.put("/system/autostart")
    def set_autostart(body: AutostartBody) -> dict[str, Any]:
        """Switch "start with Windows" on or off (Windows only; 409 elsewhere)."""
        if body.enabled:
            ctx.autostart.enable()
        else:
            ctx.autostart.disable()
        return autostart_out()

    @router.get("/system/capabilities")
    def capabilities() -> dict[str, Any]:
        """Which optional extras are installed (tray icon, toast messages)."""
        return {
            "tray": tray_available(),
            "toast": toast_available(),
            "pdf": pdf_available(),
            "ics": ics_available(),
            "holidays": holidays_available(),
        }

    # --------------------------------------------------------------------- buttons
    @router.get("/devices/{device_id}/buttons")
    def device_buttons(device_id: str) -> dict[str, Any]:
        """The actions assigned to the cube's short and long button press."""
        return {"buttons": ctx.devices.get_buttons(device_id)}

    @router.put("/devices/{device_id}/buttons/{press}")
    def set_device_button(device_id: str, press: str, body: ButtonBody) -> dict[str, Any]:
        """Assign an action (``pause_resume``, ``stop``, ``start_last``) or ``none``."""
        return {"buttons": ctx.devices.set_button(device_id, press, body.action)}

    # ------------------------------------------------------------------- attention
    @router.get("/attention")
    def attention() -> dict[str, Any]:
        """Open questions plus connections that are lost but still inside the grace period."""
        moment = now()
        grace = ctx.settings.settings.tracking.disconnect_grace_seconds
        names = {d.device.id: d.device.alias for d in ctx.devices.list_devices()}
        waiting = [
            {
                "device_id": device_id,
                "alias": names.get(device_id, ""),
                "since": iso(since),
                "stops_at": iso(since + timedelta(seconds=grace)),
                "grace_seconds": grace,
            }
            for device_id, since in sorted(ctx.tracking.link_lost_since().items())
        ]
        return {
            "items": [attention_out(i) for i in ctx.attention.list_open()],
            "link_lost": waiting,
            "server_time": iso(moment),
        }

    @router.post("/attention/{item_id}/resolve")
    def resolve_attention(item_id: str, body: AttentionResolve) -> dict[str, Any]:
        """Answer a question; the allowed answers depend on its kind (see API.md)."""
        item = ctx.attention.get(item_id)
        if item.kind is AttentionKind.GAP:
            closed = ctx.tracking.resolve_gap(
                item_id, body.action, activity_id=body.activity_id, project_id=body.project_id
            )
        elif item.kind is AttentionKind.IDLE:
            closed = ctx.workday.resolve_idle(item_id, body.action)
        elif item.kind is AttentionKind.AUTO_STOP:
            closed = ctx.workday.resolve_auto_stop(item_id, body.action, body.until)
        else:
            raise InvalidStateError(
                f"Attention item {item_id} cannot be answered, only dismissed",
                user_message="Diese Meldung wird nur mit „Verstanden“ geschlossen.",
            )
        return attention_out(closed)

    @router.post("/attention/{item_id}/dismiss")
    def dismiss_attention(item_id: str) -> dict[str, Any]:
        """Close a question without acting on it."""
        return attention_out(ctx.attention.dismiss(item_id))

    @router.get("/sessions/uncertain")
    def uncertain() -> list[dict[str, Any]]:
        """Sessions waiting for the user's confirmation."""
        moment = now()
        return [session_out(s, moment) for s in ctx.tracking.list_uncertain()]

    @router.post("/sessions", status_code=201)
    def add_session(body: ManualSession) -> dict[str, Any]:
        """Add a finished, back-dated session."""
        return session_out(
            ctx.tracking.add_manual_session(
                body.activity_id, body.start, body.end, body.project_id, body.note
            )
        )

    @router.post("/sessions/{session_id}/correct")
    def correct_session(session_id: str, body: CorrectBody) -> dict[str, Any]:
        """Correct a session with an audit trail."""
        changes = {
            key: _parse_time(value) if key in ("started_at", "ended_at") else value
            for key, value in body.changes.items()
        }
        return session_out(ctx.tracking.correct_session(session_id, changes, body.reason))

    @router.post("/sessions/{session_id}/split")
    def split_session(session_id: str, body: SplitBody) -> list[dict[str, Any]]:
        """Split a session in two."""
        first, second = ctx.tracking.split_session(session_id, body.at, body.reason)
        return [session_out(first), session_out(second)]

    @router.post("/sessions/{session_id}/confirm")
    def confirm_session(session_id: str) -> dict[str, Any]:
        """Mark an uncertain session as confirmed."""
        return session_out(ctx.tracking.confirm_session(session_id))

    @router.post("/sessions/{session_id}/delete", status_code=204)
    def delete_session(session_id: str, body: ReasonBody) -> None:
        """Delete a session (reason required, audited)."""
        ctx.tracking.delete_session(session_id, body.reason)

    # ----------------------------------------------------------------------- reports
    def display_tz() -> str:
        """The display timezone from the saved settings."""
        return ctx.settings.settings.display.timezone

    @router.get("/reports")
    def report(
        start: datetime,
        end: datetime,
        tz: str | None = None,
        device_id: str | None = None,
        activity_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Report for a window and filters."""
        flt = ReportFilter(start, end, device_id, activity_id, project_id)
        return report_out(ctx.reports.report(flt, tz or display_tz()))

    @router.post("/reports/render")
    def render_report(body: RenderBody) -> dict[str, Any]:
        """A printable report (``html`` or ``pdf``, the latter as base64) for local days."""
        zone = body.tz or display_tz()
        tz = ZoneInfo(zone)
        start = local_day_bounds(body.first, tz)[0]
        end = local_day_bounds(body.last, tz)[1]
        settings = ctx.settings.settings
        report = ctx.reports.report(ReportFilter(start, end), zone)
        balance = ctx.reports.balance(
            body.first, body.last, zone, holiday_region=settings.work.holiday_region
        )
        doc = build_document(
            report,
            tz,
            first=body.first,
            last=body.last,
            author=settings.report.author,
            organization=settings.report.organization,
            balance=balance,
        )
        stem = f"zeitbericht-{body.first.isoformat()}-{body.last.isoformat()}"
        if body.format == "html":
            return {"format": "html", "filename": f"{stem}.html", "content": render_html(doc)}
        if body.format == "pdf":
            pdf = base64.b64encode(render_pdf(doc)).decode("ascii")
            return {"format": "pdf", "filename": f"{stem}.pdf", "content": pdf}
        raise ValidationError(
            f"Unknown report format {body.format!r}",
            user_message="Das Format muss html oder pdf sein.",
        )

    @router.post("/import/ics/preview")
    def ics_preview(body: IcsPreviewBody) -> dict[str, Any]:
        """Read appointments from a calendar file as proposals; nothing is booked."""
        zone = ZoneInfo(body.tz or display_tz())
        return ics_preview_out(ctx.ics.preview(body.content, body.first, body.last, zone))

    @router.post("/import/ics/apply", status_code=201)
    def ics_apply(body: IcsApplyBody) -> dict[str, Any]:
        """Book the confirmed appointments (all or nothing)."""
        created = ctx.ics.apply(
            [IcsEntry(e.start, e.end, e.activity_id, e.project_id, e.note) for e in body.entries]
        )
        return {"created": len(created)}

    @router.get("/reports/balance")
    def balance(first: date, last: date, tz: str | None = None) -> dict[str, Any]:
        """Target, actual and running balance for each local day in ``[first, last]``."""
        region = ctx.settings.settings.work.holiday_region
        return balance_out(
            ctx.reports.balance(first, last, tz or display_tz(), holiday_region=region)
        )

    @router.get("/schedule")
    def get_schedule() -> list[dict[str, Any]]:
        """The target working time per weekday, one entry per valid-from date."""
        return [schedule_out(s) for s in ctx.worktime.list_schedules()]

    @router.put("/schedule")
    def put_schedule(body: ScheduleBody) -> list[dict[str, Any]]:
        """Create or replace the schedule that starts on ``valid_from``."""
        return [schedule_out(s) for s in ctx.worktime.set_schedule(body.valid_from, body.minutes)]

    @router.delete("/schedule/{valid_from}")
    def delete_schedule(valid_from: date) -> list[dict[str, Any]]:
        """Remove one schedule version."""
        return [schedule_out(s) for s in ctx.worktime.delete_schedule(valid_from)]

    @router.get("/absences")
    def get_absences() -> list[dict[str, Any]]:
        """All absences (vacation, sick days, own holidays), oldest first."""
        return [absence_out(a) for a in ctx.worktime.list_absences()]

    @router.post("/absences", status_code=201)
    def add_absence(body: AbsenceCreate) -> dict[str, Any]:
        """Record an absence."""
        return absence_out(
            ctx.worktime.add_absence(
                body.start, body.end, body.kind, body.target_minutes, body.note
            )
        )

    @router.delete("/absences/{absence_id}", status_code=204)
    def delete_absence(absence_id: str) -> None:
        """Remove an absence."""
        ctx.worktime.delete_absence(absence_id)

    @router.get("/reports/day")
    def day_report(
        day: date,
        tz: str | None = None,
        device_id: str | None = None,
        activity_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Report for one local calendar day."""
        return report_out(
            ctx.reports.day_report(
                day,
                tz or display_tz(),
                device_id=device_id,
                activity_id=activity_id,
                project_id=project_id,
            )
        )

    @router.get("/reports/week")
    def week_report(
        day: date,
        tz: str | None = None,
        week_starts_on: Annotated[int, Query(ge=0, le=6)] = 0,
        device_id: str | None = None,
        activity_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Report for the local week containing ``day``."""
        return report_out(
            ctx.reports.week_report(
                day,
                tz or display_tz(),
                week_starts_on=week_starts_on,
                device_id=device_id,
                activity_id=activity_id,
                project_id=project_id,
            )
        )

    # ------------------------------------------------------------------- data/backup
    @router.post("/export/csv")
    def export_csv(body: ExportCsvBody) -> dict[str, Any]:
        """Write a CSV file into the export folder and return its content for download."""
        result = ctx.exports.export_sessions_csv(
            timezone_name=body.tz, delimiter=body.delimiter, start=body.start, end=body.end
        )
        content = result.path.read_text(encoding="utf-8-sig")
        return {
            "filename": result.path.name,
            "rows": result.rows,
            "size": result.size_bytes,
            "content": content,
        }

    @router.post("/backup")
    def create_backup() -> dict[str, Any]:
        """Write a JSON backup into the backup folder and return its content for download."""
        result = ctx.exports.export_backup()
        return {
            "filename": result.path.name,
            "records": result.rows,
            "size": result.size_bytes,
            "content": result.path.read_text(encoding="utf-8"),
        }

    @router.post("/restore/inspect")
    def inspect_restore(body: RestoreInspectBody) -> dict[str, Any]:
        """Validate a backup completely WITHOUT changing anything (preview)."""
        summary = ctx.exports.inspect_backup_text(body.content)
        return {
            "schema_version": summary.schema_version,
            "app_version": summary.app_version,
            "exported_at": iso(summary.exported_at),
            "counts": dict(summary.counts),
        }

    @router.post("/restore")
    def restore(body: RestoreBody) -> dict[str, Any]:
        """Replace all data with a validated backup (requires ``confirm: true``)."""
        if not body.confirm:
            raise InvalidStateError(
                "Restore requires explicit confirmation",
                user_message="Bitte bestätigen Sie die Wiederherstellung ausdrücklich.",
            )
        result = ctx.exports.restore_backup_text(body.content)
        return {
            "restored": dict(result.summary.counts),
            "pre_restore_backup": result.pre_restore_backup.name,
        }

    # ------------------------------------------------------------- data management
    def data_service() -> DataService:
        """The data-management service (always present, see ``AppContext``)."""
        assert ctx.data is not None
        return ctx.data

    def stats_out(stats: Any) -> dict[str, Any]:
        """Serialise a deletion preview."""
        return {
            "count": stats.count,
            "with_note": stats.with_note,
            "first": iso(stats.first),
            "last": iso(stats.last),
            "running_left_out": stats.running_left_out,
        }

    @router.get("/data/overview")
    def data_overview() -> dict[str, Any]:
        """How much of everything is stored."""
        o = data_service().overview()
        return {
            "sessions": o.sessions,
            "running_sessions": o.running_sessions,
            "raw_events": o.raw_events,
            "devices": o.devices,
            "activities": o.activities,
            "projects": o.projects,
            "integrations": o.integrations,
            "first_session": iso(o.first_session),
            "last_session": iso(o.last_session),
        }

    @router.post("/data/entries/preview")
    def preview_entries(body: EntriesRange) -> dict[str, Any]:
        """What deleting the entries of a period would touch (changes nothing)."""
        return stats_out(data_service().preview_entries(body.start, body.end))

    @router.post("/data/entries/delete")
    def delete_entries(body: EntriesDelete) -> dict[str, Any]:
        """Delete the entries of a period after an automatic safety backup."""
        result = data_service().delete_entries(
            body.start,
            body.end,
            expected_count=body.expected_count,
            include_events=body.include_events,
        )
        return {
            "sessions": result.sessions,
            "raw_events": result.raw_events,
            "safety_backup": result.safety_backup,
        }

    @router.post("/data/reset")
    def factory_reset(body: ResetBody) -> dict[str, Any]:
        """Delete everything (needs the exact confirmation text), after a safety backup."""
        if body.confirm_text.strip() != RESET_CONFIRMATION:
            raise InvalidStateError(
                "Reset requires the confirmation text",
                user_message=f"Bitte tippen Sie zur Bestätigung genau „{RESET_CONFIRMATION}“.",
            )
        result = data_service().factory_reset(reset_settings=body.reset_settings)
        return {
            "counts": result.counts,
            "safety_backup": result.safety_backup,
            "settings_reset": result.settings_reset,
        }

    @router.post("/devices/{device_id}/remove")
    def remove_device_with_options(device_id: str, body: DeviceRemove) -> dict[str, Any]:
        """Remove a cube; ``delete_data`` also removes everything recorded with it."""
        if ctx.agent is not None:
            ctx.agent.stop_device(device_id)
        result = data_service().remove_device(device_id, delete_data=body.delete_data)
        return {
            "sessions": result.sessions,
            "raw_events": result.raw_events,
            "safety_backup": result.safety_backup,
        }

    @router.post("/devices/{device_id}/unpair")
    def unpair_device(device_id: str) -> dict[str, Any]:
        """Stop the connection and forget the Bluetooth address; the cube and its data stay."""
        ctx.devices.get(device_id)  # 404 for unknown devices
        if ctx.agent is not None:
            ctx.agent.stop_device(device_id)
        ctx.devices.forget_address(device_id)
        return device_out(ctx.devices.get(device_id))

    # ----------------------------------------------------------------------- settings
    @router.get("/settings")
    def get_settings() -> dict[str, Any]:
        """Current settings as nested sections."""
        return settings_to_mapping(ctx.settings.settings)

    @router.put("/settings")
    def put_settings(body: SettingsBody) -> dict[str, Any]:
        """Validate and persist settings (partial sections keep the other values)."""
        merged = settings_to_mapping(ctx.settings.settings)
        for section, values in body.settings.items():
            if section not in merged:
                raise ValidationError(
                    f"Unknown settings section {section!r}",
                    user_message=f"Unbekannter Einstellungsbereich: {section}.",
                )
            merged[section].update(values)
        new = settings_from_mapping(merged)  # validates everything, rejects unknown keys
        ctx.settings.update(new)
        return settings_to_mapping(new)

    @router.post("/settings/reset")
    def reset_settings(body: SettingsReset) -> dict[str, Any]:
        """Restore the default settings of one section, or of all sections."""
        defaults = settings_to_mapping(Settings())
        if body.section is None:
            new = Settings()
        else:
            if body.section not in defaults:
                raise ValidationError(
                    f"Unknown settings section {body.section!r}",
                    user_message=f"Unbekannter Einstellungsbereich: {body.section}.",
                )
            merged = settings_to_mapping(ctx.settings.settings)
            merged[body.section] = defaults[body.section]
            new = settings_from_mapping(merged)
        ctx.settings.update(new)
        return settings_to_mapping(new)

    # ---------------------------------------------------------------------- diagnostics
    @router.get("/diagnostics/logs")
    def logs(limit: Annotated[int, Query(ge=1, le=1000)] = 200) -> dict[str, Any]:
        """The most recent (already redacted) log lines."""
        return {"lines": ctx.log_lines()[-limit:]}

    @router.get("/diagnostics/integrity")
    def integrity() -> dict[str, Any]:
        """Run the database integrity check."""
        problems = ctx.storage.database.integrity_check()
        return {"ok": not problems, "problems": problems}

    wrapper = APIRouter()
    wrapper.include_router(public)  # /health: no authentication
    wrapper.include_router(router)  # everything else: bearer token required
    return wrapper


def _parse_time(value: object) -> datetime:
    """Parse an ISO timestamp from a correction request into an aware UTC datetime."""
    if isinstance(value, datetime):
        return ensure_utc(value)
    if not isinstance(value, str):
        raise ValidationError(f"Invalid timestamp {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(
            f"Invalid timestamp {value!r}",
            user_message="Die Zeitangabe ist ungültig (erwartet: ISO-Format mit Zeitzone).",
        ) from exc
    return ensure_utc(parsed)
