"""The contract every integration adapter fulfils, and the shared field validation.

Responsibility
--------------
An *adapter* knows how to talk to one kind of target (an MQTT broker, Home Assistant, a Hue
bridge, a web address). Everything else - storing connections, assigning actions to faces,
the queue, retries, the user interface - is generic. To make the user interface generic too, an
adapter **describes itself** with an :class:`AdapterSpec`: which settings it needs, which
actions it offers and which fields each action has. The dashboard renders forms from that
description, so a new adapter needs **no** change to the GUI.

Rules for adapters
------------------
* ``execute`` is **blocking** and runs in a worker thread, never in the BLE loop or a Streamlit
  script. It must honour the ``timeout``.
* Raise :class:`~octaledger.core.errors.IntegrationConnectionError` only if the request
  **certainly did not take effect** (cannot connect, refused before sending). That error is
  retried. Everything else that fails raises
  :class:`~octaledger.core.errors.IntegrationError` and is **not** retried, because repeating
  an action whose outcome is unknown could switch a light twice.
* Never run shell commands, never follow redirects to other schemes, never put secrets into an
  exception message or a log line.
* Secrets (fields of kind ``password``) arrive separately in ``secrets`` and are not part of
  ``config``.

Limits: adapters are verified against local fakes; whether a real device or hub behaves the
same is documented per adapter (``docs/QUELLEN_UND_GRENZEN.md``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from octaledger.core.errors import IntegrationError, ValidationError

FieldKind = Literal["text", "password", "int", "bool", "choice"]

#: Longest accepted text value of a field.
MAX_TEXT_LENGTH: Final = 500


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One input of a form (a setting of the connection or a parameter of an action).

    Attributes:
        name: Key in the stored settings / parameters.
        label: German label shown to the user.
        kind: ``text``, ``password`` (a secret, stored separately), ``int``, ``bool`` or
            ``choice`` (one of ``choices``).
        required: Whether an empty value is rejected.
        help: German explanation shown as a tooltip.
        default: Pre-filled value.
        placeholder: Example text for empty text fields.
        choices: ``(value, label)`` pairs for ``choice`` fields.
        minimum: Lower bound of an ``int`` field.
        maximum: Upper bound of an ``int`` field.
        advanced: Shown only in the collapsed "Erweiterte Einstellungen" of the form; the
            field must have a sensible default so the basic form is enough for most users.
        choices_from: Names of the discovery categories (see :meth:`Adapter.discover`) a text field
            can be filled from; the dashboard then offers a pick list instead of free text.
    """

    name: str
    label: str
    kind: FieldKind = "text"
    required: bool = False
    help: str = ""
    default: Any = None
    placeholder: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    choices_from: tuple[str, ...] = ()
    advanced: bool = False

    @property
    def secret(self) -> bool:
        """Whether the value is a secret (kept out of settings, backups, API answers, logs)."""
        return self.kind == "password"


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """One thing an adapter can do (for example "call a service" or "publish").

    ``idempotent`` tells whether doing it twice has the same effect as once (turning a light
    *on* is, *toggling* it is not). The interface warns about non-idempotent actions.
    """

    id: str
    label: str
    description: str
    fields: tuple[FieldSpec, ...] = ()
    idempotent: bool = True


@dataclass(frozen=True, slots=True)
class AdapterSpec:
    """The self-description of an adapter (rendered into forms by the dashboard)."""

    kind: str
    title: str
    description: str
    config_fields: tuple[FieldSpec, ...]
    actions: tuple[ActionSpec, ...]
    #: Whether the adapter needs a one-time pairing step (for example pressing a bridge button).
    can_pair: bool = False
    pair_help: str = ""
    #: Whether :meth:`Adapter.discover` can list lights, scenes ... to choose from.
    can_discover: bool = False
    #: Whether :meth:`Adapter.find_targets` can look for the target on the network
    #: (for example a Hue Bridge) so the user does not have to type its address.
    can_find: bool = False
    #: Explains what the search does and what it sends where (shown beside the buttons).
    find_help: str = ""
    #: German step-by-step instructions (Markdown): where to get the address and the
    #: credentials, what to click. Shown next to the form so no outside manual is needed.
    setup_guide: str = ""

    def action(self, action_id: str) -> ActionSpec:
        """Return the action with ``action_id``.

        Raises:
            ValidationError: If the adapter has no such action.
        """
        for candidate in self.actions:
            if candidate.id == action_id:
                return candidate
        raise ValidationError(
            f"Unknown action {action_id!r} for {self.kind}",
            user_message="Diese Aktion kennt die Verbindung nicht.",
            details={"action": action_id},
        )


@dataclass(frozen=True, slots=True)
class PairResult:
    """What a successful pairing yields: secrets to store and settings to add."""

    secrets: Mapping[str, str] = field(default_factory=dict)
    config: Mapping[str, Any] = field(default_factory=dict)
    message: str = "Gekoppelt."


# ------------------------------------------------------------------------ validation


