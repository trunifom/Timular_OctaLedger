"""GUI tests for the setup assistant 'Seiten zuordnen'."""

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from octaledger.dashboard.views.faces import assigned_faces, next_free_face, target_key
from tests.conftest import FakeAgent, RunningApi
from tests.gui.test_gui_core import texts
from tests.gui.test_gui_devices_catalog import open_page

FACES = "faces"


@pytest.fixture
def agent(api_server: RunningApi) -> FakeAgent:
    fake = FakeAgent()
    api_server.context.agent = fake
    return fake


def device_with(api: RunningApi, faces: dict[int, str]) -> dict[str, Any]:
    """Register a device and give the listed faces the named activities."""
    device = api.client.register_device("Würfel")
    for face, name in faces.items():
        activity = api.client.create_item("activities", name)
        api.client.assign_face(device["id"], face, activity["id"], None)
    return api.client.devices()[0]


def choose(at: AppTest, device_id: str, face: int, index: int) -> None:
    at.selectbox(key=f"faces_activity_{device_id}_{face}").select_index(index).run()


# ----------------------------------------------------------------------- pure helpers


def test_next_free_face_skips_assigned_faces_and_wraps_around() -> None:
    def device(*assigned: int) -> dict[str, Any]:
        return {"faces": {str(f): {"activity_id": "a"} for f in assigned}}

    assert next_free_face(device()) == 1
    assert next_free_face(device(1, 2), after=2) == 3
    assert next_free_face(device(4, 5, 6, 7, 8), after=8) == 1  # wraps around
    assert next_free_face(device(*range(1, 9)), after=3) is None
    assert assigned_faces({"faces": {"2": {"activity_id": None}, "3": {"activity_id": "x"}}}) == {3}


# --------------------------------------------------------------------------- the page


def test_title_help_and_empty_state(api_server: RunningApi) -> None:
    at = open_page(api_server, FACES)
    assert at.header[0].value == "Seiten zuordnen"
    assert any("So funktioniert die Zuordnung" in e.label for e in at.expander)
    assert any("brauchen Sie einen eingerichteten Würfel" in i.value for i in at.info)
    assert any(b.key == "faces_to_start" for b in at.button)


def test_new_activity_is_created_on_the_spot_and_the_next_free_face_follows(
    api_server: RunningApi,
) -> None:
    device = device_with(api_server, {})
    at = open_page(api_server, FACES)
    assert at.radio(key=target_key(device["id"])).value == 1
    # No activity exists yet, so "new activity" is preselected and asks for a name.
    at.text_input(key=f"faces_new_name_{device['id']}_1").input("Entwicklung").run()
    at.button(key=f"faces_save_{device['id']}").click().run()
    assert not at.exception
    assert [a["name"] for a in api_server.client.list_items("activities")] == ["Entwicklung"]
    assert api_server.client.devices()[0]["faces"]["1"]["activity_id"]
    assert any("Seite 1 ist jetzt „Entwicklung“" in s.value for s in at.success)
    assert at.radio(key=target_key(device["id"])).value == 2  # moved on to the next free face


def test_save_is_disabled_until_a_name_is_typed(api_server: RunningApi) -> None:
    device = device_with(api_server, {})
    at = open_page(api_server, FACES)
    assert at.button(key=f"faces_save_{device['id']}").disabled
    at.text_input(key=f"faces_new_name_{device['id']}_1").input("Pause").run()
    assert not at.button(key=f"faces_save_{device['id']}").disabled


def test_an_existing_activity_can_be_picked_for_a_face(api_server: RunningApi) -> None:
    device = device_with(api_server, {1: "Meeting"})
    api_server.client.create_item("activities", "Pause")
    at = open_page(api_server, FACES)
    assert at.radio(key=target_key(device["id"])).value == 2  # first face without an activity
    activities = [a["name"] for a in api_server.client.list_items("activities")]
    choose(at, device["id"], 2, activities.index("Pause"))
    at.button(key=f"faces_save_{device['id']}").click().run()
    face = api_server.client.devices()[0]["faces"]["2"]
    pause = next(a for a in api_server.client.list_items("activities") if a["name"] == "Pause")
    assert face["activity_id"] == pause["id"]


