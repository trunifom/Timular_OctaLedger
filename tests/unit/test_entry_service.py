"""Bulk editing and deleting of entries and the change history (AP-57)."""

from datetime import datetime, timedelta, timezone

import pytest

from octaledger.core.errors import ConflictError, NotFoundError, ValidationError
from tests.conftest import RunningApi

BASE = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(days=5)


def hours(start: float, end: float) -> tuple[datetime, datetime]:
    return BASE + timedelta(hours=start), BASE + timedelta(hours=end)


class Seed:
    """Three finished entries of one activity, two hours apart, plus helpers."""

    def __init__(self, api: RunningApi) -> None:
        self.api = api
        self.activity = api.client.create_item("activities", "Arbeit")["id"]
        self.other = api.client.create_item("activities", "Pause")["id"]
        self.project = api.client.create_item("projects", "Projekt A")["id"]
        self.ids = [
            api.client.add_session(self.activity, *hours(2 * i, 2 * i + 1), None, f"n{i}")["id"]
            for i in range(3)
        ]

    def entries(self) -> dict[str, dict]:
        rows = self.api.client.journal(BASE - timedelta(days=1), BASE + timedelta(days=1))
        return {r["id"]: r for r in rows}


@pytest.fixture
def seed(api_server: RunningApi) -> Seed:
    return Seed(api_server)


def test_edit_changes_activity_project_note_and_quality_for_all(seed: Seed) -> None:
    result = seed.api.client.bulk_edit(
        seed.ids,
        "Aufräumen",
        activity_id=seed.other,
        project_id=seed.project,
        note_mode="append",
        note="geprüft",
        quality="uncertain",
    )
    assert result == {"changed": 3, "unchanged": 0, "skipped_running": 0, "safety_backup": None}
    rows = seed.entries()
    assert {r["activity_name"] for r in rows.values()} == {"Pause"}
    assert {r["project_name"] for r in rows.values()} == {"Projekt A"}
    assert rows[seed.ids[1]]["note"] == "n1 geprüft" and rows[seed.ids[0]]["revision"] == 2
    assert {r["quality"] for r in rows.values()} == {"uncertain"}


def test_a_second_identical_edit_reports_unchanged_and_clearing_works(seed: Seed) -> None:
    seed.api.client.bulk_edit(seed.ids, "a", project_id=seed.project)
    again = seed.api.client.bulk_edit(seed.ids, "b", project_id=seed.project)
    assert again["changed"] == 0 and again["unchanged"] == 3
    seed.api.client.bulk_edit(seed.ids, "c", clear_project=True, note_mode="clear")
    assert all(r["project_name"] is None and r["note"] is None for r in seed.entries().values())


def test_shift_moves_start_and_end_even_between_selected_neighbours(seed: Seed) -> None:
    before = seed.entries()
    # 3600 s later: entry 0 would run into entry 1 if it moved first - the order must avoid that
    seed.api.client.bulk_edit(seed.ids, "Zeitumstellung", shift_seconds=3600)
    after = seed.entries()
    for sid in seed.ids:
        old = datetime.fromisoformat(before[sid]["started_at"])
        assert datetime.fromisoformat(after[sid]["started_at"]) == old + timedelta(hours=1)
        assert after[sid]["duration_seconds"] == before[sid]["duration_seconds"]
    seed.api.client.bulk_edit(seed.ids, "zurück", shift_seconds=-3600)
    assert seed.entries()[seed.ids[0]]["started_at"] == before[seed.ids[0]]["started_at"]


def test_a_conflict_rolls_back_everything(seed: Seed) -> None:
    # Moving only the first entry by 2 h would land exactly on the second one (a free slot is
    # missing): all-or-nothing means neither of the selected entries moves.
    wide = seed.api.client.add_session(seed.activity, *hours(10, 11))["id"]
    before = seed.entries()
    with pytest.raises(ConflictError):
        seed.api.client.bulk_edit([seed.ids[0], wide], "x", shift_seconds=2 * 3600 + 1800)
    assert seed.entries() == before


