# OctaLedger

Lokale (local-first) Zeiterfassung für **Timeular-/ZEI-Bluetooth-Tracker** unter Windows: Würfel auf die
Seite einer Tätigkeit drehen, die Zeit läuft – gespeichert in einer lokalen Datenbank, verwaltet und
ausgewertet in einem übersichtlichen Dashboard. Kein Konto, keine Cloud, keine Telemetrie.

Das Projekt ist unabhängig von Timeular und EARLY und nicht mit deren Herstellern verbunden.

## Status

| Bereich | Stand |
|---|---|
| Software (Agent, Datenbank, API, Dashboard, Export/Backup, CLI) | **vollständig umgesetzt** |
| Automatische Tests | **923 bestanden, 2 Hardwaretests bewusst übersprungen** (Windows 11, Python 3.12); `ruff` und `mypy --strict` sauber |
| Echte Tracker-Hardware | **noch nicht geprüft** – bisher nur mit einem Simulator (FakeTransport) getestet |
| Bluetooth-Protokoll | Community-Referenz, **nicht** hardwarevalidiert (Kompatibilität pro Exemplar/Firmware prüfen) |
| Lizenz | **noch nicht gewählt** – ohne Lizenz ist veröffentlichter Code nicht frei nachnutzbar |

Details und Nachweise: [docs/FORTSCHRITT.md](docs/FORTSCHRITT.md), [docs/TESTPLAN.md](docs/TESTPLAN.md),
[docs/QUELLEN_UND_GRENZEN.md](docs/QUELLEN_UND_GRENZEN.md).

## Funktionen

- **Automatische Erfassung:** Seitenwechsel starten und beenden Zeitabschnitte; Entprellung gegen
  Fehlwechsel, Baseline-Regel (die erste Meldung startet nichts), saubere Duplikatbehandlung.
- **Robust bei Verbindungsproblemen:** automatischer Reconnect mit begrenztem Backoff; Lücken werden als
  *unsicher* markiert und nach Rückkehr von Ihnen bestätigt – es wird keine Historie erfunden.
- **Zwei Tracker:** beide registrierbar, nur der aktive erzeugt Zeiten; ausdrückliche Übergabe ohne
  doppelte Zeit.
- **Dashboard (Streamlit, 11 Bereiche in 4 Menügruppen):** *Start* (Startseite: Erklärung, geführte
  Einrichtung mit einem Klick, Handbuch zum Nachlesen), *Alltag* (Übersicht, **Würfel live**, Zeitjournal,
  Statistik), *Einrichten* (Geräte, **Seiten zuordnen**, Verwaltung), *System* (Daten, Einstellungen, Diagnose). **Statusleiste auf jeder Seite** (läuft
  etwas? Tracker verbunden? etwas zu tun?), *Erste Schritte*-Checkliste, Schnellstart-Kacheln, Hilfetext an
  jedem Feld, Hell-/Dunkel-Umschalter, zwei Schriftgrößen, lokale Schrift Inter (WCAG-AA-Kontrast). Konzept
  und Recherche: [docs/GUI_KONZEPT.md](docs/GUI_KONZEPT.md).
- **Daten sicher im Griff:** atomares Speichern, versionierte Migrationen mit automatischer Sicherung,
  CSV-Export (Excel-tauglich, Formel-Injection-Schutz), JSON-Backup mit Prüfsumme, **validierter**
  Restore mit Vorschau und Rollback.
- **Sicherheit:** lokale API nur auf Loopback, Token (nur im Header), Host-/Origin-Prüfung, keine
  Geheimnisse im Log, **keine BLE-Schreibzugriffe** (nur lesen und abonnieren).

## Schnellstart (Windows)

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]" -c constraints-tested.txt
scripts\start_all.bat
```

`start_all.bat` startet den Agenten (Hintergrunderfassung) und das Dashboard
(`http://127.0.0.1:8501`). Weiter mit dem [Schnellstart im Benutzerhandbuch](docs/BENUTZERHANDBUCH.md#3-schnellstart-in-10-minuten).

Qualitätsprüfung: `scripts\run_tests.bat` (pytest, ruff, ruff format --check, mypy).

## Architektur in einem Bild

```text
Tracker (BLE) ──► Agent: Bleak + EIN asyncio-Loop ──► Entprellung/Baseline ──► Tracking-Service
                          │                                                     │
                          └──────────── SQLite (einziger Schreiber) ◄───────────┘
                                              ▲
                          lokale Token-API (FastAPI, nur 127.0.0.1)
                                              ▲
                              Streamlit-Dashboard (nur API, kein SQL/BLE)
```

Schichten: `domain` → `application` → `infrastructure` / `api` / `agent`; das Dashboard spricht nur über
`dashboard_client` mit der API. Details: [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Dokumentation

| Zielgruppe | Dokument |
|---|---|
| **Anwender** | [Benutzerhandbuch](docs/BENUTZERHANDBUCH.md) |
| **Installation / Betrieb** | [Installation und Ausführung](docs/INSTALLATION.md) |
| **Gestaltung** | [GUI-Konzept (Recherche, Design-System)](docs/GUI_KONZEPT.md) |
| **Entwickler** | [Softwaredokumentation](docs/SOFTWAREDOKUMENTATION.md), [Architektur](docs/ARCHITEKTUR.md), [Datenmodell](docs/DATENMODELL.md), [BLE-Protokoll](docs/BLE_PROTOCOL.md), [Ordnerstruktur](docs/ORDNERSTRUKTUR.md) |
| **Anforderungen & Planung** | [Pflichtenheft](docs/PFLICHTENHEFT.md), [Roadmap](docs/ROADMAP.md), [Tests](docs/TESTPLAN.md), [Fortschritt](docs/FORTSCHRITT.md) |
| **Grenzen & Quellen** | [Quellen und Grenzen](docs/QUELLEN_UND_GRENZEN.md), [Sicherheit](SECURITY.md) |
| **Mitarbeit & LLM-Agenten** | [CLAUDE.md](CLAUDE.md), [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), [GitHub](docs/GITHUB.md) |

## Datenschutz und Lizenz

Keine echten Zeitdaten, Datenbanken, Logs oder Tokens ins Repository aufnehmen (`.gitignore` schützt
die üblichen Pfade; Nutzerdaten liegen ohnehin im Benutzerprofil). Die Vorlage enthält bewusst **keine
gewählte Open-Source-Lizenz**; **vor einer Veröffentlichung muss eine Lizenz festgelegt werden.**
Öffentlicher Quellcode ist ohne Lizenz nicht automatisch frei nachnutzbar.
