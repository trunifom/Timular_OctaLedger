"""GUI tests for control mode: the mode switch, actions per face, live view, devices, start page."""

from datetime import datetime, timezone
from typing import Any

import pytest

from octaledger.dashboard.views.faces import target_key
from octaledger.domain.models import EventKind, RawEvent
from tests.conftest import FakeAgent, RunningApi
from tests.fake_adapter import FakeAdapter
from tests.gui.test_gui_core import button, texts
from tests.gui.test_gui_devices_catalog import open_page

FACES = "faces"
LIVE = "live"
DEVICES = "devices"


@pytest.fixture
def agent(api_server: RunningApi) -> FakeAgent:
    fake = FakeAgent()
    api_server.context.agent = fake
    return fake


def adapter_of(api: RunningApi) -> FakeAdapter:
    found = api.context.integrations._adapters["fake"]  # type: ignore[union-attr]  # noqa: SLF001
    assert isinstance(found, FakeAdapter)
    return found


def make_connection(api: RunningApi, name: str = "Licht") -> str:
    return str(
        api.client.create_integration("fake", name, {"host": "h", "password": "richtig"})["id"]
    )


def control_device(api: RunningApi) -> str:
    device = api.client.register_device("Steuerung")
    api.client.set_device_mode(device["id"], "control")
    return str(device["id"])


def prefix(did: str, face: int = 1) -> str:
    return f"faces_ac_{did}_{face}"


# ------------------------------------------------------------------------ mode switch


def test_the_mode_switch_turns_a_cube_into_a_controller(api_server: RunningApi) -> None:
    device = api_server.client.register_device("Würfel")
    at = open_page(api_server, FACES)
    assert at.radio(key=f"faces_mode_{device['id']}").value == "time"
    at.radio(key=f"faces_mode_{device['id']}").set_value("control").run()
    assert not at.exception
    assert api_server.client.devices()[0]["mode"] == "control"
    assert any("steuert" in c.value for c in at.caption)
    assert at.radio(key=f"faces_mode_{device['id']}").value == "control"


def test_a_running_time_entry_refuses_the_switch_and_the_switch_snaps_back(
    api_server: RunningApi,
) -> None:
    device = api_server.client.register_device("Würfel")  # the first tracker is the active one
    activity = api_server.client.create_item("activities", "Meeting")
    api_server.client.assign_face(device["id"], 1, activity["id"], None)
    api_server.context.tracking.record_event(
        RawEvent(device["id"], EventKind.FACE_CHANGE, 1, "c1", datetime.now(timezone.utc), 1)
    )
    assert api_server.client.status()["tracking"]["running"] is not None
    at = open_page(api_server, FACES)
    at.radio(key=f"faces_mode_{device['id']}").set_value("control").run()
    assert any("läuft gerade eine Zeit" in e.value for e in at.error)
    assert "OL-STATE-003" in texts(at)
    assert at.radio(key=f"faces_mode_{device['id']}").value == "time"  # reverted
    assert api_server.client.devices()[0]["mode"] == "time"


def test_switching_back_restores_the_activity_editor(api_server: RunningApi) -> None:
    make_connection(api_server)  # without one the editor only points to the connections page
    did = control_device(api_server)
    at = open_page(api_server, FACES)
    assert any(s.key == f"{prefix(did)}_label" for s in at.text_input)  # the action editor
    at.radio(key=f"faces_mode_{did}").set_value("time").run()
    assert api_server.client.devices()[0]["mode"] == "time"
    assert not any(s.key == f"{prefix(did)}_label" for s in at.text_input)


# ----------------------------------------------------------------------- the editor


def test_without_a_connection_the_editor_points_to_the_connections_page(
    api_server: RunningApi,
) -> None:
    control_device(api_server)
    at = open_page(api_server, FACES)
    assert any("noch keine eingeschaltete Verbindung" in i.value for i in at.info)
    assert any(b.key == "faces_to_connections" for b in at.button)


