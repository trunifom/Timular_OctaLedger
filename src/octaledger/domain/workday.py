"""Pure rules for the working day: automatic stop, idle detection and reminders.

The most common wrong booking is the forgotten stop (and the forgotten start). These rules
decide, from the clock, the running entry and the idle time, **what should be raised**; they
do no I/O and make no changes themselves. Everything is off after installation.

Privacy: the only input is *how long ago the last keyboard/mouse input was*; nothing about
what was typed or shown is ever looked at.

Times are evaluated in the display timezone (``tz``) because "workday ends at 17:30" means the
user's local clock. The returned moments are UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from octaledger.core.settings import WorkSettings


class WorkAction(StrEnum):
    """What the service should do."""

    #: End the running entry at the end of the workday.
    AUTO_STOP = "auto_stop"
    #: Ask what to do about a period without input.
    IDLE = "idle"
    #: Remind that no timer is running although the day has started.
    REMIND_NO_TIMER = "remind_no_timer"
    #: Remind that one entry has been running for a long time.
    REMIND_RUNNING = "remind_running"


@dataclass(frozen=True, slots=True)
class WorkDecision:
    """One thing to do, with the moment it refers to (UTC)."""

    action: WorkAction
    at: datetime


@dataclass(frozen=True, slots=True)
class RunningEntry:
    """The running entry as far as the rules need it."""

    id: str
    started_at: datetime


@dataclass(frozen=True, slots=True)
class DayState:
    """What was already done, so every cause is handled **once**.

    Attributes:
        auto_stopped_on: Local date (ISO text) of the last automatic stop.
        reminded_no_timer_on: Local date (ISO text) of the last "no timer" reminder.
        reminded_running: Id of the entry the "running too long" reminder was sent for.
        idle_asked_for: Id of the entry an idle question was raised for.
    """

    auto_stopped_on: str | None = None
    reminded_no_timer_on: str | None = None
    reminded_running: str | None = None
    idle_asked_for: str | None = None


def parse_clock(text: str) -> time | None:
    """Parse ``HH:MM``; an empty text means "off" (``None``)."""
    if not text:
        return None
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


def is_workday(settings: WorkSettings, moment: datetime, tz: ZoneInfo) -> bool:
    """Whether ``moment`` falls on one of the configured weekdays (1 = Monday)."""
    return moment.astimezone(tz).isoweekday() in settings.workday_numbers()


def evaluate(
    now: datetime,
    tz: ZoneInfo,
    settings: WorkSettings,
    running: RunningEntry | None,
    idle_seconds: float | None,
    state: DayState,
) -> list[WorkDecision]:
    """Return what should be raised or done at ``now`` (usually nothing).

    Args:
        now: Current time (timezone-aware).
        tz: Display timezone (decides what "17:30" means).
        settings: The ``work`` settings.
        running: The running entry, if any.
        idle_seconds: Seconds since the last input, or ``None`` if unknown.
        state: What has already been handled.
    """
    decisions: list[WorkDecision] = []
    local = now.astimezone(tz)
    today = local.date().isoformat()
    workday = is_workday(settings, now, tz)

    end = parse_clock(settings.workday_end)
    if end is not None and workday and running is not None and state.auto_stopped_on != today:
        end_local = datetime.combine(local.date(), end, tzinfo=tz)
        # Only an entry that began *before* the end is stopped: someone who deliberately starts
        # after the workday has ended must not be stopped at once.
        if local >= end_local and running.started_at < end_local:
            decisions.append(WorkDecision(WorkAction.AUTO_STOP, end_local.astimezone(now.tzinfo)))

    if (
        settings.idle_minutes > 0
        and running is not None
        and idle_seconds is not None
        and idle_seconds >= settings.idle_minutes * 60
        and state.idle_asked_for != running.id
    ):
        decisions.append(WorkDecision(WorkAction.IDLE, now - timedelta(seconds=idle_seconds)))

    start_check = parse_clock(settings.reminder_no_timer_after)
    if (
        start_check is not None
        and workday
        and running is None
        and state.reminded_no_timer_on != today
        and local.time() >= start_check
        and (end is None or local.time() < end)
    ):
        decisions.append(WorkDecision(WorkAction.REMIND_NO_TIMER, now))

    if (
        settings.reminder_running_hours > 0
        and running is not None
        and state.reminded_running != running.id
        and now - running.started_at >= timedelta(hours=settings.reminder_running_hours)
    ):
        decisions.append(WorkDecision(WorkAction.REMIND_RUNNING, now))
    return decisions
