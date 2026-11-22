"""Tags, note templates, budgets and hourly rates (AP-41)."""

import csv
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from octaledger.application.budget_watch import BudgetWatch
from octaledger.application.export_service import CSV_COLUMNS, ExportService
from octaledger.application.reporting_service import ReportFilter, ReportService
from octaledger.application.tag_service import TagService
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import ConflictError, NotFoundError, ValidationError
from octaledger.domain.models import Activity, Device, Project, Session, SessionSource
from octaledger.domain.tags import ProjectBilling, Tag, amount_cents, budget_fraction
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

UTC = UTC
T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
H = timedelta(hours=1)


# -------------------------------------------------------------------- pure rules


def test_amounts_are_rounded_only_when_computed() -> None:
    assert amount_cents(timedelta(minutes=90), 12000) == 18000
    assert amount_cents(timedelta(minutes=20), 10000) == 3333  # 33.33 rounded to cents
    assert amount_cents(timedelta(hours=1), None) is None
    assert amount_cents(timedelta(0), 5000) == 0


def test_budget_fraction() -> None:
    assert budget_fraction(timedelta(minutes=30), 60) == 0.5
    assert budget_fraction(timedelta(hours=2), 60) == 2.0
    assert budget_fraction(timedelta(hours=1), None) is None


