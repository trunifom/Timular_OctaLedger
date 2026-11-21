"""Live page: watch the cube move and see what each movement does inside OctaLedger.

The page answers three questions in plain language and refreshes every second:

1. **Was meldet der Würfel?** - the face the radio reports right now.
2. **Wird es geprüft?** - a new face is only accepted after it stayed put for the debounce time,
   so a wobble or a roll through other faces does not start anything.
3. **Was macht die Software?** - the activity assigned to the accepted face and the running time.

Below the picture a short history lists the last movements as sentences. Nothing here changes data
and nothing is stored: it only reads ``GET /devices/{id}/live``.
"""

from __future__ import annotations

import re
from typing import Any

import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.core.settings import Theme
from octaledger.dashboard.cube import FaceLabel, cube_svg
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import (
    STATE_LABELS,
    call,
    format_hms,
    format_local,
    page_help,
    to_local,
)
from octaledger.dashboard_client.client import ApiClient

HISTORY_LINES = 12
READY = "ready"
#: Fill colour of a face that has an action (control mode); the name tells them apart.
ACTION_COLOR = "#6D597A"
_MARKDOWN_SPECIAL = re.compile(r"[\\`*_{}\[\]<>()#+!|~$]")


def escape_markdown(text: str) -> str:
    """Neutralise Markdown syntax in user-chosen names (an activity called ``*x*`` stays text)."""
    return _MARKDOWN_SPECIAL.sub(lambda match: "\\" + match.group(0), text)


def face_labels(live: dict[str, Any]) -> dict[int, FaceLabel]:
    """Names and colours of the eight faces from a live-view response."""
    labels: dict[int, FaceLabel] = {}
    control = live.get("mode") in ("control", "music")
    for key, entry in live["faces"].items():
        if control:
            action = entry.get("action")
            labels[int(key)] = FaceLabel(action["label"], ACTION_COLOR) if action else FaceLabel()
            continue
        activity = entry["activity"]
        labels[int(key)] = (
            FaceLabel(activity["name"], activity["color"]) if activity else FaceLabel()
        )
    return labels


def face_text(value: int | None, labels: dict[int, FaceLabel]) -> str:
    """``3`` -> ``Seite 3 („Meeting“)``; ``0`` -> intermediate position; ``None`` -> unknown."""
    if value is None:
        return "noch nichts"
    if value == 0:
        return "Zwischenlage (keine Seite)"
    label = labels.get(value, FaceLabel())
    return f"Seite {value} („{label.name}“)" if label.name else f"Seite {value} (noch frei)"


def _action_hint(value: int | None, labels: dict[int, FaceLabel]) -> str:
    """Control mode: what the accepted face triggers (or that it triggers nothing)."""
    name = labels.get(value or 0, FaceLabel()).name
    return f" Die Aktion „{name}“ wird gesendet." if name else " Diese Seite hat keine Aktion."


def describe_event(
    event: dict[str, Any], labels: dict[int, FaceLabel], control: bool = False
) -> str:
    """One history entry as a German sentence (what happened, and what it means)."""
    kind, value = event["kind"], event["value"]
    where = face_text(value, labels)
    nothing = "Das löst noch nichts aus." if control else "Das startet noch nichts."
    lost = "" if control else " Laufende Zeit gilt als unsicher."
    return {
        "raw": f"Der Würfel zeigt {where}.",
        "baseline": f"Verbunden. Ausgangslage: {where}. {nothing}",
        "face_change": f"{where} wurde angenommen."
        + (_action_hint(value, labels) if control else ""),
        "neutral": "Der Würfel liegt in einer Zwischenlage (angenommen).",
        "disconnect": f"Die Verbindung ging verloren.{lost}",
        "reconnect": "Die Verbindung steht wieder.",
        "invalid": "Eine unverständliche Meldung wurde ignoriert.",
        "button": "Die Taste des Würfels wurde gedrückt.",
    }.get(kind, f"Ereignis: {kind}")


def _now_playing(client: ApiClient, device_id: str, tz: str) -> None:
    """The "♪ title, face, since" line of a music cube (or that nothing plays)."""
    try:
        states = client.music_state()
    except OctaLedgerError:
        return
    entry = next((s for s in states if s["device_id"] == device_id), None)
    if entry is None:
        return
    playing = entry["playing"]
    if playing is None:
        st.markdown("♪ **Es spielt nichts.** Drehen Sie den Würfel auf eine Seite mit Titel.")
        return
    since = format_local(playing["since"], tz)[-5:]
    st.markdown(
        f"♪ **{escape_markdown(playing['label'])}** · Seite {playing['face']} · seit {since}. "
        "In der Halterung endet die Musik."
    )
    if entry.get("lost_since"):
        st.warning(
            "Die Verbindung zum Würfel ist abgebrochen. Die Musik wird nach der eingestellten "
            "Frist beendet, wenn der Würfel nicht zurückkommt.",
            icon=":material/bluetooth_disabled:",
        )


