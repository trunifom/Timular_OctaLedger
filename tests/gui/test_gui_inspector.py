"""GUI tests for AP-54: the inspector shows what is set up on each face and opens its editor."""

from streamlit.testing.v1 import AppTest

from octaledger.dashboard.views.faces import PENDING_KEY
from tests.conftest import RunningApi
from tests.gui.test_gui_devices_catalog import open_page

PAGE = "inspector"


def markdown_text(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def face_button(at: AppTest, did: str, face: int):  # type: ignore[no-untyped-def]
    return next(b for b in at.button if b.key == f"inspector_face_{did}_{face}")


def test_empty_state_explains_what_to_do(api_server: RunningApi) -> None:
    at = open_page(api_server, PAGE)
    assert at.header[0].value == "Würfel-Inspektor"
    assert any("So funktioniert der Würfel-Inspektor" in e.label for e in at.expander)
    assert any("noch kein Würfel eingerichtet" in i.value for i in at.info)


def test_time_cube_shows_activity_project_and_the_table(api_server: RunningApi) -> None:
    client = api_server.client
    cube = client.register_device("Büro")
    meeting = client.create_item("activities", "Meeting")
    alpha = client.create_item("projects", "Alpha")
    client.assign_face(cube["id"], 3, meeting["id"], alpha["id"])
    at = open_page(api_server, PAGE)
    assert not at.exception
    body = markdown_text(at)
    assert "Seite 3" in body and "Meeting" in body and "Alpha" in body  # first set-up face
    assert any(r for r in at.dataframe)  # all faces at a glance
    face_button(at, cube["id"], 5).click().run()
    assert "Seite 5" in markdown_text(at)
    assert any("Diese Seite startet keine Zeit" in i.value for i in at.info)


def test_clicking_a_number_changes_the_sheet_and_the_choice_is_remembered(
    api_server: RunningApi,
) -> None:
    client = api_server.client
    cube = client.register_device("Büro")
    meeting = client.create_item("activities", "Meeting")
    client.assign_face(cube["id"], 1, meeting["id"], None)
    at = open_page(api_server, PAGE)
    face_button(at, cube["id"], 2).click().run()
    assert at.session_state[f"inspector_face_{cube['id']}"] == 2
    at.sidebar.button(key="nav_overview").click().run()
    at.sidebar.button(key="nav_inspector").click().run()
    assert at.session_state[f"inspector_face_{cube['id']}"] == 2  # still the same face


def test_smart_home_cube_shows_every_step_of_the_chain(api_server: RunningApi) -> None:
    client = api_server.client
    cube = client.register_device("Licht")
    client.set_device_mode(cube["id"], "control")
    connection = client.create_integration("fake", "Zuhause", {"host": "h", "password": "richtig"})
    client.assign_steps(
        cube["id"],
        2,
        [
            {
                "integration_id": connection["id"],
                "label": "Abend",
                "params": {"action": "ping", "target": "lamp1"},
                "delay_ms": 0,
                "continue_on_error": False,
                "enabled": True,
                "condition": None,
            },
            {
                "integration_id": connection["id"],
                "label": "Abend",
                "params": {"action": "toggle"},
                "delay_ms": 700,
                "continue_on_error": True,
                "enabled": True,
                "condition": {"start": "18:00", "end": "23:00", "weekdays": ""},
            },
        ],
    )
    at = open_page(api_server, PAGE)
    assert not at.exception
    body = markdown_text(at)
    assert "Schritt 1" in body and "Schritt 2" in body and "Zuhause" in body
    assert "Anpingen" in body and "wartet vorher 700 ms" in body
    assert "nur zwischen 18:00 und 23:00 Uhr" in body and "löst diese Kette aus" in body
    assert "🎛 Smarthome" in body


def test_music_cube_shows_title_target_and_the_holder(api_server: RunningApi) -> None:
    client = api_server.client
    cube = client.register_device("Musik")
    client.set_device_mode(cube["id"], "music")
    at = open_page(api_server, PAGE)
    assert not at.exception
    assert any("Stille-Seite" in i.value for i in at.info)  # nothing set up: a silence face
    frames = list(at.dataframe)
    assert frames and any("Halterung" in str(f.value) for f in frames)  # the holder row


def test_edit_opens_the_editor_of_that_face(api_server: RunningApi) -> None:
    cube = api_server.client.register_device("Büro")
    at = open_page(api_server, PAGE)
    face_button(at, cube["id"], 4).click().run()
    edit = next(b for b in at.button if b.key == "inspector_edit")
    assert edit.help
    edit.click().run()
    assert not at.exception
    assert at.session_state["nav"] == "faces"
    assert at.session_state[f"faces_target_{cube['id']}"] == 4  # the editor shows face 4


def test_clearing_a_face_removes_its_setting(api_server: RunningApi) -> None:
    client = api_server.client
    cube = client.register_device("Büro")
    meeting = client.create_item("activities", "Meeting")
    client.assign_face(cube["id"], 1, meeting["id"], None)
    at = open_page(api_server, PAGE)
    clear = next(b for b in at.button if b.key == "inspector_clear")
    assert not clear.disabled
    clear.click().run()
    assert not at.exception
    assert (
        client.devices()[0]["faces"].get("1") is None
        or not client.devices()[0]["faces"]["1"]["activity_id"]
    )


def test_export_text_lists_the_cube(api_server: RunningApi) -> None:
    api_server.client.register_device("Büro")
    at = open_page(api_server, PAGE)
    exported = " ".join(c.value for c in at.code)
    assert "Einstellungen des Würfels" in exported and "Büro" in exported


def test_every_button_has_a_help_text(api_server: RunningApi) -> None:
    api_server.client.register_device("Büro")
    at = open_page(api_server, PAGE)
    missing = [b.key for b in at.button if b.key and b.key.startswith("inspector_") and not b.help]
    assert not missing, missing
    assert PENDING_KEY  # the constant the "edit" button uses exists
