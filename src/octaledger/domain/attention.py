"""The attention centre: questions that wait for a decision of the user.

An :class:`AttentionItem` records *that* something needs a decision (a gap after a lost
connection, an idle period ...) and, later, how the user decided. It never changes time data by
itself. Shared by several features (see ``docs/UMSETZUNGSPLAN.md`` section 3.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from octaledger.domain.models import _check_id, new_id
from octaledger.domain.time_rules import ensure_utc


class AttentionKind(StrEnum):
    """What kind of decision is pending."""

    #: Gap after a lost connection that outlasted the grace period.
    GAP = "gap"
    #: Idle period detected (planned).
    IDLE = "idle"
    #: An automatic stop happened; please check (planned).
    AUTO_STOP = "auto_stop"
    #: A reminder (planned).
    REMINDER = "reminder"
    #: Break hint (planned).
    BREAK_HINT = "break_hint"


class AttentionStatus(StrEnum):
    """Life cycle of an attention item."""

    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class AttentionItem:
    """One open or answered question.

    Attributes:
        kind: The kind of decision.
        created_at: When it was raised (UTC).
        payload: Case-specific data (JSON-compatible, no secrets).
        session_id: The entry the question is about, if any.
        status: Life-cycle state.
        resolved_at: When it was answered (UTC), if it was.
        resolution: Short code of the answer (for example ``keep``).
    """

    kind: AttentionKind
    created_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    status: AttentionStatus = AttentionStatus.OPEN
    resolved_at: datetime | None = None
    resolution: str | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        """Validate ids, enums and timestamps."""
        object.__setattr__(self, "id", _check_id(self.id, "id"))
        if self.session_id is not None:
            object.__setattr__(self, "session_id", _check_id(self.session_id, "session_id"))
        object.__setattr__(self, "kind", AttentionKind(self.kind))
        object.__setattr__(self, "status", AttentionStatus(self.status))
        object.__setattr__(self, "created_at", ensure_utc(self.created_at, name="created_at"))
        if self.resolved_at is not None:
            object.__setattr__(
                self, "resolved_at", ensure_utc(self.resolved_at, name="resolved_at")
            )
