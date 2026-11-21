"""Data page: CSV export, JSON backup and a validated, confirmed restore."""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

import streamlit as st

from octaledger.dashboard.ui import call, from_local, page_help
from octaledger.dashboard.views import data_cleanup
from octaledger.dashboard_client.client import ApiClient

DELIMITERS = {";": "Semikolon (deutsches Excel)", ",": "Komma", "\t": "Tabulator"}
COUNT_LABELS = {
    "devices": "Geräte",
    "activities": "Tätigkeiten",
    "projects": "Projekte",
    "face_mappings": "Seitenzuordnungen",
    "raw_events": "Rohereignisse",
    "sessions": "Einträge",
    "corrections": "Korrekturen",
    "audit_log": "Protokolleinträge",
    "integrations": "Verbindungen",
    "face_actions": "Aktionen",
}


def render(client: ApiClient, tz: str) -> None:
    """Render the data page."""
    st.header("Daten")
    page_help(
        "So funktionieren Export, Sicherung und Wiederherstellung",
        "- **CSV-Export** für Excel/LibreOffice: Ihre Einträge so, wie sie nach Korrekturen "
        "gelten.\n"
        "- **Sicherung (JSON):** Alles in einer Datei mit Prüfsumme. Erstellen Sie regelmäßig "
        "eine und kopieren Sie sie auf einen **anderen Datenträger**.\n"
        "- **Wiederherstellen:** Die Datei wird zuerst **vollständig geprüft, ohne etwas zu "
        "ändern** (Vorschau). Erst nach Ihrer Bestätigung werden alle Daten ersetzt – vorher legt "
        "OctaLedger automatisch eine Kopie des aktuellen Stands an. Bei jedem Problem bleibt alles "
        "unverändert.\n"
        "- Testen Sie das Wiederherstellen einmal in Ruhe: Erst eine erfolgreich getestete "
        "Sicherung ist belastbar.\n"
        "- **Wiederherstellen** ist zugleich der **Import**: Sie können jede OctaLedger-Sicherung "
        "Sicherung einspielen, auch auf einem anderen Rechner.\n"
        "- **Löschen:** gezielt Einträge eines Zeitraums oder alles zurücksetzen. Vorher gibt es "
        "immer eine automatische Sicherung, die Ihr Rückgängig ist.",
    )
    export_tab, backup_tab, restore_tab, delete_tab = st.tabs(
        ["CSV-Export", "Sicherung", "Wiederherstellen", "Löschen"]
    )
    with export_tab:
        _export(client, tz)
    with backup_tab:
        _backup(client)
    with restore_tab:
        _restore(client)
    with delete_tab:
        data_cleanup.render(client, tz)


def _export(client: ApiClient, tz: str) -> None:
    everything = st.checkbox(
        "Alle Zeiten exportieren",
        value=True,
        key="export_all",
        help="Ohne Haken können Sie einen Zeitraum wählen.",
    )
    start = end = None
    if not everything:
        a, b = st.columns(2)
        first = a.date_input(
            "Von",
            date.today() - timedelta(days=29),
            key="export_from",
            format="DD.MM.YYYY",
            help="Erster Tag.",
        )
        last = b.date_input(
            "Bis (einschließlich)",
            date.today(),
            key="export_to",
            format="DD.MM.YYYY",
            help="Letzter Tag, einschließlich.",
        )
        start = from_local(first, time(0, 0), tz)
        end = from_local(last + timedelta(days=1), time(0, 0), tz)
    delimiter = st.selectbox(
        "Trennzeichen",
        list(DELIMITERS),
        key="export_delimiter",
        format_func=DELIMITERS.__getitem__,
        help="Deutsches Excel erwartet das Semikolon; für andere Programme eignet sich das Komma.",
    )
    st.caption(f"Zeiten erscheinen in Ihrer Zeitzone ({tz}) und zusätzlich in UTC.")
    if st.button(
        "📄 CSV erzeugen",
        key="btn_export",
        type="primary",
        help="Erzeugt die Datei, speichert sie im Ordner „exports“ und bietet den Download an.",
    ):
        ok, result = call(client.export_csv, tz, delimiter, start, end)
        if ok:
            st.session_state["_csv"] = result
    result = st.session_state.get("_csv")
    if result:
        st.success(
            f"{result['rows']} Zeile(n) exportiert ({result['size']} Bytes): {result['filename']}"
        )
        st.download_button(
            "⬇️ CSV herunterladen",
            ("﻿" + result["content"]).encode("utf-8"),
            file_name=result["filename"],
            mime="text/csv",
            key="download_csv",
            help="Lädt die Datei herunter (UTF-8 mit BOM, öffnet in Excel mit korrekten Umlauten).",
        )


