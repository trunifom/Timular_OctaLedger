"""GUI tests for the connections page and the generic form renderer."""

from datetime import datetime, timedelta, timezone

import pytest
from streamlit.testing.v1 import AppTest

from octaledger.domain.models import IntegrationJob
from tests.conftest import RunningApi
from tests.fake_adapter import FakeAdapter
from tests.gui.test_gui_core import texts
from tests.gui.test_gui_devices_catalog import open_page

CONNECTIONS = "connections"


def adapter_of(api: RunningApi) -> FakeAdapter:
    adapter = api.context.integrations._adapters["fake"]  # type: ignore[union-attr]  # noqa: SLF001
    assert isinstance(adapter, FakeAdapter)
    return adapter


def make_connection(api: RunningApi, name: str = "Licht") -> str:
    created = api.client.create_integration(
        "fake", name, {"host": "10.0.0.5", "password": "richtig"}
    )
    return str(created["id"])


def fill_new(at: AppTest, name: str = "Licht", **overrides: str) -> None:
    values = {"host": "10.0.0.5", "password": "richtig"} | overrides
    at.text_input(key="new_conn_name_fake").input(name)
    for field, value in values.items():
        at.text_input(key=f"new_conn_fake_{field}").input(value)
    at.run()


# ----------------------------------------------------------------------------- page


def test_title_help_and_empty_state(api_server: RunningApi) -> None:
    at = open_page(api_server, CONNECTIONS)
    assert at.header[0].value == "Verbindungen"
    assert any("So funktioniert die Seite" in e.label for e in at.expander)
    assert any("Noch keine Verbindung angelegt" in i.value for i in at.info)
    assert any("Noch wurde keine Aktion gesendet" in c.value for c in at.caption)


def test_a_connection_is_created_from_the_description_and_secrets_stay_hidden(
    api_server: RunningApi,
) -> None:
    at = open_page(api_server, CONNECTIONS)
    fill_new(at)
    at.button(key="new_conn_create").click().run()
    assert not at.exception
    (created,) = api_server.client.integrations()
    assert created["name"] == "Licht" and created["config"]["host"] == "10.0.0.5"
    assert created["secrets_set"] == ["password"]
    page = texts(at)
    assert any("„Licht“ wurde angelegt" in s.value for s in at.success)
    assert "Passwort: gespeichert ✔" in page and "richtig" not in page
    assert all("richtig" not in str(w.value) for w in [*at.text_input, *at.markdown])


def test_missing_required_fields_are_explained_in_german_with_the_code(
    api_server: RunningApi,
) -> None:
    at = open_page(api_server, CONNECTIONS)
    at.text_input(key="new_conn_name_fake").input("Licht").run()
    at.text_input(key="new_conn_fake_password").input("richtig").run()
    at.button(key="new_conn_create").click().run()
    assert any("Adresse" in e.value for e in at.error)
    assert "OL-VALID-001" in texts(at) and api_server.client.integrations() == []


def test_a_duplicate_name_is_reported(api_server: RunningApi) -> None:
    make_connection(api_server, "Licht")
    at = open_page(api_server, CONNECTIONS)
    fill_new(at, name="licht")
    at.button(key="new_conn_create").click().run()
    assert "OL-STATE-002" in texts(at) and len(api_server.client.integrations()) == 1


# -------------------------------------------------------------- testing and pairing


