"""GUI tests for the attention panel (connection loss with a grace period, gap question)."""

from datetime import UTC, datetime, timedelta

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
    now = datetime.now(UTC)
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
    now = datetime.now(UTC)
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
                created_at=datetime.now(UTC),
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

    now = datetime.now(UTC)
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


def test_the_balance_tab_shows_target_actual_and_absences(api_server: RunningApi) -> None:
    from datetime import date

    api_server.client.set_schedule(date(2026, 1, 1), [480] * 5 + [0, 0])
    api_server.client.add_absence(date(2026, 1, 6), date(2026, 1, 6), "vacation", None, "Skiferien")
    at = open_page(api_server, "statistics")
    assert [t.label for t in at.tabs][:2] == ["Auswertung", "Soll und Saldo"]
    assert at.number_input(key="sched_0").value == 8.0
    assert any(m.label == "Saldo" for m in at.metric)
    assert any("Skiferien" in m.value for m in at.markdown)
    key = next(b.key for b in at.button if b.key and b.key.startswith("abs_del_"))
    at.button(key=key).click().run()
    assert api_server.client.absences() == []
    widgets = [*at.number_input, *at.selectbox, *at.date_input, *at.text_input]
    assert all(w.help for w in widgets if w.key and w.key.startswith(("sched_", "abs_", "bal_")))


def test_the_balance_tab_explains_a_missing_schedule(api_server: RunningApi) -> None:
    at = open_page(api_server, "statistics")
    assert any("Noch kein Soll eingetragen" in i.value for i in at.info)


def test_holiday_and_break_settings_have_defaults_and_help(api_server: RunningApi) -> None:
    at = open_page(api_server, "settings")
    assert at.text_input(key="set_holiday_region").value == ""
    assert at.selectbox(key="set_break_region").value == "off"
    assert "keine Rechtsberatung" in at.selectbox(key="set_break_region").help


def test_tags_billing_and_budget_pages(api_server: RunningApi) -> None:
    client = api_server.client
    activity = client.create_item("activities", "Code")["id"]
    project = client.create_item("projects", "Alpha")["id"]
    tag = client.create_tag("Kunde", "#112233")
    at = open_page(api_server, "catalog")
    assert [t.label for t in at.tabs][:3] == ["Tätigkeiten", "Projekte", "Tags"]
    assert at.text_input(key=f"tag_name_{tag['id']}").value == "Kunde"
    at.multiselect(key=f"act_tags_{activity}").select(tag["id"]).run()
    at.button(key=f"act_defaults_save_{activity}").click().run()
    assert [t["name"] for t in client.activity_defaults(activity)["tags"]] == ["Kunde"]
    at.number_input(key=f"proj_budget_{project}").set_value(2.0)
    at.number_input(key=f"proj_rate_{project}").set_value(100.0)
    at.checkbox(key=f"proj_billable_{project}").check().run()
    at.button(key=f"proj_billing_save_{project}").click().run()
    saved = client.project_billing(project)
    assert (saved["budget_minutes"], saved["hourly_rate_cents"], saved["billable"]) == (
        120,
        10000,
        True,
    )
    stats = open_page(api_server, "statistics")
    assert "Projekte & Budget" in [t.label for t in stats.tabs]
    assert any("Alpha" in m.value for m in stats.markdown)
    widgets = [*at.number_input, *at.multiselect, *at.checkbox, *at.text_area]
    assert all(w.help for w in widgets if w.key and w.key.startswith(("proj_", "act_")))


def test_the_journal_offers_tag_filter_and_entry_tags(api_server: RunningApi) -> None:
    client = api_server.client
    activity = client.create_item("activities", "Code")["id"]
    tag = client.create_tag("Fokus")
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(hours=3)
    session = client.add_session(activity, start, start + timedelta(hours=1))
    at = open_page(api_server, "journal")
    assert at.selectbox(key="journal_tag").help
    at.multiselect(key=f"entry_tags_{session['id']}").select("Fokus").run()
    at.button(key=f"entry_tags_save_{session['id']}").click().run()
    assert client.journal(start - timedelta(hours=1), now)[0]["tags"] == ["Fokus"]
    assert client.journal(start - timedelta(hours=1), now, tag_id=tag["id"])


def test_budget_reminder_text(api_server: RunningApi) -> None:
    from octaledger.domain.attention import AttentionItem, AttentionKind

    with api_server.storage.transaction() as repos:
        repos.attention.add(
            AttentionItem(
                kind=AttentionKind.REMINDER,
                created_at=datetime.now(UTC),
                payload={
                    "reason": "budget",
                    "project": "Alpha",
                    "percent": 80,
                    "used_minutes": 96,
                    "budget_minutes": 120,
                },
            )
        )
    at = open_page(api_server, "journal")
    assert any("Budget „Alpha“ zu 80 % verbraucht" in w.value for w in at.warning)


def test_report_tab_offers_html_and_explains_the_pdf_extra(api_server: RunningApi) -> None:
    from octaledger.application.report_render import pdf_available

    api_server.client.create_item("activities", "Code")
    at = open_page(api_server, "statistics")
    assert "Bericht" in [t.label for t in at.tabs]
    assert at.date_input(key="rep_from").help and at.date_input(key="rep_to").help
    pdf_button = [b for b in at.button if b.key == "rep_dl_pdf_off"]
    assert bool(pdf_button) is (not pdf_available())
    if pdf_button:
        assert pdf_button[0].disabled and "pip install" in pdf_button[0].help


def test_calendar_import_section_and_header_settings(api_server: RunningApi) -> None:
    from octaledger.application.ics_import import ics_available

    api_server.client.create_item("activities", "Code")
    at = open_page(api_server, "journal")
    assert [e for e in at.expander if e.label.startswith("Aus Kalender")]
    if ics_available():
        assert at.button(key="ics_read").disabled  # nothing chosen yet
    settings = open_page(api_server, "settings")
    assert settings.text_input(key="set_report_author").value == ""
    assert "Voreinstellung" in settings.text_input(key="set_report_org").help


def test_bridge_search_fills_the_address_field(api_server: RunningApi) -> None:
    from octaledger.application.integration_service import IntegrationService
    from octaledger.core.secrets import SecretStore
    from octaledger.infrastructure.integrations.hue import HueAdapter

    calls: list[bool] = []

    def local(_timeout: float) -> list[dict[str, str]]:
        calls.append(False)
        return [{"id": "x", "address": "192.168.1.77", "name": "Wohnzimmer-Bridge"}]

    def cloud(_timeout: float) -> list[dict[str, str]]:
        calls.append(True)
        return []

    api_server.context.integrations = IntegrationService(
        api_server.storage,
        SecretStore(api_server.tmp_path / "s2.json"),
        {"hue": HueAdapter(mdns_finder=local, cloud_finder=cloud)},
    )
    at = open_page(api_server, "connections")
    assert at.button(key="new_conn_find_local").help and at.button(key="new_conn_find_online").help
    assert any("Anfrage an den Dienst von Philips" in c.value for c in at.caption)
    at.button(key="new_conn_find_local").click().run()
    assert calls == [False]  # the internet was not asked
    assert "Wohnzimmer-Bridge (192.168.1.77)" in at.selectbox(key="new_conn_found_pick").options
    at.button(key="new_conn_found_use").click().run()
    assert at.text_input(key="new_conn_hue_host").value == "192.168.1.77"
    at.button(key="new_conn_find_online").click().run()
    assert calls.count(True) == 1  # the internet was asked once, on its own click
    assert "Wohnzimmer-Bridge (192.168.1.77)" in at.selectbox(key="new_conn_found_pick").options
