"""GUI tests for the devices page (registration, scan, calibration) and the management page."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from octaledger.dashboard_client.client import ApiClient
from octaledger.domain.models import Session, SessionSource
from tests.conftest import FakeAgent, RunningApi
from tests.gui.test_gui_core import button, open_app, texts

DEVICES = "devices"
CATALOG = "catalog"


def open_page(api: RunningApi, page: str) -> AppTest:
    at = open_app(api.client)
    at.sidebar.button(key=f"nav_{page}").click().run()
    assert not at.exception
    return at


def all_help(at: AppTest) -> list[Any]:
    """Widgets that must carry a help text (form submit buttons are exempt)."""
    widgets = [*at.selectbox, *at.text_input, *at.checkbox, *at.toggle, *at.color_picker]
    widgets += [b for b in at.button if not getattr(b, "form_id", "")]
    return widgets


@pytest.fixture
def agent(api_server: RunningApi) -> FakeAgent:
    fake = FakeAgent()
    api_server.context.agent = fake
    return fake


# ----------------------------------------------------------------------------- devices


def test_devices_page_with_empty_state(api_server: RunningApi) -> None:
    at = open_page(api_server, DEVICES)
    assert at.header[0].value == "Würfel verwalten"
    assert any("Noch kein Tracker registriert" in i.value for i in at.info)
    assert any("So funktioniert „Würfel verwalten“" in e.label for e in at.expander)


def test_register_device_and_duplicate_alias(api_server: RunningApi) -> None:
    at = open_page(api_server, DEVICES)
    at.text_input(key="register_alias").input("Tracker Büro")
    button(at, "Registrieren").click().run()
    assert [d["alias"] for d in api_server.client.devices()] == ["Tracker Büro"]
    assert any("registriert" in s.value for s in at.success)
    at.text_input(key="register_alias").input("tracker büro")
    button(at, "Registrieren").click().run()
    assert any("widerspricht" in e.value for e in at.error)  # duplicate name, German message
    assert "OL-STATE-002" in texts(at)
    assert len(api_server.client.devices()) == 1


def test_empty_alias_shows_validation_message(api_server: RunningApi) -> None:
    at = open_page(api_server, DEVICES)
    button(at, "Registrieren").click().run()
    assert any("OL-VALID-001" in c.value for c in at.caption)
    assert api_server.client.devices() == []


def test_scan_without_agent_explains_the_problem(api_server: RunningApi) -> None:
    api_server.client.register_device("A")
    at = open_page(api_server, DEVICES)
    button(at, "Nach Geräten suchen").click().run()
    assert any("OL-API-002" in c.value for c in at.caption)
    assert not at.exception


def test_scan_pick_and_store_address(api_server: RunningApi, agent: FakeAgent) -> None:
    device = api_server.client.register_device("A")
    at = open_page(api_server, DEVICES)
    button(at, "Nach Geräten suchen").click().run()
    pick = at.selectbox(key="scan_pick")
    assert "ZEI" in pick.options[0] and "passender Dienst" in pick.options[0]
    button(at, "Adresse speichern").click().run()
    assert api_server.client.devices()[0]["has_address"] is True
    assert "AA:BB" not in texts(at)  # the address itself is never displayed
    assert device["id"] == api_server.client.devices()[0]["id"]


def test_scan_with_no_results_and_no_devices_give_hints(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    agent.scan_results = []
    at = open_page(api_server, DEVICES)
    button(at, "Nach Geräten suchen").click().run()
    assert any("Keine Geräte gefunden" in i.value for i in at.info)
    agent.scan_results = FakeAgent().scan_results
    button(at, "Nach Geräten suchen").click().run()
    # No tracker exists yet: the result is still shown and can be registered right away.
    assert "ZEI" in at.selectbox(key="scan_pick").options[0]
    assert at.text_input(key="scan_new_alias").value == "Mein Würfel"
    at.button(key="scan_register").click().run()
    (device,) = api_server.client.devices()
    assert device["alias"] == "Mein Würfel" and device["has_address"]


def test_scan_failure_shows_bluetooth_message(api_server: RunningApi, agent: FakeAgent) -> None:
    agent.fail_scan = True
    at = open_page(api_server, DEVICES)
    button(at, "Nach Geräten suchen").click().run()
    assert any("Bluetooth ist aus." in e.value for e in at.error)


def test_connect_and_disconnect(api_server: RunningApi, agent: FakeAgent) -> None:
    device = api_server.client.register_device("A")
    at = open_page(api_server, DEVICES)
    button(at, "Verbinden").click().run()  # no address stored yet
    assert any("Adresse" in e.value for e in at.error) and agent.started == []
    api_server.client.set_device_address(device["id"], "AA:BB")
    at = open_page(api_server, DEVICES)
    button(at, "Verbinden").click().run()
    assert agent.started == [device["id"]]
    assert "Bereit" in texts(at) and "87 %" in texts(at) and "Batterie" in texts(at)
    button(at, "Trennen").click().run()
    assert agent.stopped == [device["id"]]


def test_hand_over_between_two_trackers(api_server: RunningApi) -> None:
    first = api_server.client.register_device("Eins")
    second = api_server.client.register_device("Zwei")
    at = open_page(api_server, DEVICES)
    assert at.button(key=f"activate_{first['id']}").disabled  # already the active one
    at.button(key=f"activate_{second['id']}").click().run()
    assert {d["alias"]: d["is_active"] for d in api_server.client.devices()} == {
        "Eins": False,
        "Zwei": True,
    }


def test_calibration_saves_only_changed_faces(api_server: RunningApi) -> None:
    client = api_server.client
    device = client.register_device("A")
    meeting = client.create_item("activities", "Meeting")
    code = client.create_item("activities", "Code")
    project = client.create_item("projects", "Alpha")
    at = open_page(api_server, DEVICES)
    assert any("0 von 8 Seiten" in e.proto.text for e in at.get("progress"))
    did = device["id"]
    at.selectbox(key=f"face_act_{did}_3").select_index(1)  # Code (options sorted by name)
    at.selectbox(key=f"face_act_{did}_5").select_index(2)
    at.selectbox(key=f"face_proj_{did}_5").select_index(1)
    button(at, "Kalibrierung speichern").click().run()
    faces = client.devices()[0]["faces"]
    assert set(faces) == {"3", "5"} and client.devices()[0]["configured_faces"] == 2
    assert faces["5"]["project_id"] == project["id"]
    assert {faces["3"]["activity_id"], faces["5"]["activity_id"]} == {meeting["id"], code["id"]}
    # Clearing a face removes the mapping; unchanged faces are not touched.
    at = open_page(api_server, DEVICES)
    at.selectbox(key=f"face_act_{did}_3").select_index(0)
    button(at, "Kalibrierung speichern").click().run()
    assert set(client.devices()[0]["faces"]) == {"5"}


def test_calibration_shows_the_face_that_is_up(api_server: RunningApi) -> None:
    from octaledger.domain.models import EventKind, RawEvent

    device = api_server.client.register_device("A")
    api_server.client.create_item("activities", "Meeting")
    with api_server.storage.transaction() as repos:
        repos.events.add(
            RawEvent(
                device_id=device["id"],
                kind=EventKind.FACE_CHANGE,
                sequence=1,
                connection_id="c",
                raw_value=5,
            )
        )
    at = open_page(api_server, DEVICES)
    assert "Seite 5" in texts(at) and "oben" in texts(at)


def test_calibration_requires_activities(api_server: RunningApi) -> None:
    api_server.client.register_device("A")
    at = open_page(api_server, DEVICES)
    assert any("Tätigkeiten & Projekte" in i.value for i in at.info)


def test_rename_and_remove_with_confirmation(api_server: RunningApi) -> None:
    client = api_server.client
    device = client.register_device("Alt")
    at = open_page(api_server, DEVICES)
    at.text_input(key=f"rename_{device['id']}").input("Neu")
    at.button(key=f"rename_btn_{device['id']}").click().run()
    assert client.devices()[0]["alias"] == "Neu"
    assert f"delete_{device['id']}" not in [b.key for b in at.button]  # asks first
    at.button(key=f"remove_ask_{device['id']}").click().run()
    at.button(key=f"remove_keep_{device['id']}").click().run()
    assert len(client.devices()) == 1  # keeping changes nothing
    at.button(key=f"remove_ask_{device['id']}").click().run()
    at.button(key=f"delete_{device['id']}").click().run()
    assert client.devices() == []


def test_a_cube_with_data_is_removed_only_when_its_data_may_go(api_server: RunningApi) -> None:
    client = api_server.client
    device = client.register_device("Mit Daten")
    activity = client.create_item("activities", "Meeting")
    now = datetime.now(UTC).replace(microsecond=0)
    with api_server.storage.transaction() as repos:
        repos.sessions.add(
            Session(
                activity_id=activity["id"],
                device_id=device["id"],
                source=SessionSource.DEVICE,
                started_at=now - timedelta(days=2),
                ended_at=now - timedelta(days=2) + timedelta(hours=1),
            )
        )
    at = open_page(api_server, DEVICES)
    at.button(key=f"remove_ask_{device['id']}").click().run()
    at.button(key=f"delete_{device['id']}").click().run()
    assert "OL-STATE-002" in texts(at) and len(client.devices()) == 1  # data protects the cube
    at.checkbox(key=f"remove_data_{device['id']}").check().run()
    at.button(key=f"delete_{device['id']}").click().run()
    assert client.devices() == []
    assert any("Sicherung vorher" in s.value for s in at.success)


def test_unpairing_forgets_the_address_but_keeps_the_cube(api_server: RunningApi) -> None:
    client = api_server.client
    device = client.register_device("Gekoppelt")
    client.set_device_address(device["id"], "AA:BB:CC")
    at = open_page(api_server, DEVICES)
    at.button(key=f"unpair_{device['id']}").click().run()
    assert (
        client.devices()[0]["has_address"] is False and client.devices()[0]["alias"] == "Gekoppelt"
    )
    assert at.button(key=f"unpair_{device['id']}").disabled  # nothing left to unpair


def test_devices_page_widgets_have_help_texts(api_server: RunningApi) -> None:
    api_server.client.register_device("A")
    api_server.client.create_item("activities", "Meeting")
    at = open_page(api_server, DEVICES)
    for widget in all_help(at):
        assert widget.help, f"{widget.key or widget.label} has no help text"


def test_user_supplied_device_name_is_escaped(api_server: RunningApi) -> None:
    api_server.client.register_device("<script>x</script>")
    assert "<script>x</script>" not in "".join(
        m.value for m in open_page(api_server, DEVICES).markdown
    )


# ----------------------------------------------------------------------------- catalog


def test_catalog_page_create_rename_archive_delete(api_server: RunningApi) -> None:
    client = api_server.client
    at = open_page(api_server, CATALOG)
    assert at.header[0].value == "Tätigkeiten & Projekte" and len(at.tabs) == 3
    at.text_input(key="new_name_activities").input("Meeting")
    button(at, "Tätigkeit anlegen").click().run()
    (item,) = client.list_items("activities")
    assert item["name"] == "Meeting" and item["color"].startswith("#")  # automatic colour

    at = open_page(api_server, CATALOG)
    at.text_input(key=f"name_activities_{item['id']}").input("Besprechung")
    at.button(key=f"save_activities_{item['id']}").click().run()
    assert client.list_items("activities")[0]["name"] == "Besprechung"

    at.button(key=f"archive_activities_{item['id']}").click().run()
    assert client.list_items("activities") == []
    assert client.list_items("activities", True)[0]["archived"] is True

    at.toggle(key="show_archived_activities").set_value(True).run()
    assert "(archiviert)" in "".join(e.label for e in at.expander)
    at.button(key=f"archive_activities_{item['id']}").click().run()  # restore
    assert client.list_items("activities")[0]["archived"] is False

    at.checkbox(key=f"confirm_activities_{item['id']}").check().run()
    at.button(key=f"delete_activities_{item['id']}").click().run()
    assert client.list_items("activities", True) == []


def test_custom_color_and_projects_tab(api_server: RunningApi) -> None:
    client = api_server.client
    at = open_page(api_server, CATALOG)
    at.text_input(key="new_name_projects").input("Alpha")
    at.checkbox(key="new_custom_projects").check()
    at.color_picker(key="new_color_projects").set_value("#AA0000")
    button(at, "Projekt anlegen").click().run()
    assert client.list_items("projects")[0]["color"] == "#AA0000"


def test_used_activity_cannot_be_deleted_and_says_why(api_server: RunningApi) -> None:
    client = api_server.client
    item = client.create_item("activities", "Meeting")
    client.start_tracking(item["id"])
    at = open_page(api_server, CATALOG)
    at.checkbox(key=f"confirm_activities_{item['id']}").check().run()
    at.button(key=f"delete_activities_{item['id']}").click().run()
    assert any("archivieren" in e.value for e in at.error)
    assert len(client.list_items("activities")) == 1


def test_duplicate_name_is_reported(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Meeting")
    at = open_page(api_server, CATALOG)
    at.text_input(key="new_name_activities").input("MEETING")
    button(at, "Tätigkeit anlegen").click().run()
    assert any("widerspricht" in e.value for e in at.error)


def test_catalog_widgets_have_help_texts(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Meeting")
    api_server.client.create_item("projects", "Alpha")
    at = open_page(api_server, CATALOG)
    for widget in all_help(at):
        assert widget.help, f"{widget.key or widget.label} has no help text"


def test_empty_catalog_gives_a_hint(api_server: RunningApi) -> None:
    at = open_page(api_server, CATALOG)
    assert any("Noch keine Tätigkeiten" in i.value for i in at.info)
    assert any("Noch keine Projekte" in i.value for i in at.info)


def test_unused_import_guard() -> None:
    assert ApiClient is not None
