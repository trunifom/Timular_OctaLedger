# Testplan und Teststand

## 1. Automatische Tests (Stand: nach Steuerungsmodus und Dokumentation)

`scripts\run_tests.bat` führt aus: `pytest`, `ruff check .`, `ruff format --check .`, `mypy` (strict).

| Schicht | Ort | Anzahl | Was geprüft wird |
|---|---|---|---|
| Unit | `tests/unit` | 1151 | Fehler, Logging, Dateizugriff, Einstellungen, Domäne, Zustandsautomaten, Zeitalgebra, Datenbank/Migrationen, Repositories, Services, BLE-Protokoll, Fake-Transport, Bleak-Schicht (Stubs), Supervisor, Reporting, Export/Restore, API-Sicherheit, API, Dashboard-Client, CLI; **Steuerungsmodus:** Moduswechsel, Warteschlange, Dispatcher, Geheimnisspeicher, die vier Adapter (Webhook gegen echten lokalen HTTP-Server, MQTT gegen Fake-Broker auf Protokollebene, Home Assistant, Hue); **Dokumentation:** Wächtertests |
| Integration | `tests/integration` | 18 | echter Server + echter Client über HTTP; **ganzer Agent** (BLE-Thread + API-Thread) mit synthetischem Tracker, auch die Kette Drehung → Aktion im Steuerungsmodus |
| GUI | `tests/gui` | 210 | alle 13 Dashboard-Seiten (inkl. Startseite, Würfel live, Seiten zuordnen, Verbindungen) mit `streamlit.testing.v1.AppTest` gegen den **echten** API-Server: Bedienabläufe, Hilfetexte, Fehlermeldungen, Hell/Dunkel, Schriftgröße, HTML-Escaping |
| Hardware | `tests/hardware` | 2 | **manuell**, standardmäßig übersprungen (`OCTALEDGER_HARDWARE_TESTS=1`) |
| **Summe** | | **1381** | **1377 bestanden, 4 übersprungen**: 2 Hardwaretests (bewusst, nur manuell), 1 Test der POSIX-Dateirechte (unter Windows nicht anwendbar) und der Wächtertest „Seite erklärt sich“ für die Startseite (sie ist selbst die Erklärung); ein zeitabhängiger GUI-Test überspringt nur in bestimmten UTC-Stunden |

Grenzen der automatischen Tests (ehrlich):

- Der Tracker wird durch `FakeTransport` **simuliert** (synthetische Daten, nie als echte
  Arbeitszeitdaten auszugeben). Verhalten echter Geräte, Adapter und Treiber ist damit **nicht** belegt.
- `AppTest` prüft Logik und Elemente, **nicht** das visuelle Erscheinungsbild im Browser (Layout, Farben
  im echten Rendering); Kontrastverhältnisse der Farbpaare sind rechnerisch getestet.
- GUI-Tests mit Beispieldaten „heute 00:00–03:00 UTC“ werden zwischen 00:00 und 03:30 UTC übersprungen.
- Zeitabhängige Asynchron-Tests (Supervisor, Agent) nutzen kleine echte Zeiten mit beschränktem Polling;
  sie wurden mehrfach wiederholt ausgeführt (stabil), können aber auf sehr langsamen Rechnern Zeit brauchen.

### Datenverwaltung und Einstellungsseiten (AP-33, AP-34)

Gelöscht wird nur nach Vorschau, Bestätigung mit der Zahl und einer automatischen Sicherung; getestet sind: Wiederherstellung **aus** der Sicherung, Abbruch bei geänderter Zahl, laufender
Eintrag bleibt, Würfel mit/ohne Daten, Zurücksetzen (mit/ohne Einstellungen), Eintippen der Bestätigungstexte, Hilfetext an **jedem** Knopf und Feld, Voreinstellungen im Hilfetext,
Zurücksetzen der App-Einstellungen ohne das Aussehen zu berühren, Sofortwirkung der Darstellung.