def _backup(client: ApiClient) -> None:
    st.markdown(
        "Eine Sicherung enthält **alle** Daten: Geräte, Seitenzuordnungen, Tätigkeiten, Projekte, "
        "Einträge, Korrekturen, Rohereignisse und das Protokoll."
    )
    if st.button(
        "💾 Sicherung erstellen",
        key="btn_backup",
        type="primary",
        help="Erzeugt eine vollständige Sicherung (JSON mit Prüfsumme) im Ordner „backups“.",
    ):
        ok, result = call(client.create_backup)
        if ok:
            st.session_state["_backup"] = result
    result = st.session_state.get("_backup")
    if result:
        st.success(f"Sicherung erstellt: {result['filename']} ({result['records']} Datensätze)")
        st.download_button(
            "⬇️ Sicherung herunterladen",
            result["content"].encode("utf-8"),
            file_name=result["filename"],
            mime="application/json",
            key="download_backup",
            help="Speichern Sie die Datei zusätzlich auf einem anderen Datenträger.",
        )


def _restore(client: ApiClient) -> None:
    st.warning(
        "Beim Wiederherstellen werden **alle aktuellen Daten ersetzt**. Vorher wird automatisch "
        "eine "
        "Kopie des aktuellen Stands angelegt.",
        icon="⚠️",
    )
    uploaded = st.file_uploader(
        "Sicherungsdatei (.json)",
        type=["json"],
        key="restore_file",
        help="Eine mit OctaLedger erstellte Sicherung.",
    )
    content: str | None = None
    if uploaded is not None:
        try:
            content = uploaded.getvalue().decode("utf-8-sig")
        except UnicodeDecodeError:
            st.error("Die Datei ist keine gültige Textdatei (UTF-8).")
            return
    with st.expander("Alternativ: Inhalt einfügen"):
        pasted = st.text_area(
            "Inhalt der Sicherung",
            key="restore_text",
            height=120,
            help="Fügen Sie hier den kompletten Inhalt einer Sicherungsdatei ein.",
        )
        if pasted.strip():
            content = pasted
    if not content:
        st.info("Wählen Sie eine Sicherungsdatei, um sie zu prüfen.")
        return
    ok, preview = call(client.inspect_restore, content)
    if not ok or preview is None:
        return
    st.success("Die Datei ist gültig. Es wurde **noch nichts verändert**.")
    st.caption(
        f"Version {preview['schema_version']} · erstellt mit OctaLedger {preview['app_version']} · "
        f"Stand {preview['exported_at']}"
    )
    _counts(preview["counts"])
    sure = st.checkbox(
        "Ich habe verstanden: Alle aktuellen Daten werden durch diese Sicherung ersetzt.",
        key="restore_confirm",
        help="Pflichtbestätigung. Vorher wird automatisch eine Kopie des aktuellen Stands "
        "angelegt.",
    )
    if st.button(
        "♻️ Jetzt wiederherstellen",
        key="btn_restore",
        type="primary",
        disabled=not sure,
        help="Ersetzt alle Daten durch den Inhalt der Sicherung.",
    ):
        done, result = call(client.restore, content, True)
        if done and result:
            st.session_state.pop("_display", None)  # settings may differ after a restore
            st.success(
                "Wiederhergestellt. Der vorherige Stand liegt als "
                f"**{result['pre_restore_backup']}** im Ordner „backups“."
            )
            _counts(result["restored"])


def _counts(counts: dict[str, Any]) -> None:
    columns = st.columns(4)
    for index, (key, label) in enumerate(COUNT_LABELS.items()):
        columns[index % 4].metric(
            label, counts.get(key, 0), help=f"Anzahl {label} in der Sicherung."
        )
