"""Calendar import on the journal page: appointments become proposals you confirm.

Choose an ``.ics`` file and a period (at most 90 days). OctaLedger **only reads** the file and
lists the appointments; for each one you choose an activity (and may skip it). Only the
confirmed appointments are booked, all together or not at all. Appointments that overlap an
existing entry are marked; booking them is refused. The file is never stored.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st

from octaledger.dashboard.ui import call, format_local
from octaledger.dashboard_client.client import ApiClient

PREVIEW_KEY = "_ics_preview"


def render(client: ApiClient, tz: str, activities: list[dict[str, Any]]) -> None:
    """Render the import section (folded away by default)."""
    with st.expander("Aus Kalender vorschlagen (.ics)", key="ics_import"):
        st.caption(
            "Liest Termine aus einer Kalenderdatei und zeigt sie als **Vorschläge**. Gebucht wird "
            "nur, was Sie bestätigen. Die Datei wird nicht gespeichert; ganztägige und "
            "abgesagte Termine werden übersprungen."
        )
        ok_c, caps = call(client.capabilities)
        if ok_c and caps and not caps.get("ics"):
            st.info(
                'Für den Kalender-Import fehlen Zusatzpakete: `pip install -e ".[ics]"`. '
                "Alles andere funktioniert unverändert."
            )
            return
        if not activities:
            st.info("Legen Sie zuerst eine Tätigkeit an (Seite *Tätigkeiten & Projekte*).")
            return
        upload = st.file_uploader(
            "Kalenderdatei",
            type=["ics"],
            key="ics_file",
            help="Eine .ics-Datei (höchstens 2 MiB), z. B. aus Outlook, Google oder Apple "
            "Kalender.",
        )
        today = date.today()
        a, b = st.columns(2)
        first = a.date_input(
            "Von",
            today - timedelta(days=6),
            key="ics_from",
            format="DD.MM.YYYY",
            help="Erster Tag (höchstens 90 Tage bis zum Ende).",
        )
        last = b.date_input(
            "Bis",
            today,
            key="ics_to",
            format="DD.MM.YYYY",
            help="Letzter Tag, einschließlich.",
        )
        if st.button(
            "Vorschläge lesen",
            key="ics_read",
            disabled=upload is None,
            icon=":material/event:",
            help="Liest die Datei und zeigt die Termine des Zeitraums. Es wird nichts gebucht.",
        ):
            text = upload.getvalue().decode("utf-8", errors="replace") if upload else ""
            ok, preview = call(client.ics_preview, text, first, last, tz)
            st.session_state[PREVIEW_KEY] = preview if ok else None
        preview = st.session_state.get(PREVIEW_KEY)
        if preview:
            _proposals(client, tz, activities, preview)


def _proposals(
    client: ApiClient, tz: str, activities: list[dict[str, Any]], preview: dict[str, Any]
) -> None:
    items = preview["proposals"]
    skipped = ", ".join(f"{n}× {reason}" for reason, n in preview["skipped"].items())
    if skipped:
        st.caption(f"Übersprungen: {skipped}.")
    if not items:
        st.info("Im Zeitraum gibt es keine passenden Termine.")
        return
    names = {a["id"]: a["name"] for a in activities}
    chosen: list[dict[str, Any]] = []
    for item in items:
        i = item["index"]
        take, pick, text = st.columns([1, 2, 5], vertical_alignment="center")
        use = take.checkbox(
            "Übernehmen",
            value=not item["overlaps"],
            disabled=item["overlaps"],
            key=f"ics_take_{i}",
            help="Nur angehakte Termine werden gebucht. Termine, die sich mit einem vorhandenen "
            "Eintrag überschneiden, können nicht übernommen werden.",
        )
        activity = pick.selectbox(
            "Tätigkeit",
            list(names),
            format_func=names.__getitem__,
            key=f"ics_activity_{i}",
            label_visibility="collapsed",
            help="Auf diese Tätigkeit wird der Termin gebucht.",
        )
        text.markdown(
            f"{format_local(item['start'], tz)} – {format_local(item['end'], tz)[-5:]} · "
            f"**{item['title']}**"
            + ("  \n:orange[überschneidet sich mit einem Eintrag]" if item["overlaps"] else "")
        )
        if use:
            chosen.append(
                {
                    "start": item["start"],
                    "end": item["end"],
                    "activity_id": activity,
                    "note": item["title"],
                }
            )
    if st.button(
        f"{len(chosen)} Termin(e) übernehmen",
        key="ics_apply",
        type="primary",
        disabled=not chosen,
        icon=":material/check:",
        help="Bucht die angehakten Termine mit der gewählten Tätigkeit, alle zusammen oder gar "
        "keinen. Jeder Termin wird als Eintrag von Hand gebucht und ist im Protokoll vermerkt.",
    ):
        ok, result = call(client.ics_apply, chosen)
        if ok and result:
            st.session_state.pop(PREVIEW_KEY, None)
            st.success(f"{result['created']} Eintrag/Einträge wurden gebucht.")
