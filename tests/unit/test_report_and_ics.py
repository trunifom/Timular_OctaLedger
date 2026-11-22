"""Printable report (HTML/PDF) and the calendar import (AP-42)."""

import base64
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from octaledger.application import report_render
from octaledger.application.ics_import import (
    MAX_BYTES,
    IcsEntry,
    IcsService,
    ics_available,
    parse_ics,
)
from octaledger.application.report_render import (
    build_document,
    pdf_available,
    render_html,
    render_pdf,
)
from octaledger.application.reporting_service import ReportFilter, ReportService
from octaledger.core.errors import (
    ConfigurationError,
    ConflictError,
    ImportDataError,
    NotFoundError,
    ValidationError,
)
from octaledger.domain.models import Activity, Project, Session, SessionSource
from octaledger.domain.time_rules import local_day_bounds
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

UTC = UTC
TZ = ZoneInfo("Europe/Zurich")
needs_ics = pytest.mark.skipif(not ics_available(), reason="optional ics packages not installed")
needs_pdf = pytest.mark.skipif(not pdf_available(), reason="optional pdf package not installed")


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.now = datetime(2026, 1, 9, 20, tzinfo=UTC)
        self.reports = ReportService(self.storage, clock=lambda: self.now)
        self.ics = IcsService(self.storage, clock=lambda: self.now)
        with self.storage.transaction() as repos:
            self.code = repos.activities.add(Activity(name="Entwicklung <b>")).id
            self.meeting = repos.activities.add(Activity(name="Sitzung")).id
            self.project = repos.projects.add(Project(name="Kunde „Ä“")).id

    def add(
        self, start: datetime, end: datetime, activity: str | None = None, **kw: object
    ) -> None:
        with self.storage.transaction() as repos:
            repos.sessions.add(
                Session(activity or self.code, start, end, source=SessionSource.MANUAL, **kw)  # type: ignore[arg-type]
            )

    def sessions(self) -> list[Session]:
        with self.storage.read() as repos:
            return repos.sessions.list_all()


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, minute, tzinfo=TZ).astimezone(UTC)


def document(env: Env, **kw: object):  # type: ignore[no-untyped-def]
    first, last = date(2026, 1, 5), date(2026, 1, 7)
    window = (local_day_bounds(first, TZ)[0], local_day_bounds(last, TZ)[1])
    report = env.reports.report(ReportFilter(*window), "Europe/Zurich")
    return build_document(report, TZ, first=first, last=last, now=env.now, **kw), report


# ------------------------------------------------------------------------ report


def test_the_report_shows_the_same_sums_as_the_statistics(env: Env) -> None:
    env.add(at(5, 8), at(5, 12))
    env.add(at(6, 9), at(6, 10, 30), env.meeting, project_id=env.project)
    doc, report = document(env)
    assert doc.personal_time == report.personal_time == timedelta(hours=5, minutes=30)
    assert [(r.name, report_render.hm(r.duration)) for r in doc.by_activity] == [
        ("Entwicklung <b>", "4:00"),
        ("Sitzung", "1:30"),
    ]
    assert sum(r.share_percent for r in doc.by_activity) in (99, 100, 101)
    page = render_html(doc)
    assert "Persönliche Arbeitszeit: 5:30 h" in page


def test_html_escapes_all_user_text_and_has_no_script(env: Env) -> None:
    env.add(at(5, 8), at(5, 9))
    doc, _ = document(env, author="<script>alert(1)</script>", organization='A & "B"')
    page = render_html(doc)
    assert "<script" not in page.lower() and "javascript:" not in page.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "A &amp; &quot;B&quot;" in page
    assert "Entwicklung &lt;b&gt;" in page and "Entwicklung <b>" not in page
    assert page.startswith("<!doctype html>") and "@media print" in page


def test_uncertain_and_running_time_is_stated_openly(env: Env) -> None:
    env.add(at(5, 8), at(5, 9), quality="uncertain")
    with env.storage.transaction() as repos:
        repos.sessions.add(Session(env.code, at(6, 8), None, source=SessionSource.MANUAL))
    env.now = at(6, 10)
    doc, _ = document(env)
    page = render_html(doc)
    assert "unsicher" in page and "laufende Zeit" in page


def test_header_lines_stay_empty_when_not_configured(env: Env) -> None:
    env.add(at(5, 8), at(5, 9))
    doc, _ = document(env)
    assert doc.author == "" and doc.organization == ""
    assert "Name:" not in render_html(doc)


def test_balance_is_included_only_with_a_schedule(env: Env) -> None:
    from octaledger.application.work_time_service import WorkTimeService

    env.add(at(5, 8), at(5, 17))
    first, last = date(2026, 1, 5), date(2026, 1, 5)
    plain = env.reports.balance(first, last, "Europe/Zurich")
    doc, _ = document(env, balance=plain)
    assert doc.target is None and "Soll:" not in render_html(doc)
    WorkTimeService(env.storage).set_schedule(date(2026, 1, 1), [480] * 5 + [0, 0])
    full = env.reports.balance(first, last, "Europe/Zurich")
    doc, _ = document(env, balance=full)
    assert doc.target == timedelta(hours=8) and "Soll: 8:00 h" in render_html(doc)


