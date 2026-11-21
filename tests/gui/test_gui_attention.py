"""GUI tests for the attention panel (connection loss with a grace period, gap question)."""

from datetime import datetime, timedelta, timezone

from octaledger.domain.models import Device, EventKind, RawEvent
from tests.conftest import RunningApi
from tests.gui.test_gui_devices_catalog import open_page


def lose_link(api: RunningApi, *, ended: bool) -> str:
    """Run an entry, lose the link; with ``ended`` the grace period is over (gap question)."""
    activity = api.client.create_item("activities", "Meeting")["id"]
    with api.storage.transaction() as repos:
        device = repos.devices.add(Device(alias="Büro"))
        repos.mappings.assign(device.id, 1, activity)
    tracking = api.context.tracking
    tracking.set_active_device(device.id)
    now = datetime.now(timezone.utc)
    lost = now - timedelta(minutes=60 if ended else 1)
    for kind, value, at in (
        (EventKind.FACE_CHANGE, 1, lost - timedelta(minutes=30)),
        (EventKind.DISCONNECT, None, lost),
    ):
        tracking.record_event(
            RawEvent(
                device_id=device.id,
                kind=kind,
                sequence=0,
                connection_id="c",
                raw_value=value,
                received_at=at,
            )
        )
    if ended:
        assert len(tracking.watchdog()) == 1
    return activity


def entries(api: RunningApi) -> list[dict]:  # type: ignore[type-arg]
    now = datetime.now(timezone.utc)
    return api.client.journal(now - timedelta(days=2), now + timedelta(days=1))


def keys(at) -> list[str]:  # type: ignore[no-untyped-def]
    return [b.key for b in at.button]


def test_a_waiting_connection_explains_when_the_time_will_stop(api_server: RunningApi) -> None:
    lose_link(api_server, ended=False)
    at = open_page(api_server, "journal")
    assert any("Verbindung zu „Büro“ verloren" in w.value for w in at.warning)
    assert any("Verlusts beendet" in w.value for w in at.warning)


def test_no_question_without_a_problem(api_server: RunningApi) -> None:
    at = open_page(api_server, "journal")
    assert not any(k.startswith("att_") for k in keys(at))


def test_the_gap_question_offers_four_answers_on_every_page(api_server: RunningApi) -> None:
    lose_link(api_server, ended=True)
    for page in ("overview", "journal"):
        at = open_page(api_server, page)
        labels = [b.label for b in at.button if b.key and b.key.startswith("att_")]
        assert labels == [
            "Lücke behalten",
            "Lücke leer lassen",
            "Anderer Tätigkeit zuordnen",
            "Nichts tun",
        ], page
        assert all(b.help for b in at.button if b.key and b.key.startswith("att_")), page


def test_keep_extends_the_entry_and_removes_the_question(api_server: RunningApi) -> None:
    lose_link(api_server, ended=True)
    at = open_page(api_server, "journal")
    key = next(k for k in keys(at) if k.startswith("att_keep_"))
    at.button(key=key).click().run()
    assert not at.exception
    assert api_server.client.attention()["items"] == []
    (entry,) = entries(api_server)
    assert entry["duration_seconds"] > 29 * 60  # the entry now reaches over the gap


def test_discard_leaves_the_entry_as_it_was(api_server: RunningApi) -> None:
    lose_link(api_server, ended=True)
    at = open_page(api_server, "journal")
    at.button(key=next(k for k in keys(at) if k.startswith("att_discard_"))).click().run()
    assert api_server.client.attention()["items"] == []
    (entry,) = entries(api_server)
    assert entry["duration_seconds"] == 30 * 60


def test_assign_needs_a_second_step_with_an_activity(api_server: RunningApi) -> None:
    lose_link(api_server, ended=True)
    api_server.client.create_item("activities", "Reise")
    at = open_page(api_server, "journal")
    at.button(key=next(k for k in keys(at) if k.startswith("att_assign_") and "_go_" not in k))
    first = next(k for k in keys(at) if k.startswith("att_assign_") and "_go_" not in k)
    assert not any("_go_" in k for k in keys(at))  # nothing happens before the click
    at.button(key=first).click().run()
    go = next(k for k in keys(at) if "_go_" in k)
    assert [s.label for s in at.selectbox if s.key.startswith("att_")] == [
        "Tätigkeit für die Lücke",
        "Projekt (optional)",
    ]
    at.button(key=go).click().run()
    assert api_server.client.attention()["items"] == []
    assert len(entries(api_server)) == 2  # the entry and the booked gap


def test_dismiss_changes_nothing(api_server: RunningApi) -> None:
    lose_link(api_server, ended=True)
    at = open_page(api_server, "journal")
    at.button(key=next(k for k in keys(at) if k.startswith("att_dismiss_"))).click().run()
    assert api_server.client.attention()["items"] == []
    (entry,) = entries(api_server)
    assert entry["duration_seconds"] == 30 * 60


