# OctaLedger

Local-first time tracking for Timeular / ZEI Bluetooth trackers.

Status: Entwicklungsgrundgerüst, kein fertiger Timeular-Client.

OctaLedger soll kompatible Tracker direkt per BLE auslesen, Zeitabschnitte lokal
speichern und über ein Streamlit-Dashboard verwalten und auswerten. Das Projekt
ist unabhängig von Timeular und EARLY und nicht mit deren Herstellern verbunden.

## Bereits enthalten

- Installierbares Pythonpaket im src-Layout.
- CLI mit Hilfe, Version und ausdrücklich als Test gekennzeichnetem Decoderaufruf.
- Validierung eines Orientierungsbytes und elementare UTC-Zeitvalidierung.
- Streamlit-Startseite mit ehrlicher Funktionsübersicht, ohne erfundene Zeitdaten.
- Unit-Tests, Qualitätskonfiguration und CI-Workflow.
- Architektur, Pflichtenheft, Datenmodell, Roadmap, GitHub-Vorbereitung.

## Noch nicht implementiert

BLE-Suche/Verbindung, Agentenserver, Datenbankmigration, automatische Sitzungen,
CRUD-Verwaltung, Diagramme, Export/Import, Hintergrundbetrieb und Autostart.
Die entsprechenden Modulgrenzen sind als Dateien vorbereitet.

## Installation unter Windows

Voraussetzung: Python 3.12 oder neuer; für BLE später die konkrete Bleak-/Windows-
Kompatibilität prüfen. Windows 11 ist das geplante erste Hardware-Testziel.

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m octaledger --help
.venv\Scripts\python.exe -m pytest
scripts\start_dashboard.bat
```

Die Installation benötigt Zugriff auf Paketquellen. Versionen sind noch nicht
hardwarevalidiert und nicht vollständig gesperrt. Nach erstem erfolgreichen Build
reproduzierbare Lockdatei einführen.

## Dokumentation

- [Pflichtenheft](docs/PFLICHTENHEFT.md)
- [Architektur](docs/ARCHITEKTUR.md)
- [Ordnerstruktur](docs/ORDNERSTRUKTUR.md)
- [Datenmodell](docs/DATENMODELL.md)
- [BLE-Protokoll](docs/BLE_PROTOCOL.md)
- [Roadmap](docs/ROADMAP.md)
- [Tests](docs/TESTPLAN.md)
- [GitHub](docs/GITHUB.md)
- [Quellen und Grenzen](docs/QUELLEN_UND_GRENZEN.md)

## Datenschutz und Lizenz

Keine echten Zeitdaten oder Tokens ins Repository aufnehmen. Die Vorlage enthält
bewusst keine gewählte Open-Source-Lizenz; vor Veröffentlichung Lizenz festlegen.
Öffentlicher Quellcode ist ohne Lizenz nicht automatisch frei nachnutzbar.
