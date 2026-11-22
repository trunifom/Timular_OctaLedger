"""GUI tests for the data, settings and diagnostics pages (AppTest against the real server)."""

import json
from datetime import date, datetime, timezone

import pytest

from octaledger.dashboard.views.diagnostics import build_report
from tests.conftest import FakeAgent, RunningApi
from tests.gui.test_gui_core import button, open_app, texts
from tests.gui.test_gui_devices_catalog import all_help, open_page

DATA = "data"
SETTINGS = "settings"
DIAG = "diagnostics"
UTC = timezone.utc


def seed_session(api: RunningApi) -> str:
    activity = api.client.create_item("activities", "Meeting")
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC).replace(hour=0)
    api.client.add_session(activity["id"], start.replace(hour=0), start.replace(hour=1))
    return str(activity["id"])


# ------------------------------------------------------------------------------- data


def test_data_page_structure_and_help(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Meeting")
    at = open_page(api_server, DATA)
    assert at.header[0].value == "Daten"
    assert {"CSV-Export", "Sicherung", "Wiederherstellen"} <= {t.label for t in at.tabs}
    assert any("So funktionieren" in e.label for e in at.expander)
    for widget in [*all_help(at), *at.date_input, *at.text_area, *at.file_uploader]:
        assert widget.help, f"{widget.key or widget.label} has no help text"


def test_csv_export_offers_a_download_with_bom(api_server: RunningApi) -> None:
    if datetime.now(UTC).hour < 2:
        pytest.skip("the seeded session would lie in the future")
    seed_session(api_server)
    at = open_page(api_server, DATA)
    at.selectbox(key="export_delimiter").select(",").run()
    button(at, "CSV erzeugen").click().run()
    assert any("1 Zeile(n) exportiert" in s.value for s in at.success)
    downloads = at.get("download_button")
    assert len(downloads) == 1  # exactly one download offer for the generated file


def test_csv_export_of_empty_data_still_works(api_server: RunningApi) -> None:
    at = open_page(api_server, DATA)
    button(at, "CSV erzeugen").click().run()
    assert any("0 Zeile(n) exportiert" in s.value for s in at.success)


def test_csv_export_with_date_range(api_server: RunningApi) -> None:
    at = open_page(api_server, DATA)
    at.checkbox(key="export_all").uncheck().run()
    assert at.date_input(key="export_from") is not None
    button(at, "CSV erzeugen").click().run()
    assert any("exportiert" in s.value for s in at.success) and not at.exception


def test_backup_is_created_and_offered_for_download(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Meeting")
    at = open_page(api_server, DATA)
    button(at, "Sicherung erstellen").click().run()
    assert any("Sicherung erstellt" in s.value for s in at.success)
    assert len(at.get("download_button")) >= 1
    assert list((api_server.tmp_path / "bk2").glob("octaledger-backup-*.json"))  # file written too


def test_restore_preview_requires_confirmation_then_restores(api_server: RunningApi) -> None:
    client = api_server.client
    client.create_item("activities", "Alt")
    backup = client.create_backup()["content"]
    client.create_item("activities", "Neu nach der Sicherung")

    at = open_page(api_server, DATA)
    assert any("Wählen Sie eine Sicherungsdatei" in i.value for i in at.info)
    at.text_area(key="restore_text").input(backup).run()
    assert any("noch nichts verändert" in s.value for s in at.success)
    counts = {m.label: m.value for m in at.metric}
    assert counts["Tätigkeiten"] == "1" and counts["Einträge"] == "0"
    assert at.button(key="btn_restore").disabled  # not before the explicit confirmation
    assert len(client.list_items("activities")) == 2  # preview changed nothing

    at.checkbox(key="restore_confirm").check().run()
    at.button(key="btn_restore").click().run()
    assert [a["name"] for a in client.list_items("activities")] == ["Alt"]
    assert any("octaledger-pre-restore-" in s.value for s in at.success)


def test_invalid_backup_is_rejected_without_changing_data(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Bleibt")
    at = open_page(api_server, DATA)
    at.text_area(key="restore_text").input("{not json").run()
    assert any("keine Daten verändert" in e.value for e in at.error)
    assert "OL-DATA-002" in texts(at) and not at.exception
    tampered = json.loads(api_server.client.create_backup()["content"])
    tampered["data"]["activities"][0]["name"] = "Manipuliert"
    at = open_page(api_server, DATA)
    at.text_area(key="restore_text").input(json.dumps(tampered)).run()
    assert any("Prüfsumme" in e.value for e in at.error)
    assert [a["name"] for a in api_server.client.list_items("activities")] == ["Bleibt"]


# --------------------------------------------------------------------------- settings


def test_settings_page_shows_current_values_and_help(api_server: RunningApi) -> None:
    at = open_page(api_server, SETTINGS)
    assert at.header[0].value == "App"
    assert at.selectbox(key="set_timezone").value == "UTC"
    assert at.slider(key="set_debounce").value == 300
    assert "empfohlen" in at.selectbox(key="set_baseline").options[0]
    for widget in [*at.selectbox, *at.slider]:
        assert widget.help, f"{widget.key or widget.label} has no help text"


def test_saving_the_timezone_applies_immediately_without_restart_hint(
    api_server: RunningApi,
) -> None:
    at = open_page(api_server, SETTINGS)
    at.selectbox(key="set_timezone").select("Europe/Zurich")
    button(at, "Einstellungen speichern").click().run()
    assert api_server.client.get_settings()["display"]["timezone"] == "Europe/Zurich"
    assert any("gespeichert" in s.value for s in at.success)
    assert not any("Neustart" in i.value for i in at.info)  # nothing agent-related changed
    assert at.session_state["_display"]["timezone"] == "Europe/Zurich"


def test_changing_tracking_rules_saves_and_asks_for_an_agent_restart(
    api_server: RunningApi,
) -> None:
    at = open_page(api_server, SETTINGS)
    at.slider(key="set_debounce").set_value(450)
    at.selectbox(key="set_baseline").select("adopt_current")
    at.selectbox(key="set_disconnect").select("stop_session")
    at.selectbox(key="set_log_level").select("DEBUG")
    button(at, "Einstellungen speichern").click().run()
    saved = api_server.client.get_settings()
    assert saved["tracking"]["debounce_ms"] == 450
    assert saved["tracking"]["baseline_policy"] == "adopt_current"
    assert saved["tracking"]["disconnect_policy"] == "stop_session"
    assert saved["logging"]["level"] == "DEBUG"
    assert any("Neustart des Agenten" in i.value for i in at.info)


def test_settings_technical_info_is_read_only(api_server: RunningApi) -> None:
    at = open_page(api_server, SETTINGS)
    rendered = texts(at)
    assert "127.0.0.1" in rendered and "nur lokal erreichbar" in rendered


# ------------------------------------------------------------------------- diagnostics


def test_diagnostics_shows_devices_logs_and_integrity(api_server: RunningApi) -> None:
    api_server.context.log_lines = lambda: ["zeile eins", "zeile zwei"]
    api_server.client.register_device("Büro")
    at = open_page(api_server, DIAG)
    assert at.header[0].value == "Diagnose"
    assert any("Nicht verbunden" in c.value for c in at.caption)
    assert "zeile zwei" in "".join(c.value for c in at.code)
    button(at, "Datenbank prüfen").click().run()
    assert any("in Ordnung" in s.value for s in at.success)
    assert len(at.get("download_button")) == 1


def test_diagnostics_with_live_device_status(api_server: RunningApi) -> None:
    agent = FakeAgent()
    api_server.context.agent = agent
    device = api_server.client.register_device("Büro")
    api_server.client.set_device_address(device["id"], "AA:BB")
    api_server.client.connect_device(device["id"])
    at = open_page(api_server, DIAG)
    rendered = texts(at)
    assert (
        "Bereit" in rendered
        and "Batterie: 87" in rendered
        and "ignorierte Duplikate: 2" in rendered
    )


def test_diagnostics_empty_log_and_no_devices(api_server: RunningApi) -> None:
    at = open_page(api_server, DIAG)
    assert any("Noch kein Tracker" in i.value for i in at.info)
    assert "(noch keine Einträge)" in "".join(c.value for c in at.code)


def test_diagnostics_widgets_have_help_texts(api_server: RunningApi) -> None:
    api_server.client.register_device("A")
    at = open_page(api_server, DIAG)
    for widget in [*all_help(at), *at.slider]:
        assert widget.help, f"{widget.key or widget.label} has no help text"


def test_report_is_anonymised() -> None:
    devices = [
        {
            "alias": "Mein Geheimes Gerät",
            "is_active": True,
            "configured_faces": 8,
            "has_address": True,
            "model": "ZEI",
            "firmware": "1.2",
            "status": {"state": "ready", "attempt": 2},
        },
        {
            "alias": "Zweites",
            "is_active": False,
            "configured_faces": 0,
            "has_address": False,
            "model": None,
            "firmware": None,
            "status": None,
        },
    ]
    report = build_report(
        devices,
        {"ok": False, "problems": ["foreign key: table sessions"]},
        ["2026-01-01 INFO token=*** ok"],
    )
    assert "Mein Geheimes Gerät" not in report and "Zweites" not in report
    assert "Gerät 1:" in report and "Gerät 2:" in report and "Zustand=ready" in report
    assert "Zustand=nicht verbunden" in report and "PROBLEME" in report
    assert "foreign key: table sessions" in report and "token=***" in report
    assert "OctaLedger Diagnosebericht" in report and "Programmversion:" in report


def test_every_page_of_the_menu_renders(api_server: RunningApi) -> None:
    from octaledger.dashboard.views import PAGES

    at = open_app(api_server.client)
    assert len(PAGES) == 15
    for slug in PAGES:  # every page renders without an exception
        at.sidebar.button(key=f"nav_{slug}").click().run()
        assert not at.exception, slug
