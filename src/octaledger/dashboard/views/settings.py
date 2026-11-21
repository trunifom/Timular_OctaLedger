"""App settings page: how time is recorded, the time zone, the log. (Looks are on *Darstellung*.)

Layout rule (research, ``docs/GUI_KONZEPT.md``): the **basic settings** that nearly everyone may
want to change come first (time zone, debounce time); everything that is rarely needed sits in the
collapsed **Erweiterte Einstellungen**. Every value has a sensible default, is named in its help
text, and **Auf Voreinstellungen zurücksetzen** restores all of them in one step.

Saving is explicit (a form): the settings depend on each other and are validated together, so
nothing is applied half-way. Invalid values are refused with an explanation.
"""

from __future__ import annotations

from zoneinfo import available_timezones

import streamlit as st

from octaledger.core.settings import (
    LoggingSettings,
    NotificationSettings,
    Settings,
    TrackingSettings,
)
from octaledger.dashboard.ui import call, page_help
from octaledger.dashboard_client.client import ApiClient

BASELINE = {
    "observe_only": "Nur merken, nie automatisch starten (empfohlen)",
    "adopt_current": "Aktuelle Seite sofort als Start übernehmen",
}
DISCONNECT = {
    "grace_then_stop": "Weiterlaufen, nach einer Frist beenden und nachfragen (empfohlen)",
    "mark_uncertain": "Unbegrenzt weiterlaufen und als unsicher markieren",
    "stop_session": "Zeit beenden und als unsicher markieren",
}
NEUTRAL = {
    "observe_only": "Nur protokollieren (empfohlen)",
    "pause": "Als Pause behandeln (experimentell, nicht mit Hardware geprüft)",
}
LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_TRACKING = TrackingSettings()
DEFAULT_LOGGING = LoggingSettings()
DEFAULT_NOTIFICATIONS = NotificationSettings()
DEFAULT_TIMEZONE = Settings().display.timezone


