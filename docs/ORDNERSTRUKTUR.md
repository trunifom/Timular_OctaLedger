# Ordner- und Dateistruktur

Die folgende Liste wird aus dem tatsächlichen Dateibestand erzeugt (`git ls-files`, einschließlich neuer,
noch nicht committeter Dateien) und entspricht damit dem Ist-Zustand.

```text
octaledger/
  .env.example
  .gitattributes
  .github/workflows/ci.yml
  .gitignore
  .streamlit/config.toml
  AGENTS.md
  assets/.gitkeep
  CHANGELOG.md
  CLAUDE.md
  config/settings.example.toml
  constraints-tested.txt
  CONTRIBUTING.md
  dashboard/app.py
  docs/ADAPTER_ENTWICKLUNG.md
  docs/API.md
  docs/ARCHITEKTUR.md
  docs/BENUTZERHANDBUCH.md
  docs/BLE_PROTOCOL.md
  docs/DATENMODELL.md
  docs/FORTSCHRITT.md
  docs/GITHUB.md
  docs/GLOSSAR.md
  docs/GUI_KONZEPT.md
  docs/images/app-einstellungen.png
  docs/images/darstellung.png
  docs/images/daten.png
  docs/images/seiten-aktionen.png
  docs/images/seiten-zuordnen.png
  docs/images/startseite.png
  docs/images/statistik.png
  docs/images/uebersicht.png
  docs/images/verbindungen.png
  docs/images/wuerfel-live.png
  docs/INSTALLATION.md
  docs/ORDNERSTRUKTUR.md
  docs/PFLICHTENHEFT.md
  docs/QUELLEN_UND_GRENZEN.md
  docs/README.md
  docs/REZEPTE.md
  docs/ROADMAP.md
  docs/SOFTWAREDOKUMENTATION.md
  docs/TESTPLAN.md
  docs/UMSETZUNGSPLAN.md
  pyproject.toml
  README.md
  scripts/run_tests.bat
  scripts/start_agent.bat
  scripts/start_all.bat
  scripts/start_dashboard.bat
  scripts/update_ordnerstruktur.py
  SECURITY.md
  src/octaledger/__init__.py
  src/octaledger/__main__.py
  src/octaledger/agent/__init__.py
  src/octaledger/agent/dispatcher.py
  src/octaledger/agent/housekeeper.py
  src/octaledger/agent/main.py
  src/octaledger/agent/supervisor.py
  src/octaledger/agent/tray.py
  src/octaledger/api/__init__.py
  src/octaledger/api/app.py
  src/octaledger/api/context.py
  src/octaledger/api/routes.py
  src/octaledger/api/schemas.py
  src/octaledger/api/security.py
  src/octaledger/application/__init__.py
  src/octaledger/application/attention_service.py
  src/octaledger/application/battery_watch.py
  src/octaledger/application/budget_watch.py
  src/octaledger/application/catalog_service.py
  src/octaledger/application/data_service.py
  src/octaledger/application/device_service.py
  src/octaledger/application/export_service.py
  src/octaledger/application/ics_import.py
  src/octaledger/application/integration_service.py
  src/octaledger/application/music_service.py
  src/octaledger/application/music_state.py
  src/octaledger/application/notifier.py
  src/octaledger/application/outbox.py
  src/octaledger/application/report_render.py
  src/octaledger/application/reporting_service.py
  src/octaledger/application/tag_service.py
  src/octaledger/application/tracking_service.py
  src/octaledger/application/work_time_service.py
  src/octaledger/application/workday_service.py
  src/octaledger/cli.py
  src/octaledger/core/__init__.py
  src/octaledger/core/errors.py
  src/octaledger/core/fileio.py
  src/octaledger/core/logging.py
  src/octaledger/core/secrets.py
  src/octaledger/core/settings.py
  src/octaledger/dashboard/__init__.py
  src/octaledger/dashboard/attention.py
  src/octaledger/dashboard/cube.py
  src/octaledger/dashboard/docs_reader.py
  src/octaledger/dashboard/forms.py
  src/octaledger/dashboard/identity.py
  src/octaledger/dashboard/main.py
  src/octaledger/dashboard/nav.py
  src/octaledger/dashboard/shell.py
  src/octaledger/dashboard/static/Inter-Variable.woff2
  src/octaledger/dashboard/static/OFL.txt
  src/octaledger/dashboard/streamlit_app.py
  src/octaledger/dashboard/theme.py
  src/octaledger/dashboard/ui.py
  src/octaledger/dashboard/views/__init__.py
  src/octaledger/dashboard/views/catalog.py
  src/octaledger/dashboard/views/catalog_extras.py
  src/octaledger/dashboard/views/connections.py
  src/octaledger/dashboard/views/data.py
  src/octaledger/dashboard/views/data_cleanup.py
  src/octaledger/dashboard/views/devices.py
  src/octaledger/dashboard/views/diagnostics.py
  src/octaledger/dashboard/views/display.py
  src/octaledger/dashboard/views/faces.py
  src/octaledger/dashboard/views/faces_actions.py
  src/octaledger/dashboard/views/faces_music.py
  src/octaledger/dashboard/views/journal.py
  src/octaledger/dashboard/views/journal_ics.py
  src/octaledger/dashboard/views/live.py
  src/octaledger/dashboard/views/overview.py
  src/octaledger/dashboard/views/player.py
  src/octaledger/dashboard/views/settings.py
  src/octaledger/dashboard/views/start.py
  src/octaledger/dashboard/views/statistics.py
  src/octaledger/dashboard/views/statistics_balance.py
  src/octaledger/dashboard/views/statistics_budget.py
  src/octaledger/dashboard/views/statistics_report.py
  src/octaledger/dashboard_client/__init__.py
  src/octaledger/dashboard_client/client.py
  src/octaledger/domain/__init__.py
  src/octaledger/domain/attention.py
  src/octaledger/domain/break_rules.py
  src/octaledger/domain/conditions.py
  src/octaledger/domain/device_identity.py
  src/octaledger/domain/link_loss.py
  src/octaledger/domain/models.py
  src/octaledger/domain/music.py
  src/octaledger/domain/music_source.py
  src/octaledger/domain/orientation.py
  src/octaledger/domain/placeholders.py
  src/octaledger/domain/schedule.py
  src/octaledger/domain/state_machine.py
  src/octaledger/domain/steps.py
  src/octaledger/domain/tags.py
  src/octaledger/domain/time_rules.py
  src/octaledger/domain/workday.py
  src/octaledger/infrastructure/__init__.py
  src/octaledger/infrastructure/audio/__init__.py
  src/octaledger/infrastructure/audio/engine.py
  src/octaledger/infrastructure/audio/worker.py
  src/octaledger/infrastructure/ble/__init__.py
  src/octaledger/infrastructure/ble/client.py
  src/octaledger/infrastructure/ble/fake.py
  src/octaledger/infrastructure/ble/protocol.py
  src/octaledger/infrastructure/ble/scanner.py
  src/octaledger/infrastructure/ble/transport.py
  src/octaledger/infrastructure/integrations/__init__.py
  src/octaledger/infrastructure/integrations/base.py
  src/octaledger/infrastructure/integrations/browser.py
  src/octaledger/infrastructure/integrations/demo.py
  src/octaledger/infrastructure/integrations/homeassistant.py
  src/octaledger/infrastructure/integrations/httpio.py
  src/octaledger/infrastructure/integrations/hue.py
  src/octaledger/infrastructure/integrations/mqtt.py
  src/octaledger/infrastructure/integrations/player.py
  src/octaledger/infrastructure/integrations/registry.py
  src/octaledger/infrastructure/integrations/spotify.py
  src/octaledger/infrastructure/integrations/urlcheck.py
  src/octaledger/infrastructure/integrations/webhook.py
  src/octaledger/infrastructure/storage/__init__.py
  src/octaledger/infrastructure/storage/database.py
  src/octaledger/infrastructure/storage/migrations/0001_initial.sql
  src/octaledger/infrastructure/storage/migrations/0002_app_state.sql
  src/octaledger/infrastructure/storage/migrations/0003_integrations.sql
  src/octaledger/infrastructure/storage/migrations/0004_attention.sql
  src/octaledger/infrastructure/storage/migrations/0005_buttons.sql
  src/octaledger/infrastructure/storage/migrations/0006_work.sql
  src/octaledger/infrastructure/storage/migrations/0007_tags_budgets.sql
  src/octaledger/infrastructure/storage/migrations/0008_action_steps.sql
  src/octaledger/infrastructure/storage/migrations/0009_music_mode.sql
  src/octaledger/infrastructure/storage/migrations/0010_device_color.sql
  src/octaledger/infrastructure/storage/repositories.py
  src/octaledger/infrastructure/system/__init__.py
  src/octaledger/infrastructure/system/autostart.py
  src/octaledger/infrastructure/system/holidays_provider.py
  src/octaledger/infrastructure/system/idle.py
  src/octaledger/infrastructure/system/toast.py
  tests/__init__.py
  tests/conftest.py
  tests/fake_adapter.py
  tests/fixtures/.gitkeep
  tests/gui/__init__.py
  tests/gui/test_gui_attention.py
  tests/gui/test_gui_connections.py
  tests/gui/test_gui_control.py
  tests/gui/test_gui_core.py
  tests/gui/test_gui_data_cleanup.py
  tests/gui/test_gui_data_settings_diagnostics.py
  tests/gui/test_gui_devices_catalog.py
  tests/gui/test_gui_faces.py
  tests/gui/test_gui_identity.py
  tests/gui/test_gui_journal_statistics.py
  tests/gui/test_gui_live.py
  tests/gui/test_gui_player.py
  tests/gui/test_gui_redesign.py
  tests/gui/test_gui_settings_areas.py
  tests/gui/test_gui_start.py
  tests/hardware/.gitkeep
  tests/hardware/test_hardware_smoke.py
  tests/integration/.gitkeep
  tests/integration/__init__.py
  tests/integration/test_agent_runtime.py
  tests/integration/test_client_server.py
  tests/unit/__init__.py
  tests/unit/test_action_chains.py
  tests/unit/test_adapter_browser.py
  tests/unit/test_adapter_demo_and_hints.py
  tests/unit/test_adapter_homeassistant.py
  tests/unit/test_adapter_hue.py
  tests/unit/test_adapter_mqtt.py
  tests/unit/test_adapter_spotify.py
  tests/unit/test_adapter_webhook.py
  tests/unit/test_api.py
  tests/unit/test_api_security.py
  tests/unit/test_attention.py
  tests/unit/test_balance.py
  tests/unit/test_ble_bleak_layer.py
  tests/unit/test_ble_protocol_and_fake.py
  tests/unit/test_button_and_battery.py
  tests/unit/test_cli.py
  tests/unit/test_control_mode.py
  tests/unit/test_cube.py
  tests/unit/test_dashboard_client.py
  tests/unit/test_data_service.py
  tests/unit/test_database.py
  tests/unit/test_device_catalog_services.py
  tests/unit/test_device_identity.py
  tests/unit/test_dispatcher.py
  tests/unit/test_docs_reader.py
  tests/unit/test_documentation.py
  tests/unit/test_errors.py
  tests/unit/test_export_service.py
  tests/unit/test_fileio.py
  tests/unit/test_gui_documentation.py
  tests/unit/test_hue_extended.py
  tests/unit/test_integration_service.py
  tests/unit/test_integrations_storage.py
  tests/unit/test_link_loss.py
  tests/unit/test_logging.py
  tests/unit/test_media_player.py
  tests/unit/test_models.py
  tests/unit/test_music_mode.py
  tests/unit/test_orientation.py
  tests/unit/test_presets_placeholders.py
  tests/unit/test_report_and_ics.py
  tests/unit/test_reporting_service.py
  tests/unit/test_repositories.py
  tests/unit/test_secret_store.py
  tests/unit/test_settings.py
  tests/unit/test_state_machine.py
  tests/unit/test_supervisor.py
  tests/unit/test_tags_budgets.py
  tests/unit/test_time_intervals.py
  tests/unit/test_time_rules.py
  tests/unit/test_tracking_service.py
  tests/unit/test_tray_notify_autostart.py
  tests/unit/test_workday.py
```