def test_a_switched_off_connection_is_not_offered(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    api_server.client.update_integration(cid, enabled=False)
    control_device(api_server)
    at = open_page(api_server, FACES)
    assert any("noch keine eingeschaltete Verbindung" in i.value for i in at.info)


def test_a_face_gets_a_named_action_and_the_assistant_moves_on(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    did = control_device(api_server)
    at = open_page(api_server, FACES)
    assert at.radio(key=target_key(did)).value == 1
    base = f"{prefix(did)}_{cid}"
    at.text_input(key=f"{base}_ping_target").input("wohnzimmer").run()
    at.text_input(key=f"{prefix(did)}_label").input("Schreibtischlampe").run()
    at.button(key=f"{prefix(did)}_save").click().run()
    assert not at.exception
    action = api_server.client.devices()[0]["actions"]["1"]
    assert action["label"] == "Schreibtischlampe" and action["integration_id"] == cid
    assert action["params"] == {"action": "ping", "target": "wohnzimmer"}
    assert any("Seite 1 heißt jetzt „Schreibtischlampe“" in s.value for s in at.success)
    assert at.radio(key=target_key(did)).value == 2
    picture = next(m.value for m in at.markdown if "<svg" in str(m.value))
    assert "Schreibti…" in picture  # the name shows in the picture (shortened to fit)


def test_saving_needs_a_name(api_server: RunningApi) -> None:
    make_connection(api_server)
    did = control_device(api_server)
    at = open_page(api_server, FACES)
    assert at.button(key=f"{prefix(did)}_save").disabled
    at.text_input(key=f"{prefix(did)}_label").input("Lampe").run()
    assert not at.button(key=f"{prefix(did)}_save").disabled


def test_an_invalid_action_is_reported_and_nothing_is_stored(api_server: RunningApi) -> None:
    make_connection(api_server)
    did = control_device(api_server)
    at = open_page(api_server, FACES)
    at.text_input(key=f"{prefix(did)}_label").input("Lampe").run()  # the required target is empty
    at.button(key=f"{prefix(did)}_save").click().run()
    assert any("Ziel" in e.value for e in at.error)
    assert api_server.client.devices()[0]["actions"] == {}


def test_a_pick_list_from_discovery_replaces_typing(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    did = control_device(api_server)
    at = open_page(api_server, FACES)
    at.button(key=f"{prefix(did)}_discover").click().run()
    pick = at.selectbox(key=f"{prefix(did)}_{cid}_ping_target")
    assert pick.options == ["Schreibtisch"]
    pick.select("1").run()
    at.button(key=f"{prefix(did)}_probe").click().run()
    assert any("gesendet" in s.value for s in at.success)
    assert adapter_of(api_server).calls[-1][2] == {"action": "ping", "target": "1"}
    assert api_server.client.devices()[0]["actions"] == {}  # trying saves nothing


def test_actions_that_act_on_every_trigger_carry_a_warning(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    did = control_device(api_server)
    at = open_page(api_server, FACES)
    assert not any("bei **jedem** Auslösen" in w.value for w in at.warning)
    at.selectbox(key=f"{prefix(did)}_{cid}_action").select_index(1).run()  # toggle
    assert any("bei **jedem** Auslösen" in w.value for w in at.warning)


def test_an_existing_action_is_shown_and_can_be_removed(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    did = control_device(api_server)
    api_server.client.assign_action(did, 1, cid, "Lampe", {"action": "toggle"})
    at = open_page(api_server, FACES)
    assert at.progress[0].text == "1 von 8 Seiten eingerichtet"  # actions count as set up
    assert at.radio(key=target_key(did)).value == 2  # the first face without an action
    at.radio(key=target_key(did)).set_value(1).run()
    assert at.text_input(key=f"{prefix(did)}_label").value == "Lampe"
    assert at.selectbox(key=f"{prefix(did)}_{cid}_action").value["id"] == "toggle"
    at.button(key=f"{prefix(did)}_clear").click().run()
    assert api_server.client.devices()[0]["actions"] == {}
    assert any("Seite 1 ist wieder frei" in s.value for s in at.success)


def test_all_inputs_of_the_action_editor_have_help_texts(api_server: RunningApi) -> None:
    make_connection(api_server)
    did = control_device(api_server)
    api_server.client.set_device_address(did, "AA:BB")
    at = open_page(api_server, FACES)
    widgets = [*at.selectbox, *at.text_input, *at.radio, *at.number_input, *at.checkbox]
    widgets += [b for b in at.button if not b.key.startswith("nav_")]
    assert widgets and [w.key for w in widgets if not w.help] == []


# --------------------------------------------------------------------------- live view


def test_the_live_view_of_a_controller_names_the_action(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    cid = make_connection(api_server)
    did = control_device(api_server)
    api_server.client.assign_action(did, 3, cid, "Schreibtischlampe", {"action": "toggle"})
    api_server.client.set_device_address(did, "AA:BB")
    api_server.client.connect_device(did)  # the fake cube reports face 3
    at = open_page(api_server, LIVE)
    assert not at.exception
    page = texts(at)
    assert "③ Die Aktion" in page and "**steuert** Dinge" in page
    assert "Seite 3: Die Aktion „Schreibtischlampe“ wird ausgelöst." in page
    assert "Die Aktion „Schreibtischlampe“ wird gesendet." in page  # in the history, too
    picture = next(m.value for m in at.markdown if "<svg" in str(m.value))
    assert "Schreibtis" in picture and "oben liegt Seite 3" in picture


def test_a_face_without_an_action_says_so(api_server: RunningApi, agent: FakeAgent) -> None:
    make_connection(api_server)
    did = control_device(api_server)
    api_server.client.set_device_address(did, "AA:BB")
    api_server.client.connect_device(did)
    at = open_page(api_server, LIVE)
    assert any("Seite 3 hat noch keine Aktion" in i.value for i in at.info)
    assert "Diese Seite hat keine Aktion." in texts(at)


def test_the_live_view_lists_the_last_sent_actions(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    cid = make_connection(api_server)
    did = control_device(api_server)
    api_server.client.assign_action(did, 3, cid, "Lampe", {"action": "toggle"})
    api_server.client.set_device_address(did, "AA:BB")
    api_server.client.connect_device(did)
    at = open_page(api_server, LIVE)
    assert any("Noch wurde keine Aktion gesendet" in c.value for c in at.caption)
    api_server.context.tracking.record_event(
        RawEvent(did, EventKind.FACE_CHANGE, 7, "c1", datetime.now(timezone.utc), 3)
    )
    api_server.context.integrations.process_due()  # type: ignore[union-attr]
    at = open_page(api_server, LIVE)
    page = texts(at)
    assert "Letzte Aktionen" not in page or "✅ gesendet" in page  # markdown escapes the brackets
    assert "Lampe" in page and "Licht" in page and "✅ gesendet" in page


def test_time_cubes_keep_their_live_view(api_server: RunningApi, agent: FakeAgent) -> None:
    device = api_server.client.register_device("Zeit")
    api_server.client.set_device_address(device["id"], "AA:BB")
    api_server.client.connect_device(device["id"])
    at = open_page(api_server, LIVE)
    assert "③ Die Software" in texts(at) and "Letzte Aktionen" not in texts(at)


# ------------------------------------------------------------------------ devices page


def test_the_devices_page_marks_a_controller_and_hides_the_activity_table(
    api_server: RunningApi,
) -> None:
    did = control_device(api_server)
    at = open_page(api_server, DEVICES)
    assert any("Steuerung" in e.label for e in at.expander)
    assert any("Steuerungsmodus" in i.value for i in at.info)
    assert not any(k.startswith("face_act_") for k in [s.key for s in at.selectbox])
    assert at.button(key=f"activate_{did}").disabled  # a controller never records time
    at.button(key=f"to_faces_{did}").click().run()
    assert at.header[0].value == "Seiten zuordnen"


def test_a_time_cube_keeps_its_calibration_table(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Meeting")
    api_server.client.register_device("Zeit")
    at = open_page(api_server, DEVICES)
    assert any(s.key and s.key.startswith("face_act_") for s in at.selectbox)
    assert not any("Steuerung" in e.label for e in at.expander)


# ------------------------------------------------------------ status bar and start page


def test_the_status_bar_names_a_controller(api_server: RunningApi, agent: FakeAgent) -> None:
    did = control_device(api_server)
    api_server.client.set_device_address(did, "AA:BB")
    api_server.client.connect_device(did)
    at = open_page(api_server, FACES)
    assert any("Steuerung (Steuerung)" in str(m.value) for m in at.markdown)


def test_the_status_api_reports_the_mode(api_server: RunningApi) -> None:
    control_device(api_server)
    api_server.client.register_device("Zeit")
    modes = {d["alias"]: d["mode"] for d in api_server.client.status()["devices"]}
    assert modes == {"Steuerung": "control", "Zeit": "time"}


def test_the_welcome_page_mentions_controlling_things(api_server: RunningApi) -> None:
    at = open_page(api_server, "start")
    page = texts(at)
    assert "Dinge steuern" in page and "Home Assistant, MQTT, Philips Hue" in page
    assert "Matter" in page and "Google Home" in page and "über Home Assistant" in page
    assert button(at, "Jetzt einrichten") is not None


def test_a_controller_counts_as_set_up_on_the_start_page(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    did = control_device(api_server)
    api_server.client.set_device_address(did, "AA:BB")
    for face in range(1, 9):
        api_server.client.assign_action(did, face, cid, f"Aktion {face}", {"action": "toggle"})
    at = open_page(api_server, "start")
    assert "Alles eingerichtet" in texts(at)


def describe(events: list[dict[str, Any]], control: bool) -> list[str]:
    from octaledger.dashboard.cube import FaceLabel
    from octaledger.dashboard.views.live import describe_event

    labels = {1: FaceLabel("Lampe", "#000000"), 2: FaceLabel()}
    return [describe_event(event, labels, control) for event in events]


def test_history_sentences_differ_by_mode() -> None:
    change = {"kind": "face_change", "value": 1}
    empty = {"kind": "face_change", "value": 2}
    base = {"kind": "baseline", "value": 1}
    gone = {"kind": "disconnect", "value": None}
    time_text = describe([change, base, gone], False)
    control_text = describe([change, empty, base, gone], True)
    assert time_text[0] == "Seite 1 („Lampe“) wurde angenommen."
    assert "Das startet noch nichts." in time_text[1] and "unsicher" in time_text[2]
    assert control_text[0].endswith("Die Aktion „Lampe“ wird gesendet.")
    assert control_text[1].endswith("Diese Seite hat keine Aktion.")
    assert "Das löst noch nichts aus." in control_text[2] and "unsicher" not in control_text[3]


def test_a_face_can_get_several_steps_with_delay_and_condition(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    did = control_device(api_server)
    at = open_page(api_server, FACES)
    base = prefix(did)
    at.text_input(key=f"{base}_label").input("Fokus").run()
    at.selectbox(key=f"{base}_{cid}_action").select_index(0).run()  # ping needs a target
    target_key = next(
        t.key for t in at.text_input if t.key and t.key.startswith(f"{base}_{cid}_ping")
    )
    at.text_input(key=target_key).input("licht").run()
    at.button(key=f"{base}_add").click().run()
    second = f"{base}_s1"
    assert at.number_input(key=f"{second}_delay").value == 0.0  # a new step starts with no delay
    at.button(key=f"{base}_drop").click().run()  # the form can shrink again ...
    assert not [w for w in at.number_input if w.key == f"{second}_delay"]
    at.button(key=f"{base}_add").click().run()  # ... and grow
    at.text_input(key=f"{second}_label").input("Musik").run()
    target2 = next(
        t.key for t in at.text_input if t.key and t.key.startswith(f"{second}_{cid}_ping")
    )
    at.text_input(key=target2).input("radio").run()
    at.number_input(key=f"{second}_delay").set_value(3.0).run()
    at.text_input(key=f"{second}_from").input("08:00").run()
    at.text_input(key=f"{second}_to").input("18:00").run()
    assert all(
        w.help for w in (at.number_input(key=f"{second}_delay"), at.checkbox(key=f"{second}_goon"))
    )
    at.button(key=f"{base}_save").click().run()
    chain = api_server.client.action_chains(did)["1"]
    assert [(s["label"], s["delay_ms"]) for s in chain] == [("Fokus", 0), ("Musik", 3000)]
    assert chain[1]["condition"] == {"start": "08:00", "end": "18:00", "weekdays": ""}
