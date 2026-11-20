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

## 7. Fehlersuche

| Symptom | Ursache / Abhilfe |
|---|---|
| `Zugriff verweigert` beim Anlegen von Cache-Ordnern | Wird durch `-p no:cacheprovider` in `pyproject.toml` vermieden |
| `ModuleNotFoundError: octaledger` | Paket nicht installiert: `pip install -e ".[dev]"` im aktiven venv |
| Ausgabe enthält `[OL-…-nnn]` | Stabiler Fehlercode, Bedeutung siehe [SOFTWAREDOKUMENTATION.md](SOFTWAREDOKUMENTATION.md) §2.2 |