## Verantwortung der Ordner

- `src/octaledger/` enthält das installierbare Paket (src-Layout):
- `src/octaledger/core/` – Querschnitt: Fehler, Logging, Dateizugriff, Einstellungen/Pfade
- `src/octaledger/domain/` – reine Regeln und Modelle (kein BLE/HTTP/SQL/Streamlit)
- `src/octaledger/application/` – Anwendungsfälle (Tracking, Geräte, Katalog, Berichte, Export)
- `src/octaledger/infrastructure/ble/` – Bluetooth: Protokoll, Transport-Abstraktion, Fake, Bleak
- `src/octaledger/infrastructure/storage/` – SQLite, Migrationen (`migrations/*.sql`), Repositories
- `src/octaledger/infrastructure/integrations/` – Adapter des Steuerungsmodus (Webhook, MQTT, Home Assistant, Hue), gemeinsame HTTP-Logik `httpio`
- `src/octaledger/agent/` – Hintergrundprozess: Laufzeit und Supervisor
- `src/octaledger/api/` – lokale HTTP-API: Sicherheit, Kontext, Routen, Schemas, App
- `src/octaledger/dashboard_client/` – HTTP-Client des Dashboards
- `src/octaledger/dashboard/` – Streamlit-Oberfläche (Theme, UI-Helfer, Seiten)
- `tests/unit/` – Unit-Tests (reine Regeln, Services, API mit TestClient)
- `tests/integration/` – echter Server/Agent, ganze Kette
- `tests/gui/` – AppTest-GUI-Tests aller Seiten
- `tests/hardware/` – manuelle Hardwaretests (standardmäßig übersprungen)
- `dashboard/app.py` ist ein dünner Streamlit-Einstieg; der eigentliche Einstieg liegt im Paket
  (`src/octaledger/dashboard/streamlit_app.py`, gestartet durch `octaledger dashboard`).
- `config/` enthält nur Beispiele; Nutzerdaten liegen im Benutzerprofil (siehe INSTALLATION.md).
- SQL-Migrationen liegen im Paket (`NNNN_name.sql`, lückenlos ab `0001`) und werden als Package-Data
  ausgeliefert.
- `scripts/` enthält die Windows-Startskripte und das Qualitäts-Gate (`run_tests.bat`).
- `.streamlit/config.toml` erzwingt lokalen Betrieb und schaltet Telemetrie ab.
- `constraints-tested.txt` hält die zuletzt getesteten Abhängigkeitsversionen fest.
- Leere `.gitkeep`-Dateien sind nur Git-Ordnermarker.
