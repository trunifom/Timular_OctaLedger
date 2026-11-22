"""Tab "Änderungsprotokoll": who changed what, when, why - with old and new value (AP-58).

The data comes from ``GET /entries/history`` (corrections of single entries and of bulk edits,
plus deletions). Times are shown in the user's timezone; ids were already turned into names by
the service. The table can be searched and narrowed to a kind of change.
"""

from __future__ import annotations

from typing import Any, Final

import pandas as pd
import streamlit as st

from octaledger.dashboard.ui import call, format_local
from octaledger.dashboard_client.client import ApiClient

FIELD_TEXT: Final = {
    "activity_id": "Tätigkeit",
    "project_id": "Projekt",
    "started_at": "Beginn",
    "ended_at": "Ende",
    "note": "Notiz",
    "quality": "Qualität",
    "delete": "Gelöscht",
    "bulk_edit": "Sammelbearbeitung",
    "set_session_tags": "Tags",
}
_TIME_FIELDS: Final = frozenset({"started_at", "ended_at"})


def history_rows(history: list[dict[str, Any]], tz: str) -> list[dict[str, Any]]:
    """The table rows of the change protocol (pure; times in the user's timezone)."""

    def value(row: dict[str, Any], key: str) -> str:
        """Old or new value as text (times in the user's timezone)."""
        text = row[key]
        if text is None:
            return "–" if row["kind"] == "Korrektur" else ""
        return format_local(text, tz) if row["field"] in _TIME_FIELDS else str(text)

    return [
        {
            "Zeit": format_local(h["at"], tz),
            "Art": h["kind"],
            "Was": FIELD_TEXT.get(h["field"], h["field"]),
            "Vorher": value(h, "old_value"),
            "Nachher": value(h, "new_value"),
            "Grund / Angabe": h["reason"],
            "Eintrag": (h["session_id"] or "")[:8],
            "Rev.": h["revision"],
        }
        for h in history
    ]


def render(client: ApiClient, tz: str) -> None:
    """Render the change protocol."""
    st.caption(
        "Hier steht jede Korrektur und jedes Löschen mit Zeit, altem und neuem Wert und Ihrem "
        "Grund. Nichts davon lässt sich hier ändern: Es ist das Protokoll."
    )
    left, right = st.columns([3, 1])
    needle = left.text_input(
        "Im Protokoll suchen",
        key="ent_hist_text",
        max_chars=200,
        help="Findet Zeilen, in denen dieses Wort vorkommt (Grund, Werte, Art).",
    )
    limit = right.selectbox(
        "Anzahl",
        [100, 300, 1000, 5000],
        index=1,
        key="ent_hist_limit",
        help="Wie viele der neuesten Zeilen geladen werden.",
    )
    kinds = st.multiselect(
        "Art",
        ["Korrektur", "Aktion"],
        key="ent_hist_kind",
        placeholder="Alle",
        help="Korrekturen ändern einen Eintrag; Aktionen sind z. B. Löschungen und "
        "Sammelbearbeitungen.",
    )
    ok, history = call(client.entry_history, None, int(limit))
    if not ok or history is None:
        return
    rows = history_rows(history, tz)
    if kinds:
        rows = [r for r in rows if r["Art"] in kinds]
    if needle.strip():
        words = needle.casefold().split()
        rows = [
            r for r in rows if all(w in " ".join(map(str, r.values())).casefold() for w in words)
        ]
    if not rows:
        st.info("Noch keine Änderungen im Protokoll." if not history else "Keine Zeile passt.")
        return
    st.caption(f"{len(rows)} Zeile(n), neueste zuerst.")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", key="ent_hist_table")
