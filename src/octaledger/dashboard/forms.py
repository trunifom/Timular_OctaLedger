"""Render the forms of the integrations from their self-description (no per-adapter GUI code).

Every adapter describes its settings and actions with fields (``GET /adapters``); this module turns
such a list of fields into Streamlit widgets and returns what the user entered. That is why a new
adapter needs no change in the dashboard.

Rules followed here (``CLAUDE.md`` section 6): every input has a ``help=`` text, widget keys are
unique (``key_prefix`` + field name), secrets use a password field and an already stored secret is
never shown - an empty field means "keep the stored one".
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

#: Text shown for a field when the adapter gave no help of its own.
FALLBACK_HELP = "Angabe für diese Verbindung."


def _titled(titles: Mapping[str, str]) -> Callable[[str], str]:
    """A ``format_func`` that shows ``titles[option]`` for every option."""
    return lambda option: titles[option]


def field_label(field: Mapping[str, Any]) -> str:
    """The label with a marker for required fields."""
    return f"{field['label']} *" if field.get("required") else str(field["label"])


def picker_options(
    field: Mapping[str, Any], discovered: Mapping[str, Sequence[Mapping[str, str]]] | None
) -> list[dict[str, str]]:
    """Items found on the target (lights, scenes ...) that can fill ``field``, if any.

    The field names the discovery categories it can be filled from (``choices_from``); the lists
    are merged and a leading category name is added to the label when several are mixed.
    """
    categories = list(field.get("choices_from") or [])
    if not categories or not discovered:
        return []
    mixed = len([c for c in categories if discovered.get(c)]) > 1
    options: list[dict[str, str]] = []
    for category in categories:
        for item in discovered.get(category, ()):
            label = f"{item['name']} ({category})" if mixed else item["name"]
            options.append({"id": item["id"], "label": label})
    return options


def render_fields(
    fields: Sequence[Mapping[str, Any]],
    *,
    key_prefix: str,
    values: Mapping[str, Any] | None = None,
    secrets_set: Sequence[str] = (),
    discovered: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
) -> dict[str, Any]:
    """Draw one widget per field and return the entered values.

    Args:
        fields: Field descriptions as returned by the API.
        key_prefix: Prefix of every widget key (must be unique on the page).
        values: Current values used as the initial content (an edit form).
        secrets_set: Names of secrets that are already stored; their field says so and an
            empty entry keeps the stored value.
        discovered: Items found on the target by category; a field with ``choices_from`` becomes a
            pick list of them instead of a free text field.

    Returns:
        ``{name: value}`` for every field that has a value. Empty texts and empty numbers are
        omitted, switches are always included.
    """
    current = values or {}
    entered: dict[str, Any] = {}
    for field in fields:
        name = str(field["name"])
        key = f"{key_prefix}_{name}"
        label = field_label(field)
        help_text = str(field.get("help") or FALLBACK_HELP)
        initial = current.get(name, field.get("default"))
        kind = field["kind"]
        value: Any
        if kind == "bool":
            value = st.checkbox(label, value=bool(initial), key=key, help=help_text)
        elif kind == "int":
            value = st.number_input(
                label,
                min_value=field.get("minimum"),
                max_value=field.get("maximum"),
                value=int(initial) if initial not in (None, "") else None,
                step=1,
                key=key,
                help=help_text,
            )
            value = None if value is None else int(value)
        elif kind == "choice":
            options = [choice["value"] for choice in field["choices"]]
            titles = {choice["value"]: choice["label"] for choice in field["choices"]}
            index = options.index(str(initial)) if str(initial) in options else 0
            value = st.selectbox(
                label,
                options,
                index=index,
                format_func=_titled(titles),
                key=key,
                help=help_text,
            )
        elif kind == "password":
            stored = name in secrets_set
            value = st.text_input(
                label,
                type="password",
                key=key,
                help=help_text
                + (" Gespeichert: leer lassen, um den Wert zu behalten." if stored else ""),
                placeholder="gespeichert" if stored else "",
            )
        else:
            picks = picker_options(field, discovered)
            if picks:
                ids = [pick["id"] for pick in picks]
                value = st.selectbox(
                    label,
                    ids,
                    index=ids.index(str(initial)) if str(initial) in ids else None,
                    format_func=_titled({pick["id"]: pick["label"] for pick in picks}),
                    placeholder="Aus der Liste wählen …",
                    key=key,
                    help=help_text,
                )
            else:
                value = st.text_input(
                    label,
                    value="" if initial is None else str(initial),
                    placeholder=str(field.get("placeholder") or ""),
                    key=key,
                    help=help_text,
                )
        if kind == "bool" or (value is not None and str(value).strip() != ""):
            entered[name] = value.strip() if isinstance(value, str) else value
    return entered
