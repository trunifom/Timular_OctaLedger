"""Page "Würfel-Inspektor": click a face of the cube and see exactly what is set up on it.

Left the picture of the cube (clickable, plus an equivalent row of buttons 1 to 8), right the
**sheet** of the chosen face: for a time cube the activity, project, tags and note template; for a
smart-home cube the whole chain of actions; for a music cube the title, target and volume. Below,
the table "all faces at a glance" with a plain-text export. **Neu programmieren** opens the editor
of that face on *Seiten zuordnen*.

Nothing here changes data except the explicit buttons "Seite leeren" (after the sheet is shown) and
"Neu programmieren" (which only navigates).
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from octaledger.core.settings import Theme
from octaledger.dashboard.cube import INNER_RADIUS, OUTER_RADIUS, SIZE, FaceLabel, cube_svg
from octaledger.dashboard.cube_picker import cube_picker
from octaledger.dashboard.face_sheet import (
    FACES,
    FaceSheet,
    control_sheet,
    export_text,
    holder_sheet,
    music_sheet,
    overview_rows,
    time_sheet,
)
from octaledger.dashboard.identity import banner, mode_text, selected_cube
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import call, page_help
from octaledger.dashboard.views.faces import PENDING_KEY
from octaledger.dashboard.views.live import ACTION_COLOR
from octaledger.dashboard_client.client import ApiClient


def face_key(device_id: str) -> str:
    """Session key of the face shown in the inspector (one per cube)."""
    return f"inspector_face_{device_id}"


def _choose(device_id: str, face: int) -> None:
    """Button callback: remember the chosen face."""
    st.session_state[face_key(device_id)] = face


def _sheets(
    client: ApiClient, device: dict[str, Any]
) -> tuple[dict[int, FaceSheet], FaceSheet | None] | None:
    """All eight sheets of the cube (and the holder sheet of a music cube), or ``None`` on error."""
    mode = device["mode"]
    if mode == "time":
        ok_a, activities = call(client.list_items, "activities", True)
        ok_p, projects = call(client.list_items, "projects", True)
        if not (ok_a and ok_p) or activities is None or projects is None:
            return None
        sheets: dict[int, FaceSheet] = {}
        for face in FACES:
            entry = device["faces"].get(str(face))
            defaults = None
            if entry and entry["activity_id"]:
                ok, data = call(client.activity_defaults, entry["activity_id"])
                if ok and data:
                    defaults = {
                        "tag_names": [t["name"] for t in data["tags"]],
                        "note_template": data.get("note_template"),
                    }
            sheets[face] = time_sheet(face, device, activities, projects, defaults)
        return sheets, None
    ok_c, connections = call(client.integrations)
    ok_s, specs = call(client.adapters)
    ok_x, chains = call(client.action_chains, device["id"])
    if not (ok_c and ok_s and ok_x) or connections is None or specs is None:
        return None
    build = music_sheet if mode == "music" else control_sheet
    found = {
        face: build(face, (chains or {}).get(str(face), []), connections, specs) for face in FACES
    }
    holder = None
    if mode == "music":
        ok, settings = call(client.music_settings, device["id"])
        holder = holder_sheet(settings) if ok and settings else None
    return found, holder


def _labels(sheets: dict[int, FaceSheet], mode: str) -> dict[int, FaceLabel]:
    """What the picture writes on each face (name and, for time cubes, the activity colour)."""
    return {
        face: FaceLabel(sheet.title or None, ACTION_COLOR if sheet.title else None)
        for face, sheet in sheets.items()
    }


def _time_labels(device: dict[str, Any], client: ApiClient) -> dict[int, FaceLabel]:
    """Activity names and colours of a time cube."""
    ok, activities = call(client.list_items, "activities", True)
    by_id = {a["id"]: a for a in (activities or [])} if ok else {}
    labels: dict[int, FaceLabel] = {}
    for key, entry in device["faces"].items():
        activity = by_id.get(entry["activity_id"]) if entry["activity_id"] else None
        labels[int(key)] = (
            FaceLabel(activity["name"], activity["color"]) if activity else FaceLabel()
        )
    return labels


def render(client: ApiClient, tz: str) -> None:
    """Render the inspector page."""
    st.header("Würfel-Inspektor")
    page_help(
        "So funktioniert der Würfel-Inspektor",
        "Hier sehen Sie **im Detail, was auf jeder Seite des Würfels eingestellt ist**.\n\n"
        "- **Seite wählen:** Klicken Sie im Würfelbild auf eine Seite oder drücken Sie unter dem "
        "Bild die Zahl (beides tut dasselbe).\n"
        "- **Seitenblatt:** Rechts steht in Klartext, was beim Drehen auf diese Seite passiert: "
        "bei *Zeit* die Tätigkeit, bei *Smarthome* die ganze Aktionskette, bei *Musik* der Titel.\n"
        "- **Neu programmieren** öffnet den Editor dieser Seite. **Seite leeren** entfernt die "
        "Einstellung.\n"
        "- Unten sehen Sie **alle Seiten auf einen Blick** und können sie als Text kopieren.\n"
        "- Der Inspektor **ändert nichts**, solange Sie keinen Knopf drücken.",
    )
    ok, devices = call(client.devices)
    if not ok or devices is None:
        return
    if not devices:
        st.info(
            "Es ist noch kein Würfel eingerichtet. Die Startseite führt Sie durch die Einrichtung."
        )
        st.button(
            "Zur Einrichtung",
            key="inspector_to_start",
            on_click=go,
            args=("start",),
            type="primary",
            help="Öffnet die Startseite mit der geführten Einrichtung.",
        )
        return
    device = selected_cube(devices) or devices[0]
    banner(device, key="inspector_banner", action="untersuchen")
    built = _sheets(client, device)
    if built is None:
        return
    sheets, holder = built
    key = face_key(device["id"])
    if st.session_state.get(key) not in FACES:
        first = next((f for f, s in sheets.items() if not s.empty), 1)
        st.session_state[key] = first
    display = st.session_state.get("_display", {})
    theme = Theme(display.get("theme", Theme.LIGHT.value))
    labels = (
        _time_labels(device, client)
        if device["mode"] == "time"
        else _labels(sheets, device["mode"])
    )

    picture, sheet_column = st.columns([5, 6])
    with picture:
        svg = cube_svg(
            theme,
            labels,
            selected=st.session_state[key],
            caption=f"Würfel von oben, Seite {st.session_state[key]} gewählt",
        )
        clicked = cube_picker(
            svg,
            key=f"inspector_picker_{device['id']}",
            size=SIZE,
            inner=INNER_RADIUS,
            outer=OUTER_RADIUS,
        )
        if clicked is not None and clicked != st.session_state[key]:
            st.session_state[key] = clicked
            st.rerun()
        for row in (FACES[:4], FACES[4:]):
            for column, face in zip(st.columns(4), row, strict=True):
                column.button(
                    str(face),
                    key=f"inspector_face_{device['id']}_{face}",
                    type="primary" if face == st.session_state[key] else "secondary",
                    on_click=_choose,
                    args=(device["id"], face),
                    width="stretch",
                    help=f"Zeigt, was auf Seite {face} eingestellt ist: {sheets[face].summary}.",
                )
    with sheet_column:
        _sheet(client, device, st.session_state[key], sheets[st.session_state[key]])

    st.subheader("Alle Seiten auf einen Blick")
    rows = overview_rows([*sheets.values(), *([holder] if holder else [])])
    st.dataframe(rows, hide_index=True, width="stretch")
    text = export_text(
        device["alias"], mode_text(device), [*sheets.values(), *([holder] if holder else [])]
    )
    with st.expander("Als Text kopieren oder speichern", key="inspector_export"):
        st.code(text, language=None)
        st.download_button(
            "Als Textdatei speichern",
            text,
            file_name="wuerfel-einstellungen.txt",
            mime="text/plain",
            key="inspector_download",
            icon=":material/download:",
            help="Speichert die Einstellungen dieses Würfels als Textdatei auf Ihrem Rechner.",
        )


def _sheet(client: ApiClient, device: dict[str, Any], face: int, sheet: FaceSheet) -> None:
    """The sheet of one face with its buttons."""
    with st.container(border=True, key="inspector_sheet"):
        st.markdown(f"### Seite {face}")
        if sheet.empty:
            st.info(sheet.lines[0] if sheet.lines else "Nichts zugeordnet.")
        else:
            for line in sheet.lines:
                st.markdown(line)
        edit, clear = st.columns(2)
        edit.button(
            "Neu programmieren",
            key="inspector_edit",
            on_click=_edit,
            args=(device["id"], face),
            type="primary",
            icon=":material/edit:",
            width="stretch",
            help="Öffnet „Seiten zuordnen“ mit dieser Seite, um sie neu einzustellen.",
        )
        if clear.button(
            "Seite leeren",
            key="inspector_clear",
            disabled=sheet.empty,
            icon=":material/delete:",
            width="stretch",
            help="Entfernt die Einstellung dieser Seite. Die Verbindungen und Tätigkeiten selbst "
            "bleiben.",
        ):
            action = client.clear_face if device["mode"] == "time" else client.clear_action
            if call(action, device["id"], face)[0]:
                st.rerun()


def _edit(device_id: str, face: int) -> None:
    """Button callback: open the editor of this face on *Seiten zuordnen*."""
    st.session_state[PENDING_KEY] = (device_id, face)
    go("faces")
