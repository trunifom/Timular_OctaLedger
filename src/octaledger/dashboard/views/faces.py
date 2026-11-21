"""Setup assistant "Seiten zuordnen": see which face is up and give it an activity right away.

The classic calibration is a table of eight dropdowns. This page replaces the guesswork with a
guided flow:

1. The picture of the cube (refreshed every second) shows which face is **up right now**.
2. One click on **"Diese Seite einrichten"** selects that face. The faces can also be picked by
   hand, so the page is usable without Bluetooth (and for faces the user wants to change later).
3. For the selected face the user picks an existing activity **or types a new name**; the new
   activity is created on the spot. Optionally a project.
4. After saving, the assistant jumps to the next free face and asks the user to turn the cube.

Layout rule (Streamlit): the picture lives in an auto-refreshing fragment, the editor does **not**.
A refreshing fragment would otherwise throw away text the user is still typing.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.core.settings import Theme
from octaledger.dashboard.cube import cube_svg
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import call, page_help
from octaledger.dashboard.views.faces_actions import render_action_editor
from octaledger.dashboard.views.live import READY, face_labels, pending_face
from octaledger.dashboard_client.client import ApiClient

FACES = tuple(range(1, 9))
FLASH_KEY = "faces_flash"
PENDING_KEY = "faces_pending_target"
MODE_ERROR_KEY = "faces_mode_error"
NEW_ACTIVITY: dict[str, Any] = {"id": None, "name": "➕ Neue Tätigkeit anlegen …"}


def is_new(choice: dict[str, Any] | None) -> bool:
    """Whether the picked option is "create a new activity" (compared by value, not identity)."""
    return choice is not None and choice["id"] is None


def target_key(device_id: str) -> str:
    """Session key of the face currently being edited (also the key of the face picker)."""
    return f"faces_target_{device_id}"


def assigned_faces(device: dict[str, Any]) -> set[int]:
    """Faces of ``device`` that are set up: with an activity (time) or an action (control)."""
    if device.get("mode") == "control":
        return {int(face) for face in device.get("actions", {})}
    return {int(face) for face, entry in device["faces"].items() if entry["activity_id"]}


def next_free_face(device: dict[str, Any], after: int = 0) -> int | None:
    """The next face without an activity after ``after`` (wrapping around), or ``None``."""
    taken = assigned_faces(device)
    for step in range(1, len(FACES) + 1):
        candidate = (after - 1 + step) % len(FACES) + 1
        if candidate not in taken:
            return candidate
    return None


def render(client: ApiClient, tz: str) -> None:
    """Render the setup assistant."""
    st.header("Seiten zuordnen")
    page_help(
        "So funktioniert die Zuordnung",
        "Jede der acht Würfelseiten bekommt eine Tätigkeit. Dann genügt später ein Dreh, und die "
        "Zeit der passenden Tätigkeit läuft.\n\n"
        "1. **Würfel verbinden** (Bereich *Würfel verwalten*, oder unten mit einem Klick).\n"
        "2. **Würfel auf eine Seite legen.** Im Bild sehen Sie sofort, welche Seite oben liegt.\n"
        "3. **„Diese Seite einrichten“** wählt sie aus. Sie können eine Seite auch von Hand "
        "wählen.\n"
        "4. **Tätigkeit wählen oder neu benennen** (z. B. „Kundengespräch“) und speichern. Der "
        "Assistent springt zur nächsten freien Seite.\n\n"
        "**Steuerung statt Zeit:** Stellen Sie den Würfel oben auf *Steuerung*, dann bekommt jede "
        "Seite statt einer Tätigkeit eine **Aktion** (zum Beispiel Licht schalten über "
        "Home Assistant oder Hue). Dafür brauchen Sie eine Verbindung "
        "(Seite *Smarthome & Verbindungen*). "
        "Ein Würfel kennt "
        "immer nur einen der beiden Modi.\n\n"
        "Die Nummern im Bild sind die **technischen Seitennummern** des Würfels. Sie müssen nicht "
        "mit einer Aufschrift auf dem Gehäuse übereinstimmen; durch diese Zuordnung entsteht erst "
        "die Verbindung zu Ihren Tätigkeiten.",
    )
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)
    ok, devices = call(client.devices)
    ok_a, activities = call(client.list_items, "activities")
    ok_p, projects = call(client.list_items, "projects")
    if not (ok and ok_a and ok_p) or devices is None or activities is None or projects is None:
        return
    if not devices:
        st.info(
            "Zuerst brauchen Sie einen eingerichteten Würfel. Die geführte Einrichtung auf der "
            "Startseite erledigt das in wenigen Minuten."
        )
        st.button(
            "Zur Einrichtung",
            key="faces_to_start",
            on_click=go,
            args=("start",),
            type="primary",
            help="Öffnet die Startseite mit der geführten Einrichtung.",
        )
        return
    device = next((d for d in devices if d["is_active"]), devices[0])
    if len(devices) > 1:
        device = st.selectbox(
            "Tracker",
            devices,
            key="faces_device",
            index=devices.index(device),
            format_func=lambda d: d["alias"] + (" ⭐" if d["is_active"] else ""),
            help="Für welchen Tracker Sie die Seiten einrichten.",
        )
    key = target_key(device["id"])
    # A widget key must not change after its widget exists in this run, so callers leave the
    # wished face in PENDING_KEY and it is applied here, before the face picker is created.
    pending = st.session_state.pop(PENDING_KEY, None)
    if pending and pending[0] == device["id"]:
        st.session_state[key] = pending[1]
    if st.session_state.get(key) not in FACES:
        st.session_state[key] = next_free_face(device) or 1

    _mode_switch(client, device)
    done = len(assigned_faces(device))
    st.progress(done / len(FACES), text=f"{done} von {len(FACES)} Seiten eingerichtet")
    _connection_hint(client, device)

    picture, editor = st.columns([5, 6], gap="large")
    display = st.session_state.get("_display", {})
    with picture:
        _live_picture(client, device["id"], Theme(display.get("theme", Theme.LIGHT.value)))
    with editor:
        _editor(client, device, activities, projects)
    if done == len(FACES):
        st.success("**Alle acht Seiten sind eingerichtet.** Jetzt können Sie den Würfel benutzen.")
        left, right = st.columns(2)
        left.button(
            "Würfel live ansehen",
            key="faces_to_live",
            on_click=go,
            args=("live",),
            width="stretch",
            help="Drehen Sie den Würfel und sehen Sie zu, was passiert.",
        )
        right.button(
            "Zur Übersicht",
            key="faces_to_overview",
            on_click=go,
            args=("overview",),
            type="primary",
            width="stretch",
            help="Dort sehen Sie, was gerade läuft.",
        )


def _on_mode_change(client: ApiClient, device_id: str, key: str, current: str) -> None:
    """Callback of the mode switch: apply it, or put it back and remember why it failed."""
    wanted = st.session_state[key]
    try:
        client.set_device_mode(device_id, wanted)
    except OctaLedgerError as exc:
        st.session_state[key] = current
        st.session_state[MODE_ERROR_KEY] = (exc.user_message, exc.error_code)


def _mode_switch(client: ApiClient, device: dict[str, Any]) -> None:
    """The switch between time recording and control for this cube."""
    key = f"faces_mode_{device['id']}"
    if key not in st.session_state:
        st.session_state[key] = device["mode"]
    st.radio(
        "Wofür benutzen Sie diesen Würfel?",
        ("time", "control"),
        key=key,
        horizontal=True,
        format_func=lambda mode: "⏱ Zeit erfassen" if mode == "time" else "🎛 Dinge steuern",
        on_change=_on_mode_change,
        args=(client, device["id"], key, device["mode"]),
        help="Zeit erfassen: jede Seite ist eine Tätigkeit. Dinge steuern: jede Seite löst eine "
        "Aktion aus (Licht, Szene, Nachricht). Ein Würfel kennt immer nur einen Modus.",
    )
    failure = st.session_state.pop(MODE_ERROR_KEY, None)
    if failure:
        st.error(failure[0], icon="🚫")
        st.caption(f"Fehlercode: {failure[1]}")
    if device["mode"] == "control":
        st.caption(
            "Dieser Würfel **steuert**: Eine Drehung löst die Aktion der Seite aus und erfasst "
            "keine Zeit."
        )


def _connection_hint(client: ApiClient, device: dict[str, Any]) -> None:
    """Explain the connection state and offer the one-click fix where possible."""
    live = device["status"]
    if live and live["state"] == READY:
        return
    st.info(
        "Der Würfel ist **nicht verbunden**. Sie können die Seiten trotzdem von Hand einrichten. "
        "Mit Verbindung sehen Sie zusätzlich live, welche Seite oben liegt.",
        icon=":material/bluetooth_disabled:",
    )
    if device["has_address"]:
        if st.button(
            "Jetzt verbinden",
            key="faces_connect",
            icon=":material/bluetooth:",
            help="Baut die Bluetooth-Verbindung zu diesem Würfel auf (dauert einige Sekunden).",
        ):
            if call(client.connect_device, device["id"])[0]:
                st.rerun()
    else:
        st.button(
            "Würfel suchen und verbinden",
            key="faces_to_devices",
            on_click=go,
            args=("devices",),
            icon=":material/bluetooth_searching:",
            help="Dieser Tracker hat noch keine Bluetooth-Adresse. Im Bereich *Würfel "
            "verwalten* suchen Sie den Würfel.",
        )


@st.fragment(run_every="1s")
def _live_picture(client: ApiClient, device_id: str, theme: Theme) -> None:
    """The auto-refreshing picture plus the "set up the face that is up" shortcut."""
    key = target_key(device_id)
    try:
        live = client.live_view(device_id)
    except OctaLedgerError:  # a refresh problem must not blank the page; the next tick retries
        st.caption("Die Live-Anzeige ist gerade nicht erreichbar.")
        return
    labels = face_labels(live)
    connected = live["state"] == READY
    committed = live["committed_value"]
    up = committed if connected and committed in FACES else None
    target = st.session_state.get(key)
    st.markdown(
        cube_svg(
            theme,
            labels,
            up=up,
            pending=pending_face(live) if connected else None,
            selected=target if target in FACES else None,
            caption="Würfel von oben. Der blaue Ring markiert die Seite, die Sie einrichten.",
        ),
        unsafe_allow_html=True,
    )
    if not connected:
        st.caption("Blauer Ring: die Seite, die Sie gerade einrichten.")
        return
    if up is None:
        st.caption("Legen Sie den Würfel auf eine Seite. Blauer Ring: Ihre Auswahl.")
    elif up == target:
        st.caption(f"Seite {up} liegt oben und ist ausgewählt.")
    elif st.button(
        f"Seite {up} einrichten",
        key=f"faces_use_current_{device_id}",
        icon=":material/touch_app:",
        type="primary",
        width="stretch",
        help="Wählt die Seite aus, die der Würfel gerade oben hat, und zeigt rechts ihre "
        "Einstellungen.",
    ):
        st.session_state[PENDING_KEY] = (device_id, up)
        st.rerun()


def _editor(
    client: ApiClient,
    device: dict[str, Any],
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
) -> None:
    """Pick a face, then give it an existing or a new activity (outside the fragment)."""
    key = target_key(device["id"])
    taken = assigned_faces(device)
    st.radio(
        "Seite",
        FACES,
        key=key,
        horizontal=True,
        format_func=lambda n: f"{n} ✔" if n in taken else str(n),
        help="Die Seite, die Sie gerade einrichten. Ein Haken bedeutet: hat schon eine Tätigkeit.",
    )
    face = int(st.session_state[key])
    if device["mode"] == "control":
        render_action_editor(client, device, face)
        return
    current = device["faces"].get(str(face)) or {}
    by_id = {a["id"]: a for a in activities}
    st.markdown(
        f"**Seite {face}**" + (" – schon eingerichtet" if face in taken else " – noch frei")
    )

    options = [*activities, NEW_ACTIVITY]
    current_activity = by_id.get(current.get("activity_id"))
    index = options.index(current_activity) if current_activity in options else None
    if index is None and not activities:
        index = len(options) - 1  # nothing to pick from: go straight to "new activity"
    choice = st.selectbox(
        f"Tätigkeit für Seite {face}",
        options,
        index=index,
        key=f"faces_activity_{device['id']}_{face}",
        placeholder="Tätigkeit wählen …",
        format_func=lambda a: a["name"],
        help="Was startet, wenn Seite "
        + str(face)
        + " oben liegt. Neue Tätigkeit: Namen eintippen.",
    )
    new_name = ""
    if is_new(choice):
        new_name = st.text_input(
            "Name der neuen Tätigkeit",
            key=f"faces_new_name_{device['id']}_{face}",
            max_chars=100,
            placeholder="z. B. Kundengespräch",
            help="Die Tätigkeit wird beim Speichern angelegt und dieser Seite zugeordnet.",
        ).strip()
    project_options: list[dict[str, Any] | None] = [None, *projects]
    project = st.selectbox(
        "Projekt (optional)",
        project_options,
        index=next(
            (
                i
                for i, p in enumerate(project_options)
                if p and p["id"] == current.get("project_id")
            ),
            0,
        ),
        key=f"faces_project_{device['id']}_{face}",
        format_func=lambda p: "– kein Projekt –" if p is None else p["name"],
        help="Wofür die Zeit gebucht wird. Kann leer bleiben.",
    )
    ready = choice is not None and (not is_new(choice) or bool(new_name))
    save, clear = st.columns([3, 2])
    if save.button(
        f"Seite {face} speichern",
        key=f"faces_save_{device['id']}",
        type="primary",
        width="stretch",
        disabled=not ready,
        icon=":material/save:",
        help="Speichert die Zuordnung und springt zur nächsten freien Seite.",
    ):
        _save(client, device, face, choice, new_name, project)
    if clear.button(
        "Entfernen",
        key=f"faces_clear_{device['id']}",
        width="stretch",
        disabled=face not in taken,
        icon=":material/delete:",
        help="Löst die Tätigkeit von dieser Seite. Die Tätigkeit selbst bleibt erhalten.",
    ):
        if call(client.clear_face, device["id"], face)[0]:
            st.session_state[FLASH_KEY] = f"Seite {face} ist wieder frei."
            st.rerun()


def _save(
    client: ApiClient,
    device: dict[str, Any],
    face: int,
    choice: dict[str, Any] | None,
    new_name: str,
    project: dict[str, Any] | None,
) -> None:
    """Create the activity if needed, assign it to the face and move on."""
    if choice is None:
        return
    name = choice["name"]
    activity_id = choice["id"]
    if is_new(choice):
        created, activity = call(client.create_item, "activities", new_name)
        if not created or activity is None:
            return
        activity_id, name = activity["id"], activity["name"]
    done, _ = call(
        client.assign_face, device["id"], face, activity_id, project["id"] if project else None
    )
    if not done:
        return
    refreshed = {**device, "faces": {**device["faces"], str(face): {"activity_id": activity_id}}}
    following = next_free_face(refreshed, after=face)
    message = f"Seite {face} ist jetzt „{name}“."
    if following is not None:
        st.session_state[PENDING_KEY] = (device["id"], following)
        message += f" Weiter mit Seite {following}: Drehen Sie den Würfel darauf."
    st.session_state[FLASH_KEY] = message
    st.rerun()
