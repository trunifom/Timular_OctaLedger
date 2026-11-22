"""GUI tests for AP-52: every cube's battery is always visible, with text; weak ones warn."""

from datetime import datetime, timedelta, timezone

from streamlit.testing.v1 import AppTest

from tests.conftest import RunningApi
from tests.gui.test_gui_devices_catalog import open_page


def markdown_text(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def log_battery(api: RunningApi, device_id: str, *values: int) -> None:
    """Store readings, the newest one a minute ago (older ones step back by a day)."""
    now = datetime.now(timezone.utc)
    with api.storage.transaction() as repos:
        for index, value in enumerate(reversed(values)):
            repos.battery.add(device_id, now - timedelta(minutes=1, days=index), value)


def test_an_unknown_battery_is_explained_not_hidden(api_server: RunningApi) -> None:
    api_server.client.register_device("Büro")
    at = open_page(api_server, "overview")
    assert "Batterie: noch nicht gemeldet" in markdown_text(at)


def test_status_bar_shows_every_cube_with_bar_percent_and_stage(api_server: RunningApi) -> None:
    first = api_server.client.register_device("Büro")
    second = api_server.client.register_device("Wohnzimmer")
    log_battery(api_server, first["id"], 62)
    log_battery(api_server, second["id"], 85)
    for page in ("overview", "faces", "journal"):  # on every page, not only on one
        at = open_page(api_server, page)
        text = markdown_text(at)
        assert "① Büro" in text and "62 %" in text and "gut" in text, page
        assert "② Wohnzimmer" in text and "85 %" in text, page
        assert "zuletzt gemessen" in text  # no live connection in the test: last stored value


def test_a_weak_battery_is_a_visible_warning_with_an_estimate_text(
    api_server: RunningApi,
) -> None:
    cube = api_server.client.register_device("Büro")
    log_battery(api_server, cube["id"], 18)
    at = open_page(api_server, "overview")
    warning = " ".join(w.value for w in at.warning)
    assert "Büro" in warning and "schwach" in warning and "18 %" in warning
    assert "keine Schätzung" in warning  # not enough history: honestly no estimate


def test_a_good_battery_raises_no_warning(api_server: RunningApi) -> None:
    cube = api_server.client.register_device("Büro")
    log_battery(api_server, cube["id"], 90)
    at = open_page(api_server, "overview")
    assert not any("Batterie" in w.value for w in at.warning)


def test_devices_page_shows_estimate_and_history(api_server: RunningApi) -> None:
    cube = api_server.client.register_device("Büro")
    # twelve days, falling two percent per day: enough for an estimate
    log_battery(api_server, cube["id"], *[90 - 2 * day for day in range(12)][::-1][::-1])
    at = open_page(api_server, "devices")
    assert not at.exception
    page = markdown_text(at) + " ".join(c.value for c in at.caption)
    assert "Schätzung" in page
    assert any(label.label == "Batterie: Stand und Verlauf" for label in at.expander)
