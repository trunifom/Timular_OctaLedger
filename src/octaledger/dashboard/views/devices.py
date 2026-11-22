"""Devices page: register trackers, find them via Bluetooth, connect and calibrate the 8 faces."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from octaledger.dashboard.identity import cube_html
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import (
    STATE_LABELS,
    STATE_LEVEL,
    call,
    format_local,
    page_help,
    status_dot,
)
from octaledger.dashboard_client.client import ApiClient

NO_ACTIVITY = "– nicht belegt –"
NO_PROJECT = "– kein Projekt –"
FACES = range(1, 9)


def render(client: ApiClient, tz: str) -> None:
    """Render the devices page."""
    st.header("Würfel verwalten")
    page_help(
        "So funktioniert „Würfel verwalten“",
        "**1. Registrieren:** Geben Sie Ihrem Würfel einen Namen.\n\n"
        "**2. Finden:** *Nach Geräten suchen* zeigt Bluetooth-Geräte in der Nähe. Wählen Sie Ihren "
        "Würfel und ordnen Sie ihn dem Tracker zu. OctaLedger verbindet nie von selbst mit "
        "unbekannten Geräten.\n\n"
        "**3. Verbinden:** Mit *Verbinden* baut der Agent die Bluetooth-Verbindung auf.\n\n"
        "**4. Seiten zuordnen (Kalibrierung):** Halten Sie eine Seite nach oben – die technische "
        "Nummer erscheint („liegt oben“). Wählen Sie dafür eine Tätigkeit, und wiederholen Sie das "
        "für alle acht Seiten.\n\n"
        "**Aktiver Tracker:** Nur er erzeugt Zeiten. Mit *Zum aktiven Tracker machen* wechseln Sie "
        "ausdrücklich (die Zeit des alten Trackers endet dabei, es entsteht keine doppelte Zeit).",
    )
    flash = st.session_state.pop("devices_flash", None)
    if flash:
        st.success(flash)
    ok, devices = call(client.devices)
    ok_a, activities = call(client.list_items, "activities")
    ok_p, projects = call(client.list_items, "projects")
    if not (ok and ok_a and ok_p) or devices is None or activities is None or projects is None:
        return

    _register_form(client)
    _scan_section(client, devices)
    st.subheader("Ihre Tracker")
    if not devices:
        st.info("Noch kein Tracker registriert. Legen Sie oben Ihren ersten Würfel an.")
    for device in devices:
        _device_panel(client, device, activities, projects, tz, expanded=len(devices) == 1)


def _register_form(client: ApiClient) -> None:
    st.subheader("Tracker registrieren")
    with st.form("register_form", clear_on_submit=True):
        alias = st.text_input(
            "Name des Trackers",
            key="register_alias",
            max_chars=100,
            placeholder="z. B. Tracker Büro",
            help="Frei wählbarer Name, nur zur Anzeige. Jeder Name darf nur einmal vorkommen.",
        )
        if st.form_submit_button(
            "➕ Registrieren",
            type="primary",
            help="Legt den Tracker mit diesem Namen an; die Bluetooth-Adresse folgt per Suche.",
        ):
            created, device = call(client.register_device, alias)
            if created and device:
                st.success(f"„{device['alias']}“ wurde registriert.")


def _scan_section(client: ApiClient, devices: list[dict[str, Any]]) -> None:
    st.subheader("Bluetooth-Suche")
    st.caption("Die Suche läuft nur, wenn Sie sie starten (ca. 5 Sekunden).")
    if st.button(
        "🔍 Nach Geräten suchen",
        key="btn_scan",
        help="Sucht Bluetooth-Geräte in der Nähe. Es wird nichts verbunden.",
    ):
        with st.spinner("Suche läuft …"):
            found, results = call(client.scan, 5.0)
        if found:
            st.session_state["_scan"] = results
    results = st.session_state.get("_scan")
    if results is None:
        return
    if not results:
        st.info(
            "Keine Geräte gefunden. Ist Bluetooth eingeschaltet, der Würfel wach (einmal drehen) "
            "und in der Nähe?"
        )
        return
    pick = st.selectbox(
        "Gefundenes Gerät",
        results,
        key="scan_pick",
        format_func=_scan_label,
        help="✅ markiert Geräte, die den erwarteten Orientierungsdienst anbieten, „vermutlich Ihr "
        "Würfel“ solche mit passendem Namen. Andere Geräte werden nicht ausgeblendet, falls Ihr "
        "Würfel anders meldet.",
    )
    if not devices:
        _register_found(client, pick)
        return
    target = st.selectbox(
        "Zuordnen zu Tracker",
        devices,
        key="scan_target",
        format_func=lambda d: d["alias"],
        help="Der registrierte Tracker, der dieses Bluetooth-Gerät verwenden soll.",
    )
    if st.button(
        "💾 Adresse speichern",
        key="scan_assign",
        help="Speichert die Bluetooth-Adresse für diesen Tracker.",
    ):
        if call(client.set_device_address, target["id"], pick["address"])[0]:
            st.success(f"Gerät dem Tracker „{target['alias']}“ zugeordnet.")
            st.session_state.pop("_scan", None)
            st.rerun()


def _scan_label(result: dict[str, Any]) -> str:
    """Picker label: the signal-strength label plus hints that this is probably the cube."""
    hint = ""
    if result["is_candidate"]:
        hint = " ✅ passender Dienst"
    elif result["looks_like_tracker"]:
        hint = " ← vermutlich Ihr Würfel"
    return f"{result['label']}{hint}"


def _register_found(client: ApiClient, pick: dict[str, Any]) -> None:
    """No tracker exists yet: name it and register + assign the found device in one step."""
    alias = st.text_input(
        "Name für den neuen Tracker",
        value="Mein Würfel",
        key="scan_new_alias",
        max_chars=100,
        help="Frei wählbar, nur zur Anzeige. Der Tracker wird angelegt und dem gefundenen Gerät "
        "zugeordnet.",
    ).strip()
    if st.button(
        "➕ Registrieren und zuordnen",
        key="scan_register",
        type="primary",
        disabled=not alias,
        help="Legt den Tracker an und speichert die Bluetooth-Adresse des gefundenen Geräts.",
    ):
        created, device = call(client.register_device, alias)
        if created and device and call(client.set_device_address, device["id"], pick["address"])[0]:
            st.session_state.pop("_scan", None)
            st.rerun()


def _device_panel(
    client: ApiClient,
    device: dict[str, Any],
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    tz: str,
    *,
    expanded: bool,
) -> None:
    did = device["id"]
    live = device["status"]
    badge = " ⭐ aktiv" if device["is_active"] else ""
    if device["mode"] == "control":
        badge += " · 🎛 Steuerung"
    if device["mode"] == "music":
        badge += " · 🎵 Musik"
    title = f"{device.get('badge', '')} {device['alias']}".strip()
    with st.expander(f"{title}{badge}", expanded=expanded):
        st.markdown(
            f"{cube_html(device)} · Farbe {html.escape(device.get('color_name', ''))}",
            unsafe_allow_html=True,
        )
        label = STATE_LABELS.get(live["state"], live["state"]) if live else "Nicht verbunden"
        level = STATE_LEVEL.get(live["state"], "warn") if live else "bad"
        st.markdown(status_dot(level, f"**{label}**"), unsafe_allow_html=True)
        details = [
            f"Modell: {device['model'] or 'unbekannt'}",
            f"Firmware: {device['firmware'] or 'unbekannt'}",
            "Bluetooth-Adresse: "
            + ("gespeichert" if device["has_address"] else "noch nicht zugeordnet"),
            f"registriert: {format_local(device['created_at'], tz)}",
        ]
        if live and live.get("battery_percent") is not None:
            details.append(f"Batterie: {live['battery_percent']} %")
        st.caption(" · ".join(details))
        if live and live.get("last_error"):
            st.warning(f"Letzte Meldung: {live['last_error']}", icon="⚠️")

        a, b, c = st.columns(3)
        if a.button(
            "🔗 Verbinden",
            key=f"connect_{did}",
            width="stretch",
            help="Baut die Bluetooth-Verbindung auf. Erfordert eine zugeordnete Adresse.",
        ):
            if call(client.connect_device, did)[0]:
                st.rerun()
        if b.button(
            "⛔ Trennen",
            key=f"disconnect_{did}",
            width="stretch",
            help="Beendet die Verbindung bewusst. Es folgen keine automatischen Neuversuche.",
        ):
            if call(client.disconnect_device, did)[0]:
                st.rerun()
        if c.button(
            "⭐ Zum aktiven Tracker machen",
            key=f"activate_{did}",
            width="stretch",
            disabled=device["is_active"] or device["mode"] != "time",
            help="Übergabe: Nur der aktive Tracker erzeugt Zeiten. Die laufende "
            "Tracker-Zeit des bisherigen Trackers endet dabei. Ein Würfel im Steuerungsmodus "
            "erfasst keine Zeit.",
        ):
            if call(client.activate_device, did)[0]:
                st.rerun()

        _calibration(client, device, activities, projects)
        if device["mode"] == "time":
            _button_section(client, device)
        _manage(client, device)


def _calibration(
    client: ApiClient,
    device: dict[str, Any],
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
) -> None:
    did = device["id"]
    if device["mode"] in ("control", "music"):
        if device["mode"] == "music":
            st.info(
                "Dieser Würfel ist im **Musik-Modus**: Jede Seite spielt einen Titel, die "
                "Halterung beendet die Musik. Die Titel legen Sie im Bereich *Seiten zuordnen* "
                "fest."
            )
        else:
            st.info(
                "Dieser Würfel ist im **Steuerungsmodus**: Seine Seiten lösen Aktionen aus "
                "statt Zeit zu erfassen. Die Aktionen legen Sie im Bereich *Seiten zuordnen* fest."
            )
        st.button(
            "Zu „Seiten zuordnen“",
            key=f"to_faces_{did}",
            on_click=go,
            args=("faces",),
            help="Öffnet den Assistenten für die Aktionen der Seiten.",
        )
        return
    st.markdown("**Seiten zuordnen (Kalibrierung)**")
    st.progress(
        device["configured_faces"] / 8,
        text=f"{device['configured_faces']} von 8 Seiten haben eine Tätigkeit",
    )
    _, observed = call(client.observed_face, did)
    up = observed["face"] if observed else None
    if up is None:
        st.caption("Noch keine Seite gemeldet – drehen Sie den Würfel, sobald er verbunden ist.")
    elif up == 0:
        st.caption("Der Würfel liegt gerade auf keiner stabilen Seite (neutral).")
    else:
        st.caption(f"👈 Aktuell liegt **Seite {up}** oben.")
    if not activities:
        st.info("Legen Sie zuerst im Bereich **Tätigkeiten & Projekte** Tätigkeiten an.")
        return

    activity_options: list[dict[str, Any] | None] = [None, *activities]
    project_options: list[dict[str, Any] | None] = [None, *projects]

    def index_of(options: list[dict[str, Any] | None], wanted: str | None) -> int:
        """Position of the option with id ``wanted`` (0, the empty choice, if there is none)."""
        return next((i for i, o in enumerate(options) if o and o["id"] == wanted), 0)

    with st.form(f"calib_{did}"):
        for face in FACES:
            current = device["faces"].get(str(face), {})
            col_face, col_activity, col_project = st.columns([1.2, 3, 3])
            col_face.markdown(f"**Seite {face}**" + (" 👈" if face == up else ""))
            col_activity.selectbox(
                f"Tätigkeit Seite {face}",
                activity_options,
                key=f"face_act_{did}_{face}",
                index=index_of(activity_options, current.get("activity_id")),
                format_func=lambda a: NO_ACTIVITY if a is None else a["name"],
                label_visibility="collapsed",
                help=f"Welche Tätigkeit startet, wenn Seite {face} oben liegt.",
            )
            col_project.selectbox(
                f"Projekt Seite {face}",
                project_options,
                key=f"face_proj_{did}_{face}",
                index=index_of(project_options, current.get("project_id")),
                format_func=lambda p: NO_PROJECT if p is None else p["name"],
                label_visibility="collapsed",
                help=f"Optionales Projekt für Seite {face}.",
            )
        if st.form_submit_button(
            "💾 Kalibrierung speichern",
            type="primary",
            help="Speichert die geänderten Seitenzuordnungen dieses Würfels.",
        ):
            _save_calibration(client, device, activity_options, project_options)


def _save_calibration(
    client: ApiClient,
    device: dict[str, Any],
    activity_options: list[dict[str, Any] | None],
    project_options: list[dict[str, Any] | None],
) -> None:
    """Send only the faces that changed."""
    did = device["id"]
    changed = 0
    for face in FACES:
        activity = st.session_state[f"face_act_{did}_{face}"]
        project = st.session_state[f"face_proj_{did}_{face}"]
        activity_id = activity["id"] if activity else None
        project_id = project["id"] if project and activity else None
        current = device["faces"].get(str(face))
        if current is None and activity_id is None:
            continue
        if current and (current["activity_id"], current["project_id"]) == (activity_id, project_id):
            continue
        done, _ = (
            call(client.assign_face, did, face, activity_id, project_id)
            if activity_id
            else call(client.clear_face, did, face)
        )
        if not done:
            return
        changed += 1
    st.success(f"{changed} Seite(n) gespeichert." if changed else "Nichts geändert.")
    if changed:
        st.rerun()


ASK_REMOVE_KEY = "devices_ask_remove"  # id of the cube whose removal is being confirmed


BUTTON_ACTIONS = {
    "none": "Nichts tun (Voreinstellung)",
    "pause_resume": "Pause / Fortsetzen",
    "stop": "Zeit beenden",
    "start_last": "Letzte Tätigkeit starten",
}
PRESS_LABELS = {"short": "Kurzer Druck", "long": "Langer Druck"}


def _button_section(client: ApiClient, device: dict[str, Any]) -> None:
    """Assign actions to the cube's button (off by default; not hardware-confirmed)."""
    did = device["id"]
    with st.expander("Taste des Würfels", key=f"buttons_{did}"):
        st.caption(
            "Der Würfel hat eine Taste. Hier legen Sie fest, was ein **kurzer** und ein **langer** "
            "Druck tut. Ohne Auswahl passiert **nichts**. **Noch nicht mit echter Hardware "
            "geprüft:** Ob Ihr Würfel die Taste so meldet wie in der Community-Beschreibung, "
            "zeigt die Seite *Würfel live* („Letzte Bewegungen“)."
        )
        ok, buttons = call(client.device_buttons, did)
        if not ok or buttons is None:
            return
        for press, label in PRESS_LABELS.items():
            current = buttons.get(press) or "none"
            choice = st.selectbox(
                label,
                list(BUTTON_ACTIONS),
                index=list(BUTTON_ACTIONS).index(current),
                format_func=BUTTON_ACTIONS.__getitem__,
                key=f"button_{press}_{did}",
                help="Was dieser Tastendruck bewirkt. Nur der **aktive** Tracker beeinflusst die "
                "Zeit. Voreinstellung: nichts.",
            )
            if choice != current and call(client.set_device_button, did, press, choice)[0]:
                st.rerun()


