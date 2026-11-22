"""Showing the battery of a cube: always visible, always with text (AP-52).

The API delivers a ``battery`` object per cube (percent, stage, text, bar, whether the value is
live, the estimate). This module turns it into the same short line everywhere, for example
``✔ ▮▮▮▮▯ 62 % · gut`` or ``▲ ▮▯▯▯▯ 18 % · schwach · zuletzt gemessen``. The stage is always
written out, so the state is never conveyed by colour alone.
"""

from __future__ import annotations

import html
from typing import Any, Final

import streamlit as st

from octaledger.core.errors import OctaLedgerError
from octaledger.dashboard.ui import format_local
from octaledger.dashboard_client.client import ApiClient

_CSS: Final = {"ok": "ol-ok", "warn": "ol-warn", "bad": "ol-bad"}


def battery_html(battery: dict[str, Any] | None, *, tz: str | None = None) -> str:
    """The one-line description of a battery (HTML, escaped); a missing battery is explained."""
    if battery is None:
        return '<span class="ol-muted">Batterie: noch nicht gemeldet</span>'
    css = _CSS.get(str(battery["level"]), "ol-warn")
    old = ""
    if not battery["live"]:
        when = ""
        if tz and battery.get("measured_at"):
            when = f" ({html.escape(format_local(battery['measured_at'], tz))})"
        old = f" · zuletzt gemessen{when}"
    return (
        f'<span class="{css}">{html.escape(str(battery["icon"]))}</span> '
        f"Batterie {html.escape(str(battery['bar']))} <b>{int(battery['percent'])} %</b> · "
        f"{html.escape(str(battery['stage_text']))}{old}"
    )


def needs_attention(battery: dict[str, Any] | None) -> bool:
    """Whether the battery is weak or nearly empty (shown as a warning, not only as a line)."""
    return battery is not None and battery["stage"] in ("weak", "empty")


def warning_text(device: dict[str, Any]) -> str:
    """The sentence of the permanent warning for a weak battery."""
    battery = device["battery"]
    name = f"{device.get('badge', '')} {device['alias']}".strip()
    text = (
        f"**Die Batterie von {name} ist {battery['stage_text']} ({battery['percent']} %).** "
        "Tauschen Sie die Batterie bald, sonst reißt die Verbindung ab. "
    )
    return text + str(battery["estimate_text"]) + "."


def render_history(client: ApiClient, device: dict[str, Any], tz: str) -> None:
    """Chart of the stored course and the estimate (inside a panel of the device page)."""
    try:
        data = client.battery(device["id"], 90)
    except OctaLedgerError as exc:
        st.caption(f"Der Batterie-Verlauf konnte nicht geladen werden ({exc.code}).")
        return
    summary = data["summary"]
    st.markdown(battery_html(summary, tz=tz), unsafe_allow_html=True)
    if summary:
        st.caption(
            f"{summary['estimate_text'].capitalize()}. Der Prozentwert stammt vom Würfel selbst; "
            "die Schätzung ist eine Gerade durch den gespeicherten Verlauf, keine Zusage."
        )
    history = data["history"]
    if len(history) < 2:
        st.caption(
            "Der Verlauf füllt sich mit der Zeit: OctaLedger speichert den Wert, wenn er sich "
            "ändert, und mindestens alle 6 Stunden."
        )
        return
    st.line_chart(
        {"Batterie in %": [h["percent"] for h in history]},
        x_label="Messungen (älteste links)",
        y_label="Prozent",
        height=160,
    )