@needs_pdf
def test_pdf_is_a_real_pdf_with_umlauts_and_replaced_quotes(env: Env) -> None:
    env.add(at(5, 8), at(5, 12), env.meeting, project_id=env.project)
    doc, _ = document(env, author="Müller €")
    pdf = render_pdf(doc)
    assert pdf.startswith(b"%PDF") and len(pdf) > 500


def test_pdf_without_the_package_explains_what_to_do(
    monkeypatch: pytest.MonkeyPatch, env: Env
) -> None:
    monkeypatch.setattr(report_render, "pdf_available", lambda: False)
    doc, _ = document(env)
    with pytest.raises(ConfigurationError) as info:
        render_pdf(doc)
    assert "pip install" in info.value.user_message and "Strg+P" in info.value.user_message


def test_latin1_replacements_keep_text_drawable() -> None:
    assert report_render._latin1("„Zürich“ – 5 €…") == '"Zürich" - 5 EUR...'
    assert report_render._latin1("日本") == "??"


# --------------------------------------------------------------------------- ICS

CAL = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:1
DTSTAMP:20260101T000000Z
DTSTART;TZID=Europe/Zurich:20260105T090000
DTEND;TZID=Europe/Zurich:20260105T100000
SUMMARY:Planung
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTAMP:20260101T000000Z
DTSTART:20260106T080000Z
DTEND:20260106T090000Z
SUMMARY:Utc   Termin
END:VEVENT
BEGIN:VEVENT
UID:3
DTSTAMP:20260101T000000Z
DTSTART;VALUE=DATE:20260107
DTEND;VALUE=DATE:20260108
SUMMARY:Ganztags
END:VEVENT
BEGIN:VEVENT
UID:4
DTSTAMP:20260101T000000Z
DTSTART:20260105T140000
DTEND:20260105T150000
SUMMARY:Schwebend
END:VEVENT
BEGIN:VEVENT
UID:5
DTSTAMP:20260101T000000Z
DTSTART:20260105T160000Z
DTEND:20260105T170000Z
STATUS:CANCELLED
SUMMARY:Abgesagt
END:VEVENT
BEGIN:VEVENT
UID:6
DTSTAMP:20260101T000000Z
DTSTART:20260105T170000Z
DTEND:20260105T170000Z
SUMMARY:Ohne Dauer
END:VEVENT
BEGIN:VEVENT
UID:7
DTSTAMP:20260101T000000Z
DTSTART:20260105T180000Z
DTEND:20260108T180000Z
SUMMARY:Dreitaegig
END:VEVENT
BEGIN:VEVENT
UID:8
DTSTAMP:20260101T000000Z
DTSTART;TZID=Europe/Zurich:20260105T120000
DTEND;TZID=Europe/Zurich:20260105T123000
RRULE:FREQ=DAILY
SUMMARY:Daily
END:VEVENT
END:VCALENDAR
"""


@needs_ics
def test_parse_reads_zones_floating_time_and_skips_the_unsuitable() -> None:
    found, skipped = parse_ics(CAL, date(2026, 1, 5), date(2026, 1, 7), TZ)
    titles = [t for _s, _e, t in found]
    assert titles.count("Daily") == 3  # an endless rule is expanded only inside the window
    assert "Planung" in titles and "Utc Termin" in titles  # whitespace collapsed
    planning = next(f for f in found if f[2] == "Planung")
    assert planning[0] == at(5, 9) and planning[1] == at(5, 10)
    floating = next(f for f in found if f[2] == "Schwebend")
    assert floating[0] == at(5, 14)  # a floating time is the user's own clock
    assert skipped == {"ganztägig": 1, "abgesagt": 1, "ohne Dauer": 1, "länger als 24 Stunden": 1}
    assert found == sorted(found)


@needs_ics
@pytest.mark.parametrize(
    ("first", "last"),
    [(date(2026, 1, 5), date(2026, 4, 20)), (date(2026, 1, 9), date(2026, 1, 5))],
)
def test_the_window_is_limited_to_90_days(first: date, last: date) -> None:
    with pytest.raises(ValidationError):
        parse_ics(CAL, first, last, TZ)


@needs_ics
def test_size_limit_and_broken_files_are_clear_errors() -> None:
    with pytest.raises(ImportDataError, match="2 MiB|zu groß|larger"):
        parse_ics("x" * (MAX_BYTES + 1), date(2026, 1, 5), date(2026, 1, 6), TZ)
    with pytest.raises(ImportDataError):
        parse_ics("das ist keine Kalenderdatei", date(2026, 1, 5), date(2026, 1, 6), TZ)
    with pytest.raises(ImportDataError):
        parse_ics(b"\xff\xfe\x00BEGIN:VCALENDAR\n", date(2026, 1, 5), date(2026, 1, 6), TZ)


@needs_ics
def test_too_many_appointments_are_refused() -> None:
    body = "".join(
        f"BEGIN:VEVENT\nUID:e{i}\nDTSTAMP:20260101T000000Z\nDTSTART:20260105T080000Z\n"
        f"DTEND:20260105T090000Z\nSUMMARY:x\nEND:VEVENT\n"
        for i in range(1001)
    )
    text = f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:x\n{body}END:VCALENDAR\n"
    with pytest.raises(ValidationError):
        parse_ics(text, date(2026, 1, 5), date(2026, 1, 6), TZ)


def test_without_the_packages_the_import_explains_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("octaledger.application.ics_import.ics_available", lambda: False)
    with pytest.raises(ImportDataError) as info:
        parse_ics(CAL, date(2026, 1, 5), date(2026, 1, 6), TZ)
    assert "pip install" in info.value.user_message


@needs_ics
def test_preview_marks_overlaps_and_changes_nothing(env: Env) -> None:
    env.add(at(5, 9, 30), at(5, 10, 30))  # overlaps "Planung" (9-10)
    before = env.sessions()
    preview = env.ics.preview(CAL, date(2026, 1, 5), date(2026, 1, 5), TZ)
    by_title = {p.title: p for p in preview.proposals}
    assert by_title["Planung"].overlaps and not by_title["Schwebend"].overlaps
    assert env.sessions() == before


@needs_ics
def test_apply_books_only_the_confirmed_entries_with_the_chosen_activity(env: Env) -> None:
    created = env.ics.apply(
        [
            IcsEntry(at(5, 9), at(5, 10), env.meeting, env.project, "Planung"),
            IcsEntry(at(5, 14), at(5, 15), env.code),
        ]
    )
    assert len(created) == 2
    booked = env.sessions()
    assert {s.activity_id for s in booked} == {env.meeting, env.code}
    assert all(s.source is SessionSource.MANUAL for s in booked)
    with env.storage.read() as repos:
        assert "import_ics" in [a.action for a in repos.audit.list_all()]


def test_apply_is_all_or_nothing(env: Env) -> None:
    env.add(at(5, 9, 30), at(5, 10, 30))
    with pytest.raises(ConflictError):
        env.ics.apply(
            [
                IcsEntry(at(5, 14), at(5, 15), env.code),  # fine
                IcsEntry(at(5, 9), at(5, 10), env.code),  # overlaps the existing entry
            ]
        )
    assert len(env.sessions()) == 1  # the first one was rolled back too


def test_apply_validates_its_input(env: Env) -> None:
    with pytest.raises(ValidationError):
        env.ics.apply([])
    with pytest.raises(ValidationError):
        env.ics.apply([IcsEntry(at(5, 1), at(5, 2), env.code)] * 201)
    with pytest.raises(ValidationError):  # ends in the future
        env.ics.apply(
            [IcsEntry(env.now + timedelta(hours=2), env.now + timedelta(hours=3), env.code)]
        )
    with pytest.raises(NotFoundError):
        env.ics.apply([IcsEntry(at(5, 1), at(5, 2), "0" * 32)])
    assert env.sessions() == []


# ------------------------------------------------------------------------- API


def test_render_and_import_endpoints(tmp_path: Path) -> None:
    from tests.unit.test_api import Env as ApiEnv
    from tests.unit.test_api import FakeAgent, make_activity

    api = ApiEnv(tmp_path, FakeAgent())
    activity = make_activity(api)
    assert api.get("/system/capabilities").json().keys() >= {
        "tray",
        "toast",
        "pdf",
        "ics",
        "holidays",
    }
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(hours=3)
    api.post(
        "/sessions",
        {
            "activity_id": activity,
            "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(),
        },
    )
    day = now.date().isoformat()
    html_doc = api.post(
        "/reports/render", {"first": day, "last": day, "format": "html", "tz": "UTC"}
    ).json()
    assert html_doc["filename"].endswith(".html") and "Zeitbericht" in html_doc["content"]
    assert (
        api.post("/reports/render", {"first": day, "last": day, "format": "doc"}).status_code == 422
    )
    if pdf_available():
        pdf = api.post(
            "/reports/render", {"first": day, "last": day, "format": "pdf", "tz": "UTC"}
        ).json()
        assert base64.b64decode(pdf["content"]).startswith(b"%PDF")
    if ics_available():
        preview = api.post(
            "/import/ics/preview",
            {"content": CAL, "first": "2026-01-05", "last": "2026-01-05", "tz": "Europe/Zurich"},
        )
        assert preview.status_code == 200 and preview.json()["proposals"]
        bad = api.post(
            "/import/ics/preview",
            {"content": "Quatsch", "first": "2026-01-05", "last": "2026-01-05"},
        )
        assert bad.status_code == 422 or bad.status_code == 400
    applied = api.post(
        "/import/ics/apply",
        {
            "entries": [
                {
                    "start": "2026-01-05T08:00:00+00:00",
                    "end": "2026-01-05T09:00:00+00:00",
                    "activity_id": activity,
                    "note": "Planung",
                }
            ]
        },
    )
    assert applied.status_code == 201 and applied.json() == {"created": 1}
    assert api.post("/import/ics/apply", {"entries": []}).status_code == 422