def _manage(client: ApiClient, device: dict[str, Any]) -> None:
    """Rename, unpair and remove a cube (removal is a two-step action with a safety backup)."""
    did = device["id"]
    with st.expander("Verwalten: umbenennen, Kopplung aufheben, entfernen", key=f"manage_{did}"):
        new_alias = st.text_input(
            "Neuer Name",
            value=device["alias"],
            key=f"rename_{did}",
            max_chars=100,
            help="Ändert nur die Anzeige.",
        )
        if st.button("✏️ Umbenennen", key=f"rename_btn_{did}", help="Speichert den neuen Namen."):
            if call(client.rename_device, did, new_alias)[0]:
                st.rerun()

        new_color = st.color_picker(
            "Farbe des Würfels",
            value=device["color"],
            key=f"color_{did}",
            help="Mit dieser Farbe (und der Nummer) erkennen Sie den Würfel überall wieder: in "
            "der Seitenleiste, im Banner, auf den Karten. Nur die Anzeige ändert sich.",
        )
        if st.button(
            "Farbe speichern",
            key=f"color_btn_{did}",
            icon=":material/palette:",
            disabled=new_color.upper() == device["color"].upper(),
            help="Speichert die gewählte Farbe für diesen Würfel.",
        ):
            if call(client.rename_device, did, None, new_color)[0]:
                st.rerun()

        st.markdown("**Kopplung aufheben**")
        st.caption(
            "Beendet die Verbindung und vergisst die Bluetooth-Adresse. Der Würfel, seine Seiten "
            "und alle erfassten Daten bleiben erhalten; Sie können ihn jederzeit neu koppeln "
            "(Bluetooth-Suche oben). Sinnvoll, wenn Sie einen anderen Würfel verwenden wollen."
        )
        if st.button(
            "Kopplung aufheben",
            key=f"unpair_{did}",
            icon=":material/link_off:",
            disabled=not device["has_address"],
            help="Trennt den Würfel und vergisst seine Adresse; nichts wird gelöscht.",
        ):
            if call(client.unpair_device, did)[0]:
                st.session_state["_scan"] = None
                st.rerun()

        st.markdown("**Würfel entfernen**")
        st.caption(
            "Entfernt den Würfel mitsamt Seitenzuordnung und Aktionen. Hat er bereits Daten "
            "erfasst, müssen Sie entscheiden, ob diese mit gelöscht werden."
        )
        if st.button(
            "Entfernen …",
            key=f"remove_ask_{did}",
            icon=":material/delete:",
            help="Fragt noch einmal nach. Entfernt wird erst danach.",
        ):
            st.session_state[ASK_REMOVE_KEY] = did
        if st.session_state.get(ASK_REMOVE_KEY) == did:
            _confirm_remove(client, device)


