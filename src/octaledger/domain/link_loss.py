"""Pure decision logic for a lost tracker connection with a grace period.

When the connection to a tracker drops, OctaLedger does not guess: the running entry keeps
running (flagged uncertain) for a configurable *grace period*. If the tracker comes back in
time the entry simply continues. If not, the entry is ended **at the moment of the loss** (the
last moment known to be true) and the user is asked what happened in between.

This module contains only the time rule, without I/O, so it can be tested exhaustively with an
injected "now". The orchestration lives in :mod:`octaledger.application.tracking_service`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum


class LinkAction(StrEnum):
    """What the watchdog has to do for one lost connection."""

    #: Keep waiting (grace period still running, or already handled).
    NONE = "none"
    #: End the running entry at the time of the loss and ask the user about the gap.
    STOP_AT_LOSS = "stop_at_loss"


def decide(
    lost_at: datetime, now: datetime, grace: timedelta, *, already_stopped: bool
) -> LinkAction:
    """Decide what to do about a connection that was lost at ``lost_at``.

    Args:
        lost_at: UTC time of the loss (timezone-aware).
        now: Current UTC time (timezone-aware).
        grace: Length of the grace period; ``timedelta(0)`` means "stop immediately".
        already_stopped: Whether the entry was already ended for this loss.

    Returns:
        :attr:`LinkAction.STOP_AT_LOSS` once the grace period is **reached** (the boundary
        counts as expired) and nothing was done yet, otherwise :attr:`LinkAction.NONE`.
    """
    if already_stopped:
        return LinkAction.NONE
    if now - lost_at >= grace:
        return LinkAction.STOP_AT_LOSS
    return LinkAction.NONE
