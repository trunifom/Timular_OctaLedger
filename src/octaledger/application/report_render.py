"""Printable reports: a neutral report model with an HTML and an optional PDF rendering.

The model (:class:`ReportDocument`) is built from the same numbers as the statistics page
(``Report``), so the sums always agree. Two renderings:

* **HTML** (no extra package): a self-contained, print-optimised page without scripts. Open it
  in the browser and print or "save as PDF" (Ctrl+P). All user text is escaped.
* **PDF** (optional extra ``pdf``, ``fpdf2``, **LGPL-3.0**, loaded only when used): a simple
  table report with the standard Helvetica font. Standard fonts only know Latin-1, so a few
  characters (typographic quotes, the euro sign, dashes) are replaced; names with characters
  outside that range are shown with ``?``.

Nothing is invented: the header lines (name, organisation) come from the user's settings and
stay empty otherwise; uncertain time is stated openly.
"""

from __future__ import annotations

import html
import importlib.util
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from octaledger.application.reporting_service import Balance, Report, Share
from octaledger.core.errors import ConfigurationError

#: Replacements for characters the standard PDF fonts (Latin-1) cannot draw.
_PDF_REPLACEMENTS = {
    "„": '"',
    "“": '"',
    "”": '"',
    "‚": "'",
    "‘": "'",
    "’": "'",
    "–": "-",
    "—": "-",
    "€": "EUR",
    "…": "...",
}


def pdf_available() -> bool:
    """Whether the optional PDF package is installed."""
    return importlib.util.find_spec("fpdf") is not None


@dataclass(frozen=True, slots=True)
class ReportRow:
    """One line of a table: a name with its time."""

    name: str
    duration: timedelta
    uncertain: timedelta
    share_percent: int


@dataclass(frozen=True, slots=True)
class ReportDocument:
    """Everything a rendering needs (already formatted for the reader)."""

    title: str
    period: str
    author: str
    organization: str
    generated: str
    personal_time: timedelta
    uncertain_time: timedelta
    includes_running: bool
    by_activity: tuple[ReportRow, ...]
    by_project: tuple[ReportRow, ...]
    days: tuple[tuple[str, timedelta], ...]
    target: timedelta | None
    difference: timedelta | None


def hm(duration: timedelta) -> str:
    """``timedelta(minutes=90)`` -> ``1:30`` (negative values keep their sign)."""
    total = int(duration.total_seconds())
    sign = "-" if total < 0 else ""
    hours, rest = divmod(abs(total), 3600)
    return f"{sign}{hours}:{rest // 60:02d}"


def _rows(shares: tuple[Share, ...]) -> tuple[ReportRow, ...]:
    return tuple(
        ReportRow(s.name, s.duration, s.uncertain, round(s.fraction * 100)) for s in shares
    )


def build_document(
    report: Report,
    tz: ZoneInfo,
    *,
    first: date,
    last: date,
    author: str = "",
    organization: str = "",
    balance: Balance | None = None,
    now: datetime | None = None,
) -> ReportDocument:
    """Build the document from a report (and optionally the target/actual balance)."""
    stamp = (now or datetime.now(tz)).astimezone(tz)
    return ReportDocument(
        title="Zeitbericht",
        period=f"{first.strftime('%d.%m.%Y')} bis {last.strftime('%d.%m.%Y')} ({tz.key})",
        author=author,
        organization=organization,
        generated=stamp.strftime("%d.%m.%Y %H:%M"),
        personal_time=report.personal_time,
        uncertain_time=report.uncertain_time,
        includes_running=report.includes_running,
        by_activity=_rows(report.by_activity),
        by_project=_rows(report.by_project),
        days=tuple((d.day.strftime("%a %d.%m.%Y"), d.personal_time) for d in report.daily),
        target=balance.target if balance is not None and balance.has_schedule else None,
        difference=balance.difference if balance is not None and balance.has_schedule else None,
    )


# ------------------------------------------------------------------------------- HTML

_CSS = (
    "body{font-family:Arial,Helvetica,sans-serif;color:#111;margin:2rem auto;max-width:46rem;"
    "line-height:1.4}"
    "h1{font-size:1.5rem;margin:0 0 .25rem}h2{font-size:1.1rem;margin:1.6rem 0 .4rem}"
    ".meta{color:#444;font-size:.9rem}.total{font-size:1.2rem;margin:1rem 0}"
    "table{border-collapse:collapse;width:100%}"
    "th,td{border-bottom:1px solid #bbb;padding:.3rem .5rem;text-align:left}"
    "th{background:#f0f0f0}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}"
    ".note{border:1px solid #c80;background:#fff7e6;padding:.5rem .75rem;margin:.75rem 0;"
    "font-size:.9rem}"
    "@media print{body{margin:0;max-width:none}h2{break-after:avoid}"
    "table{break-inside:auto}tr{break-inside:avoid}}"
)


