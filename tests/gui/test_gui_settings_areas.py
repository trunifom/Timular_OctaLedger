"""GUI tests for the separated settings areas: App (time recording) and Darstellung (looks)."""

from tests.conftest import RunningApi
from tests.gui.test_gui_devices_catalog import open_page


def test_the_app_page_has_basics_up_front_and_advanced_collapsed(api_server: RunningApi) -> None:
    at = open_page(api_server, "settings")
    assert at.header[0].value == "App"
    assert [s.value for s in at.subheader][0] == "Grundeinstellungen"
    advanced = next(e for e in at.expander if e.label == "Erweiterte Einstellungen")
    assert advanced is not None
    for key in ("set_baseline", "set_disconnect", "set_neutral", "set_log_level"):
        assert at.selectbox(key=key) is not None  # present, tucked into the expander


def test_every_setting_names_its_default_in_the_help_text(api_server: RunningApi) -> None:
    at = open_page(api_server, "settings")
    for widget in (at.selectbox(key="set_timezone"), at.slider(key="set_debounce")):
        assert "Voreinstellung" in widget.help
    for key in ("set_baseline", "set_disconnect", "set_neutral", "set_log_level"):
        assert "Voreinstellung" in at.selectbox(key=key).help


def test_the_reset_button_is_disabled_at_defaults_and_restores_them(
    api_server: RunningApi,
) -> None:
    api_server.client.update_settings(
        {"tracking": {"debounce_ms": 900}, "display": {"timezone": "Europe/Zurich"}}
    )
    at = open_page(api_server, "settings")
    assert not at.button(key="set_reset").disabled
    at.button(key="set_reset").click().run()
    settings = api_server.client.get_settings()
    assert settings["tracking"]["debounce_ms"] == 300 and settings["display"]["timezone"] == "UTC"
    assert at.button(key="set_reset").disabled


def test_the_reset_does_not_touch_the_looks(api_server: RunningApi) -> None:
    api_server.client.update_settings({"display": {"theme": "dark", "timezone": "Europe/Zurich"}})
    at = open_page(api_server, "settings")
    at.button(key="set_reset").click().run()
    assert api_server.client.get_settings()["display"]["theme"] == "dark"


def test_the_look_page_applies_immediately_and_is_saved(api_server: RunningApi) -> None:
    at = open_page(api_server, "display")
    assert at.header[0].value == "Darstellung"
    at.radio(key="display_theme_light").set_value("dark").run()
    assert api_server.client.get_settings()["display"]["theme"] == "dark"
    at.radio(key="display_font_normal").set_value("large").run()
    assert api_server.client.get_settings()["display"]["font_size"] == "large"
    assert not at.exception


def test_the_look_page_can_go_back_to_the_defaults(api_server: RunningApi) -> None:
    api_server.client.update_settings({"display": {"theme": "dark", "font_size": "large"}})
    at = open_page(api_server, "display")
    at.button(key="display_reset").click().run()
    display = api_server.client.get_settings()["display"]
    assert (display["theme"], display["font_size"]) == ("light", "normal")
    assert at.button(key="display_reset").disabled


def test_the_look_page_has_help_on_every_control(api_server: RunningApi) -> None:
    at = open_page(api_server, "display")
    assert all(r.help for r in at.radio) and all(
        b.help for b in at.button if b.key == "display_reset"
    )