def render(client: ApiClient, tz: str) -> None:
    """Render the app settings page."""
    st.header("App")
    page_help(
        "So funktionieren die App-Einstellungen",
        "Hier legen Sie fest, **wie OctaLedger Zeit erfasst**. Die Seite hat zwei Teile:\n\n"
        "- **Grundeinstellungen:** Zeitzone und Entprellung. Das genügt für den Alltag.\n"
        "- **Erweiterte Einstellungen** (eingeklappt): Verhalten beim ersten Verbinden, bei "
        "Verbindungsverlust und bei „neutral“, Protokollstufe. Die Voreinstellungen sind für die "
        "meisten Fälle richtig.\n\n"
        "Die **Zeitzone** gilt sofort. Entprellung, Verhalten und Protokollstufe liest der Agent "
        "beim **Start**: Nach dem Speichern bitte den Agenten neu starten. Ungültige Werte werden "
        "mit einer Erklärung abgelehnt; nichts wird halb gespeichert.\n\n"
        "Wo finde ich was? **Würfel** und ihre Seiten: *Würfel verwalten*. **Aussehen** "
        "(Hell/Dunkel, Schrift): *Darstellung*. **Tätigkeiten und Projekte**: "
        "*Tätigkeiten & Projekte*. **Smarthome**: *Smarthome & Verbindungen*. "
        "**Export und Sicherung**: *Daten*.",
    )
    ok, settings = call(client.get_settings)
    if not ok or settings is None:
        return
    display, tracking, logging_ = settings["display"], settings["tracking"], settings["logging"]
    notifications = settings["notifications"]
    zones = sorted(available_timezones())
    if display["timezone"] not in zones:
        zones.insert(0, display["timezone"])

    with st.form("settings_form"):
        st.subheader("Grundeinstellungen")
        timezone = st.selectbox(
            "Zeitzone",
            zones,
            index=zones.index(display["timezone"]),
            key="set_timezone",
            help="Alle Zeiten werden in dieser Zeitzone angezeigt, z. B. Europe/Zurich. "
            f"Gespeichert wird immer in UTC. Voreinstellung: {DEFAULT_TIMEZONE}.",
        )
        debounce = st.slider(
            "Entprellung (Millisekunden)",
            0,
            2000,
            int(tracking["debounce_ms"]),
            step=50,
            key="set_debounce",
            help="So lange muss eine Seite ruhig oben liegen, bevor sie zählt. Verhindert "
            f"Fehlwechsel beim Drehen. Voreinstellung: {DEFAULT_TRACKING.debounce_ms}.",
        )
        with st.expander("Erweiterte Einstellungen", expanded=False, key="set_advanced"):
            st.caption(
                "Meist können Sie alles hier unverändert lassen: Die Voreinstellungen passen für "
                "die üblichen Fälle."
            )
            baseline = st.selectbox(
                "Erste Seite nach dem Verbinden",
                list(BASELINE),
                key="set_baseline",
                index=list(BASELINE).index(tracking["baseline_policy"]),
                format_func=BASELINE.__getitem__,
                help="Was mit der ersten gemeldeten Seite nach dem Verbinden geschieht. "
                "Voreinstellung: nur merken – so startet kein ungewollter Zeitabschnitt.",
            )
            disconnect = st.selectbox(
                "Bei Verbindungsverlust",
                list(DISCONNECT),
                key="set_disconnect",
                index=list(DISCONNECT).index(tracking["disconnect_policy"]),
                format_func=DISCONNECT.__getitem__,
                help="Was mit der laufenden Zeit geschieht, wenn der Würfel die Verbindung "
                "verliert. Voreinstellung: weiterlaufen, nach einer Frist am Moment des Verlusts "
                "beenden und nachfragen (so wird keine Zeit erfunden).",
            )
            grace = st.number_input(
                "Frist bei Verbindungsverlust (Sekunden)",
                min_value=0,
                max_value=3600,
                value=int(tracking["disconnect_grace_seconds"]),
                step=30,
                key="set_grace",
                help="Gilt für „Weiterlaufen, nach einer Frist beenden“. So lange läuft die Zeit "
                "nach einem Verbindungsverlust weiter; kommt der Würfel nicht zurück, endet sie "
                "am Moment des Verlusts und Sie werden gefragt. 0 beendet sofort. "
                f"Voreinstellung: {DEFAULT_TRACKING.disconnect_grace_seconds} Sekunden.",
            )
            neutral = st.selectbox(
                "Neutralwert (Würfel auf keiner Seite)",
                list(NEUTRAL),
                key="set_neutral",
                index=list(NEUTRAL).index(tracking["neutral_policy"]),
                format_func=NEUTRAL.__getitem__,
                help="Die Pausenregel ist noch nicht mit echter Hardware geprüft. "
                "Voreinstellung: nur protokollieren.",
            )
            battery = st.number_input(
                "Batterie-Warnung (Prozent)",
                min_value=0,
                max_value=90,
                value=int(notifications["battery_warning_percent"]),
                step=5,
                key="set_battery",
                help="Einmal warnen, wenn die Batterie des Würfels unter diesen Wert fällt. 0 "
                "schaltet die Warnung aus. Gilt sofort. "
                f"Voreinstellung: {DEFAULT_NOTIFICATIONS.battery_warning_percent} %.",
            )
            level = st.selectbox(
                "Protokollstufe",
                LOG_LEVELS,
                key="set_log_level",
                index=LOG_LEVELS.index(logging_["level"]),
                help="INFO genügt im Alltag. DEBUG zeichnet zusätzlich alle Programmschritte auf "
                f"(für die Fehlersuche). Voreinstellung: {DEFAULT_LOGGING.level}.",
            )
        submitted = st.form_submit_button(
            "💾 Einstellungen speichern",
            type="primary",
            help="Speichert alle Einstellungen dieser Seite gemeinsam.",
        )

    if submitted:
        changes = {
            "display": {"timezone": timezone},
            "tracking": {
                "debounce_ms": debounce,
                "baseline_policy": baseline,
                "disconnect_policy": disconnect,
                "disconnect_grace_seconds": int(grace),
                "neutral_policy": neutral,
            },
            "logging": {"level": level},
            "notifications": {"battery_warning_percent": int(battery)},
        }
        saved, _ = call(client.update_settings, changes)
        if saved:
            st.session_state.setdefault("_display", {})["timezone"] = timezone
            needs_restart = (
                debounce != tracking["debounce_ms"]
                or baseline != tracking["baseline_policy"]
                or disconnect != tracking["disconnect_policy"]
                or grace != tracking["disconnect_grace_seconds"]
                or neutral != tracking["neutral_policy"]
                or level != logging_["level"]
            )
            st.success("Einstellungen gespeichert.")
            if needs_restart:
                st.info(
                    "Entprellung, Verhalten und Protokollstufe wirken nach einem **Neustart des "
                    "Agenten** (`octaledger agent`)."
                )

    _reset(client, display, tracking, logging_, notifications)
    with st.expander("Technische Angaben (nur lesen)", key="set_technical"):
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


def _reset(
    client: ApiClient,
    display: dict[str, str],
    tracking: dict[str, object],
    logging_: dict[str, object],
    notifications: dict[str, object],
) -> None:
    """The way back: every setting of this page to its default (looks are not touched)."""
    already_default = (
        display["timezone"] == DEFAULT_TIMEZONE
        and tracking["debounce_ms"] == DEFAULT_TRACKING.debounce_ms
        and tracking["baseline_policy"] == DEFAULT_TRACKING.baseline_policy.value
        and tracking["disconnect_policy"] == DEFAULT_TRACKING.disconnect_policy.value
        and tracking["disconnect_grace_seconds"] == DEFAULT_TRACKING.disconnect_grace_seconds
        and tracking["neutral_policy"] == DEFAULT_TRACKING.neutral_policy.value
        and logging_["level"] == DEFAULT_LOGGING.level
        and notifications["battery_warning_percent"]
        == DEFAULT_NOTIFICATIONS.battery_warning_percent
    )
    if st.button(
        "Auf Voreinstellungen zurücksetzen",
        key="set_reset",
        icon=":material/restart_alt:",
        disabled=already_default,
        help="Stellt Zeitzone, Entprellung, Verhalten und Protokollstufe auf die "
        "Voreinstellungen zurück. Hell/Dunkel und Schrift bleiben unberührt.",
    ):
        done = [
            call(client.reset_settings, "tracking")[0],
            call(client.reset_settings, "logging")[0],
            call(client.reset_settings, "notifications")[0],
            call(client.update_settings, {"display": {"timezone": DEFAULT_TIMEZONE}})[0],
        ]
        if all(done):
            st.session_state.setdefault("_display", {})["timezone"] = DEFAULT_TIMEZONE
            st.rerun()