def _table(title: str, rows: tuple[ReportRow, ...], head: str) -> str:
    if not rows:
        return ""
    body = "".join(
        f"<tr><td>{html.escape(r.name)}</td><td class='n'>{hm(r.duration)}</td>"
        f"<td class='n'>{r.share_percent} %</td></tr>"
        for r in rows
    )
    return (
        f"<h2>{html.escape(title)}</h2><table><tr><th>{html.escape(head)}</th>"
        f"<th class='n'>Zeit (h:mm)</th><th class='n'>Anteil</th></tr>{body}</table>"
    )


def render_html(doc: ReportDocument) -> str:
    """Render a complete, script-free HTML page (all text is escaped)."""
    meta = [doc.period]
    if doc.author:
        meta.append(f"Name: {doc.author}")
    if doc.organization:
        meta.append(doc.organization)
    meta.append(f"erstellt am {doc.generated}")
    parts = [
        "<!doctype html><html lang='de'><head><meta charset='utf-8'>",
        f"<title>{html.escape(doc.title)}</title><style>{_CSS}</style></head><body>",
        f"<h1>{html.escape(doc.title)}</h1>",
        f"<div class='meta'>{html.escape(' · '.join(meta))}</div>",
        f"<div class='total'><b>Persönliche Arbeitszeit: {hm(doc.personal_time)} h</b></div>",
    ]
    if doc.target is not None and doc.difference is not None:
        parts.append(
            f"<div>Soll: {hm(doc.target)} h · Saldo: {'+' if doc.difference > timedelta(0) else ''}"
            f"{hm(doc.difference)} h</div>"
        )
    if doc.uncertain_time > timedelta(0):
        parts.append(
            f"<div class='note'>Davon <b>{hm(doc.uncertain_time)} h unsicher</b> (noch nicht "
            "bestätigt, z. B. nach einem Verbindungsabbruch). Die Summe gilt dafür nur mit "
            "Vorbehalt.</div>"
        )
    if doc.includes_running:
        parts.append(
            "<div class='note'>Eine laufende Zeit ist bis zur Erstellung eingerechnet.</div>"
        )
    parts.append(_table("Nach Tätigkeit", doc.by_activity, "Tätigkeit"))
    parts.append(_table("Nach Projekt", doc.by_project, "Projekt"))
    if doc.days:
        rows = "".join(
            f"<tr><td>{html.escape(day)}</td><td class='n'>{hm(total)}</td></tr>"
            for day, total in doc.days
        )
        parts.append(
            f"<h2>Nach Tag</h2><table><tr><th>Tag</th><th class='n'>Zeit (h:mm)</th></tr>"
            f"{rows}</table>"
        )
    parts.append("</body></html>")
    return "".join(parts)


# -------------------------------------------------------------------------------- PDF


def _latin1(text: str) -> str:
    """Make ``text`` drawable with the standard PDF fonts."""
    for old, new in _PDF_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def render_pdf(doc: ReportDocument) -> bytes:
    """Render a simple PDF (optional extra ``pdf``).

    Raises:
        ConfigurationError: If the optional package is not installed.
    """
    if not pdf_available():
        raise ConfigurationError(
            "fpdf2 is not installed",
            user_message='Für PDF fehlt das Zusatzpaket: pip install -e ".[pdf]". '
            "Alternativ den HTML-Bericht öffnen und mit Strg+P drucken.",
        )
    from fpdf import FPDF  # type: ignore[import-not-found,unused-ignore]

    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _latin1(doc.title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    meta = [doc.period]
    if doc.author:
        meta.append(f"Name: {doc.author}")
    if doc.organization:
        meta.append(doc.organization)
    meta.append(f"erstellt am {doc.generated}")
    pdf.multi_cell(0, 5, _latin1(" | ".join(meta)), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(
        0, 8, f"Persönliche Arbeitszeit: {hm(doc.personal_time)} h", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.set_font("Helvetica", "", 10)
    if doc.target is not None and doc.difference is not None:
        pdf.cell(
            0,
            6,
            f"Soll: {hm(doc.target)} h   Saldo: {hm(doc.difference)} h",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    if doc.uncertain_time > timedelta(0):
        pdf.multi_cell(
            0,
            5,
            _latin1(
                f"Davon {hm(doc.uncertain_time)} h unsicher (noch nicht bestätigt); "
                "die Summe gilt dafür nur mit Vorbehalt."
            ),
            new_x="LMARGIN",
            new_y="NEXT",
        )

    def table(title: str, rows: list[tuple[str, str, str]]) -> None:
        """Draw a titled three-column table (name, time, share)."""
        if not rows:
            return
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _latin1(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for name, duration, share in rows:
            pdf.cell(110, 6, _latin1(name)[:60], border="B")
            pdf.cell(35, 6, duration, border="B", align="R")
            pdf.cell(35, 6, share, border="B", align="R", new_x="LMARGIN", new_y="NEXT")

    table(
        "Nach Tätigkeit",
        [(r.name, hm(r.duration), f"{r.share_percent} %") for r in doc.by_activity],
    )
    table(
        "Nach Projekt",
        [(r.name, hm(r.duration), f"{r.share_percent} %") for r in doc.by_project],
    )
    table("Nach Tag", [(day, hm(total), "") for day, total in doc.days])
    return bytes(pdf.output())