### Dokumentation als Testgegenstand

`tests/unit/test_documentation.py` und `tests/unit/test_gui_documentation.py` machen aus Dokumentationsregeln Testfehler: Docstring an jedem Modul, jeder Klasse und jeder Funktion;
jeder Endpunkt steht in `docs/API.md`; jede Quell- und Dokumentationsdatei steht in `docs/ORDNERSTRUKTUR.md`; kein Verweis zwischen den Markdown-Dateien führt ins Leere;
jedes Eingabefeld jeder Seite hat einen Hilfetext; jede Seite hat „So funktioniert diese Seite“; jedes im Handbuch angebotene Dokument existiert und hat Kapitel.

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

### Abnahme des Steuerungsmodus (A-12 bis A-17)

| ID | Kriterium | Software-Nachweis | Nachweis mit echten Zielen |
|---|---|---|---|
| A-12 | Moduswechsel pro Würfel; Zeiterfassung bleibt unberührt, andere Würfel behalten ihren Modus | `test_control_mode`: `test_control_events_never_create_or_touch_time_entries`, `test_other_devices_keep_their_modes_when_one_switches`, `test_a_running_time_entry_blocks_switching_that_tracker_to_control` | – |
| A-13 | Eine Drehung löst genau **eine** Aktion aus; Baseline, „neutral“ und Seiten ohne Aktion lösen nichts aus | `test_a_face_change_queues_exactly_the_action_of_that_face`, `test_the_job_is_tied_to_the_event_so_a_trigger_cannot_be_sent_twice`, `test_only_a_real_face_change_triggers_anything`; Kette: `test_turning_the_cube_in_control_mode_sends_the_action_and_records_no_time` | **offen** |
| A-14 | Aktionen verfallen nach 30 s; die Warteschlange ist begrenzt; Reihenfolge bleibt erhalten | `test_overdue_jobs_expire_instead_of_being_sent_late`, `test_the_queue_is_bounded_and_says_why_it_dropped_an_action`, `test_jobs_are_sent_in_the_order_they_were_created` | – |
| A-15 | Wiederholung nur wenn die Anfrage **sicher nicht ankam**; höchstens 3 Versuche; ein fehlschlagender Adapter blockiert nichts | `test_a_transient_error_is_retried_later_and_then_succeeds`, `test_a_permanent_error_is_not_retried`, `test_retries_stop_after_the_attempts_are_used_up`, `test_a_crashing_adapter_does_not_stop_the_dispatcher`; Adapter-Tests je Fehlerklasse | **offen** |
| A-16 | Zugangsdaten stehen nie in Datenbank, Sicherung, API-Antwort oder Protokoll | `test_secrets_go_to_the_secret_store_and_never_into_the_settings`, `test_stored_and_loaded_secrets_are_masked_in_log_text`, API-Test „Zugangsdaten tauchen nie in Antworten oder Sicherungen auf“ | – |
| A-17 | Jede Anbindung funktioniert mit einem **echten** Ziel (Home Assistant, Hue-Bridge, MQTT-Broker, Webhook-Ziel) | – | **offen** (Tester: „Verbindung testen“, „Jetzt ausprobieren“, dann Würfel drehen; Ergebnis hier eintragen) |

### Geplante Abnahmen A-18 bis A-35 (Erweiterungen)

Für die geplanten Pakete AP-35 bis AP-50 stehen die Abnahmekriterien **A-18 bis A-35** im [Pflichtenheft](PFLICHTENHEFT.md#125-neue-abnahmekriterien) §12.5 und je Paket im [Umsetzungsplan](UMSETZUNGSPLAN.md). Sie sind **noch nicht umgesetzt**; die mit **[HW]** gekennzeichneten brauchen den echten Würfel oder echte Geräte und werden hier mit dem Ergebnis eingetragen, sobald sie geprüft sind.

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
