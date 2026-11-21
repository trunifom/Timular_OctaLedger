"""The "Soll und Saldo" tab: target versus actual working time, schedule and absences.

Three parts, each explained on the page:

1. **Soll je Wochentag** – the target per weekday, valid from a date (a change, for example
   part-time, never alters earlier balances).
2. **Saldo** – per day: target, actual, difference and the running balance.
3. **Abwesenheiten** – vacation, sick days, own holidays (a whole day off has target 0).

Nothing here is legal advice; public holidays come from an optional offline package and can
always be overridden by an absence.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from octaledger.dashboard.ui import call, format_hm
from octaledger.dashboard_client.client import ApiClient
from octaledger.domain.schedule import WEEKDAY_NAMES

KINDS = {
    "vacation": "Ferien",
    "sick": "Krank",
    "holiday_custom": "Eigener Feiertag / halber Feiertag",
    "other": "Sonstiges",
}


def _signed(seconds: int) -> str:
    """``-5400`` -> ``-1:30`` (with an explicit plus sign for overtime)."""
    sign = "-" if seconds < 0 else "+" if seconds > 0 else ""
    return f"{sign}{format_hm(abs(seconds))}"


def render(client: ApiClient, tz: str) -> None:
    """Render the tab."""
    st.markdown(
        "Vergleich von **Soll** (Ihrer Arbeitszeit je Wochentag) und **Ist** (erfasste "
        "persönliche Zeit). Feiertage und Abwesenheiten setzen das Soll des Tages auf 0 "
        "(oder auf den eingetragenen Wert)."
    )
    ok, schedules = call(client.schedule)
    if not ok or schedules is None:
        return
    _schedule(client, schedules)
    _balance(client, tz, bool(schedules))
    _absences(client)


def _schedule(client: ApiClient, schedules: list[dict[str, Any]]) -> None:
    st.subheader("Soll je Wochentag")
    if schedules:
        current = schedules[-1]
        st.caption(
            "Gültig ab "
            + ", ".join(
                f"{date.fromisoformat(s['valid_from']).strftime('%d.%m.%Y')}" for s in schedules
            )
            + " (die jeweils letzte Version vor einem Tag gilt für diesen Tag)."
        )
        defaults = current["minutes"]
    else:
        st.info(
            "Noch kein Soll eingetragen. Tragen Sie unten Ihre tägliche Soll-Arbeitszeit ein, "
            "dann zeigt OctaLedger Ihren Saldo (Überstunden)."
        )
        defaults = [480, 480, 480, 480, 480, 0, 0]
    with st.expander("Soll bearbeiten", key="sched_edit", expanded=not schedules):
        valid_from = st.date_input(
            "Gültig ab",
            date.today().replace(day=1) if not schedules else date.today(),
            key="sched_from",
            format="DD.MM.YYYY",
            help="Ab diesem Tag gilt das neue Soll. Frühere Tage behalten ihr altes Soll, "
            "damit alte Salden sich nicht ändern.",
        )
        cols = st.columns(7)
        values = [
            cols[i].number_input(
                name[:2],
                min_value=0.0,
                max_value=24.0,
                value=defaults[i] / 60,
                step=0.25,
                key=f"sched_{i}",
                help=f"Soll am {name} in Stunden (0 = kein Arbeitstag). Voreinstellung: "
                f"{'8' if i < 5 else '0'} Stunden.",
            )
            for i, name in enumerate(WEEKDAY_NAMES)
        ]
        if st.button(
            "Soll speichern",
            key="sched_save",
            icon=":material/save:",
            help="Speichert das Soll ab dem gewählten Datum.",
        ):
            if call(client.set_schedule, valid_from, [round(v * 60) for v in values])[0]:
                st.rerun()
        if len(schedules) > 1 and st.button(
            "Neueste Version löschen",
            key="sched_delete",
            icon=":material/delete:",
            help="Entfernt die zuletzt gültig gewordene Version; spätere Tage nutzen dann die "
            "davor.",
        ):
            if call(client.delete_schedule, date.fromisoformat(schedules[-1]["valid_from"]))[0]:
                st.rerun()


def _balance(client: ApiClient, tz: str, has_schedule: bool) -> None:
    st.subheader("Saldo")
    today = date.today()
    a, b = st.columns(2)
    first = a.date_input(
        "Von",
        today - timedelta(days=today.weekday()),
        key="bal_from",
        format="DD.MM.YYYY",
        help="Erster Tag der Auswertung (Voreinstellung: Montag dieser Woche).",
    )
    last = b.date_input(
        "Bis",
        today,
        key="bal_to",
        format="DD.MM.YYYY",
        help="Letzter Tag der Auswertung (Voreinstellung: heute).",
    )
    if last < first:
        st.warning("Das Ende liegt vor dem Anfang.")
        return
    ok, result = call(client.balance, first, last, tz)
    if not ok or result is None:
        return
    if not has_schedule:
        st.caption(
            "Ohne eingetragenes Soll gilt das Soll als 0; der Saldo zeigt dann nur die Ist-Zeit."
        )
    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Soll", format_hm(result["target_seconds"]), help="Summe der Soll-Zeiten im Zeitraum."
    )
    m2.metric("Ist", format_hm(result["actual_seconds"]), help="Erfasste persönliche Zeit.")
    m3.metric(
        "Saldo",
        _signed(result["difference_seconds"]),
        help="Ist minus Soll. Positiv = Überstunden, negativ = Minusstunden.",
    )
    if result["includes_running"]:
        st.caption("Die laufende Zeit ist bis jetzt eingerechnet.")
    table = pd.DataFrame(
        [
            {
                "Tag": date.fromisoformat(d["day"]).strftime("%a %d.%m.%Y"),
                "Soll": format_hm(d["target_seconds"]),
                "Ist": format_hm(d["actual_seconds"]),
                "Differenz": _signed(d["difference_seconds"]),
                "Saldo": _signed(d["balance_seconds"]),
                "Hinweis": d["reason"],
            }
            for d in result["days"]
        ]
    )
    st.dataframe(table, hide_index=True, width="stretch")


def _absences(client: ApiClient) -> None:
    st.subheader("Abwesenheiten")
    st.caption(
        "Ferien, Krankheit oder ein eigener Feiertag. Ein ganzer freier Tag hat Soll 0; für "
        "einen halben Feiertag geben Sie das Soll des Tages an."
    )
    ok, items = call(client.absences)
    if not ok or items is None:
        return
    with st.expander("Abwesenheit eintragen", key="abs_new"):
        kind = st.selectbox(
            "Art",
            list(KINDS),
            format_func=KINDS.__getitem__,
            key="abs_kind",
            help="Der Grund der Abwesenheit.",
        )
        a, b = st.columns(2)
        start = a.date_input(
            "Erster Tag",
            date.today(),
            key="abs_start",
            format="DD.MM.YYYY",
            help="Erster freier Tag.",
        )
        end = b.date_input(
            "Letzter Tag",
            date.today(),
            key="abs_end",
            format="DD.MM.YYYY",
            help="Letzter freier Tag (derselbe Tag für einen einzelnen Tag).",
        )
        target = st.number_input(
            "Soll an diesen Tagen (Stunden)",
            min_value=0.0,
            max_value=24.0,
            value=0.0,
            step=0.25,
            key="abs_target",
            help="0 = ganzer Tag frei. Zum Beispiel 4 für einen halben Feiertag. "
            "Voreinstellung: 0.",
        )
        note = st.text_input(
            "Notiz (optional)",
            key="abs_note",
            max_chars=200,
            help="Eine kurze Erinnerung, z. B. „Skiferien“.",
        )
        if st.button(
            "Abwesenheit speichern",
            key="abs_save",
            icon=":material/add:",
            help="Trägt die Abwesenheit ein; das Soll dieser Tage ändert sich sofort.",
        ):
            if call(client.add_absence, start, end, kind, round(target * 60), note or None)[0]:
                st.rerun()
    if not items:
        st.info("Keine Abwesenheiten eingetragen.")
        return
    for item in reversed(items):
        left, right = st.columns([6, 2], vertical_alignment="center")
        left.markdown(
            f"**{KINDS[item['kind']]}** · {date.fromisoformat(item['start']).strftime('%d.%m.%Y')}"
            f" – {date.fromisoformat(item['end']).strftime('%d.%m.%Y')}"
            + (
                f" · Soll {format_hm((item['target_minutes'] or 0) * 60)}"
                if item["target_minutes"]
                else ""
            )
            + (f" · {item['note']}" if item["note"] else "")
        )
        if right.button(
            "Löschen",
            key=f"abs_del_{item['id']}",
            icon=":material/delete:",
            width="stretch",
            help="Entfernt diese Abwesenheit; das Soll dieser Tage gilt wieder normal.",
        ):
            if call(client.delete_absence, item["id"])[0]:
                st.rerun()
