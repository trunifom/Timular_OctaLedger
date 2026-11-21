"""GUI tests for the start page: welcome, guided setup and the manual."""

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from octaledger.dashboard.views import start
from octaledger.dashboard.views.start import setup_state
from octaledger.infrastructure.ble.protocol import ORIENTATION_SERVICE_UUID
from octaledger.infrastructure.ble.scanner import ScanResult
from tests.conftest import FakeAgent, RunningApi
from tests.gui.test_gui_core import app_script, texts
from tests.gui.test_gui_devices_catalog import open_page

START = "start"


@pytest.fixture
def agent(api_server: RunningApi) -> FakeAgent:
    fake = FakeAgent()
    api_server.context.agent = fake
    return fake


def open_fresh(api: RunningApi) -> AppTest:
    """Open the dashboard like a brand-new browser tab (no page chosen yet)."""
    at = AppTest.from_function(app_script, default_timeout=30)
    at.session_state["_client"] = api.client
    return at.run()


def section(at: AppTest, name: str) -> AppTest:
    return at.radio(key="start_section").set_value(name).run()


def device_dict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "is_active": True,
        "has_address": True,
        "configured_faces": 0,
        "status": None,
    }
    return base | overrides


# ----------------------------------------------------------------------- pure helpers


def test_setup_state_follows_the_real_device_data() -> None:
    assert setup_state([]).next_step == "connect" and not setup_state([]).has_device
    assert setup_state([device_dict(has_address=False)]).next_step == "connect"
    assert setup_state([device_dict(configured_faces=3)]).next_step == "faces"
    complete = setup_state([device_dict(configured_faces=8, status={"state": "ready"})])
    assert complete.next_step == "done" and complete.complete and complete.connected
    # the active tracker decides, not the first one in the list
    mixed = [device_dict(is_active=False, configured_faces=8), device_dict(configured_faces=2)]
    assert setup_state(mixed).faces_done == 2


# ------------------------------------------------------------------------ default page


def test_a_new_session_opens_on_the_start_page(api_server: RunningApi) -> None:
    at = open_fresh(api_server)
    assert not at.exception
    assert at.header[0].value == "Startseite"
    assert at.sidebar.button(key="nav_start").proto.type == "primary"


# ------------------------------------------------------------------------------ welcome


def test_welcome_explains_the_cube_and_its_uses(api_server: RunningApi) -> None:
    at = open_page(api_server, START)
    page = texts(at)
    assert "Was ist der Würfel?" in page and "achtseitiger Würfel" in page
    assert "Wofür Sie OctaLedger einsetzen können" in page and "Lokal und privat" in page
    assert "So geht es los" in page
    picture = next(m.value for m in at.markdown if "<svg" in str(m.value))
    assert "Coding" in picture and "Meeting" in picture  # example faces, labelled as such
    assert any("Beispiel" in c.value for c in at.caption)


def test_banner_points_to_connecting_the_cube_first(api_server: RunningApi) -> None:
    at = open_page(api_server, START)
    assert "Nächster Schritt: Ihren Würfel verbinden" in texts(at)
    at.button(key="start_go_setup").click().run()
    assert at.radio(key="start_section").value == "Einrichten"


def test_banner_asks_for_the_faces_once_the_cube_is_known(api_server: RunningApi) -> None:
    device = api_server.client.register_device("Würfel")
    api_server.client.set_device_address(device["id"], "AA:BB")
    activity = api_server.client.create_item("activities", "Meeting")
    api_server.client.assign_face(device["id"], 1, activity["id"], None)
    at = open_page(api_server, START)
    assert "1 von 8 Seiten sind eingerichtet" in texts(at)
    assert any(b.key == "start_go_faces" for b in at.button)


def test_banner_celebrates_a_complete_setup(api_server: RunningApi) -> None:
    device = api_server.client.register_device("Würfel")
    api_server.client.set_device_address(device["id"], "AA:BB")
    for number in range(1, 9):
        activity = api_server.client.create_item("activities", f"T{number}")
        api_server.client.assign_face(device["id"], number, activity["id"], None)
    at = open_page(api_server, START)
    assert "Alles eingerichtet" in texts(at)
    assert {"start_go_overview", "start_go_live"} <= {b.key for b in at.button}


# ------------------------------------------------------------------------------- setup


def tracker(address: str = "AA:BB") -> ScanResult:
    return ScanResult(address, "Timeular Tra", -52, (), False)


