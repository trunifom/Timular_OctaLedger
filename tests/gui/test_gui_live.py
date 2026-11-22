"""GUI tests for the live page: the picture, the three steps and the movement history."""

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import FakeAgent, RunningApi
from tests.gui.test_gui_core import texts
from tests.gui.test_gui_devices_catalog import open_page

LIVE = "live"


@pytest.fixture
def agent(api_server: RunningApi) -> FakeAgent:
    fake = FakeAgent()
    api_server.context.agent = fake
    return fake


def svg_of(at: AppTest) -> str:
    return next((m.value for m in at.markdown if "<svg" in str(m.value)), "")


def connected_device(api: RunningApi, agent: FakeAgent, name: str = "Würfel") -> str:
    """Register a device with an address and start it in the fake agent (reports face 3)."""
    device = api.client.register_device(name)
    api.client.set_device_address(device["id"], "AA:BB")
    api.client.connect_device(device["id"])
    assert agent.started == [device["id"]]
    return str(device["id"])


def test_page_title_help_and_empty_state(api_server: RunningApi) -> None:
    at = open_page(api_server, LIVE)
    assert at.header[0].value == "Würfel live"
    assert any("So funktioniert die Live-Ansicht" in e.label for e in at.expander)
    assert any("noch kein Würfel eingerichtet" in i.value for i in at.info)
    assert any(b.key == "live_to_start" for b in at.button)
    assert svg_of(at) == ""  # nothing to draw without a device


def test_device_that_was_never_started_is_not_shown_as_live(api_server: RunningApi) -> None:
    activity = api_server.client.create_item("activities", "Meeting")
    device = api_server.client.register_device("Würfel")
    api_server.client.assign_face(device["id"], 3, activity["id"], None)
    at = open_page(api_server, LIVE)
    assert not at.exception
    page = texts(at)
    assert "Keine Verbindung" in page and "Nicht verbunden" in page
    assert "Meeting" in svg_of(at) and "▲" not in svg_of(at)  # assignment yes, position no
    assert any("Noch keine Bewegung gesehen" in c.value for c in at.caption)


def test_connected_cube_shows_face_flow_and_history(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    activity = api_server.client.create_item("activities", "Meeting")
    device_id = connected_device(api_server, agent)
    api_server.client.assign_face(device_id, 3, activity["id"], None)
    at = open_page(api_server, LIVE)
    assert not at.exception
    page = texts(at)
    assert "① Der Würfel meldet" in page and "② Wird geprüft" in page and "③ Die Software" in page
    assert "Seite 3 („Meeting“)" in page and "Stabil" in page
    assert "▲" in svg_of(at) and "oben liegt Seite 3" in svg_of(at)
    assert "wurde angenommen" in page and "Der Würfel zeigt" in page  # newest first


def test_unassigned_face_explains_why_nothing_starts(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    connected_device(api_server, agent)
    at = open_page(api_server, LIVE)
    assert any("Seite 3 hat noch keine Tätigkeit" in i.value for i in at.info)


def test_a_tracker_that_is_not_active_is_called_out(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    api_server.client.register_device("Erster")  # the first tracker becomes the active one
    second = api_server.client.register_device("Zweiter")
    api_server.client.set_device_address(second["id"], "CC:DD")
    api_server.client.connect_device(second["id"])
    at = open_page(api_server, LIVE)
    at.sidebar.selectbox(key="cube_selected").select_index(1).run()
    assert any("nicht der aktive" in w.value for w in at.warning)


def test_activity_names_cannot_inject_markup_into_the_picture(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    activity = api_server.client.create_item("activities", "<b>x</b>")
    device_id = connected_device(api_server, agent)
    api_server.client.assign_face(device_id, 3, activity["id"], None)
    at = open_page(api_server, LIVE)
    assert "<b>x</b>" not in svg_of(at) and "&lt;b&gt;" in svg_of(at)


def test_running_time_is_shown_in_the_software_step(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    activity = api_server.client.create_item("activities", "Meeting")
    connected_device(api_server, agent)
    api_server.client.start_tracking(activity["id"])
    at = open_page(api_server, LIVE)
    assert "läuft seit" in texts(at)
