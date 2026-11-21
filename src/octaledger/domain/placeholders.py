"""Placeholders in message texts: ``{device}``, ``{face}``, ``{label}``, ``{time}``.

A Node-RED flow (or any receiver) can tell *which* face was turned when the message carries it:
``{"device":"{device}","face":{face},"label":"{label}","time":"{time}"}``. Replacement is plain
**text substitution with a whitelist**: an unknown name is an error when the action is saved,
there are no expressions and nothing is evaluated.

Injection safety: when the text is a JSON template (see :func:`is_json_template`), the inserted
values are JSON-escaped (quotes, backslashes and control characters), so a label such as
``Lampe"} {"x":1`` cannot change the structure of the message. Headers never take placeholders.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Final

from octaledger.core.errors import ValidationError

ALLOWED: Final = ("device", "face", "label", "time")
_PATTERN: Final = re.compile(r"\{([a-z_]+)\}")


def names_in(text: str) -> list[str]:
    """The placeholder names used in ``text`` (in order, with repeats)."""
    return _PATTERN.findall(text)


def check(text: str) -> None:
    """Reject unknown placeholder names.

    Raises:
        ValidationError: Naming the unknown placeholder and the allowed ones.
    """
    unknown = sorted({name for name in names_in(text) if name not in ALLOWED})
    if unknown:
        allowed = ", ".join("{" + name + "}" for name in ALLOWED)
        raise ValidationError(
            f"Unknown placeholder(s): {unknown}",
            user_message=f"Unbekannter Platzhalter: {{{unknown[0]}}}. Erlaubt sind: {allowed}.",
        )


def is_json_template(text: str) -> bool:
    """Whether ``text`` is a JSON object or array once its placeholders hold sample values.

    Only then are inserted values JSON-escaped; a bare ``{label}`` is just text.
    """
    sample = _PATTERN.sub(lambda m: "1" if m.group(1) == "face" else "x", text)
    try:
        return isinstance(json.loads(sample), dict | list)
    except ValueError:
        return False


def render(text: str, values: Mapping[str, str | int]) -> str:
    """Replace the allowed placeholders in ``text`` (names without a value stay as they are)."""
    looks_like_json = is_json_template(text)

    def replace(match: re.Match[str]) -> str:
        """Replacement of one match: the value, escaped when the text is a JSON template."""
        name = match.group(1)
        if name not in ALLOWED or name not in values:
            return match.group(0)
        value = values[name]
        if isinstance(value, int):
            return str(value)
        return json.dumps(value, ensure_ascii=False)[1:-1] if looks_like_json else value

    return _PATTERN.sub(replace, text)
