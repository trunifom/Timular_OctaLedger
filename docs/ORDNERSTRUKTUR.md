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
  CHANGELOG.md
  CLAUDE.md
  CONTRIBUTING.md
  README.md
  SECURITY.md
  assets/.gitkeep
  config/settings.example.toml
  constraints-tested.txt
  dashboard/app.py
  docs/ARCHITEKTUR.md
  docs/BENUTZERHANDBUCH.md
  docs/BLE_PROTOCOL.md
  docs/DATENMODELL.md
  docs/FORTSCHRITT.md
  docs/GITHUB.md
  docs/INSTALLATION.md
  docs/ORDNERSTRUKTUR.md
  docs/PFLICHTENHEFT.md
  docs/QUELLEN_UND_GRENZEN.md
  docs/ROADMAP.md
  docs/SOFTWAREDOKUMENTATION.md
  docs/TESTPLAN.md
  pyproject.toml
  scripts/run_tests.bat
  scripts/start_agent.bat
  scripts/start_all.bat
  scripts/start_dashboard.bat
  src/octaledger/__init__.py
  src/octaledger/__main__.py
  src/octaledger/agent/__init__.py
  src/octaledger/agent/main.py
  src/octaledger/agent/supervisor.py
  src/octaledger/api/__init__.py
  src/octaledger/api/app.py
  src/octaledger/api/context.py
  src/octaledger/api/routes.py
  src/octaledger/api/schemas.py
  src/octaledger/api/security.py
  src/octaledger/application/__init__.py
  src/octaledger/application/catalog_service.py
  src/octaledger/application/device_service.py
  src/octaledger/application/export_service.py
  src/octaledger/application/reporting_service.py
  src/octaledger/application/tracking_service.py
  src/octaledger/cli.py
  src/octaledger/core/__init__.py
  src/octaledger/core/errors.py
  src/octaledger/core/fileio.py
  src/octaledger/core/logging.py
  src/octaledger/core/settings.py
  src/octaledger/dashboard/__init__.py
  src/octaledger/dashboard/main.py
  src/octaledger/dashboard/pages/__init__.py
  src/octaledger/dashboard/pages/catalog.py
  src/octaledger/dashboard/pages/data.py
  src/octaledger/dashboard/pages/devices.py
  src/octaledger/dashboard/pages/diagnostics.py
  src/octaledger/dashboard/pages/journal.py
  src/octaledger/dashboard/pages/overview.py
  src/octaledger/dashboard/pages/settings.py
  src/octaledger/dashboard/pages/statistics.py
  src/octaledger/dashboard/streamlit_app.py
  src/octaledger/dashboard/theme.py
  src/octaledger/dashboard/ui.py
  src/octaledger/dashboard_client/__init__.py
  src/octaledger/dashboard_client/client.py
  src/octaledger/domain/__init__.py
  src/octaledger/domain/models.py
  src/octaledger/domain/orientation.py
  src/octaledger/domain/state_machine.py
  src/octaledger/domain/time_rules.py
  src/octaledger/infrastructure/__init__.py
  src/octaledger/infrastructure/ble/__init__.py
  src/octaledger/infrastructure/ble/client.py
  src/octaledger/infrastructure/ble/fake.py
  src/octaledger/infrastructure/ble/protocol.py
  src/octaledger/infrastructure/ble/scanner.py
  src/octaledger/infrastructure/ble/transport.py
  src/octaledger/infrastructure/integrations/__init__.py
  src/octaledger/infrastructure/integrations/base.py
  src/octaledger/infrastructure/storage/__init__.py
  src/octaledger/infrastructure/storage/database.py
  src/octaledger/infrastructure/storage/migrations/0001_initial.sql
  src/octaledger/infrastructure/storage/migrations/0002_app_state.sql
  src/octaledger/infrastructure/storage/repositories.py
  tests/__init__.py
  tests/conftest.py
  tests/fixtures/.gitkeep
  tests/gui/__init__.py
  tests/gui/test_gui_core.py
  tests/gui/test_gui_data_settings_diagnostics.py
  tests/gui/test_gui_devices_catalog.py
  tests/gui/test_gui_journal_statistics.py
  tests/hardware/.gitkeep
  tests/hardware/test_hardware_smoke.py
  tests/integration/.gitkeep
  tests/integration/__init__.py
  tests/integration/test_agent_runtime.py
  tests/integration/test_client_server.py
  tests/unit/__init__.py
  tests/unit/test_api.py
  tests/unit/test_api_security.py
  tests/unit/test_ble_bleak_layer.py
  tests/unit/test_ble_protocol_and_fake.py
  tests/unit/test_cli.py
  tests/unit/test_dashboard_client.py
  tests/unit/test_database.py
  tests/unit/test_device_catalog_services.py
  tests/unit/test_errors.py
  tests/unit/test_export_service.py
  tests/unit/test_fileio.py
  tests/unit/test_logging.py
  tests/unit/test_models.py
  tests/unit/test_orientation.py
  tests/unit/test_reporting_service.py
  tests/unit/test_repositories.py
  tests/unit/test_settings.py
  tests/unit/test_state_machine.py
  tests/unit/test_supervisor.py
  tests/unit/test_time_intervals.py
  tests/unit/test_time_rules.py
  tests/unit/test_tracking_service.py
```

## Verantwortung der Ordner

- `src/octaledger/` enthält das installierbare Paket (src-Layout):
- `src/octaledger/core/` – Querschnitt: Fehler, Logging, Dateizugriff, Einstellungen/Pfade
- `src/octaledger/domain/` – reine Regeln und Modelle (kein BLE/HTTP/SQL/Streamlit)
- `src/octaledger/application/` – Anwendungsfälle (Tracking, Geräte, Katalog, Berichte, Export)
- `src/octaledger/infrastructure/ble/` – Bluetooth: Protokoll, Transport-Abstraktion, Fake, Bleak
- `src/octaledger/infrastructure/storage/` – SQLite, Migrationen (`migrations/*.sql`), Repositories
- `src/octaledger/infrastructure/integrations/` – Platz für optionale Ausgabeadapter (F-20, noch leer)
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
