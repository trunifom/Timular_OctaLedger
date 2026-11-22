"""GUI tests for AP-51: one selected cube on every page, always shown with number, name, colour."""

from streamlit.testing.v1 import AppTest

from tests.conftest import RunningApi
from tests.gui.test_gui_core import texts
from tests.gui.test_gui_devices_catalog import open_page


def two_cubes(api: RunningApi) -> tuple[dict, dict]:
    first = api.client.register_device("Büro")
    second = api.client.register_device("Wohnzimmer")
    return first, second


def banner_text(at: AppTest) -> str:
    return " ".join(
        str(m.value) for m in at.markdown if "Sie " in str(m.value) and "ol-dot" in str(m.value)
    )


def test_single_cube_is_shown_without_a_selector(api_server: RunningApi) -> None:
    api_server.client.register_device("Büro")
    at = open_page(api_server, "faces")
    assert not at.sidebar.selectbox  # one cube: nothing to choose
    assert "Ausgewählter Würfel" in " ".join(str(m.value) for m in at.sidebar.markdown)
    assert "① Büro" in banner_text(at)


def test_several_cubes_get_a_selector_that_every_page_follows(api_server: RunningApi) -> None:
    first, second = two_cubes(api_server)
    at = open_page(api_server, "faces")
    selector = at.sidebar.selectbox(key="cube_selected")
    assert selector.help and len(selector.options) == 2
    assert "① Büro" in banner_text(at)  # the first (active time) cube is the default
    selector.select(second["id"]).run()
    assert "② Wohnzimmer" in banner_text(at)
    assert at.session_state["cube_selected"] == second["id"]
    # another page uses the same cube
    at.sidebar.button(key="nav_live").click().run()
    assert not at.exception
    assert "② Wohnzimmer" in banner_text(at)
    assert "beobachten" in banner_text(at)


def test_cubes_have_different_colours_in_the_banner(api_server: RunningApi) -> None:
    first, second = two_cubes(api_server)
    assert first["color"] != second["color"]
    at = open_page(api_server, "faces")
    assert first["color"] in " ".join(str(m.value) for m in at.markdown)


def test_a_removed_cube_is_replaced_by_a_valid_selection(api_server: RunningApi) -> None:
    first, second = two_cubes(api_server)
    at = open_page(api_server, "faces")
    at.sidebar.selectbox(key="cube_selected").select(second["id"]).run()
    api_server.client.remove_device(second["id"])
    at.run()
    assert not at.exception
    assert at.session_state["cube_selected"] == first["id"]
    assert "① Büro" in banner_text(at)


def test_overview_lists_every_cube_with_number_and_area(api_server: RunningApi) -> None:
    two_cubes(api_server)
    at = open_page(api_server, "overview")
    page = texts(at) + " ".join(str(m.value) for m in at.markdown)
    assert "① Büro" in page and "② Wohnzimmer" in page and "Zeit" in page


def test_devices_page_offers_colour_and_shows_identity(api_server: RunningApi) -> None:
    first, _ = two_cubes(api_server)
    at = open_page(api_server, "devices")
    picker = next(w for w in at.get("color_picker") if w.key == f"color_{first['id']}")
    assert picker.help
    picker.set_value("#112233").run()
    next(b for b in at.button if b.key == f"color_btn_{first['id']}").click().run()
    assert not at.exception
    assert api_server.client.devices()[0]["color"] == "#112233"
