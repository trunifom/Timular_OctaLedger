"""Page "Würfel-Datenblatt": everything the cube reports, read-only, stored and exportable.

The page asks the agent to **read** every characteristic the connected cube offers and shows the
result as a table: service, characteristic, rights, raw value in hex, length and - only where the
meaning is known - a plain-language reading. Unknown characteristics keep their raw bytes without
an invented meaning; characteristics that cannot be read are listed and **not touched**. Nothing
is ever written to the cube.

A second section records the accelerometer characteristic for a few seconds (raw bytes only, the
format is not confirmed by the sources). Every read-out is stored (the newest twenty per cube) and
can be exported as JSON or CSV.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from typing import Any, Final

import streamlit as st

from octaledger.dashboard.identity import banner, selected_cube
from octaledger.dashboard.nav import go
from octaledger.dashboard.ui import call, format_local, page_help
from octaledger.dashboard_client.client import ApiClient

SHOWN_KEY: Final = "datasheet_shown_"
_FORMULA_START: Final = ("=", "+", "-", "@", "\t", "\r")
INTERVALS: Final = {200: "0,2 s", 500: "0,5 s", 1000: "1 s", 2000: "2 s"}
KIND_TEXT: Final = {"datasheet": "Datenblatt", "accelerometer": "Beschleunigungs-Aufzeichnung"}


def safe_cell(value: object) -> str:
    """Text for a CSV cell with spreadsheet formulas neutralised (values come from the cube)."""
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def sheet_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """The table rows of a read-out (words come from the API)."""
    short = [
        {
            "Dienst": f"{r['service_name']} ({r['service_short']})",
            "Characteristic": f"{r['name']} ({r['short']})",
            "Rechte": ", ".join(r["properties"]),
            "Wert (hex)": r["raw_hex"] or "",
            "Länge": r["length"],
            "Deutung": r["meaning"] or "",
            "Hinweis": r["error"]
            or ("" if "read" in r["properties"] else "nicht lesbar, nicht angefasst"),
        }
        for r in snapshot["readings"]
    ]
    return short


def sample_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """The table rows of an accelerometer recording (time offset, raw bytes, length)."""
    step = int(snapshot.get("interval_ms") or 0)
    return [
        {
            "Nr.": index + 1,
            "Zeit seit Beginn (ms)": index * step,
            "Rohwert (hex)": r["raw_hex"] or "",
            "Länge (Byte)": r["length"],
        }
        for index, r in enumerate(snapshot["readings"])
    ]


def to_csv(rows: list[dict[str, Any]]) -> str:
    """CSV text (UTF-8 with BOM for Excel, formulas neutralised)."""
    if not rows:
        return ""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(list(rows[0]))
    for row in rows:
        writer.writerow(["" if v is None else safe_cell(v) for v in row.values()])
    return "﻿" + out.getvalue()


def render(client: ApiClient, tz: str) -> None:
    """Render the data sheet page."""
    st.header("Würfel-Datenblatt")
    page_help(
        "So funktioniert das Datenblatt",
        "Hier sehen Sie **alles, was der Würfel über Bluetooth meldet**.\n\n"
        "- **Auslesen:** OctaLedger **liest** jede Angabe, die der Würfel zum Lesen anbietet "
        "(Modell, Firmware, Seriennummer, Batterie, Lage ...). Es wird **nichts geschrieben** und "
        "nichts am Würfel verändert.\n"
        "- **Deutung nur, wo sie bekannt ist:** Bekannte Angaben stehen in Klartext. Alles andere "
        "zeigt die **Rohdaten** (Hexwerte), **ohne erfundene Bedeutung**. Nicht lesbare Angaben "
        "stehen in der Liste und werden **nicht angefasst**.\n"
        "- **Voraussetzung:** Der Würfel muss verbunden und bereit sein.\n"
        "- **Aufzeichnung:** Für wenige Sekunden werden die Rohdaten des Beschleunigungssensors "
        "mitgeschrieben. Das Format ist nicht bestätigt, deshalb gibt es nur Rohwerte.\n"
        "- Jedes Auslesen wird gespeichert (die letzten 20 je Würfel) und lässt sich als JSON "
        "oder CSV speichern.",
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
            key="datasheet_to_start",
            on_click=go,
            args=("start",),
            type="primary",
            help="Öffnet die Startseite mit der geführten Einrichtung.",
        )
        return
    device = selected_cube(devices) or devices[0]
    banner(device, key="datasheet_banner", action="auslesen")
    did = device["id"]
    ready = bool(device["status"]) and device["status"]["state"] == "ready"
    if not ready:
        st.warning(
            "Der Würfel ist **nicht verbunden**. Zum Auslesen muss er bereit sein; gespeicherte "
            "Auslesungen können Sie trotzdem ansehen.",
            icon=":material/bluetooth_disabled:",
        )
    _take(client, did, ready)
    _record(client, did, ready)
    _stored(client, device, tz)


def _take(client: ApiClient, did: str, ready: bool) -> None:
    """The button that reads the data sheet."""
    st.subheader("Datenblatt auslesen")
    if st.button(
        "Jetzt auslesen",
        key="datasheet_take",
        type="primary",
        icon=":material/download:",
        disabled=not ready,
        help="Liest alle lesbaren Angaben des Würfels (nur lesen, nichts schreiben) und speichert "
        "das Ergebnis. Dauert einige Sekunden.",
    ):
        with st.spinner("Der Würfel wird ausgelesen …"):
            done, snapshot = call(client.read_out, did, "datasheet")
        if done and snapshot:
            st.session_state[SHOWN_KEY + did] = snapshot["id"]
            st.rerun()


def _record(client: ApiClient, did: str, ready: bool) -> None:
    """The accelerometer recording."""
    with st.expander("Beschleunigungssensor aufzeichnen (Rohdaten)", key="datasheet_record_box"):
        st.caption(
            "Schreibt für einige Sekunden die Rohdaten des Beschleunigungssensors mit. **Bewegen "
            "Sie den Würfel währenddessen.** Es werden nur Rohwerte gespeichert: Das Datenformat "
            "ist nicht bestätigt, deshalb deutet OctaLedger sie nicht."
        )
        left, right = st.columns(2)
        seconds = left.slider(
            "Dauer in Sekunden",
            5,
            30,
            10,
            key="datasheet_seconds",
            help="So lange wird aufgezeichnet (5 bis 30 Sekunden).",
        )
        interval = right.select_slider(
            "Abstand zwischen zwei Messungen",
            options=list(INTERVALS),
            value=500,
            format_func=INTERVALS.__getitem__,
            key="datasheet_interval",
            help="Wie oft gemessen wird. Kürzere Abstände ergeben mehr Daten.",
        )
        if st.button(
            "Aufzeichnung starten",
            key="datasheet_record",
            icon=":material/fiber_manual_record:",
            disabled=not ready,
            help="Startet die Aufzeichnung. Die Seite wartet, bis sie fertig ist.",
        ):
            with st.spinner(f"Es wird {seconds} Sekunden aufgezeichnet – bewegen Sie den Würfel …"):
                done, snapshot = call(client.read_out, did, "accelerometer", seconds, interval)
            if done and snapshot:
                st.session_state[SHOWN_KEY + did] = snapshot["id"]
                st.rerun()


def _stored(client: ApiClient, device: dict[str, Any], tz: str) -> None:
    """The stored read-outs: choose one, see it, export it, delete it."""
    did = device["id"]
    ok, snapshots = call(client.snapshots, did)
    if not ok or snapshots is None:
        return
    st.subheader("Gespeicherte Auslesungen")
    if not snapshots:
        st.info(
            "Noch nichts ausgelesen. Drücken Sie oben **Jetzt auslesen**, sobald der Würfel "
            "verbunden ist."
        )
        return
    by_id = {s["id"]: s for s in snapshots}
    wanted = st.session_state.get(SHOWN_KEY + did)
    if wanted not in by_id:
        wanted = snapshots[0]["id"]
    chosen = st.selectbox(
        "Auslesung",
        list(by_id),
        index=list(by_id).index(wanted),
        format_func=lambda i: (
            f"{format_local(by_id[i]['taken_at'], tz)} · {KIND_TEXT.get(by_id[i]['kind'], '')} "
            f"({by_id[i]['count']})"
        ),
        key=f"datasheet_choice_{did}",
        help="Welche gespeicherte Auslesung Sie ansehen. Die neueste steht oben.",
    )
    ok, snapshot = call(client.snapshot, chosen)
    if not ok or snapshot is None:
        return
    if snapshot["kind"] == "accelerometer":
        _show_recording(snapshot)
    else:
        rows = sheet_rows(snapshot)
        st.dataframe(rows, hide_index=True, width="stretch")
        unread = sum(1 for r in snapshot["readings"] if r["raw_hex"] is None)
        st.caption(
            f"{len(rows)} Angaben, davon {len(rows) - unread} gelesen. Rohwerte sind Hexzahlen; "
            "eine Deutung gibt es nur, wo die Bedeutung bekannt ist."
        )
    _export(
        snapshot, sheet_rows(snapshot) if snapshot["kind"] == "datasheet" else sample_rows(snapshot)
    )
    if st.button(
        "Diese Auslesung löschen",
        key=f"datasheet_delete_{chosen}",
        icon=":material/delete:",
        help="Löscht nur diese gespeicherte Auslesung, nichts am Würfel.",
    ):
        if call(client.delete_snapshot, chosen)[0]:
            st.session_state.pop(SHOWN_KEY + did, None)
            st.rerun()


def _show_recording(snapshot: dict[str, Any]) -> None:
    """Summary and table of an accelerometer recording (raw values only)."""
    rows = sample_rows(snapshot)
    lengths = Counter(r["length"] for r in snapshot["readings"])
    summary = ", ".join(f"{n}× {length} Byte" for length, n in sorted(lengths.items()))
    st.markdown(f"**{len(rows)} Messungen** ({summary}).")
    distinct = len({r["raw_hex"] for r in snapshot["readings"]})
    st.caption(
        f"{distinct} verschiedene Werte. Nur Rohdaten: Das Format ist nicht bestätigt. Bewegt sich "
        "der Würfel, sollten sich die Werte ändern; bleiben alle gleich, liefert dieser Anschluss "
        "keine Bewegungsdaten."
    )
    st.dataframe(rows, hide_index=True, width="stretch")


def _export(snapshot: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Download buttons (JSON and CSV) for the shown read-out."""
    left, right = st.columns(2)
    stamp = snapshot["taken_at"][:19].replace(":", "-")
    left.download_button(
        "Als JSON speichern",
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        file_name=f"wuerfel-{snapshot['kind']}-{stamp}.json",
        mime="application/json",
        key=f"datasheet_json_{snapshot['id']}",
        icon=":material/data_object:",
        width="stretch",
        help="Speichert die Auslesung mit allen Rohwerten als JSON-Datei.",
    )
    right.download_button(
        "Als CSV speichern",
        to_csv(rows),
        file_name=f"wuerfel-{snapshot['kind']}-{stamp}.csv",
        mime="text/csv",
        key=f"datasheet_csv_{snapshot['id']}",
        icon=":material/table:",
        width="stretch",
        help="Speichert die Tabelle als CSV-Datei (für Excel; Formeln werden entschärft).",
    )
