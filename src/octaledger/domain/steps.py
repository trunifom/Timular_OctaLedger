"""Action chains: the ordered steps a face runs when it comes up (control mode).

A face has one or more **steps**. Step 1 is what a face always had (one action of one
connection); further steps run after a delay, optionally only inside a time window. All steps are
queued at the moment the cube is turned; a new turn of the same cube cancels the steps of the
previous chain that were not sent yet (so "music after 10 s" does not start after you already
moved on), and a failed step cancels the following ones unless it is marked "continue".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from octaledger.core.errors import ValidationError
from octaledger.domain.conditions import Condition
from octaledger.domain.models import _check_face, _check_id, _check_json_object, _clean_text

MAX_STEPS: Final = 10
MAX_DELAY_MS: Final = 300_000
#: The delays of one chain may not add up to more than this (five minutes).
MAX_CHAIN_MS: Final = 300_000


@dataclass(frozen=True, slots=True)
class ActionStep:
    """One step of a face's chain.

    Attributes:
        position: Order in the chain, starting at 0.
        delay_ms: Wait after the turn before this step is sent.
        continue_on_error: Whether the chain goes on if *this* step fails.
        enabled: Disabled steps stay in the editor but are skipped.
        condition: Optional time window / weekdays.
    """

    device_id: str
    face: int
    position: int
    integration_id: str
    label: str
    params: Mapping[str, Any] = field(default_factory=dict)
    delay_ms: int = 0
    continue_on_error: bool = False
    enabled: bool = True
    condition: Condition | None = None

    def __post_init__(self) -> None:
        """Validate every part."""
        object.__setattr__(self, "device_id", _check_id(self.device_id, "device_id"))
        object.__setattr__(self, "face", _check_face(self.face))
        object.__setattr__(self, "integration_id", _check_id(self.integration_id, "integration_id"))
        object.__setattr__(
            self,
            "label",
            _clean_text(self.label, "Bezeichnung", max_length=100, required=True),
        )
        object.__setattr__(self, "params", _check_json_object(self.params, "params"))
        if (
            isinstance(self.position, bool)
            or not isinstance(self.position, int)
            or not 0 <= self.position < MAX_STEPS
        ):
            raise ValidationError(f"Invalid step position {self.position!r}")
        if (
            isinstance(self.delay_ms, bool)
            or not isinstance(self.delay_ms, int)
            or not 0 <= self.delay_ms <= MAX_DELAY_MS
        ):
            raise ValidationError(
                f"Invalid delay {self.delay_ms!r}",
                user_message="Die Verzögerung darf höchstens 5 Minuten betragen.",
            )


def check_chain(steps: list[ActionStep]) -> None:
    """Validate a whole chain: size, order and the sum of the delays.

    Raises:
        ValidationError: For an empty or too long chain, wrong positions or too long delays.
    """
    if not steps:
        raise ValidationError(
            "A chain needs at least one step",
            user_message="Eine Seite braucht mindestens einen Schritt.",
        )
    if len(steps) > MAX_STEPS:
        raise ValidationError(
            "Too many steps", user_message=f"Höchstens {MAX_STEPS} Schritte je Seite."
        )
    if [s.position for s in steps] != list(range(len(steps))):
        raise ValidationError("Step positions must be 0, 1, 2 ...")
    if sum(s.delay_ms for s in steps) > MAX_CHAIN_MS:
        raise ValidationError(
            "Chain delays too long",
            user_message="Alle Verzögerungen zusammen dürfen höchstens 5 Minuten betragen.",
        )
