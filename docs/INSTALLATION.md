# Installation und Ausführung

Stand: Entwicklungsversion. Der BLE-Agent, die API und das vollständige Dashboard sind
noch nicht fertig; der jeweils aktuelle Stand steht in [FORTSCHRITT.md](FORTSCHRITT.md).

## 1. Voraussetzungen

| Komponente | Anforderung |
|---|---|
| Betriebssystem | Windows 11 (erstes Testziel) |
| Python | 3.12 oder neuer |
| Bluetooth | Bluetooth-LE-Adapter mit aktivem Treiber (erst für den Agenten nötig) |
| Browser | Aktueller Browser für das lokale Dashboard |
| Internet | Nur für Installation und Updates; die Erfassung läuft offline |

## 2. Installation

Im Projektordner in einer Eingabeaufforderung (`cmd`) oder PowerShell:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Prüfen:

```bat
.venv\Scripts\python.exe -m octaledger --version
.venv\Scripts\python.exe -m octaledger --help
```

## 3. Qualitätsprüfung (Entwickler)

```bat
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
```

Alle drei Befehle müssen ohne Fehler enden. Dasselbe führt die CI aus
(`.github/workflows/ci.yml`). Alternativ: `scripts\run_tests.bat`.

## 4. Dashboard starten

```bat
scripts\start_dashboard.bat
```

Das Dashboard bindet ausschließlich an `127.0.0.1` und ist nur lokal erreichbar.

## 5. Datenablage und Konfiguration

Nutzerdaten liegen **nicht** im Projektordner. Rangfolge für das Wurzelverzeichnis:

1. Programmargument (für Tests/Skripte),
2. Umgebungsvariable `OCTALEDGER_DATA_DIR`,
3. Benutzerprofil: unter Windows `%LOCALAPPDATA%\OctaLedger`.

```text
settings.toml   data\octaledger.sqlite3   logs\octaledger.log   backups\   exports\
```

Konfiguration: Vorlage `config\settings.example.toml` nach `<Wurzel>\settings.toml` kopieren
und anpassen. Fehlt die Datei, gelten Standardwerte. Überschreibungen per Umgebungsvariable:

| Variable | Wirkung |
|---|---|
| `OCTALEDGER_DATA_DIR` | Datenverzeichnis |
| `OCTALEDGER_HOST` | API-Adresse (nur `127.0.0.1`, `::1`, `localhost`) |
| `OCTALEDGER_PORT` | API-Port (1024–65535) |

Beispiel (PowerShell): `$env:OCTALEDGER_DATA_DIR = "D:\OctaLedgerDaten"`

## 6. Logfiles

Logfiles liegen im Ordner `logs` der Datenablage (siehe Abschnitt 5). Die
Protokollstufe (`DEBUG`, `INFO`, `WARNING`, `ERROR`) wird in den Einstellungen gesetzt.
Geheimnisse werden vor dem Schreiben maskiert; siehe SOFTWAREDOKUMENTATION.md §3.

## Datenbank und Backups

- Die Datenbank wird beim ersten Start automatisch erzeugt; spätere Programmversionen
  migrieren sie selbstständig (Backup vorher in `backups\`).
- Manuelle Sicherung der laufenden Datenbank (konsistent, auch während der Agent läuft):

  ```bat
  .venv\Scripts\python.exe -c "from pathlib import Path; from octaledger.infrastructure.storage.database import Database; Database(Path(r'%LOCALAPPDATA%\OctaLedger\data\octaledger.sqlite3')).backup_to(Path(r'D:\Sicherung\octaledger.sqlite3'))"
  ```

  (Eine komfortable Oberfläche dafür folgt mit dem Export-/Backup-Dienst, AP-15.)
- Zusatzdateien `*.sqlite3-wal` und `*.sqlite3-shm` neben der Datenbank sind normal (WAL-Modus)
  und dürfen nicht einzeln gelöscht werden.
- Beim Paket-Build werden die SQL-Migrationen als Package-Data mitgeliefert
  (`pyproject.toml`, Abschnitt `[tool.setuptools.package-data]`).

## Bluetooth und Hardwaretest

- Voraussetzung für echte Erfassung: Bluetooth-LE-Adapter mit funktionierendem Windows-Treiber,
  Bluetooth in den Windows-Einstellungen **eingeschaltet**. Der Tracker darf nicht gleichzeitig
  mit der Hersteller-App verbunden sein (ein Gerät hat meist nur eine aktive Verbindung).
- Die normale Testsuite benötigt **keine** Hardware (`pytest` überspringt die Hardwaretests).
- **Hardwaretest bewusst starten** (nur Suchen/Lesen/Abonnieren, kein Schreiben):

  ```bat
  set OCTALEDGER_HARDWARE_TESTS=1
  .venv\Scripts\python.exe -m pytest tests\hardware -s
  rem Adresse aus der Ausgabe übernehmen und Verbindungstest starten:
  set OCTALEDGER_HARDWARE_ADDRESS=<Adresse>
  .venv\Scripts\python.exe -m pytest tests\hardware -s
  ```
- Trage Ergebnisse (Modell, Firmware, Windows, Adapter, Treiber, Python, Bleak, App-Version) in die
  Kompatibilitätsmatrix von `docs\TESTPLAN.md` ein. **Erst danach** gelten Abnahmekriterien mit
  Hardwarebezug (A-01, A-05…) als geprüft.

## API-Token

- Beim ersten Start des Agenten wird ein zufälliges **API-Token** (256 Bit) erzeugt und in der Datei
  `api_token` im Datenordner gespeichert (Rechte: nur Ihr Benutzerkonto, über Ihr Windows-Profil).
  Agent und Dashboard lesen **dieselbe** Datei, es ist keine Eingabe nötig.
- Alternativ per Umgebungsvariable (mindestens 32 Zeichen):
  `set OCTALEDGER_API_TOKEN=<langer-zufälliger-Wert>` (für Agent **und** Dashboard setzen).
- **Neues Token erzeugen:** Agent beenden, Datei `api_token` löschen, Agent und Dashboard neu starten.
- Das Token gehört **nie** ins Repository, in Screenshots, Tickets oder Logs (Logs maskieren es
  automatisch). Die Datei steht im Benutzerprofil, nicht im Projektordner.
- Die API ist nur lokal erreichbar (`127.0.0.1`) und prüft zusätzlich `Host` und `Origin`.
  Öffnen Sie das Dashboard nur auf dem eigenen Rechner (`127.0.0.1` oder `localhost`).

## 7. Fehlersuche

| Symptom | Ursache / Abhilfe |
|---|---|
| `Zugriff verweigert` beim Anlegen von Cache-Ordnern | Wird durch `-p no:cacheprovider` in `pyproject.toml` vermieden |
| `ModuleNotFoundError: octaledger` | Paket nicht installiert: `pip install -e ".[dev]"` im aktiven venv |
| Ausgabe enthält `[OL-…-nnn]` | Stabiler Fehlercode, Bedeutung siehe [SOFTWAREDOKUMENTATION.md](SOFTWAREDOKUMENTATION.md) §2.2 |