def test_a_shift_into_the_future_is_refused(seed: Seed) -> None:
    with pytest.raises(ValidationError):
        seed.api.client.bulk_edit(seed.ids, "x", shift_seconds=60 * 24 * 3600)


def test_tags_can_be_added_removed_and_replaced(seed: Seed) -> None:
    a = seed.api.client.create_tag("PERSON-B")["id"]
    b = seed.api.client.create_tag("TAG-1")["id"]
    seed.api.client.bulk_edit(seed.ids, "t", tags_add=[a, b])
    assert all(sorted(r["tags"]) == ["PERSON-B", "TAG-1"] for r in seed.entries().values())
    again = seed.api.client.bulk_edit(seed.ids, "t", tags_add=[a])
    assert again["changed"] == 0
    seed.api.client.bulk_edit(seed.ids[:2], "t", tags_remove=[a])
    rows = seed.entries()
    assert rows[seed.ids[0]]["tags"] == ["TAG-1"] and len(rows[seed.ids[2]]["tags"]) == 2
    seed.api.client.bulk_edit(seed.ids, "t", tags_replace=[a])
    assert all(r["tags"] == ["PERSON-B"] for r in seed.entries().values())
    seed.api.client.bulk_edit(seed.ids, "t", tags_replace=[])
    assert all(r["tags"] == [] for r in seed.entries().values())


def test_bad_requests_are_refused_and_change_nothing(seed: Seed) -> None:
    with pytest.raises(ValidationError):
        seed.api.client.bulk_edit(seed.ids, "  ", activity_id=seed.other)  # reason is required
    with pytest.raises(ValidationError):
        seed.api.client.bulk_edit(seed.ids, "x")  # nothing to change
    with pytest.raises(NotFoundError):
        seed.api.client.bulk_edit(seed.ids, "x", activity_id="0" * 32)
    with pytest.raises(NotFoundError):
        seed.api.client.bulk_edit([*seed.ids, "f" * 32], "x", activity_id=seed.other)
    assert all(r["revision"] == 1 for r in seed.entries().values())


def test_a_running_entry_is_never_shifted_or_deleted(seed: Seed) -> None:
    ctx = seed.api.context
    ctx.tracking.start_manual(seed.activity)
    running = next(
        r["id"] for r in seed.api.client.journal(BASE, BASE + timedelta(days=9)) if r["running"]
    )
    shifted = seed.api.client.bulk_edit([running, seed.ids[0]], "x", shift_seconds=-60)
    assert shifted["skipped_running"] == 1 and shifted["changed"] == 1
    with pytest.raises(ValidationError):
        seed.api.client.bulk_delete([running], "x")
    result = seed.api.client.bulk_delete([running, seed.ids[0]], "x")
    assert result["changed"] == 1 and result["skipped_running"] == 1
    assert seed.ids[0] not in seed.entries()


def test_delete_removes_the_selection_with_backup_and_audit(seed: Seed) -> None:
    result = seed.api.client.bulk_delete(seed.ids[:2], "Testdaten")
    assert result["changed"] == 2 and result["safety_backup"].startswith("octaledger-pre-delete-")
    assert list(seed.entries()) == [seed.ids[2]]
    history = seed.api.client.entry_history()
    assert any(h["kind"] == "Aktion" and "Testdaten" in h["reason"] for h in history)
    with pytest.raises(ValidationError):
        seed.api.client.bulk_delete(seed.ids[2:], "")


def test_history_shows_old_and_new_values_with_names(seed: Seed) -> None:
    seed.api.client.bulk_edit(seed.ids[:1], "Falsch gebucht", activity_id=seed.other)
    rows = seed.api.client.entry_history(seed.ids[0])
    row = next(r for r in rows if r["field"] == "activity_id")
    assert (row["old_value"], row["new_value"]) == ("Arbeit", "Pause")
    assert row["reason"] == "Sammelbearbeitung: Falsch gebucht" and row["revision"] == 2
    everything = seed.api.client.entry_history()
    assert any(h["kind"] == "Aktion" and h["field"] == "bulk_edit" for h in everything)
    assert len(seed.api.client.entry_history(limit=1)) == 1
    with pytest.raises(ValidationError):
        seed.api.client.entry_history(limit=0)
