"""GUI tests for AP-58: search, filter, search log and bulk actions on the page Einträge."""

from datetime import UTC
from typing import Any

from streamlit.testing.v1 import AppTest

from tests.conftest import RunningApi
from tests.gui.test_gui_devices_catalog import open_page
from tests.gui.test_gui_journal_statistics import needs_afternoon, seed

PAGE = "entries"


def submit(at: AppTest, label: str) -> None:
    """Press a form submit button by its label (they carry no key)."""
    next(b for b in at.button if b.label == label).click().run()


def captions(at: AppTest) -> str:
    return " ".join(c.value for c in at.caption) + " " + " ".join(m.value for m in at.markdown)


def journal(api: RunningApi) -> list[dict[str, Any]]:
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    return api.client.journal(now - timedelta(days=3), now + timedelta(days=1))


def test_page_title_help_and_empty_state(api_server: RunningApi) -> None:
    at = open_page(api_server, PAGE)
    assert at.header[0].value == "Einträge"
    assert any("So funktioniert die Seite" in e.label for e in at.expander)
    assert any("keine Einträge" in i.value for i in at.info)
    assert [t.label for t in at.tabs][:2] == ["Einträge", "Änderungsprotokoll"]


@needs_afternoon
def test_search_filters_the_list_and_fills_the_search_log(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, PAGE)
    assert "2** von 2" in captions(at)
    assert any("Suchprotokoll (0)" in e.label for e in at.expander)
    at.text_input(key="ent_text").set_value("planung").run()
    assert not at.exception
    assert "1** von 2" in captions(at) and "Text „planung“" in captions(at)
    assert any("Suchprotokoll (1)" in e.label for e in at.expander)
    at.text_input(key="ent_text").set_value("").run()
    assert "2** von 2" in captions(at)
    # one click on the log restores the search
    next(b for b in at.button if b.key == "ent_log_apply_0").click().run()
    assert at.text_input(key="ent_text").value == "planung" and "1** von 2" in captions(at)
    next(b for b in at.button if b.key == "ent_log_clear").click().run()
    assert any("Suchprotokoll (0)" in e.label for e in at.expander)


@needs_afternoon
def test_filters_by_activity_project_and_duration(api_server: RunningApi) -> None:
    ids = seed(api_server)
    at = open_page(api_server, PAGE)
    at.multiselect(key="ent_act").set_value([ids["code"]]).run()
    assert "1** von 2" in captions(at)
    at.multiselect(key="ent_act").set_value([]).run()
    at.multiselect(key="ent_proj").set_value(["-"]).run()  # no project
    assert "1** von 2" in captions(at) and "ohne" in captions(at)
    at.multiselect(key="ent_proj").set_value([]).run()
    at.number_input(key="ent_min").set_value(90).run()  # only the 2 h entry
    assert "1** von 2" in captions(at)
    next(b for b in at.button if b.key == "ent_reset").click().run()
    assert "2** von 2" in captions(at)


@needs_afternoon
def test_nothing_is_selected_until_you_choose(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, PAGE)
    assert any("Noch nichts ausgewählt" in i.value for i in at.info)
    at.radio(key="ent_scope").set_value("all").run()
    assert any("2 Einträge** ausgewählt" in m.value for m in at.markdown)


@needs_afternoon
def test_assigning_a_tag_to_all_hits_and_removing_it_again(api_server: RunningApi) -> None:
    seed(api_server)
    api_server.client.create_tag("PERSON-B")
    at = open_page(api_server, PAGE)
    at.radio(key="ent_scope").set_value("all").run()
    at.radio(key="ent_b_tagmode").set_value("add")
    at.multiselect(key="ent_b_tags").set_value(["PERSON-B"])
    at.text_input(key="ent_b_reason_assign").set_value("Zuordnung testen")
    submit(at, "Zuordnung anwenden")
    assert not at.exception
    assert any("2 Eintrag/Einträge zugeordnet" in s.value for s in at.success)
    assert all(e["tags"] == ["PERSON-B"] for e in journal(api_server))
    # reset all tags of all hits
    at.radio(key="ent_scope").set_value("all").run()
    at.radio(key="ent_b_tagmode").set_value("clear")
    at.text_input(key="ent_b_reason_assign").set_value("zurücksetzen")
    submit(at, "Zuordnung anwenden")
    assert all(e["tags"] == [] for e in journal(api_server))