def test_the_connection_test_reports_success_and_failure(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    at = open_page(api_server, CONNECTIONS)
    at.button(key=f"conn_check_{cid}").click().run()
    assert any("Verbunden mit 10.0.0.5." in s.value for s in at.success)
    api_server.client.update_integration(cid, values={"password": "falsch"})
    at = open_page(api_server, CONNECTIONS)
    at.button(key=f"conn_check_{cid}").click().run()
    assert any("Zugangsdaten abgelehnt" in e.value for e in at.error)
    assert "OL-INTEG-001" in texts(at)
    assert "falsch" not in texts(at)


def test_pairing_stores_what_the_adapter_returns(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    at = open_page(api_server, CONNECTIONS)
    at.button(key=f"conn_pair_{cid}").click().run()
    assert any("Gekoppelt!" in s.value for s in at.success)
    assert api_server.client.integrations()[0]["config"]["host"] == "bridge.local"


# --------------------------------------------------------------------- trying actions


def test_an_action_can_be_tried_with_a_pick_list_from_discovery(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    at = open_page(api_server, CONNECTIONS)
    assert any(t.key == f"conn_try_{cid}_ping_target" for t in at.text_input)  # free text first
    at.button(key=f"conn_discover_{cid}").click().run()
    pick = at.selectbox(key=f"conn_try_{cid}_ping_target")  # now a list of what was found
    assert pick.options == ["Schreibtisch"]
    pick.select("1").run()
    at.button(key=f"conn_probe_{cid}").click().run()
    assert any("gesendet" in s.value for s in at.success)
    assert adapter_of(api_server).calls[-1][2] == {"action": "ping", "target": "1"}


def test_trying_with_a_missing_field_sends_nothing(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    at = open_page(api_server, CONNECTIONS)
    at.button(key=f"conn_probe_{cid}").click().run()
    assert any("Ziel" in e.value for e in at.error) and adapter_of(api_server).calls == []


def test_actions_that_act_on_every_send_carry_a_warning(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    at = open_page(api_server, CONNECTIONS)
    assert not any("bei **jedem** Senden" in w.value for w in at.warning)  # ping is harmless
    toggle = at.selectbox(key=f"conn_action_{cid}")
    toggle.select_index(1).run()
    assert any("bei **jedem** Senden" in w.value for w in at.warning)


# ------------------------------------------------------------------ changing things


def test_settings_can_be_changed_and_a_blank_password_keeps_the_secret(
    api_server: RunningApi,
) -> None:
    cid = make_connection(api_server)
    at = open_page(api_server, CONNECTIONS)
    at.text_input(key=f"conn_name_{cid}").input("Lampe")
    at.text_input(key=f"conn_edit_{cid}_host").input("10.0.0.9").run()
    at.button(key=f"conn_save_{cid}").click().run()
    (changed,) = api_server.client.integrations()
    assert changed["name"] == "Lampe" and changed["config"]["host"] == "10.0.0.9"
    assert changed["secrets_set"] == ["password"]
    assert api_server.context.integrations.check(cid).startswith("Verbunden")  # type: ignore[union-attr]


def test_a_connection_can_be_switched_off_and_on(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    at = open_page(api_server, CONNECTIONS)
    at.button(key=f"conn_toggle_{cid}").click().run()
    assert api_server.client.integrations()[0]["enabled"] is False
    assert any("Ausgeschaltet" in c.value for c in at.caption)
    at.button(key=f"conn_toggle_{cid}").click().run()
    assert api_server.client.integrations()[0]["enabled"] is True


def test_deleting_needs_a_confirmation_and_is_refused_while_a_face_uses_it(
    api_server: RunningApi,
) -> None:
    cid = make_connection(api_server)
    device = api_server.client.register_device("Würfel")
    api_server.client.assign_action(device["id"], 1, cid, "Lampe", {"action": "toggle"})
    at = open_page(api_server, CONNECTIONS)
    assert at.button(key=f"conn_delete_{cid}").disabled  # not before the confirmation
    at.checkbox(key=f"conn_confirm_{cid}").check().run()
    at.button(key=f"conn_delete_{cid}").click().run()
    assert "OL-STATE-002" in texts(at) and len(api_server.client.integrations()) == 1
    api_server.client.clear_action(device["id"], 1)
    at.button(key=f"conn_delete_{cid}").click().run()
    assert api_server.client.integrations() == []


# --------------------------------------------------------------------------- history


def test_the_history_shows_every_result(api_server: RunningApi) -> None:
    cid = make_connection(api_server)
    now = datetime.now(timezone.utc)
    with api_server.storage.transaction() as repos:
        repos.jobs.enqueue(
            IntegrationJob(
                "a",
                cid,
                "Schreibtischlampe",
                {"action": "toggle"},
                expires_at=now + timedelta(seconds=30),
                face=2,
            )
        )
    at = open_page(api_server, CONNECTIONS)
    frame = at.dataframe[0].value
    assert list(frame["Aktion"]) == ["Schreibtischlampe"] and list(frame["Seite"]) == [2]
    assert list(frame["Ergebnis"]) == ["⏳ wartet"]
    api_server.context.integrations.process_due()  # type: ignore[union-attr]
    at = open_page(api_server, CONNECTIONS)
    assert list(at.dataframe[0].value["Ergebnis"]) == ["✅ gesendet"]


# ------------------------------------------------------------------------- general


def test_every_input_has_a_help_text(api_server: RunningApi) -> None:
    make_connection(api_server)
    at = open_page(api_server, CONNECTIONS)
    widgets = [*at.selectbox, *at.text_input, *at.number_input, *at.checkbox]
    widgets += [b for b in at.button if not b.key.startswith("nav_")]
    missing = [w.key for w in widgets if not w.help]
    assert widgets and missing == []


def test_the_page_explains_when_control_mode_is_unavailable(api_server: RunningApi) -> None:
    api_server.context.integrations = None
    at = open_page(api_server, CONNECTIONS)
    assert "OL-API-002" in texts(at) and not at.exception


# --------------------------------------------------------- the generic form renderer


def forms_app() -> None:
    """AppTest script: every field kind, a mixed pick list and a stored secret."""
    from typing import Any

    import streamlit as st

    from octaledger.dashboard.forms import render_fields

    def field(name: str, kind: str, **extra: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "name": name,
            "label": name.title(),
            "kind": kind,
            "required": False,
            "help": "",
            "default": None,
            "placeholder": "",
            "choices": [],
            "minimum": None,
            "maximum": None,
            "choices_from": [],
        }
        return base | extra

    fields = [
        field("host", "text", required=True),
        field("port", "int", default=80, minimum=1, maximum=65535),
        field("brightness", "int", minimum=1, maximum=100),
        field("secure", "bool"),
        field(
            "mode",
            "choice",
            default="b",
            choices=[{"value": "a", "label": "Alpha"}, {"value": "b", "label": "Beta"}],
        ),
        field("password", "password"),
        field("entity", "text", choices_from=["light", "switch"]),
    ]
    st.session_state["result"] = render_fields(
        fields,
        key_prefix="t",
        secrets_set=["password"],
        discovered={
            "light": [{"id": "light.a", "name": "A"}],
            "switch": [{"id": "switch.b", "name": "B"}],
        },
    )


def test_every_kind_of_field_becomes_a_widget_with_help() -> None:
    at = AppTest.from_function(forms_app).run()
    assert not at.exception
    assert at.text_input(key="t_host").label == "Host *"  # required fields are marked
    assert at.number_input(key="t_port").value == 80
    assert at.selectbox(key="t_mode").value == "b"
    assert at.text_input(key="t_password").proto.type == 1  # a password field
    assert "Gespeichert: leer lassen" in at.text_input(key="t_password").help
    assert at.text_input(key="t_host").help and at.checkbox(key="t_secure").help  # fallback help
    # Empty texts and empty numbers are left out, switches are always reported.
    assert at.session_state["result"] == {"port": 80, "secure": False, "mode": "b"}


def test_entered_values_are_returned_and_stripped() -> None:
    at = AppTest.from_function(forms_app).run()
    at.text_input(key="t_host").input("  10.0.0.5 ").run()
    at.number_input(key="t_brightness").set_value(40).run()
    at.checkbox(key="t_secure").check().run()
    at.selectbox(key="t_mode").select("a").run()
    at.text_input(key="t_password").input("geheim").run()
    assert at.session_state["result"] == {
        "host": "10.0.0.5",
        "port": 80,
        "brightness": 40,
        "secure": True,
        "mode": "a",
        "password": "geheim",
    }


def test_a_pick_list_merges_categories_and_names_them() -> None:
    at = AppTest.from_function(forms_app).run()
    pick = at.selectbox(key="t_entity")
    assert pick.options == ["A (light)", "B (switch)"]
    pick.select("switch.b").run()
    assert at.session_state["result"]["entity"] == "switch.b"


def test_required_marker_and_pick_list_helpers() -> None:
    from octaledger.dashboard.forms import field_label, picker_options

    assert field_label({"label": "Adresse", "required": True}) == "Adresse *"
    assert field_label({"label": "Port", "required": False}) == "Port"
    field = {"choices_from": ["lights"]}
    assert picker_options(field, None) == [] and picker_options(field, {}) == []
    assert picker_options({"choices_from": []}, {"lights": [{"id": "1", "name": "x"}]}) == []
    found = picker_options(field, {"lights": [{"id": "1", "name": "Lampe"}]})
    assert found == [{"id": "1", "label": "Lampe"}]  # a single category needs no suffix


@pytest.mark.parametrize("name", ["host", "port"])
def test_the_page_script_does_not_leak_secrets_through_widget_state(
    api_server: RunningApi, name: str
) -> None:
    make_connection(api_server)
    at = open_page(api_server, CONNECTIONS)
    assert "richtig" not in repr(
        at.session_state[f"conn_edit_{api_server.client.integrations()[0]['id']}_{name}"]
    )
