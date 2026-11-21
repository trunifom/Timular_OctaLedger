"""Devices page: register trackers, find them via Bluetooth, connect and calibrate the 8 faces."""

from __future__ import annotations

from typing import Any

import streamlit as st

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
    st.header("Geräte")
    page_help(
        "So funktioniert die Geräte-Seite",
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
        if st.form_submit_button("➕ Registrieren", type="primary"):
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
    if not devices:
        st.info("Registrieren Sie zuerst einen Tracker, dem Sie das gefundene Gerät zuordnen.")
        return
    pick = st.selectbox(
        "Gefundenes Gerät",
        results,
        key="scan_pick",
        format_func=lambda r: r["label"] + (" ✅ passender Dienst" if r["is_candidate"] else ""),
        help="✅ markiert Geräte, die den erwarteten Orientierungsdienst anbieten. Andere Geräte "
        "werden nicht ausgeblendet, falls Ihr Würfel anders meldet.",
    )
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
    with st.expander(f"{device['alias']}{badge}", expanded=expanded):
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
            disabled=device["is_active"],
            help="Übergabe: Nur der aktive Tracker erzeugt Zeiten. Die laufende "
            "Tracker-Zeit des bisherigen Trackers endet dabei.",
        ):
            if call(client.activate_device, did)[0]:
                st.rerun()

        _calibration(client, device, activities, projects)
        _manage(client, device)


def _calibration(
    client: ApiClient,
    device: dict[str, Any],
    activities: list[dict[str, Any]],
    projects: list[dict[str, Any]],
) -> None:
    did = device["id"]
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
        st.info("Legen Sie zuerst im Bereich **Verwaltung** Tätigkeiten an.")
        return

    activity_options: list[dict[str, Any] | None] = [None, *activities]
    project_options: list[dict[str, Any] | None] = [None, *projects]

    def index_of(options: list[dict[str, Any] | None], wanted: str | None) -> int:
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
        if st.form_submit_button("💾 Kalibrierung speichern", type="primary"):
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


def _manage(client: ApiClient, device: dict[str, Any]) -> None:
    did = device["id"]
    with st.expander("Umbenennen oder löschen"):
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
        confirm = st.checkbox(
            f"Ja, „{device['alias']}“ löschen",
            key=f"delete_confirm_{did}",
            help="Löschen ist nur möglich, solange für das Gerät noch keine Daten aufgezeichnet "
            "wurden.",
        )
        if st.button(
            "🗑 Löschen",
            key=f"delete_{did}",
            disabled=not confirm,
            help="Entfernt den Tracker samt Seitenzuordnung.",
        ):
            if call(client.remove_device, did)[0]:
                st.rerun()