def test_one_search_and_one_click_register_assign_and_connect(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    agent.scan_results = [ScanResult("CC:DD", "Kopfhörer", -40, (), False), tracker()]
    at = open_page(api_server, START)
    section(at, "Einrichten")
    at.button(key="start_scan").click().run()
    assert not at.exception
    pick = at.selectbox(key="start_pick")
    assert "vermutlich Ihr Würfel" in pick.options[0]  # the probable cube is listed first
    at.button(key="start_use").click().run()
    (device,) = api_server.client.devices()
    assert device["alias"] == "Mein Würfel" and device["has_address"]
    assert agent.started == [device["id"]]
    # The fake cube is ready at once, so the page already shows the finished first step.
    assert "„Mein Würfel“ ist eingerichtet" in texts(at) and "Bereit" in texts(at)


def test_a_chosen_name_is_used(api_server: RunningApi, agent: FakeAgent) -> None:
    agent.scan_results = [tracker()]
    at = open_page(api_server, START)
    section(at, "Einrichten")
    at.text_input(key="start_alias").input("Büro").run()
    at.button(key="start_scan").click().run()
    at.button(key="start_use").click().run()
    assert [d["alias"] for d in api_server.client.devices()] == ["Büro"]


def test_without_a_name_the_cube_cannot_be_used(api_server: RunningApi, agent: FakeAgent) -> None:
    agent.scan_results = [tracker()]
    at = open_page(api_server, START)
    section(at, "Einrichten")
    at.text_input(key="start_alias").input("   ").run()
    at.button(key="start_scan").click().run()
    assert at.button(key="start_use").disabled


def test_an_unrecognised_device_list_gets_a_helpful_warning(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    agent.scan_results = [ScanResult("CC:DD", "Kopfhörer", -40, (), False)]
    at = open_page(api_server, START)
    section(at, "Einrichten")
    at.button(key="start_scan").click().run()
    assert any("nicht erkannt" in w.value for w in at.warning)
    assert at.button(key="start_use") is not None  # the user may still pick another device


def test_a_service_advertising_device_counts_as_the_cube(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    agent.scan_results = [ScanResult("AA", None, -80, (ORIENTATION_SERVICE_UUID,), True)]
    at = open_page(api_server, START)
    section(at, "Einrichten")
    at.button(key="start_scan").click().run()
    assert not any("nicht erkannt" in w.value for w in at.warning)


def test_an_empty_search_explains_what_to_check(api_server: RunningApi, agent: FakeAgent) -> None:
    agent.scan_results = []
    at = open_page(api_server, START)
    section(at, "Einrichten")
    at.button(key="start_scan").click().run()
    assert any("Bluetooth am Computer eingeschaltet" in i.value for i in at.info)


def test_a_registered_cube_without_address_is_reused_not_duplicated(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    existing = api_server.client.register_device("Schon da")
    agent.scan_results = [tracker()]
    at = open_page(api_server, START)
    section(at, "Einrichten")
    assert not any(t.key == "start_alias" for t in at.text_input)  # no second name needed
    at.button(key="start_scan").click().run()
    at.button(key="start_use").click().run()
    (device,) = api_server.client.devices()
    assert device["id"] == existing["id"] and device["has_address"]


def test_steps_unlock_as_the_setup_progresses(api_server: RunningApi) -> None:
    at = open_page(api_server, START)
    section(at, "Einrichten")
    assert at.progress[0].text == "0 von 3 Schritten erledigt"
    assert at.button(key="start_open_faces").disabled and at.button(key="start_try_live").disabled
    device = api_server.client.register_device("Würfel")
    api_server.client.set_device_address(device["id"], "AA:BB")
    at = open_page(api_server, START)
    section(at, "Einrichten")
    assert at.progress[0].text == "1 von 3 Schritten erledigt"
    assert not at.button(key="start_open_faces").disabled


# ------------------------------------------------------------------------------ manual


def test_manual_shows_chapters_of_the_real_documentation(api_server: RunningApi) -> None:
    at = open_page(api_server, START)
    section(at, "Handbuch")
    assert not at.exception
    chapter = at.selectbox(key="start_chapter_BENUTZERHANDBUCH.md")
    assert chapter.options[0] == "Überblick" and len(chapter.options) > 10
    assert any("Schnellstart" in o for o in chapter.options)
    assert "](#" not in "\n".join(str(m.value) for m in at.markdown)  # no dead anchors


def test_manual_search_filters_the_chapters(api_server: RunningApi) -> None:
    at = open_page(api_server, START)
    section(at, "Handbuch")
    all_chapters = len(at.selectbox(key="start_chapter_BENUTZERHANDBUCH.md").options)
    at.text_input(key="start_doc_search_BENUTZERHANDBUCH.md").input("Sicherung").run()
    hits = at.selectbox(key="start_chapter_BENUTZERHANDBUCH.md").options
    assert 0 < len(hits) < all_chapters
    at.text_input(key="start_doc_search_BENUTZERHANDBUCH.md").input("qwertzuiop-xyz").run()
    assert any("Kein Kapitel enthält" in i.value for i in at.info)


def test_manual_offers_the_installation_guide_too(api_server: RunningApi) -> None:
    at = open_page(api_server, START)
    section(at, "Handbuch")
    at.selectbox(key="start_doc").select("Installation und Betrieb").run()
    assert not at.exception
    assert at.selectbox(key="start_chapter_INSTALLATION.md").options


def test_manual_explains_when_the_documentation_is_missing(
    api_server: RunningApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(start, "load_document", lambda _name: None)
    at = open_page(api_server, START)
    section(at, "Handbuch")
    assert any("Die Dokumentation wurde nicht gefunden" in w.value for w in at.warning)


def test_every_start_page_input_has_a_help_text(api_server: RunningApi, agent: FakeAgent) -> None:
    agent.scan_results = [tracker()]
    at = open_page(api_server, START)
    section(at, "Einrichten")
    at.button(key="start_scan").click().run()
    widgets = [*at.selectbox, *at.radio, *at.text_input]
    widgets += [b for b in at.button if not b.key.startswith("nav_")]
    assert widgets and all(w.help for w in widgets)
    section(at, "Handbuch")
    assert all(w.help for w in [*at.selectbox, *at.text_input])