def pending_face(live: dict[str, Any]) -> int | None:
    """The face waiting for confirmation, if there is one (1-8)."""
    committed = live["committed_value"]
    candidate = live["pending_value"]
    if candidate is None and live["raw_value"] != committed:
        candidate = live["raw_value"]  # seen on the radio, the debouncer has not taken it yet
    return candidate if candidate in range(1, 9) and candidate != committed else None


def render(client: ApiClient, tz: str) -> None:
    """Render the live page."""
    st.header("Würfel live")
    page_help(
        "So funktioniert die Live-Ansicht",
        "Hier sehen Sie **in Echtzeit**, was der Würfel tut und was die Software daraus macht.\n\n"
        "- **Das Bild** zeigt den Würfel von oben. Die Nummern sind die **technischen "
        "Seitennummern** des Würfels. Die Seite mit dem ▲ und dem dicken Rand liegt oben. Ein "
        "gestrichelter Rand heißt: gesehen, aber noch nicht bestätigt.\n"
        "- **Warum erst bestätigen?** Beim Drehen rollt der Würfel über andere Seiten. Eine Seite "
        "zählt erst, wenn sie kurz ruhig liegt (Entprellzeit, einstellbar unter "
        "*Einstellungen*). So startet ein Wackeln keine falsche Tätigkeit.\n"
        "- **Ausprobieren:** Drehen Sie den Würfel auf eine andere Seite und schauen Sie zu.\n"
        "- Die Ansicht liest nur mit und speichert nichts.",
    )
    ok, devices = call(client.devices)
    if not ok or devices is None:
        return
    if not devices:
        st.info(
            "Es ist noch kein Würfel eingerichtet. Mit der geführten Einrichtung auf der "
            "Startseite sind Sie in wenigen Minuten bereit."
        )
        st.button(
            "Zur Einrichtung",
            key="live_to_start",
            on_click=go,
            args=("start",),
            type="primary",
            help="Öffnet die Startseite mit der geführten Einrichtung.",
        )
        return
    device = devices[0]
    if len(devices) > 1:
        device = st.selectbox(
            "Tracker",
            devices,
            key="live_device",
            format_func=lambda d: d["alias"] + (" ⭐" if d["is_active"] else ""),
            help="Welchen Tracker Sie beobachten. Der Stern markiert den aktiven Tracker.",
        )
    display = st.session_state.get("_display", {})
    _live(client, device["id"], tz, Theme(display.get("theme", Theme.LIGHT.value)))


@st.fragment(run_every="1s")
def _live(client: ApiClient, device_id: str, tz: str, theme: Theme) -> None:
    """The auto-refreshing part: picture, three steps and history."""
    try:
        live = client.live_view(device_id)
    except OctaLedgerError as exc:
        st.error(exc.user_message, icon="🚫")
        return
    labels = face_labels(live)
    connected = live["state"] == READY
    committed = live["committed_value"]
    up = committed if committed in range(1, 9) and connected else None
    pending = pending_face(live) if connected else None
    control = live.get("mode") in ("control", "music")
    if live.get("mode") == "music":
        _now_playing(client, device_id, tz)

    picture, steps = st.columns([5, 6], vertical_alignment="center")
    with picture:
        st.markdown(
            cube_svg(
                theme,
                labels,
                up=up,
                pending=pending,
                caption=f"Würfel von oben, oben liegt {face_text(up, labels)}",
            ),
            unsafe_allow_html=True,
        )
        if not connected:
            st.caption("Nicht verbunden: das Bild zeigt nur die Zuordnung der Seiten.")
    with steps:
        _flow(live, labels, connected, pending, control)

    st.subheader("Letzte Bewegungen")
    events = live["recent"][:HISTORY_LINES]
    if not events:
        st.caption(
            "Noch keine Bewegung gesehen. Sobald der Würfel verbunden ist und Sie ihn drehen, "
            "erscheint es hier."
        )
    else:
        lines = []
        for event in events:
            moment = to_local(event["at"], tz)
            clock = moment.strftime("%H:%M:%S") if moment else "–"
            lines.append(f"- `{clock}` {escape_markdown(describe_event(event, labels, control))}")
        st.markdown("\n".join(lines))
    if control:
        _recent_actions(client, tz)


