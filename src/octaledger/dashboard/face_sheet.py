"""The "sheet" of a face: everything that is set up on it, in plain German (pure, no Streamlit).

The inspector shows, for one face of a cube, what a turn onto it does - for a time cube the
activity and project, for a smart-home cube the **whole chain of actions** (every step with its
connection, action, values, delay, error behaviour and condition), for a music cube the title, the
target and the volume. The same texts feed the table "all faces at a glance" and the copyable
export, so there is exactly one place that words these things.

Nothing here talks to the network; the functions get plain dictionaries as the API returns them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

FACES: Final = tuple(range(1, 9))
WEEKDAYS: Final = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
HOLDER: Final = 0  # the "face" of the holder (no face up) in the overview


@dataclass(frozen=True, slots=True)
class FaceSheet:
    """What is set up on one face.

    Attributes:
        face: ``1..8``; ``0`` is the holder of a music cube.
        title: Short name (activity, action label or music title); empty if nothing is set up.
        summary: One line for the table "all faces at a glance".
        lines: The detail lines (Markdown) of the sheet.
        empty: ``True`` when nothing is assigned.
    """

    face: int
    title: str
    summary: str
    lines: tuple[str, ...] = field(default_factory=tuple)
    empty: bool = False


def _empty(face: int, hint: str) -> FaceSheet:
    return FaceSheet(face, "", "– noch nichts zugeordnet –", (hint,), empty=True)


def _name_of(items: Sequence[Mapping[str, Any]], wanted: str | None) -> str | None:
    return next((str(i["name"]) for i in items if i["id"] == wanted), None)


# ------------------------------------------------------------------------------- time cubes


def time_sheet(
    face: int,
    device: Mapping[str, Any],
    activities: Sequence[Mapping[str, Any]],
    projects: Sequence[Mapping[str, Any]],
    defaults: Mapping[str, Any] | None = None,
) -> FaceSheet:
    """The sheet of a face of a cube that records time.

    Args:
        face: The face ``1..8``.
        device: The cube as the API returns it (``faces`` maps a face to its activity/project).
        activities / projects: The catalogue (to turn ids into names).
        defaults: Optional ``{"tag_ids", "note_template"}`` of the activity, with ``tag_names``.
    """
    mapping = device.get("faces", {}).get(str(face))
    activity_id = mapping.get("activity_id") if mapping else None
    if activity_id is None:
        return _empty(face, "Diese Seite startet keine Zeit. Weisen Sie ihr eine Tätigkeit zu.")
    activity = _name_of(activities, activity_id) or "(Tätigkeit nicht mehr vorhanden)"
    project = _name_of(projects, mapping.get("project_id")) if mapping else None
    lines = [f"**Tätigkeit:** {activity}", f"**Projekt:** {project or 'keines'}"]
    if defaults:
        tags = defaults.get("tag_names") or []
        lines.append("**Schlagworte:** " + (", ".join(tags) if tags else "keine"))
        note = defaults.get("note_template")
        lines.append("**Notizvorlage:** " + (str(note) if note else "keine"))
    lines.append("Eine Drehung auf diese Seite **startet** diese Tätigkeit.")
    summary = activity + (f" · {project}" if project else "")
    return FaceSheet(face, activity, summary, tuple(lines))


# ------------------------------------------------------------------- smart-home and music


def _spec_of(specs: Sequence[Mapping[str, Any]], kind: str) -> Mapping[str, Any] | None:
    return next((s for s in specs if s["kind"] == kind), None)


def _action_text(
    params: Mapping[str, Any], spec: Mapping[str, Any] | None
) -> tuple[str, list[str]]:
    """``(action name, ["Feld: Wert", ...])`` of one step, in the words of the adapter."""
    action_id = str(params.get("action", ""))
    action = next((a for a in (spec or {}).get("actions", []) if a["id"] == action_id), None)
    name = str(action["label"]) if action else (action_id or "Aktion")
    fields = {f["name"]: f for f in (action or {}).get("fields", [])}
    shown: list[str] = []
    for key, value in params.items():
        if key == "action" or value in (None, ""):
            continue
        label = str(fields[key]["label"]) if key in fields else key
        shown.append(f"{label}: {value}")
    return name, shown


def condition_text(condition: Mapping[str, Any] | None) -> str | None:
    """A condition in words, or ``None`` when the step always runs."""
    if not condition:
        return None
    start, end = str(condition.get("start") or ""), str(condition.get("end") or "")
    days = str(condition.get("weekdays") or "")
    parts: list[str] = []
    if start and end:
        parts.append(f"nur zwischen {start} und {end} Uhr")
    if days and days != "1,2,3,4,5,6,7":
        names = [WEEKDAYS[int(d) - 1] for d in days.split(",") if d.strip().isdigit()]
        parts.append("nur an: " + ", ".join(names))
    return " und ".join(parts) or None


def step_lines(
    steps: Sequence[Mapping[str, Any]],
    connections: Sequence[Mapping[str, Any]],
    specs: Sequence[Mapping[str, Any]],
) -> list[str]:
    """One Markdown line per step: connection, action, values, delay, error behaviour, condition."""
    lines: list[str] = []
    for number, step in enumerate(steps, start=1):
        connection = next((c for c in connections if c["id"] == step["integration_id"]), None)
        spec = _spec_of(specs, str(connection["kind"])) if connection else None
        where = f"„{connection['name']}“" if connection else "(Verbindung nicht mehr vorhanden)"
        kind = f" ({spec['title']})" if spec else ""
        action, values = _action_text(step.get("params", {}), spec)
        text = f"**Schritt {number}:** {where}{kind} – {action}"
        if values:
            text += " – " + "; ".join(values)
        extras: list[str] = []
        if step.get("delay_ms"):
            extras.append(f"wartet vorher {int(step['delay_ms'])} ms")
        if step.get("continue_on_error"):
            extras.append("bei einem Fehler geht es trotzdem weiter")
        when = condition_text(step.get("condition"))
        if when:
            extras.append(when)
        if step.get("enabled") is False:
            extras.append("**ausgeschaltet**")
        lines.append(text + (f" ({'; '.join(extras)})" if extras else ""))
    return lines


def control_sheet(
    face: int,
    steps: Sequence[Mapping[str, Any]],
    connections: Sequence[Mapping[str, Any]],
    specs: Sequence[Mapping[str, Any]],
) -> FaceSheet:
    """The sheet of a face of a smart-home cube (the whole chain)."""
    if not steps:
        return _empty(face, "Diese Seite löst nichts aus. Legen Sie eine Aktion an.")
    title = str(steps[0].get("label") or "Aktion")
    body = step_lines(steps, connections, specs)
    word = "Schritt" if len(steps) == 1 else "Schritte"
    lines = [f"**Name:** {title}", *body, "Eine Drehung auf diese Seite **löst diese Kette aus**."]
    return FaceSheet(face, title, f"{title} ({len(steps)} {word})", tuple(lines))


def music_sheet(
    face: int,
    steps: Sequence[Mapping[str, Any]],
    connections: Sequence[Mapping[str, Any]],
    specs: Sequence[Mapping[str, Any]],
) -> FaceSheet:
    """The sheet of a face of a music cube (a face without a title is a silence face)."""
    if not steps:
        return FaceSheet(
            face,
            "",
            "Stille (beendet die Musik)",
            (
                "Diese Seite hat **keinen Titel** und ist damit eine **Stille-Seite**: Eine "
                "Drehung darauf beendet die Musik.",
            ),
            empty=True,
        )
    title = str(steps[0].get("label") or "Titel")
    connection = next((c for c in connections if c["id"] == steps[0]["integration_id"]), None)
    target = f"„{connection['name']}“" if connection else "(Ziel nicht mehr vorhanden)"
    volume = next((s["params"]["volume"] for s in steps if "volume" in s.get("params", {})), None)
    lines = [f"**Titel:** {title}", f"**Spielt auf:** {target}"]
    if volume is not None:
        lines.append(f"**Lautstärke:** {volume} %")
    lines += step_lines(steps, connections, specs)
    lines.append("Eine Drehung auf diese Seite **spielt diesen Titel** (ein laufender endet).")
    return FaceSheet(face, title, f"♪ {title} auf {target}", tuple(lines))


def holder_sheet(settings: Mapping[str, Any]) -> FaceSheet:
    """The "holder" row of a music cube (what happens when no face is up)."""
    base = settings.get("base_action")
    action = {"pause": "pausiert", "continue": "nicht angehalten (sie läuft weiter)"}.get(
        str(base), "beendet"
    )
    delay = int(settings.get("stop_delay_ms") or 0)
    wait = (
        "" if base == "continue" else (f" nach {delay / 1000:g} Sekunden" if delay else " sofort")
    )
    lines = (
        f"In der **Halterung** (keine Seite oben) wird die Musik{wait} **{action}**.",
        f"**Standard-Lautstärke** neuer Titel: {int(settings.get('default_volume', 50))} %.",
    )
    return FaceSheet(HOLDER, "Halterung", f"Musik wird{wait} {action}", lines)


# ------------------------------------------------------------------------------ the export


def overview_rows(sheets: Sequence[FaceSheet]) -> list[dict[str, str]]:
    """The table "all faces at a glance" (one row per face, plus the holder when present)."""
    return [
        {"Seite": "Halterung" if s.face == HOLDER else str(s.face), "Einstellung": s.summary}
        for s in sheets
    ]


def export_text(alias: str, area: str, sheets: Sequence[FaceSheet]) -> str:
    """The settings of a cube as plain text (for copying or saving)."""
    out = [f"Einstellungen des Würfels „{alias}“ – Bereich {area}", ""]
    for sheet in sheets:
        label = "Halterung" if sheet.face == HOLDER else f"Seite {sheet.face}"
        out.append(f"{label}: {sheet.summary}")
        for line in sheet.lines:
            out.append("  " + line.replace("**", ""))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
