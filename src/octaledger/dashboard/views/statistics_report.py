"""The "Bericht" tab: a printable report for a period (HTML, optionally PDF).

The report shows the same sums as the statistics page. The HTML version needs no extra
package: download it, open it and print it (Ctrl+P) or save it as PDF from the browser. A real
PDF file needs the optional package ``fpdf2`` (``pip install -e ".[pdf]"``).
"""

from __future__ import annotations

import base64
from datetime import date, timedelta

import streamlit as st

from octaledger.dashboard.ui import call
from octaledger.dashboard_client.client import ApiClient


def render(client: ApiClient, tz: str) -> None:
    """Render the tab."""
    st.markdown(
        "Ein Bericht für Kunden oder Arbeitgeber mit den **gleichen Summen** wie die Statistik. "
        "Name und Firma in der Kopfzeile stellen Sie unter *App* → *Bericht* ein (leer, wenn "
        "Sie nichts eintragen). Unsichere Zeiten werden im Bericht offen genannt."
    )
    today = date.today()
    a, b = st.columns(2)
    first = a.date_input(
        "Von",
        today - timedelta(days=today.weekday()),
        key="rep_from",
        format="DD.MM.YYYY",
        help="Erster Tag des Berichts (Voreinstellung: Montag dieser Woche).",
    )
    last = b.date_input(
        "Bis",
        today,
        key="rep_to",
        format="DD.MM.YYYY",
        help="Letzter Tag des Berichts, einschließlich.",
    )
    if last < first:
        st.warning("Das Ende liegt vor dem Anfang.")
        return
    ok_c, caps = call(client.capabilities)
    has_pdf = bool(ok_c and caps and caps.get("pdf"))
    ok, html_doc = call(client.render_report, first, last, "html", tz)
    if not ok or html_doc is None:
        return
    left, right = st.columns(2)
    left.download_button(
        "HTML-Bericht herunterladen",
        data=html_doc["content"],
        file_name=html_doc["filename"],
        mime="text/html",
        icon=":material/download:",
        key="rep_dl_html",
        width="stretch",
        help="Eine druckfertige Seite ohne Skripte. Öffnen Sie sie und drucken Sie mit Strg+P "
        "(dort auch „Als PDF speichern“).",
    )
    if has_pdf:
        ok_p, pdf = call(client.render_report, first, last, "pdf", tz)
        if ok_p and pdf is not None:
            right.download_button(
                "PDF herunterladen",
                data=base64.b64decode(pdf["content"]),
                file_name=pdf["filename"],
                mime="application/pdf",
                icon=":material/picture_as_pdf:",
                key="rep_dl_pdf",
                width="stretch",
                help="Ein einfaches PDF mit Tabellen (Standardschrift).",
            )
    else:
        right.button(
            "PDF herunterladen",
            disabled=True,
            icon=":material/picture_as_pdf:",
            key="rep_dl_pdf_off",
            width="stretch",
            help='Braucht das Zusatzpaket „pdf“: pip install -e ".[pdf]". Bis dahin: '
            "HTML-Bericht herunterladen und mit Strg+P als PDF speichern.",
        )
        st.caption('PDF braucht das Zusatzpaket „pdf“ (`pip install -e ".[pdf]"`).')
    st.markdown("**Vorschau**")
    st.iframe(html_doc["content"], height=520)  # replaces the deprecated components.html
