"""GUI tests for the "Löschen" tab: preview, two-step confirmation, safety backup, reset."""

from datetime import UTC, datetime, timedelta

from tests.conftest import RunningApi
from tests.gui.test_gui_devices_catalog import open_page

DATA = "data"
UTC = UTC


def seed(api: RunningApi, count: int = 3) -> None:
    activity = api.client.create_item("activities", "Meeting")
    now = datetime.now(UTC).replace(microsecond=0)
    for i in range(count):  # finished entries a few days back, never overlapping or in the future
        start = now - timedelta(days=10 + i)
        api.client.add_session(activity["id"], start, start + timedelta(hours=1))


def cleanup_tab(api: RunningApi):  # type: ignore[no-untyped-def]
    return open_page(api, DATA)


def keys(at) -> list[str]:  # type: ignore[no-untyped-def]
    return [b.key for b in at.button]


def test_the_delete_tab_exists_and_explains_the_safety_backup(api_server: RunningApi) -> None:
    at = cleanup_tab(api_server)
    assert "Löschen" in [t.label for t in at.tabs]
    assert any("Rückgängig" in m.value for m in at.markdown)


def test_without_entries_there_is_nothing_to_delete(api_server: RunningApi) -> None:
    at = cleanup_tab(api_server)
    assert any("keine Einträge gespeichert" in i.value for i in at.info)
    assert "cleanup_ask_btn" not in keys(at)


def test_the_preview_names_the_count_before_anything_is_deleted(api_server: RunningApi) -> None:
    seed(api_server)
    at = cleanup_tab(api_server)
    at.radio(key="cleanup_scope").set_value("all").run()
    assert any("3 Einträge" in m.value for m in at.markdown)
    assert api_server.client.data_overview()["sessions"] == 3  # looking deletes nothing


def test_deleting_all_entries_needs_the_typed_word_and_makes_a_safety_backup(
    api_server: RunningApi,
) -> None:
    seed(api_server)
    at = cleanup_tab(api_server)
    at.radio(key="cleanup_scope").set_value("all").run()
    at.button(key="cleanup_ask_btn").click().run()
    assert at.button(key="cleanup_do").disabled  # not before the word is typed
    at.text_input(key="cleanup_typed").input("ALLE LÖSCHEN").run()
    assert not at.button(key="cleanup_do").disabled
    assert "3 Einträge endgültig löschen" in at.button(key="cleanup_do").label
    at.button(key="cleanup_do").click().run()
    assert api_server.client.data_overview()["sessions"] == 0
    assert any(
        "Rückgängig machen" in s.value and "octaledger-pre-delete" in s.value for s in at.success
    )


def test_keeping_cancels_the_deletion(api_server: RunningApi) -> None:
    seed(api_server)
    at = cleanup_tab(api_server)
    at.radio(key="cleanup_scope").set_value("all").run()
    at.button(key="cleanup_ask_btn").click().run()
    at.button(key="cleanup_keep").click().run()
    assert "cleanup_do" not in keys(at)
    assert api_server.client.data_overview()["sessions"] == 3


def test_a_period_without_entries_says_so(api_server: RunningApi) -> None:
    seed(api_server)  # entries are 10+ days back; the default period is the last 30 days
    at = cleanup_tab(api_server)
    at.date_input(key="cleanup_from").set_value(datetime.now(UTC).date()).run()
    assert any("keine abgeschlossenen Einträge" in i.value for i in at.info)


def test_factory_reset_needs_the_exact_text(api_server: RunningApi) -> None:
    seed(api_server)
    at = cleanup_tab(api_server)
    assert at.button(key="cleanup_reset_do").disabled
    at.text_input(key="cleanup_reset_typed").input("alles löschen bitte").run()
    assert at.button(key="cleanup_reset_do").disabled
    at.text_input(key="cleanup_reset_typed").input("ALLES LÖSCHEN").run()
    at.button(key="cleanup_reset_do").click().run()
    overview = api_server.client.data_overview()
    assert overview["sessions"] == 0 and overview["activities"] == 0
    assert any("Alles zurückgesetzt" in s.value for s in at.success)


def test_every_widget_of_the_delete_tab_has_a_help_text(api_server: RunningApi) -> None:
    seed(api_server)
    at = cleanup_tab(api_server)
    at.radio(key="cleanup_scope").set_value("all").run()
    at.button(key="cleanup_ask_btn").click().run()
    widgets = [*at.radio, *at.checkbox, *at.text_input, *at.date_input]
    widgets += [b for b in at.button if b.key and b.key.startswith("cleanup_")]
    assert widgets and all(w.help for w in widgets), [w.key for w in widgets if not w.help]
