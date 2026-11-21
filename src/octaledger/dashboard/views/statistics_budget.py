"""The "Projekte & Budget" tab: used time against budget, and amounts.

Shows projects that have a budget, an hourly rate or the billable flag (set on the page
"Tätigkeiten & Projekte"). The amount is **computed** from the rate and rounded to whole cents
here; the stored entries never contain money. Time counts all entries of the project so far
(a running entry up to now).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from octaledger.dashboard.ui import call, format_hm
from octaledger.dashboard_client.client import ApiClient


def money(cents: int | None) -> str:
    """``12345`` -> ``123.45`` (empty without a rate)."""
    return "–" if cents is None else f"{cents / 100:,.2f}".replace(",", "’")


def render(client: ApiClient, tz: str) -> None:
    """Render the tab."""
    st.markdown(
        "Zeit, Budget und Beträge je Projekt. Budget, Stundensatz und „abrechenbar“ legen Sie "
        "auf der Seite *Tätigkeiten & Projekte* beim jeweiligen Projekt fest."
    )
    ok, items = call(client.budgets)
    if not ok or items is None:
        return
    if not items:
        st.info(
            "Noch kein Projekt mit Budget oder Stundensatz. Tragen Sie beides bei einem Projekt "
            "auf der Seite *Tätigkeiten & Projekte* ein."
        )
        return
    for item in items:
        left, right = st.columns([3, 2], vertical_alignment="center")
        left.markdown(f"**{item['name']}**" + (" · abrechenbar" if item["billable"] else ""))
        used = format_hm(item["used_seconds"])
        if item["budget_minutes"]:
            right.caption(f"{used} von {format_hm(item['budget_minutes'] * 60)}")
            st.progress(
                min(1.0, item["fraction"] or 0.0),
                text=f"{round((item['fraction'] or 0) * 100)} % des Budgets",
            )
            if (item["fraction"] or 0) >= 1.0:
                st.warning(f"Das Budget von „{item['name']}“ ist aufgebraucht.")
        else:
            right.caption(f"{used} (kein Budget)")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Projekt": i["name"],
                    "Zeit": format_hm(i["used_seconds"]),
                    "Budget": format_hm(i["budget_minutes"] * 60) if i["budget_minutes"] else "–",
                    "Verbraucht": f"{round(i['fraction'] * 100)} %"
                    if i["fraction"] is not None
                    else "–",
                    "Stundensatz": money(i["hourly_rate_cents"]),
                    "Betrag": money(i["amount_cents"]),
                    "Abrechenbar": "ja" if i["billable"] else "nein",
                }
                for i in items
            ]
        ),
        hide_index=True,
        width="stretch",
    )