def validate_fields(
    fields: tuple[FieldSpec, ...],
    values: Mapping[str, Any],
    *,
    include_secrets: bool = False,
) -> dict[str, Any]:
    """Validate ``values`` against ``fields`` and return the cleaned, typed values.

    Unknown keys are rejected (a typo must not be silently ignored). Secret fields are skipped
    unless ``include_secrets`` is set, because they never belong into stored settings.

    Raises:
        ValidationError: With a German message naming the field.
    """
    known = {spec.name for spec in fields}
    unknown = sorted(set(values) - known)
    if unknown:
        raise ValidationError(
            f"Unknown fields: {unknown}",
            user_message=f"Unbekannte Angabe: {', '.join(unknown)}.",
            details={"fields": unknown},
        )
    cleaned: dict[str, Any] = {}
    for spec in fields:
        if spec.secret and not include_secrets:
            continue
        raw = values.get(spec.name, spec.default)
        value = _clean_value(spec, raw)
        if value is not None:
            cleaned[spec.name] = value
    return cleaned


def _clean_value(spec: FieldSpec, raw: Any) -> Any:
    empty = raw is None or (isinstance(raw, str) and not raw.strip())
    if empty:
        if spec.required and spec.kind != "bool":
            raise _invalid(spec, "darf nicht leer sein")
        return False if spec.kind == "bool" else None
    if spec.kind == "bool":
        if not isinstance(raw, bool):
            raise _invalid(spec, "muss „an“ oder „aus“ sein")
        return raw
    if spec.kind == "int":
        if isinstance(raw, bool) or not isinstance(raw, int | str):
            raise _invalid(spec, "muss eine ganze Zahl sein")
        try:
            number = int(raw)
        except ValueError:
            raise _invalid(spec, "muss eine ganze Zahl sein") from None
        if spec.minimum is not None and number < spec.minimum:
            raise _invalid(spec, f"muss mindestens {spec.minimum} sein")
        if spec.maximum is not None and number > spec.maximum:
            raise _invalid(spec, f"darf höchstens {spec.maximum} sein")
        return number
    if not isinstance(raw, str):
        raise _invalid(spec, "muss Text sein")
    text = raw.strip()
    if len(text) > MAX_TEXT_LENGTH:
        raise _invalid(spec, f"ist zu lang (höchstens {MAX_TEXT_LENGTH} Zeichen)")
    if "\r" in text or "\n" in text:
        raise _invalid(spec, "darf keine Zeilenumbrüche enthalten")
    if spec.kind == "choice" and text not in {value for value, _ in spec.choices}:
        raise _invalid(spec, "enthält einen unbekannten Wert")
    return text


def _invalid(spec: FieldSpec, problem: str) -> ValidationError:
    return ValidationError(
        f"Invalid value for {spec.name}: {problem}",
        user_message=f"„{spec.label}“ {problem}.",
        details={"field": spec.name},
    )


# --------------------------------------------------------------------------- adapter


class Adapter(ABC):
    """Base class of all adapters (see the module docstring for the rules)."""

    #: The self-description; set by every subclass.
    spec: AdapterSpec

    def validate_config(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Return the cleaned **non-secret** settings (secrets are handled separately)."""
        return validate_fields(self.spec.config_fields, values)

    def validate_action(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Validate an action's parameters and return them cleaned (``action`` key included).

        Raises:
            ValidationError: For an unknown action or invalid fields.
        """
        action_id = params.get("action")
        if not isinstance(action_id, str):
            raise ValidationError("Missing action", user_message="Es wurde keine Aktion gewählt.")
        action = self.spec.action(action_id)
        rest = {key: value for key, value in params.items() if key != "action"}
        return {"action": action_id, **validate_fields(action.fields, rest)}

    @abstractmethod
    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """Test the connection **without side effects**; return a short German message.

        Raises:
            IntegrationError: If the target cannot be reached or rejects the credentials.
        """

    @abstractmethod
    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Carry out an action; return a short German message about the result.

        Raises:
            IntegrationConnectionError: The request certainly had no effect (will be retried).
            IntegrationError: Anything else that failed (will not be retried).
        """

    def pair(self, config: Mapping[str, Any], *, timeout: float) -> PairResult:
        """Run the one-time pairing step (only if ``spec.can_pair``)."""
        raise IntegrationError(
            f"{self.spec.kind} needs no pairing",
            user_message="Diese Verbindung braucht keine Kopplung.",
        )

    def find_targets(self, *, online: bool = False, timeout: float) -> list[dict[str, str]]:
        """Look for the target on the network (only if ``spec.can_find``).

        Args:
            online: Also ask an internet service. Never done unless the user chose it.
            timeout: Seconds the search may take.

        Returns:
            ``[{"id", "address", "name"}, ...]`` (possibly empty).
        """
        return []

    def discover(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> dict[str, list[dict[str, str]]]:
        """List things to choose from, e.g. ``{"lights": [{"id": "1", "name": "Desk"}]}``."""
        return {}