def _confirm_remove(client: ApiClient, device: dict[str, Any]) -> None:
    did = device["id"]
    with st.container(border=True, key=f"remove_confirm_{did}"):
        with_data = st.checkbox(
            "Auch alle mit diesem Würfel erfassten Daten löschen (Einträge und Rohereignisse)",
            key=f"remove_data_{did}",
            help="Ohne Haken lässt sich nur ein Würfel ohne Daten entfernen. Mit Haken legt "
            "OctaLedger vorher automatisch eine Sicherung an (Ihr Rückgängig).",
        )
        st.warning(
            f"„{device['alias']}“ wird entfernt"
            + (" – samt aller erfassten Daten." if with_data else ".")
            + " Das lässt sich nicht rückgängig machen"
            + (" (außer über die Sicherung)." if with_data else "."),
            icon="⚠️",
        )
        yes, no = st.columns(2)
        if yes.button(
            "Würfel entfernen",
            key=f"delete_{did}",
            type="primary",
            width="stretch",
            help="Entfernt den Würfel endgültig.",
        ):
            ok, done = call(client.remove_device_with_options, did, with_data)
            if ok and done:
                st.session_state.pop(ASK_REMOVE_KEY, None)
                if done["safety_backup"]:
                    st.session_state["devices_flash"] = (
                        f"„{device['alias']}“ wurde entfernt. Sicherung vorher: "
                        f"**{done['safety_backup']}** (Ordner „backups“)."
                    )
                st.rerun()
        if no.button(
            "Behalten",
            key=f"remove_keep_{did}",
            width="stretch",
            help="Bricht ab, es wird nichts entfernt.",
        ):
            st.session_state.pop(ASK_REMOVE_KEY, None)
            st.rerun()
