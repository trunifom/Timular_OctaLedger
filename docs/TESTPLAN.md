# Testplan und Teststand

## 1. Automatische Tests (Stand: Abschluss AP-19)

`scripts\run_tests.bat` führt aus: `pytest`, `ruff check .`, `ruff format --check .`, `mypy` (strict).

| Schicht | Ort | Anzahl | Was geprüft wird |
|---|---|---|---|
| Unit | `tests/unit` | 805 | Fehler, Logging, Dateizugriff, Einstellungen, Domäne, Zustandsautomaten, Zeitalgebra, Datenbank/Migrationen, Repositories, Services, BLE-Protokoll, Fake-Transport, Bleak-Schicht (Stubs), Supervisor, Reporting, Export/Restore, API-Sicherheit, API, Dashboard-Client, CLI |
| Integration | `tests/integration` | 14 | echter Server + echter Client über HTTP; **ganzer Agent** (BLE-Thread + API-Thread) mit synthetischem Tracker |
| GUI | `tests/gui` | 81 | alle 8 Dashboard-Seiten mit `streamlit.testing.v1.AppTest` gegen den **echten** API-Server: Bedienabläufe, Hilfetexte, Fehlermeldungen, Hell/Dunkel, Schriftgröße, HTML-Escaping |
| Hardware | `tests/hardware` | 2 | **manuell**, standardmäßig übersprungen (`OCTALEDGER_HARDWARE_TESTS=1`) |
| **Summe** | | **902** | **900 bestanden, 2 übersprungen** |

Grenzen der automatischen Tests (ehrlich):

- Der Tracker wird durch `FakeTransport` **simuliert** (synthetische Daten, nie als echte
  Arbeitszeitdaten auszugeben). Verhalten echter Geräte, Adapter und Treiber ist damit **nicht** belegt.
- `AppTest` prüft Logik und Elemente, **nicht** das visuelle Erscheinungsbild im Browser (Layout, Farben
  im echten Rendering); Kontrastverhältnisse der Farbpaare sind rechnerisch getestet.
- GUI-Tests mit Beispieldaten „heute 00:00–03:00 UTC“ werden zwischen 00:00 und 03:30 UTC übersprungen.
- Zeitabhängige Asynchron-Tests (Supervisor, Agent) nutzen kleine echte Zeiten mit beschränktem Polling;
  sie wurden mehrfach wiederholt ausgeführt (stabil), können aber auf sehr langsamen Rechnern Zeit brauchen.

## 2. Abnahmekriterien (Pflichtenheft §10) – Nachweisstatus

| ID | Kriterium | Software-Nachweis | Hardware-Nachweis |
|---|---|---|---|
| A-01 | alle 8 Flächen beider Tracker kalibriert | Kalibrierung, Fortschritt, Persistenz getestet (`test_gui_devices_catalog`, `test_device_catalog_services`) | **offen** – echte Würfel nötig |
| A-02 | 20 identische Rohwerte → kein zusätzlicher Wechsel | Debouncer-, Supervisor- und Pipeline-Test | **offen** |
| A-03 | Zwischenfläche unter Stabilitätsfrist → kein Wechsel | Debouncer- und Supervisor-Test | **offen** (Entprellzeit am Gerät prüfen) |
| A-04 | Reconnect erzeugt keine unbeabsichtigte Sitzung | Tracking-Service-, Supervisor- und Agent-E2E-Test | **offen** |
| A-05 | Dashboard-Rerun/Schließen lässt Erfassung weiterlaufen | Architektur (getrennter Agentenprozess) + Agent-E2E ohne Dashboard | **offen** (Langzeitlauf) |
| A-06 | Neustart erhält bestätigte Daten, markiert unklaren Abschnitt | `test_restart_keeps_confirmed_data_and_unclear_section` | – |
| A-07 | Übergabe erzeugt keine doppelte persönliche Zeit | Übergabe-Tests (Service, API, GUI) | **offen** (zwei Geräte) |
| A-08 | Korrektur nachvollziehbar, Export = korrigierte Ansicht | Repository-, Export-Tests | – |
| A-09 | JSON-Backup in leerer Umgebung restaurierbar | Rundlauftest, CLI-/GUI-Tests | – |
| A-10 | Keine Tokens/echten Daten im Repository | `.gitignore` (DB, Logs, Token, `.env`), synthetische Fixtures; Stichprobe `git grep` ohne Treffer | – |
| A-11 | pytest, Ruff, mypy bestehen | `scripts\run_tests.bat` grün (siehe oben) | – |

## 3. Manueller Hardwaretest

Nur auf ausdrücklichen Start, nur Suchen/Lesen/Abonnieren (nie Schreiben, nie automatisches Verbinden
unbekannter Geräte). Ablauf: [INSTALLATION.md](INSTALLATION.md) Abschnitt 5.

Testfälle: alle Flächen; schnelles/langsames Drehen; Duplikate; Neutralwert; konkurrierende
Hersteller-App; Reichweite; Schlafmodus; Adapter aus/an; Reconnect; zwei Tracker; Dashboard schließen;
Agentabsturz; Neustart; Uhrsprung; Sommerzeit; voller Datenträger; beschädigter Import; API nicht
erreichbar; falsches Token; Backup in frischer Umgebung. Latenz, CPU und Langzeitstabilität **messen**,
keine Zahlen erfinden.

### Kompatibilitätsmatrix (vom Tester auszufüllen)

| Modell | Firmware | Windows | Adapter | Treiber | Python | Bleak | App-Version | Ergebnis |
|---|---|---|---|---|---|---|---|---|
| _offen_ | | | | | 3.12.3 | 3.1.0 | 0.1.0.dev0 | |

Die Testumgebung der automatischen Tests: Windows 11 (10.0.26300), Python 3.12.3, Bleak 3.1.0,
Streamlit 1.67.0, FastAPI 0.165.0 (siehe `constraints-tested.txt`).
