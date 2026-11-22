"""GUI tests for AP-59: the chart page draws every group, offers numbers and CSV, and has help."""

from streamlit.testing.v1 import AppTest

from octaledger.dashboard import charts as ch
from tests.conftest import RunningApi
from tests.gui.test_gui_devices_catalog import open_page
from tests.gui.test_gui_journal_statistics import needs_afternoon, seed

PAGE = "charts"


def figures(at: AppTest) -> list[object]:
    return list(at.get("plotly_chart"))


def test_title_help_and_empty_state(api_server: RunningApi) -> None:
    at = open_page(api_server, PAGE)
    assert at.header[0].value == "Diagramme"
    assert any("So lesen Sie die Diagramme" in e.label for e in at.expander)
    assert any("Keine Einträge für die Diagramme" in i.value for i in at.info)
    assert not figures(at)


@needs_afternoon
def test_key_figures_and_the_first_group(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, PAGE)
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Einträge"] == "2" and metrics["Gesamtzeit"] == "3 h 00 min"
    assert at.radio(key="chart_group").value == "Verlauf"
    first_group = [c for c in ch.CHARTS if c.group == "Verlauf"]
    assert len(figures(at)) == len(first_group)
    assert [s.value for s in at.subheader][: len(first_group)] == [c.title for c in first_group]


@needs_afternoon
def test_every_group_draws_its_charts_without_error(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, PAGE)
    for group in ch.GROUPS:
        at.radio(key="chart_group").set_value(group).run()
        assert not at.exception, group
        expected = [c for c in ch.CHARTS if c.group == group]
        assert len(figures(at)) == len(expected), group
        assert len(at.get("download_button")) == len(expected), group


@needs_afternoon
def test_options_change_the_chart_and_the_filter_applies(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, PAGE)
    at.selectbox(key="chart_per_period_granularity").set_value("week")
    at.selectbox(key="chart_per_period_by").set_value("project").run()
    assert not at.exception
    at.text_input(key="chart_text").set_value("planung").run()
    assert any("1** von 2" in c.value for c in at.caption)
    assert {m.label: m.value for m in at.metric}["Einträge"] == "1"
    next(b for b in at.button if b.key == "chart_reset").click().run()
    assert {m.label: m.value for m in at.metric}["Einträge"] == "2"


@needs_afternoon
def test_the_filter_of_this_page_is_independent_of_the_entries_page(
    api_server: RunningApi,
) -> None:
    seed(api_server)
    at = open_page(api_server, PAGE)
    at.text_input(key="chart_text").set_value("planung").run()
    at.sidebar.button(key="nav_entries").click().run()
    assert not at.exception
    assert at.text_input(key="ent_text").value == ""


@needs_afternoon
def test_every_input_has_a_help_text(api_server: RunningApi) -> None:
    seed(api_server)
    at = open_page(api_server, PAGE)
    widgets = [*at.text_input, *at.multiselect, *at.selectbox, *at.number_input, *at.radio]
    widgets += [*at.slider, *at.checkbox, *at.metric]
    widgets += [b for b in at.button if not getattr(b, "form_id", "")]
    missing = [getattr(w, "key", w.label) for w in widgets if not w.help]
    assert missing == []