def test_the_settings_page_offers_the_grace_period(api_server: RunningApi) -> None:
    at = open_page(api_server, "settings")
    grace = at.number_input(key="set_grace")
    assert grace.value == 300 and "Voreinstellung: 300 Sekunden" in grace.help
    api_server.client.update_settings({"tracking": {"disconnect_grace_seconds": 120}})
    assert api_server.client.get_settings()["tracking"]["disconnect_grace_seconds"] == 120


def test_button_section_and_battery_setting_are_on_the_pages(api_server: RunningApi) -> None:
    device = api_server.client.register_device("Büro")
    at = open_page(api_server, "devices")
    assert at.selectbox(key=f"button_short_{device['id']}").value == "none"
    assert "Nichts tun" in at.selectbox(key=f"button_long_{device['id']}").options[0]
    assert at.selectbox(key=f"button_short_{device['id']}").help
    at.selectbox(key=f"button_long_{device['id']}").select("stop").run()
    assert api_server.client.device_buttons(device["id"])["long"] == "stop"
    page = open_page(api_server, "settings")
    battery = page.number_input(key="set_battery")
    assert battery.value == 20 and "Voreinstellung: 20 %" in battery.help


def test_a_battery_reminder_can_be_acknowledged(api_server: RunningApi) -> None:
    from octaledger.domain.attention import AttentionItem, AttentionKind

    with api_server.storage.transaction() as repos:
        repos.attention.add(
            AttentionItem(
                kind=AttentionKind.REMINDER,
                created_at=datetime.now(timezone.utc),
                payload={"reason": "battery", "alias": "Büro", "percent": 12},
            )
        )
    at = open_page(api_server, "journal")
    assert any("Batterie von „Büro“ fast leer" in w.value for w in at.warning)
    key = next(k for k in keys(at) if k.startswith("att_ack_"))
    at.button(key=key).click().run()
    assert api_server.client.attention()["items"] == []


def test_the_working_day_settings_are_off_by_default_and_save(api_server: RunningApi) -> None:
    at = open_page(api_server, "settings")
    assert at.text_input(key="set_workday_end").value == ""
    assert "Voreinstellung" in at.text_input(key="set_workday_end").help
    assert at.number_input(key="set_idle").value == 0
    assert at.number_input(key="set_running_hours").value == 0
    assert at.multiselect(key="set_workdays").value == ["1", "2", "3", "4", "5"]
    assert all(w.help for w in (at.text_input(key="set_no_timer"), at.number_input(key="set_idle")))
    api_server.client.update_settings({"work": {"workday_end": "17:30", "idle_minutes": 15}})
    again = open_page(api_server, "settings")
    assert again.text_input(key="set_workday_end").value == "17:30"
    assert again.number_input(key="set_idle").value == 15
    assert not again.button(key="set_reset").disabled  # something differs from the defaults


def test_idle_and_auto_stop_questions_have_their_answers(api_server: RunningApi) -> None:
    from octaledger.domain.attention import AttentionItem, AttentionKind

    now = datetime.now(timezone.utc)
    with api_server.storage.transaction() as repos:
        repos.attention.add(
            AttentionItem(
                kind=AttentionKind.IDLE,
                created_at=now,
                payload={"idle_since": (now - timedelta(minutes=20)).isoformat()},
            )
        )
        repos.attention.add(
            AttentionItem(
                kind=AttentionKind.AUTO_STOP,
                created_at=now,
                payload={"ended_at": (now - timedelta(hours=1)).isoformat()},
            )
        )
    at = open_page(api_server, "journal")
    labels = [b.label for b in at.button if b.key and b.key.startswith("att_")]
    assert "Zeit behalten" in labels and "Als Pause buchen" in labels and "So lassen" in labels
    assert all(b.help for b in at.button if b.key and b.key.startswith("att_"))


def test_notification_tray_and_autostart_controls(api_server: RunningApi) -> None:
    from octaledger.infrastructure.system.autostart import Autostart

    class Memory:
        value: str | None = None

        def read(self, name: str) -> str | None:
            return self.value

        def write(self, name: str, value: str) -> None:
            self.value = value

        def delete(self, name: str) -> None:
            self.value = None

    api_server.context.autostart = Autostart(Memory(), available=True)
    at = open_page(api_server, "settings")
    toast, tray = at.toggle(key="set_toast"), at.toggle(key="set_tray")
    assert toast.value is False and "Voreinstellung: aus" in toast.help
    assert tray.help and at.text_input(key="set_quiet_start").value == "22:00"
    switch = at.toggle(key="set_autostart")
    assert switch.value is False and switch.help
    switch.set_value(True).run()
    assert api_server.client.autostart()["enabled"] is True
    assert at.toggle(key="set_autostart").value is True


def test_autostart_section_explains_when_unavailable(api_server: RunningApi) -> None:
    from octaledger.infrastructure.system.autostart import Autostart

    api_server.context.autostart = Autostart(available=False)
    at = open_page(api_server, "settings")
    assert any("nur unter Windows" in i.value for i in at.info)
    assert not [t for t in at.toggle if t.key == "set_autostart"]