@needs_afternoon
def test_a_missing_reason_is_explained_and_nothing_changes(api_server: RunningApi) -> None:
    ids = seed(api_server)
    at = open_page(api_server, PAGE)
    at.radio(key="ent_scope").set_value("all").run()
    at.selectbox(key="ent_b_act").set_value(ids["meeting"])
    submit(at, "Zuordnung anwenden")
    assert not at.exception
    assert any("Grund" in e.value for e in at.error)
    assert {e["activity_name"] for e in journal(api_server)} == {"Meeting", "Code"}


@needs_afternoon
def test_shifting_and_note_quality(api_server: RunningApi) -> None:
    seed(api_server)
    before = {e["id"]: e["started_at"] for e in journal(api_server)}
    at = open_page(api_server, PAGE)
    at.radio(key="ent_scope").set_value("all").run()
    at.number_input(key="ent_b_shift").set_value(30)
    at.radio(key="ent_b_dir").set_value("earlier")
    at.text_input(key="ent_b_reason_shift").set_value("Uhr ging nach")
    submit(at, "Verschieben")
    assert any("verschoben" in s.value for s in at.success)
    from datetime import datetime, timedelta

    for e in journal(api_server):
        assert datetime.fromisoformat(e["started_at"]) == datetime.fromisoformat(
            before[e["id"]]
        ) - timedelta(minutes=30)
    at.radio(key="ent_scope").set_value("all").run()
    at.radio(key="ent_b_note_mode").set_value("set")
    at.text_input(key="ent_b_note").set_value("geprüft")
    at.selectbox(key="ent_b_quality").set_value("uncertain")
    at.text_input(key="ent_b_reason_note").set_value("Nachkontrolle")
    submit(at, "Notiz und Qualität anwenden")
    rows = journal(api_server)
    assert {e["note"] for e in rows} == {"geprüft"} and {e["quality"] for e in rows} == {
        "uncertain"
    }


@needs_afternoon
def test_delete_needs_the_typed_count_and_a_reason(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, PAGE)
    at.radio(key="ent_scope").set_value("all").run()
    button = next(b for b in at.button if b.key == "ent_b_delete")
    assert button.disabled and button.help
    at.number_input(key="ent_b_delete_count").set_value(2).run()
    at.text_input(key="ent_b_reason_delete").set_value("Testdaten")
    next(b for b in at.button if b.key == "ent_b_delete").click().run()
    assert not at.exception
    assert any(
        "2 Eintrag/Einträge gelöscht" in s.value and "Sicherung" in s.value for s in at.success
    )
    assert journal(api_server) == []


@needs_afternoon
def test_the_change_protocol_shows_what_was_done(api_server: RunningApi) -> None:
    ids = seed(api_server)
    api_server.client.bulk_edit([ids["first"]], "Falsch gebucht", activity_id=ids["code"])
    at = open_page(api_server, PAGE)
    table = at.dataframe[-1].value
    row = table[table["Was"] == "Tätigkeit"].iloc[0]
    assert (row["Vorher"], row["Nachher"]) == ("Meeting", "Code")
    assert "Falsch gebucht" in row["Grund / Angabe"]
    at.text_input(key="ent_hist_text").set_value("gibt es nicht").run()
    assert any("Keine Zeile passt" in i.value for i in at.info)


@needs_afternoon
def test_every_input_has_a_help_text(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, PAGE)
    widgets = [*at.text_input, *at.multiselect, *at.selectbox, *at.number_input, *at.radio]
    widgets += [*at.slider, *at.checkbox]
    widgets += [b for b in at.button if not getattr(b, "form_id", "")]
    missing = [getattr(w, "key", w.label) for w in widgets if not w.help]
    assert missing == []