def test_duplicate_new_name_is_reported_and_nothing_is_assigned(api_server: RunningApi) -> None:
    device = device_with(api_server, {1: "Meeting"})
    at = open_page(api_server, FACES)
    new_index = len(api_server.client.list_items("activities"))  # "new activity" is the last entry
    choose(at, device["id"], 2, new_index)
    at.text_input(key=f"faces_new_name_{device['id']}_2").input("meeting").run()
    at.button(key=f"faces_save_{device['id']}").click().run()
    assert "OL-STATE-002" in texts(at)  # duplicate name, German message with code
    assert "2" not in api_server.client.devices()[0]["faces"]


def test_a_face_can_be_cleared_and_its_activity_survives(api_server: RunningApi) -> None:
    device = device_with(api_server, {1: "Meeting"})
    at = open_page(api_server, FACES)
    at.radio(key=target_key(device["id"])).set_value(1).run()
    at.button(key=f"faces_clear_{device['id']}").click().run()
    assert api_server.client.devices()[0]["faces"] == {}
    assert [a["name"] for a in api_server.client.list_items("activities")] == ["Meeting"]
    assert any("Seite 1 ist wieder frei" in s.value for s in at.success)


def test_the_free_face_cannot_be_cleared(api_server: RunningApi) -> None:
    device = device_with(api_server, {})
    at = open_page(api_server, FACES)
    assert at.button(key=f"faces_clear_{device['id']}").disabled


def test_connection_hint_and_one_click_connect(api_server: RunningApi, agent: FakeAgent) -> None:
    device = api_server.client.register_device("Würfel")
    api_server.client.set_device_address(device["id"], "AA:BB")
    at = open_page(api_server, FACES)
    assert any("nicht verbunden" in i.value for i in at.info)
    at.button(key="faces_connect").click().run()
    assert agent.started == [device["id"]]


def test_unknown_address_points_to_the_devices_page(api_server: RunningApi) -> None:
    api_server.client.register_device("Würfel")
    at = open_page(api_server, FACES)
    assert any(b.key == "faces_to_devices" for b in at.button)
    assert not any(b.key == "faces_connect" for b in at.button)


def test_the_face_that_is_up_can_be_selected_with_one_click(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    device = api_server.client.register_device("Würfel")
    api_server.client.set_device_address(device["id"], "AA:BB")
    api_server.client.connect_device(device["id"])  # the fake cube reports face 3
    at = open_page(api_server, FACES)
    assert at.radio(key=target_key(device["id"])).value == 1
    at.button(key=f"faces_use_current_{device['id']}").click().run()
    assert at.radio(key=target_key(device["id"])).value == 3
    assert not any(b.key == f"faces_use_current_{device['id']}" for b in at.button)  # selected now


def test_completing_all_faces_shows_the_next_steps(api_server: RunningApi) -> None:
    device = device_with(api_server, {n: f"Tätigkeit {n}" for n in range(1, 9)})
    at = open_page(api_server, FACES)
    assert any("Alle acht Seiten sind eingerichtet" in s.value for s in at.success)
    assert {"faces_to_live", "faces_to_overview"} <= {b.key for b in at.button}
    assert at.radio(key=target_key(device["id"])).value == 1


def test_names_cannot_inject_markup_into_the_picture(api_server: RunningApi) -> None:
    device_with(api_server, {1: "<b>x</b>"})
    at = open_page(api_server, FACES)
    picture = next(m.value for m in at.markdown if "<svg" in str(m.value))
    assert "<b>x</b>" not in picture and "&lt;b&gt;" in picture


def test_every_input_has_a_help_text(api_server: RunningApi) -> None:
    device = device_with(api_server, {1: "Meeting"})
    api_server.client.set_device_address(device["id"], "AA:BB")
    at = open_page(api_server, FACES)
    widgets = [*at.selectbox, *at.radio, *at.text_input]
    widgets += [b for b in at.button if not b.key.startswith("nav_")]
    assert widgets and all(w.help for w in widgets)
