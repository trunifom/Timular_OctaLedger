# Ordner- und Dateistruktur

Die folgende Liste entspricht den tatsächlich erzeugten Dateien.

```text
octaledger/
  .env.example
  .gitattributes
  .github/workflows/ci.yml
  .gitignore
  CHANGELOG.md
  CONTRIBUTING.md
  README.md
  SECURITY.md
  assets/.gitkeep
  config/settings.example.toml
  dashboard/app.py
  docs/ARCHITEKTUR.md
  docs/BLE_PROTOCOL.md
  docs/DATENMODELL.md
  docs/GITHUB.md
  docs/ORDNERSTRUKTUR.md
  docs/PFLICHTENHEFT.md
  docs/QUELLEN_UND_GRENZEN.md
  docs/ROADMAP.md
  docs/TESTPLAN.md
  migrations/.gitkeep
  pyproject.toml
  scripts/run_tests.bat
  scripts/start_dashboard.bat
  src/octaledger/__init__.py
  src/octaledger/__main__.py
  src/octaledger/agent/__init__.py
  src/octaledger/agent/main.py
  src/octaledger/agent/supervisor.py
  src/octaledger/api/__init__.py
  src/octaledger/api/app.py
  src/octaledger/api/routes.py
  src/octaledger/api/schemas.py
  src/octaledger/api/security.py
  src/octaledger/application/__init__.py
  src/octaledger/application/device_service.py
  src/octaledger/application/export_service.py
  src/octaledger/application/reporting_service.py
  src/octaledger/application/tracking_service.py
  src/octaledger/cli.py
  src/octaledger/core/__init__.py
  src/octaledger/core/logging.py
  src/octaledger/core/settings.py
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
  src/octaledger/infrastructure/ble/protocol.py
  src/octaledger/infrastructure/ble/scanner.py
  src/octaledger/infrastructure/integrations/__init__.py
  src/octaledger/infrastructure/integrations/base.py
  src/octaledger/infrastructure/storage/__init__.py
  src/octaledger/infrastructure/storage/database.py
  src/octaledger/infrastructure/storage/repositories.py
  tests/fixtures/.gitkeep
  tests/hardware/.gitkeep
  tests/integration/.gitkeep
  tests/unit/test_orientation.py
  tests/unit/test_time_rules.py
```

## Grenzen und Zuständigkeit

src enthält das installierbare Paket. dashboard ist der Streamlit-Einstieg.
tests trennt reine Regeln, spätere Integration und manuelle Hardwaretests.
config enthält nur Beispiele. Nutzerdaten landen später im Benutzerprofil.
migrations ist reserviert; es existiert noch keine SQL-Migration.
Leere .gitkeep-Dateien sind nur Git-Ordnermarker. Python-Stubs sind keine
funktionsfähigen Implementierungen.
