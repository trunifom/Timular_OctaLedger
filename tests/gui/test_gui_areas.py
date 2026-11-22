"""GUI tests for AP-53: the three areas (Zeit, Smarthome, Musik) are told apart and switchable."""

from streamlit.testing.v1 import AppTest

from tests.conftest import RunningApi
from tests.gui.test_gui_devices_catalog import open_page


def three_cubes(api: RunningApi) -> dict[str, dict]:
    time_cube = api.client.register_device("Büro")
    control = api.client.register_device("Licht")
    music = api.client.register_device("Musik")
    api.client.set_device_mode(control["id"], "control")
    api.client.set_device_mode(music["id"], "music")
    return {"time": time_cube, "control": control, "music": music}


def nav_slugs(at: AppTest) -> set[str]:
    return {b.key.removeprefix("nav_") for b in at.sidebar.button if b.key.startswith("nav_")}


def markdown_text(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def test_all_areas_show_every_menu_entry_by_default(api_server: RunningApi) -> None:
    three_cubes(api_server)
    at = open_page(api_server, "overview")
    assert at.sidebar.radio(key="area_filter").value == "all"
    assert {"journal", "statistics", "player", "connections", "faces"} <= nav_slugs(at)


def test_the_music_filter_hides_time_pages_and_other_cubes(api_server: RunningApi) -> None:
    cubes = three_cubes(api_server)
    at = open_page(api_server, "overview")
    at.sidebar.radio(key="area_filter").set_value("music").run()
    assert not at.exception
    slugs = nav_slugs(at)
    assert "player" in slugs and "connections" in slugs
    assert "journal" not in slugs and "statistics" not in slugs
    assert "faces" in slugs  # pages for every area stay
    # only one cube of this area: no selector, the music cube is selected
    assert at.session_state["cube_selected"] == cubes["music"]["id"]
    assert "🎵 Musik" in markdown_text(at)


def test_the_time_filter_hides_the_music_player(api_server: RunningApi) -> None:
    three_cubes(api_server)
    at = open_page(api_server, "overview")
    at.sidebar.radio(key="area_filter").set_value("time").run()
    slugs = nav_slugs(at)
    assert "journal" in slugs and "statistics" in slugs
    assert "player" not in slugs and "connections" not in slugs


def test_the_page_you_are_on_never_disappears(api_server: RunningApi) -> None:
    three_cubes(api_server)
    at = open_page(api_server, "journal")
    at.sidebar.radio(key="area_filter").set_value("music").run()
    assert "journal" in nav_slugs(at)  # still reachable although it is a time page


def test_an_area_without_cubes_falls_back_to_all_cubes_with_a_note(
    api_server: RunningApi,
) -> None:
    api_server.client.register_device("Büro")  # time only
    at = open_page(api_server, "overview")
    at.sidebar.radio(key="area_filter").set_value("music").run()
    assert not at.exception
    assert any("Kein Würfel im Bereich Musik" in c.value for c in at.sidebar.caption)
    assert "Büro" in markdown_text(at)  # the only cube is still shown


def test_banner_names_the_area_and_leads_to_the_switch(api_server: RunningApi) -> None:
    cubes = three_cubes(api_server)
    at = open_page(api_server, "live")
    at.sidebar.selectbox(key="cube_selected").select(cubes["music"]["id"]).run()
    banner = " ".join(str(m.value) for m in at.markdown if "Sie beobachten" in str(m.value))
    assert "ol-area-music" in banner and "🎵 Musik" in banner
    change = next(b for b in at.button if b.key == "live_banner_change_area")
    assert change.help
    change.click().run()
    assert not at.exception
    assert at.session_state["nav"] == "faces"


def test_the_faces_page_explains_what_switching_does(api_server: RunningApi) -> None:
    api_server.client.register_device("Büro")
    at = open_page(api_server, "faces")
    assert not any(b.key == "faces_banner_change_area" for b in at.button)  # the switch is here
    captions = " ".join(c.value for c in at.caption)
    assert "erfasst Zeit" in captions and "anderen Bereiche" in captions
