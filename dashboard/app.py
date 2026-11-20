"""Honest status page for the scaffold; not a BLE dashboard yet."""

import streamlit as st

st.set_page_config(page_title="OctaLedger", layout="wide")
st.title("OctaLedger")
st.caption("Lokale Zeiterfassung für kompatible Timeular-/ZEI-Tracker")
st.warning("Entwicklungsgrundgerüst: Noch keine BLE-Verbindung oder Zeiterfassung.")
st.markdown(
    "### Geplante Funktionen\n"
    "- Zwei Tracker registrieren und Seiten kalibrieren\n"
    "- Aktivitäten und Projekte verwalten\n"
    "- Zeiten lokal speichern und korrigieren\n"
    "- Tages-/Wochenberichte und Diagramme\n"
    "- CSV-Export und JSON-Backup/Restore"
)
st.info("Agent und API sind noch nicht implementiert. Es werden keine Zeitdaten angezeigt.")
