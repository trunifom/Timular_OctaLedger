"""Settings page: timezone, debouncing, baseline/disconnect/neutral policies and log level."""

from __future__ import annotations

from zoneinfo import available_timezones

import streamlit as st

from octaledger.dashboard.ui import call, page_help
from octaledger.dashboard_client.client import ApiClient

BASELINE = {
    "observe_only": "Nur merken, nie automatisch starten (empfohlen)",
    "adopt_current": "Aktuelle Seite sofort als Start übernehmen",
}
DISCONNECT = {
    "mark_uncertain": "Zeit als unsicher markieren (empfohlen)",
    "stop_session": "Zeit beenden und als unsicher markieren",
}
NEUTRAL = {
    "observe_only": "Nur protokollieren (empfohlen)",
    "pause": "Als Pause behandeln (experimentell, nicht mit Hardware geprüft)",
}
LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def render(client: ApiClient, tz: str) -> None:
    """Render the settings page."""
    st.header("Einstellungen")
    page_help(
        "So funktionieren die Einstellungen",
        "- **Zeitzone** gilt sofort für alle Anzeigen. Gespeichert wird intern immer in UTC.\n"
        "- **Entprellung**, **Verhalten** bei Neustart/Verbindungsverlust/Neutral und die "
        "**Protokollstufe** werden vom Agenten beim **Start** gelesen: Nach dem Speichern bitte "
        "den Agenten neu starten.\n"
        "- Hell/Dunkel und Schriftgröße stellen Sie in der Seitenleiste ein.\n"
        "- Ungültige Werte werden mit einer Erklärung abgelehnt; nichts wird halb gespeichert.",
    )
    ok, settings = call(client.get_settings)
    if not ok or settings is None:
        return
    display, tracking, logging_ = settings["display"], settings["tracking"], settings["logging"]
    zones = sorted(available_timezones())
    if display["timezone"] not in zones:
        zones.insert(0, display["timezone"])

    with st.form("settings_form"):
        st.subheader("Anzeige")
        timezone = st.selectbox(
            "Zeitzone",
            zones,
            index=zones.index(display["timezone"]),
            key="set_timezone",
            help="Alle Zeiten werden in dieser Zeitzone angezeigt, z. B. Europe/Zurich. "
            "Gespeichert wird immer in UTC.",
        )
        st.subheader("Erkennung der Würfelbewegung")
        debounce = st.slider(
            "Entprellung (Millisekunden)",
            0,
            2000,
            int(tracking["debounce_ms"]),
            step=50,
            key="set_debounce",
            help="So lange muss eine Seite ruhig oben liegen, bevor sie zählt. Verhindert "
            "Fehlwechsel beim Drehen. Empfohlen: 300.",
        )
        baseline = st.selectbox(
            "Erste Seite nach dem Verbinden",
            list(BASELINE),
            key="set_baseline",
            index=list(BASELINE).index(tracking["baseline_policy"]),
            format_func=BASELINE.__getitem__,
            help="Was mit der ersten gemeldeten Seite nach dem Verbinden geschieht. Empfohlen: "
            "nur merken – so startet kein ungewollter Zeitabschnitt.",
        )
        disconnect = st.selectbox(
            "Bei Verbindungsverlust",
            list(DISCONNECT),
            key="set_disconnect",
            index=list(DISCONNECT).index(tracking["disconnect_policy"]),
            format_func=DISCONNECT.__getitem__,
            help="Was mit der laufenden Zeit geschieht, wenn der Tracker die Verbindung verliert.",
        )
        neutral = st.selectbox(
            "Neutralwert (Würfel auf keiner Seite)",
            list(NEUTRAL),
            key="set_neutral",
            index=list(NEUTRAL).index(tracking["neutral_policy"]),
            format_func=NEUTRAL.__getitem__,
            help="Die Pausenregel ist noch nicht mit echter Hardware geprüft. Empfohlen: nur "
            "protokollieren.",
        )
        st.subheader("Protokoll")
        level = st.selectbox(
            "Protokollstufe",
            LOG_LEVELS,
            key="set_log_level",
            index=LOG_LEVELS.index(logging_["level"]),
            help="INFO genügt im Alltag. DEBUG zeichnet zusätzlich alle Programmschritte auf "
            "(für die Fehlersuche).",
        )
        submitted = st.form_submit_button("💾 Einstellungen speichern", type="primary")

    if submitted:
        changes = {
            "display": {"timezone": timezone},
            "tracking": {
                "debounce_ms": debounce,
                "baseline_policy": baseline,
                "disconnect_policy": disconnect,
                "neutral_policy": neutral,
            },
            "logging": {"level": level},
        }
        saved, _ = call(client.update_settings, changes)
        if saved:
            st.session_state.setdefault("_display", {})["timezone"] = timezone
            needs_restart = (
                debounce != tracking["debounce_ms"]
                or baseline != tracking["baseline_policy"]
                or disconnect != tracking["disconnect_policy"]
                or neutral != tracking["neutral_policy"]
                or level != logging_["level"]
            )
            st.success("Einstellungen gespeichert.")
            if needs_restart:
                st.info(
                    "Entprellung, Verhalten und Protokollstufe wirken nach einem **Neustart des "
                    "Agenten** (`octaledger agent`)."
                )

    with st.expander("Technische Angaben (nur lesen)"):
        agent = settings["agent"]
        st.markdown(
            f"- Schnittstelle: `{agent['host']}:{agent['port']}` (nur lokal erreichbar)\n"
            f"- Sprache: `{display['language']}`\n"
            f"- Modus: `{tracking['mode']}` (ein aktiver Tracker)"
        )
        st.caption(
            "Adresse und Port der Schnittstelle werden in der Datei settings.toml bzw. über "
            "Umgebungsvariablen geändert (siehe Installationsanleitung)."
        )
