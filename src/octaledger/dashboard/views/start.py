"""Start page: what the cube is, what OctaLedger is good for, guided setup and the manual.

Three sections, chosen with a segmented picker (a picker instead of ``st.tabs`` so that buttons
elsewhere on the page can switch the section):

* **Willkommen** - plain-language explanation of the Timeular cube and of what the software can be
  used for, plus a clear "what next" banner computed from the real setup state.
* **Einrichten** - the guided setup: find the cube, connect it and (via the setup assistant) give
  every face an activity. The cube is found with one search and registered, assigned and connected
  with **one** click, so users never have to understand "register", "assign address" and "connect"
  as separate steps.
* **Handbuch** - the user documentation from ``docs/``, one chapter at a time, with search.

Nothing on this page invents data: the example picture is labelled as an example and is replaced
by the user's real faces as soon as a tracker exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.core.settings import Theme
from octaledger.dashboard.cube import FaceLabel, cube_svg
from octaledger.dashboard.docs_reader import (
    DOCUMENTS,
    Chapter,
    load_document,
    search,
    split_chapters,
)
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import STATE_LABELS, STATE_LEVEL, call, status_dot
from octaledger.dashboard_client.client import ApiClient

SECTION_KEY = "start_section"
SECTIONS = ("Willkommen", "Einrichten", "Handbuch")
FLASH_KEY = "start_flash"
READY = "ready"
DEFAULT_ALIAS = "Mein Würfel"

#: Shown on the welcome page only while no tracker exists; clearly labelled as an example.
EXAMPLE_FACES = {
    1: FaceLabel("Coding", "#2A9D8F"),
    2: FaceLabel("Meeting", "#E76F51"),
    3: FaceLabel("Pause", "#F4A261"),
    4: FaceLabel("E-Mails", "#6D597A"),
    5: FaceLabel("Planung", "#4D908E"),
    6: FaceLabel("Kunde", "#E9C46A"),
    7: FaceLabel("Lernen", "#277DA1"),
    8: FaceLabel("Admin", "#9AA5B1"),
}


@dataclass(frozen=True, slots=True)
class SetupState:
    """How far the setup is (derived from the API, never stored)."""

    has_device: bool
    has_address: bool
    state: str | None  # connection state of the active tracker, ``None`` if never started
    faces_done: int

    @property
    def connected(self) -> bool:
        """The cube is connected and delivers values right now."""
        return self.state == READY

    @property
    def complete(self) -> bool:
        """Cube known and all eight faces have an activity."""
        return self.has_address and self.faces_done >= 8

    @property
    def next_step(self) -> str:
        """``connect``, ``faces`` or ``done``."""
        if not self.has_address:
            return "connect"
        return "faces" if self.faces_done < 8 else "done"


def setup_state(devices: list[dict[str, Any]]) -> SetupState:
    """Summarise the setup from the device list (the active tracker counts)."""
    if not devices:
        return SetupState(False, False, None, 0)
    device = next((d for d in devices if d["is_active"]), devices[0])
    live = device["status"]
    return SetupState(
        True,
        bool(device["has_address"]),
        live["state"] if live else None,
        int(device["configured_faces"]),
    )


def render(client: ApiClient, tz: str) -> None:
    """Render the start page."""
    st.header("Startseite")
    ok, devices = call(client.devices)
    if not ok or devices is None:
        return
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)
    state = setup_state(devices)
    if st.session_state.get(SECTION_KEY) not in SECTIONS:
        st.session_state[SECTION_KEY] = SECTIONS[0]
    section = st.radio(
        "Bereich",
        SECTIONS,
        key=SECTION_KEY,
        horizontal=True,
        label_visibility="collapsed",
        help="Willkommen: Was ist das? · Einrichten: Schritt für Schritt starten · "
        "Handbuch: die ganze Anleitung zum Nachlesen.",
    )
    if section == "Willkommen":
        _welcome(devices, state)
    elif section == "Einrichten":
        _setup(client, devices, state)
    else:
        _manual()


def _open_section(section: str) -> None:
    """``on_click`` callback: switch the picker (runs before the picker is created)."""
    st.session_state[SECTION_KEY] = section


# ------------------------------------------------------------------------------ welcome


def _welcome(devices: list[dict[str, Any]], state: SetupState) -> None:
    st.markdown("## Drehen. Arbeiten. Die Zeit läuft.")
    st.markdown(
        "OctaLedger erfasst Ihre Arbeitszeit mit einem **Timeular-Würfel** – lokal auf Ihrem "
        "Computer, ohne Cloud und ohne Konto."
    )
    _next_step_banner(state)

    text, picture = st.columns([6, 5], gap="large", vertical_alignment="center")
    with text:
        st.markdown("### Was ist der Würfel?")
        st.markdown(
            "Der Timeular-Tracker ist ein kleiner **achtseitiger Würfel** mit Bluetooth. Jede der "
            "**acht Seiten** steht für eine Tätigkeit, zum Beispiel *Entwicklung*, *Meeting* oder "
            "*Pause*.\n\n"
            "Sie legen den Würfel auf die Seite der Tätigkeit, an der Sie gerade arbeiten. "
            "OctaLedger bemerkt die Drehung per Bluetooth und **startet die passende Zeit**. "
            "Drehen Sie auf eine andere Seite, endet die vorige Zeit und die neue beginnt – ohne "
            "Klick, ohne Timer."
        )
    with picture:
        display = st.session_state.get("_display", {})
        theme = Theme(display.get("theme", Theme.LIGHT.value))
        st.markdown(
            cube_svg(
                theme, EXAMPLE_FACES, up=1, caption="Beispiel: der Würfel mit acht Tätigkeiten"
            ),
            unsafe_allow_html=True,
        )
        st.caption("Beispiel: so könnten Ihre acht Seiten belegt sein (Seite 1 liegt oben).")

    st.markdown("### Wofür Sie OctaLedger einsetzen können")
    cards = (
        (
            "🕒 Arbeitszeit ohne Aufwand",
            "Keine Timer starten und stoppen. Eine Drehung genügt, und Sie bleiben im Fluss.",
        ),
        (
            "📊 Auswerten nach Tätigkeit und Projekt",
            "Tag, Woche oder freier Zeitraum mit Diagrammen. Für Rechnungen und Berichte als "
            "CSV exportierbar (Excel).",
        ),
        (
            "🎯 Fokus und Pausen sichtbar machen",
            "Sehen Sie, wohin Ihre Zeit wirklich ging, und planen Sie Ihren Tag besser.",
        ),
        (
            "🔒 Lokal und privat",
            "Ihre Daten bleiben auf Ihrem Computer. Sicherung, Export und Wiederherstellung "
            "gehören dazu.",
        ),
    )
    for row in (cards[:2], cards[2:]):
        for column, (title, body) in zip(st.columns(2), row, strict=True):
            with column, st.container(border=True):
                st.markdown(f"**{title}**")
                st.markdown(body)
    st.markdown(
        "Vergessen, umzudrehen? Einträge lassen sich später **korrigieren, teilen und "
        "nachtragen**, und jede Änderung wird nachvollziehbar festgehalten."
    )

    st.markdown("### So geht es los – in vier Schritten")
    st.markdown(
        "1. **Würfel verbinden:** einmal suchen, einmal klicken.\n"
        "2. **Seiten zuordnen:** jeder der acht Seiten eine Tätigkeit geben.\n"
        "3. **Drehen und arbeiten:** die Zeit läuft von selbst.\n"
        "4. **Auswerten:** Übersicht, Zeitjournal und Statistik zeigen, was Sie geschafft haben."
    )
    st.caption(
        "Gut zu wissen: Ein Hintergrundprogramm (der *Agent*) erfasst die Zeit und hält die "
        "Bluetooth-Verbindung. Dieses Fenster ist nur die Anzeige und darf jederzeit geschlossen "
        "werden. OctaLedger ist noch nicht mit allen Würfelmodellen erprobt; prüfen Sie bei der "
        "ersten Nutzung, ob jede Seite die richtige Tätigkeit startet."
    )


def _next_step_banner(state: SetupState) -> None:
    """A clear "what next" box derived from the real setup state."""
    with st.container(border=True, key="start_next"):
        if state.next_step == "connect":
            st.markdown(
                "**Nächster Schritt: Ihren Würfel verbinden.** Das dauert etwa eine Minute."
            )
            st.button(
                "Jetzt einrichten",
                key="start_go_setup",
                on_click=_open_section,
                args=("Einrichten",),
                type="primary",
                help="Öffnet die geführte Einrichtung.",
            )
        elif state.next_step == "faces":
            st.markdown(
                f"**Nächster Schritt: den Seiten Tätigkeiten geben.** {state.faces_done} von 8 "
                "Seiten sind eingerichtet."
            )
            st.button(
                "Seiten zuordnen",
                key="start_go_faces",
                on_click=go,
                args=("faces",),
                type="primary",
                help="Öffnet den Assistenten, der Ihnen live zeigt, welche Seite oben liegt.",
            )
        else:
            st.markdown("**Alles eingerichtet.** Drehen Sie den Würfel und die Zeit läuft.")
            first, second = st.columns(2)
            first.button(
                "Zur Übersicht",
                key="start_go_overview",
                on_click=go,
                args=("overview",),
                type="primary",
                width="stretch",
                help="Dort sehen Sie, was gerade läuft.",
            )
            second.button(
                "Würfel live ansehen",
                key="start_go_live",
                on_click=go,
                args=("live",),
                width="stretch",
                help="Sehen Sie in Echtzeit, was die Drehungen bewirken.",
            )


# ------------------------------------------------------------------------------- setup


def _setup(client: ApiClient, devices: list[dict[str, Any]], state: SetupState) -> None:
    st.markdown("## Einrichten in drei Schritten")
    done_connect = state.has_address
    done_faces = state.faces_done >= 8
    st.progress(
        (int(done_connect) + int(done_faces)) / 3,
        text=f"{int(done_connect) + int(done_faces)} von 3 Schritten erledigt",
    )

    with st.container(border=True, key="start_step_connect"):
        st.markdown(("✅ " if done_connect else "① ") + "**Würfel verbinden**")
        device = next((d for d in devices if d["is_active"]), devices[0]) if devices else None
        if done_connect and device:
            st.markdown(f"„{device['alias']}“ ist eingerichtet.")
            _connection_line(client, device["id"])
            with st.expander("Anderen Würfel suchen oder neu verbinden"):
                _search_and_connect(client, device)
        else:
            st.markdown(
                "**So geht es:** Halten Sie den Knopf am Würfel **gedrückt, bis er blau blinkt** "
                "(Kopplungsmodus). Klicken Sie dann sofort auf *Würfel suchen*. Der Würfel darf "
                "nicht gleichzeitig mit dem Handy oder in den Windows-Bluetooth-Einstellungen "
                "verbunden sein."
            )
            _search_and_connect(client, device)

    with st.container(border=True, key="start_step_faces"):
        st.markdown(("✅ " if done_faces else "② ") + "**Seiten zuordnen**")
        st.markdown(
            f"{state.faces_done} von 8 Seiten haben eine Tätigkeit. Der Assistent zeigt Ihnen "
            "live, welche Seite oben liegt, und Sie geben ihr einen Namen."
        )
        st.button(
            "Seiten zuordnen" if not done_faces else "Zuordnung ansehen oder ändern",
            key="start_open_faces",
            on_click=go,
            args=("faces",),
            type="primary" if done_connect and not done_faces else "secondary",
            disabled=not state.has_device,
            help="Öffnet den Assistenten für die acht Seiten."
            if state.has_device
            else "Verbinden Sie zuerst den Würfel (Schritt ①).",
        )

    with st.container(border=True, key="start_step_try"):
        st.markdown("③ **Ausprobieren**")
        st.markdown(
            "Drehen Sie den Würfel auf verschiedene Seiten und sehen Sie zu, wie die Software "
            "reagiert. Danach läuft alles von allein."
        )
        first, second = st.columns(2)
        first.button(
            "Würfel live ansehen",
            key="start_try_live",
            on_click=go,
            args=("live",),
            width="stretch",
            disabled=not state.has_device,
            help="Zeigt in Echtzeit, welche Seite oben liegt und was die Software daraus macht.",
        )
        second.button(
            "Zur Übersicht",
            key="start_try_overview",
            on_click=go,
            args=("overview",),
            width="stretch",
            help="Dort sehen Sie, was gerade läuft.",
        )


@st.fragment(run_every="2s")
def _connection_line(client: ApiClient, device_id: str) -> None:
    """Show the live connection state of the cube (refreshes while it connects)."""
    try:
        match = next(d for d in client.devices() if d["id"] == device_id)
    except (OctaLedgerError, StopIteration):
        return
    live = match["status"]
    state = live["state"] if live else None
    label = STATE_LABELS.get(state, state) if state else "Nicht verbunden"
    level = STATE_LEVEL.get(state, "warn") if state else "bad"
    st.markdown(status_dot(level, f"**{label}**"), unsafe_allow_html=True)
    if live and live.get("last_error"):
        st.caption(f"Letzte Meldung: {live['last_error']}")
    seen_key = f"start_ready_seen_{device_id}"
    if state == READY and not st.session_state.get(seen_key):
        st.session_state[seen_key] = True
        st.rerun()  # refresh the whole page once so the next steps unlock
    elif state != READY:
        st.session_state[seen_key] = False


def _search_and_connect(client: ApiClient, device: dict[str, Any] | None) -> None:
    """Search once, pick the cube, and register + assign + connect with a single click."""
    alias = DEFAULT_ALIAS
    if device is None:
        alias = st.text_input(
            "Name für Ihren Würfel",
            value=DEFAULT_ALIAS,
            key="start_alias",
            max_chars=100,
            help="Frei wählbar, nur zur Anzeige (z. B. „Büro“). Er lässt sich später ändern.",
        ).strip()
    if st.button(
        "Würfel suchen",
        key="start_scan",
        icon=":material/bluetooth_searching:",
        help="Sucht Bluetooth-Geräte in der Nähe (etwa 5 Sekunden). Es wird nichts verbunden.",
    ):
        with st.spinner("Suche läuft … der Würfel sollte jetzt blau blinken."):
            found, results = call(client.scan, 5.0)
        if found:
            st.session_state["start_scan_results"] = results
    results = st.session_state.get("start_scan_results")
    if results is None:
        return
    if not results:
        st.info(
            "Es wurden keine Bluetooth-Geräte gefunden. Ist Bluetooth am Computer eingeschaltet? "
            "Drehen Sie den Würfel einmal und suchen Sie erneut."
        )
        return
    results = sorted(results, key=lambda r: not r["looks_like_tracker"])  # stable: cubes first
    if not any(r["looks_like_tracker"] for r in results):
        st.warning(
            "Ein Timeular-Würfel wurde **nicht erkannt**. Blinkt er blau (Knopf lange drücken)? "
            "Ist er gerade mit Handy oder Windows-Einstellungen verbunden? Sie können es erneut "
            "versuchen oder unten ein anderes Gerät wählen."
        )
    pick = st.selectbox(
        "Gefundenes Gerät",
        results,
        key="start_pick",
        format_func=_pick_label,
        help="Würfel erscheinen oben und sind markiert. Wählen Sie den eigenen, falls mehrere "
        "Treffer angezeigt werden.",
    )
    if st.button(
        "Diesen Würfel verwenden und verbinden",
        key="start_use",
        type="primary",
        disabled=not alias,
        icon=":material/link:",
        help="Merkt sich den Würfel und baut die Verbindung auf. Dauert einige Sekunden.",
    ):
        _use(client, device, alias, pick["address"])


def _pick_label(result: dict[str, Any]) -> str:
    """Label of a scan result in the picker; probable cubes are marked."""
    marker = "  ← vermutlich Ihr Würfel" if result["looks_like_tracker"] else ""
    return f"{result['label']}{marker}"


def _use(client: ApiClient, device: dict[str, Any] | None, alias: str, address: str) -> None:
    """Register (if needed), store the address and connect; report in one sentence."""
    device_id = device["id"] if device else None
    if device_id is None:
        created, new_device = call(client.register_device, alias)
        if not created or new_device is None:
            return
        device_id = new_device["id"]
    if not call(client.set_device_address, device_id, address)[0]:
        return
    connected = call(client.connect_device, device_id)[0]
    st.session_state.pop("start_scan_results", None)
    st.session_state[FLASH_KEY] = (
        "Der Würfel ist gespeichert und die Verbindung wird aufgebaut. Das dauert einige Sekunden."
        if connected
        else "Der Würfel ist gespeichert, die Verbindung konnte aber noch nicht gestartet werden."
    )
    st.rerun()


# ------------------------------------------------------------------------------ manual


def _manual() -> None:
    st.markdown("## Handbuch")
    st.caption("Die vollständige Anleitung zum Nachlesen, ohne das Programm zu verlassen.")
    label = st.selectbox(
        "Dokument",
        [name for name, _ in DOCUMENTS],
        key="start_doc",
        help="Benutzerhandbuch: Bedienung und Begriffe. Installation und Betrieb: Einrichten, "
        "Starten, Sicherung, Fehlersuche.",
    )
    file_name = dict(DOCUMENTS)[label]
    text = load_document(file_name)
    if text is None:
        st.warning(
            "Die Dokumentation wurde nicht gefunden. Sie liegt im Projektordner unter "
            f"`docs/{file_name}`."
        )
        return
    intro, chapters = split_chapters(text)
    overview = "\n".join(line for line in intro.split("\n") if not line.startswith("# ")).strip()
    if overview:
        chapters = [Chapter("Überblick", overview), *chapters]
    term = st.text_input(
        "Im Dokument suchen",
        key=f"start_doc_search_{file_name}",
        placeholder="z. B. Sicherung, Pause, Bluetooth",
        help="Zeigt nur Kapitel, die den Suchbegriff enthalten.",
    )
    hits = search(chapters, term)
    if not hits:
        st.info(f"Kein Kapitel enthält „{term.strip()}“.")
        return
    chapter = st.selectbox(
        f"Kapitel ({len(hits)})",
        hits,
        key=f"start_chapter_{file_name}",
        format_func=lambda c: c.title,
        help="Wählen Sie das Kapitel, das Sie lesen möchten.",
    )
    st.markdown(f"### {chapter.title}")
    st.markdown(chapter.body)