def _recent_actions(client: ApiClient, tz: str) -> None:
    """Control mode: the last actions that were sent and how each ended."""
    st.subheader("Letzte Aktionen")
    try:
        jobs = client.jobs(5)
    except OctaLedgerError:
        st.caption("Der Verlauf der Aktionen ist gerade nicht erreichbar.")
        return
    if not jobs:
        st.caption("Noch wurde keine Aktion gesendet.")
        return
    status = {
        "pending": "⏳ wartet",
        "done": "✅ gesendet",
        "failed": "❌ fehlgeschlagen",
        "expired": "⌛ verfallen",
    }
    lines = []
    for job in jobs:
        moment = to_local(job["created_at"], tz)
        clock = moment.strftime("%H:%M:%S") if moment else "–"
        note = f" – {job['error']}" if job["error"] else ""
        result = status.get(job["status"], job["status"])
        text = f"{job['label']} ({job['integration']}): {result}{note}"
        lines.append(f"- `{clock}` {escape_markdown(text)}")
    st.markdown("\n".join(lines))


def _flow(
    live: dict[str, Any],
    labels: dict[int, FaceLabel],
    connected: bool,
    pending: int | None,
    control: bool = False,
) -> None:
    """The three cards: what the cube reports, whether it is checked, what the software does."""
    with st.container(border=True):
        st.markdown("**① Der Würfel meldet**")
        if not connected:
            state = (
                STATE_LABELS.get(live["state"], "nicht verbunden")
                if live["state"]
                else "nicht verbunden"
            )
            st.markdown(f"Keine Verbindung ({state}).")
            st.button(
                "Zu den Geräten",
                key="live_to_devices",
                on_click=go,
                args=("devices",),
                help="Dort verbinden Sie den Würfel.",
            )
        else:
            st.markdown(face_text(live["raw_value"], labels) + ".")
    with st.container(border=True):
        st.markdown("**② Wird geprüft**")
        if pending is not None and connected:
            seconds = live["debounce_ms"] / 1000
            st.markdown(
                f"⏳ {face_text(pending, labels)} wird geprüft. Bitte {seconds:.1f} s ruhig "
                "halten, dann zählt sie."
            )
        elif connected:
            st.markdown("✅ Stabil. Nichts steht aus.")
        else:
            st.markdown("–")
    with st.container(border=True):
        st.markdown("**③ Die Aktion**" if control else "**③ Die Software**")
        if control:
            _control_effect(live, labels, connected)
        else:
            _software(live, labels, connected)


def _control_effect(live: dict[str, Any], labels: dict[int, FaceLabel], connected: bool) -> None:
    """Control mode: what the accepted face triggers."""
    st.markdown("🎛 Dieser Würfel **steuert** Dinge und erfasst keine Zeit.")
    committed = live["committed_value"]
    if not connected or committed not in range(1, 9):
        return
    name = labels.get(committed, FaceLabel()).name
    if name:
        st.markdown(f"Seite {committed}: Die Aktion „{escape_markdown(name)}“ wird ausgelöst.")
    else:
        st.info(
            f"Seite {committed} hat noch keine Aktion, darum passiert hier nichts. Ordnen Sie "
            "ihr im Bereich *Seiten zuordnen* eine zu."
        )


def _software(live: dict[str, Any], labels: dict[int, FaceLabel], connected: bool) -> None:
    tracking = live["tracking"]
    running = tracking["running"]
    committed = live["committed_value"]
    if running:
        activity = tracking["activity"] or {"name": "Unbekannt"}
        st.markdown(
            f"▶ **{escape_markdown(activity['name'])}** läuft seit "
            f"{format_hms(tracking['elapsed_seconds'])}."
        )
    elif tracking["paused"]:
        st.markdown("⏸ Pausiert.")
    else:
        st.markdown("Keine Zeiterfassung läuft.")
    if not connected:
        return
    if not live["is_active"]:
        st.warning(
            "Dieser Tracker ist **nicht der aktive**. Seine Bewegungen erzeugen keine Zeiten "
            "(Bereich *Würfel verwalten*, „Zum aktiven Tracker machen“).",
            icon="⚠️",
        )
    elif committed in range(1, 9) and labels.get(committed, FaceLabel()).name is None:
        st.info(
            f"Seite {committed} hat noch keine Tätigkeit, darum startet hier nichts. "
            "Ordnen Sie ihr im Bereich *Würfel verwalten* eine zu."
        )