@pytest.mark.parametrize(
    "bad", [{"name": ""}, {"name": "x" * 51}, {"name": "ok", "color": "red"}, {"name": "a\nb"}]
)
def test_invalid_tags_are_rejected(bad: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Tag(**{"color": "#112233", **bad})  # type: ignore[arg-type]


def test_billing_validation_and_emptiness() -> None:
    assert ProjectBilling("a" * 32).is_empty
    assert not ProjectBilling("a" * 32, billable=True).is_empty
    with pytest.raises(ValidationError):
        ProjectBilling("a" * 32, budget_minutes=0)
    with pytest.raises(ValidationError):
        ProjectBilling("a" * 32, hourly_rate_cents=-1)


# ---------------------------------------------------------------------- services


class Env:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.now = T0 + 10 * H
        self.tags = TagService(self.storage)
        self.reports = ReportService(self.storage, clock=lambda: self.now)
        self.tracking = TrackingService(self.storage, clock=lambda: self.now)
        self.exports = ExportService(
            self.storage,
            exports_dir=tmp_path / "ex",
            backup_dir=tmp_path / "bk2",
            clock=lambda: self.now,
        )
        with self.storage.transaction() as repos:
            self.activity = repos.activities.add(Activity(name="Code")).id
            self.other = repos.activities.add(Activity(name="Meeting")).id
            self.project = repos.projects.add(Project(name="Alpha")).id
            self.device = repos.devices.add(Device(alias="Büro")).id

    def add(self, start: datetime, end: datetime | None, project: bool = True) -> str:
        with self.storage.transaction() as repos:
            return repos.sessions.add(
                Session(
                    self.activity,
                    start,
                    end,
                    project_id=self.project if project else None,
                    source=SessionSource.MANUAL,
                )
            ).id


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def test_tag_names_are_unique_ignoring_case_and_can_be_changed(env: Env) -> None:
    tag = env.tags.create_tag("Kunde A", "#112233")
    with pytest.raises(ConflictError):
        env.tags.create_tag("kunde a")
    renamed = env.tags.update_tag(tag.id, name="Kunde B")
    assert renamed.name == "Kunde B" and renamed.color == "#112233"
    assert env.tags.update_tag(tag.id, color="#445566").color == "#445566"
    with pytest.raises(NotFoundError):
        env.tags.update_tag("0" * 32, name="x")
    assert [t.name for t in env.tags.list_tags()] == ["Kunde B"]


def test_tags_of_an_entry_are_replaced_and_audited(env: Env) -> None:
    a, b = env.tags.create_tag("A"), env.tags.create_tag("B")
    sid = env.add(T0, T0 + H)
    assert [t.name for t in env.tags.set_session_tags(sid, [a.id, b.id])] == ["A", "B"]
    assert [t.name for t in env.tags.set_session_tags(sid, [b.id, b.id])] == ["B"]
    with pytest.raises(NotFoundError):
        env.tags.set_session_tags(sid, ["0" * 32])
    with pytest.raises(NotFoundError):
        env.tags.set_session_tags("0" * 32, [a.id])
    with env.storage.read() as repos:
        assert "set_session_tags" in [x.action for x in repos.audit.list_all()]


def test_deleting_a_tag_keeps_the_entries(env: Env) -> None:
    tag = env.tags.create_tag("Weg")
    sid = env.add(T0, T0 + H)
    env.tags.set_session_tags(sid, [tag.id])
    env.tags.delete_tag(tag.id)
    with env.storage.read() as repos:
        assert repos.sessions.get(sid) is not None and repos.tags.of_session(sid) == []


def test_deleting_an_entry_removes_its_tag_links(env: Env) -> None:
    tag = env.tags.create_tag("T")
    sid = env.add(T0, T0 + H)
    env.tags.set_session_tags(sid, [tag.id])
    with env.storage.transaction() as repos:
        repos.sessions.delete(sid, "test", repos.audit)
        assert repos.tags.sessions_with(tag.id) == set()


def test_default_tags_are_applied_to_new_entries_by_every_route(env: Env) -> None:
    tag = env.tags.create_tag("Fokus")
    env.tags.set_activity_defaults(env.activity, [tag.id], "Kunde: \nZiel: ")
    started = env.tracking.start_manual(env.activity)
    with env.storage.read() as repos:
        assert [t.name for t in repos.tags.of_session(started.id)] == ["Fokus"]
    assert env.tags.get_activity_defaults(env.activity)["note_template"] == "Kunde: \nZiel:"
    env.tracking.start_manual(env.other)  # another activity: no default tags
    with env.storage.read() as repos:
        running = repos.sessions.get_running()
        assert running is not None and repos.tags.of_session(running.id) == []


def test_note_template_validation_and_removal(env: Env) -> None:
    with pytest.raises(ValidationError):
        env.tags.set_activity_defaults(env.activity, [], "x" * 501)
    env.tags.set_activity_defaults(env.activity, [], "Vorlage")
    env.tags.set_activity_defaults(env.activity, [], "   ")  # blank removes it
    assert env.tags.get_activity_defaults(env.activity)["note_template"] is None
    with pytest.raises(NotFoundError):
        env.tags.set_activity_defaults("0" * 32, [], None)
    with pytest.raises(NotFoundError):
        env.tags.set_activity_defaults(env.activity, ["0" * 32], None)


# ------------------------------------------------------------- reports and filters


def test_journal_and_report_can_be_filtered_by_tag(env: Env) -> None:
    tag = env.tags.create_tag("Rechnung")
    tagged = env.add(T0, T0 + H)
    env.add(T0 + 2 * H, T0 + 3 * H)
    env.tags.set_session_tags(tagged, [tag.id])
    window = (T0 - H, T0 + 5 * H)
    entries = env.reports.journal(ReportFilter(*window, tag_id=tag.id))
    assert [e.session.id for e in entries] == [tagged] and entries[0].tags == ("Rechnung",)
    assert len(env.reports.journal(ReportFilter(*window))) == 2
    report = env.reports.report(ReportFilter(*window, tag_id=tag.id))
    assert report.personal_time == H and report.session_count == 1


# ------------------------------------------------------------------------- billing


def test_billing_amounts_and_budget_share(env: Env) -> None:
    env.tags.set_billing(env.project, 240, 12000, True)  # 4 h, 120.00/h
    env.add(T0, T0 + timedelta(hours=1, minutes=30))
    (budget,) = env.reports.budgets()
    assert budget.used == timedelta(minutes=90) and budget.fraction == 0.375
    assert budget.amount_cents == 18000 and budget.billable
    entry = env.reports.journal(ReportFilter(T0 - H, T0 + 5 * H))[0]
    assert entry.billable and entry.amount_cents == 18000


def test_a_running_entry_counts_until_now(env: Env) -> None:
    env.tags.set_billing(env.project, 600, None, False)
    env.add(T0, None)  # running since 8:00, now is 18:00
    (budget,) = env.reports.budgets()
    assert budget.used == 10 * H and budget.amount_cents is None


def test_empty_billing_removes_the_row_and_validates(env: Env) -> None:
    env.tags.set_billing(env.project, 60, None, False)
    assert len(env.reports.budgets()) == 1
    env.tags.set_billing(env.project, None, None, False)
    assert env.reports.budgets() == []
    with pytest.raises(ValidationError):
        env.tags.set_billing(env.project, 0, None, False)
    with pytest.raises(NotFoundError):
        env.tags.set_billing("0" * 32, 60, None, False)


def test_stored_entries_never_contain_money(env: Env) -> None:
    env.tags.set_billing(env.project, None, 9900, True)
    sid = env.add(T0, T0 + H)
    env.tags.set_billing(env.project, None, 100, True)  # a new rate changes the report only
    with env.storage.read() as repos:
        stored = repos.sessions.get(sid)
    assert stored is not None and not hasattr(stored, "amount")
    assert env.reports.budgets()[0].amount_cents == 100


# ------------------------------------------------------------------------ CSV


def test_csv_has_tags_billable_and_amount_columns(env: Env) -> None:
    tag = env.tags.create_tag("=Formel")
    env.tags.set_billing(env.project, None, 6000, True)
    sid = env.add(T0, T0 + H)
    env.tags.set_session_tags(sid, [tag.id])
    env.add(T0 + 2 * H, T0 + 3 * H, project=False)
    text, _ = env.exports.sessions_csv()
    rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    assert tuple(rows[0]) == CSV_COLUMNS and CSV_COLUMNS[-3:] == ("tags", "billable", "amount")
    tagged = next(r for r in rows if r["session_id"] == sid)
    assert tagged["tags"] == "'=Formel"  # formula injection neutralised
    assert (tagged["billable"], tagged["amount"]) == ("yes", "60.00")
    other = next(r for r in rows if r["session_id"] != sid)
    assert (other["tags"], other["billable"], other["amount"]) == ("", "no", "")


# ----------------------------------------------------------------------- backup


def test_everything_survives_a_backup_and_restore(env: Env) -> None:
    tag = env.tags.create_tag("Rund")
    sid = env.add(T0, T0 + H)
    env.tags.set_session_tags(sid, [tag.id])
    env.tags.set_activity_defaults(env.activity, [tag.id], "Vorlage")
    env.tags.set_billing(env.project, 120, 5000, True)
    text = env.exports.create_backup_text()
    env.tags.delete_tag(tag.id)
    env.tags.set_billing(env.project, None, None, False)
    env.exports.restore_backup_text(text)
    assert [t.name for t in env.tags.list_tags()] == ["Rund"]
    assert env.tags.get_activity_defaults(env.activity)["note_template"] == "Vorlage"
    assert env.tags.get_billing(env.project).hourly_rate_cents == 5000
    with env.storage.read() as repos:
        assert [t.name for t in repos.tags.of_session(sid)] == ["Rund"]


# ------------------------------------------------------------------ budget watch


class WatchEnv:
    def __init__(self, env: Env) -> None:
        self.env = env
        self.tick = 0.0
        self.watch = BudgetWatch(
            env.storage, env.reports, clock=lambda: env.now, monotonic=lambda: self.tick
        )

    def check(self) -> list[int]:
        self.tick += 1000  # always past the interval
        return [i.payload["percent"] for i in self.watch.check()]


def test_budget_warnings_come_once_at_80_and_100_percent(env: Env) -> None:
    env.tags.set_billing(env.project, 100, None, False)  # 100 minutes
    watch = WatchEnv(env)
    assert watch.check() == []
    sid = env.add(T0, T0 + timedelta(minutes=70))
    assert watch.check() == []
    with env.storage.transaction() as repos:
        repos.sessions.correct(sid, {"ended_at": T0 + timedelta(minutes=85)}, "test")
    assert watch.check() == [80] and watch.check() == []
    with env.storage.transaction() as repos:
        repos.sessions.correct(sid, {"ended_at": T0 + timedelta(minutes=105)}, "test")
    assert watch.check() == [100] and watch.check() == []


def test_a_jump_over_80_warns_only_at_100(env: Env) -> None:
    env.tags.set_billing(env.project, 60, None, False)
    env.add(T0, T0 + 2 * H)
    assert WatchEnv(env).check() == [100]


def test_a_raised_budget_resets_the_levels(env: Env) -> None:
    env.tags.set_billing(env.project, 60, None, False)
    env.add(T0, T0 + timedelta(minutes=70))
    watch = WatchEnv(env)
    assert watch.check() == [100]
    env.tags.set_billing(env.project, 600, None, False)  # plenty of room again
    assert watch.check() == []
    env.tags.set_billing(env.project, 80, None, False)  # now 87 % of the new budget
    assert watch.check() == [80]  # 70 of 80 minutes: the new budget warns afresh


def test_the_check_runs_at_most_once_per_interval(env: Env) -> None:
    env.tags.set_billing(env.project, 60, None, False)
    env.add(T0, T0 + 2 * H)
    ticks = iter([0.0, 1.0, 100.0])
    watch = BudgetWatch(env.storage, env.reports, monotonic=lambda: next(ticks), interval=60)
    assert len(watch.check()) == 1  # first call
    assert watch.check() == []  # 1 s later: skipped
    assert watch.check() == []  # 100 s later: checked, nothing new
