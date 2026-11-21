# Softwaredokumentation (Entwickler)

Diese Datei beschreibt Module, Schnittstellen und Entwurfsentscheidungen des
implementierten Codes. Die Zielarchitektur steht in [ARCHITEKTUR.md](ARCHITEKTUR.md),
die Anforderungen im [Pflichtenheft](PFLICHTENHEFT.md), die Arbeitsregeln in
[CLAUDE.md](../CLAUDE.md). Jedes Arbeitspaket (AP) ergänzt hier seinen Abschnitt.

**Inhalt**

1. [Überblick](#1-überblick)
2. [Fehlerbehandlung (`octaledger.core.errors`, AP-01)](#2-fehlerbehandlung-octaledgercoreerrors-ap-01)
3. [Logging (`octaledger.core.logging`, AP-02)](#3-logging-octaledgercorelogging-ap-02)
4. [Dateizugriff (`octaledger.core.fileio`, AP-03a)](#4-dateizugriff-octaledgercorefileio-ap-03a)
5. [Einstellungen und Pfade (`octaledger.core.settings`, AP-03)](#5-einstellungen-und-pfade-octaledgercoresettings-ap-03)
6. [Domänenmodelle (`octaledger.domain.models`, AP-04)](#6-domänenmodelle-octaledgerdomainmodels-ap-04)
7. [Zustandsautomaten (`octaledger.domain.state_machine`, AP-05)](#7-zustandsautomaten-octaledgerdomainstate_machine-ap-05)
8. [Intervall-Algebra (`octaledger.domain.time_rules`, AP-06)](#8-intervall-algebra-octaledgerdomaintime_rules-ap-06)
9. [Datenbank und Migrationen (`octaledger.infrastructure.storage.database`, AP-07)](#9-datenbank-und-migrationen-octaledgerinfrastructurestoragedatabase-ap-07)
10. [Repositories (`octaledger.infrastructure.storage.repositories`, AP-08)](#10-repositories-octaledgerinfrastructurestoragerepositories-ap-08)
11. [Tracking-Service (`octaledger.application.tracking_service`, AP-09)](#11-tracking-service-octaledgerapplicationtracking_service-ap-09)
12. [Geräte- und Katalog-Service (`application.device_service`, `application.catalog_service`, AP-10)](#12-geräte--und-katalog-service-applicationdevice_service-applicationcatalog_service-ap-10)
13. [BLE-Protokoll, Transport-Abstraktion, FakeTransport (`infrastructure.ble`, AP-11)](#13-ble-protokoll-transport-abstraktion-faketransport-infrastructureble-ap-11)
14. [Bleak-Scanner und -Client (`infrastructure.ble.scanner`, `infrastructure.ble.client`, AP-12)](#14-bleak-scanner-und--client-infrastructureblescanner-infrastructurebleclient-ap-12)
15. [Agent-Supervisor (`octaledger.agent.supervisor`, AP-13)](#15-agent-supervisor-octaledgeragentsupervisor-ap-13)
16. [Reporting-Service (`octaledger.application.reporting_service`, AP-14)](#16-reporting-service-octaledgerapplicationreporting_service-ap-14)
17. [Export, Backup und Restore (`octaledger.application.export_service`, AP-15)](#17-export-backup-und-restore-octaledgerapplicationexport_service-ap-15)
18. [API-Sicherheit (`octaledger.api.security`, AP-16a)](#18-api-sicherheit-octaledgerapisecurity-ap-16a)
19. [Lokale HTTP-API (`octaledger.api`, AP-16)](#19-lokale-http-api-octaledgerapi-ap-16)
20. [Dashboard-Client (`octaledger.dashboard_client.client`, AP-17)](#20-dashboard-client-octaledgerdashboard_clientclient-ap-17)
21. [Dashboard-Grundgerüst (`octaledger.dashboard`, AP-18a)](#21-dashboard-grundgerüst-octaledgerdashboard-ap-18a)
22. [Seiten „Geräte“ und „Verwaltung“ (`dashboard.views.devices`, `dashboard.views.catalog`, AP-18b)](#22-seiten-geräte-und-verwaltung-dashboardpagesdevices-dashboardpagescatalog-ap-18b)
23. [Seiten „Zeitjournal“ und „Statistik“ (`dashboard.views.journal`, `dashboard.views.statistics`, AP-18c)](#23-seiten-zeitjournal-und-statistik-dashboardpagesjournal-dashboardpagesstatistics-ap-18c)
24. [Seiten „Daten“, „Einstellungen“ und „Diagnose“ (AP-18d)](#24-seiten-daten-einstellungen-und-diagnose-ap-18d)
25. [Agent-Laufzeit und Kommandozeile (`octaledger.agent.main`, `octaledger.cli`, AP-19)](#25-agent-laufzeit-und-kommandozeile-octaledgeragentmain-octaledgercli-ap-19)
26. [Qualitätssicherung, Teststrategie und Erweiterungspunkte (AP-20)](#26-qualitätssicherung-teststrategie-und-erweiterungspunkte-ap-20)
27. [GUI-Überarbeitung: Design-System, Navigation, Statusleiste (AP-21)](#27-gui-überarbeitung-design-system-navigation-statusleiste-ap-21)
28. [Live-Ansicht und Würfelgrafik (`dashboard.views.live`, `dashboard.cube`, AP-23)](#28-live-ansicht-und-würfelgrafik-dashboardviewslive-dashboardcube-ap-23)
29. [Zuordnungs-Assistent „Seiten zuordnen“ (`dashboard.views.faces`, AP-24)](#29-zuordnungs-assistent-seiten-zuordnen-dashboardviewsfaces-ap-24)
30. [Startseite, geführte Einrichtung und Handbuch (`dashboard.views.start`, `dashboard.docs_reader`, AP-25)](#30-startseite-geführte-einrichtung-und-handbuch-dashboardviewsstart-dashboarddocs_reader-ap-25)
31. [Steuerungsmodus und Integrationen (AP-26 bis AP-31)](#31-steuerungsmodus-und-integrationen-ap-26-bis-ap-31)

## 1. Überblick

### 1.1 Pakete und Schichten

```text
src/octaledger/
  core/              Fehler (§2), Logging (§3), Dateizugriff (§4), Einstellungen/Pfade (§5)
  domain/            Modelle (§6), Zustandsautomaten (§7), Zeit/Intervalle (§6, §8) - rein, ohne I/O
  application/       Tracking (§11), Geräte/Katalog (§12), Berichte (§16), Export/Backup (§17)
  infrastructure/
    storage/         SQLite, Migrationen (§9), Repositories (§10)
    ble/             Protokoll/Transport/Fake (§13), Bleak-Scanner und -Client (§14)
    integrations/    leerer Platzhalter für optionale Adapter (F-20)
  agent/             Supervisor (§15), Laufzeit und Start/Shutdown (§25)
  api/               Sicherheit (§18), Routen/Schemas/App (§19)
  dashboard_client/  HTTP-Client (§20)
  dashboard/         Streamlit-Oberfläche (§21-24)
  cli.py             Kommandozeile (§25)
```

Abhängigkeitsrichtung: `domain` ← `application` ← `infrastructure`/`api`/`agent`. `core` darf von allen
Schichten genutzt werden, importiert selbst nichts aus ihnen. Das Dashboard kennt nur `dashboard_client`.

### 1.2 Datenfluss einer Würfeldrehung

```text
Tracker --BLE notify--> BleakTransport._callback --> DeviceWorker._on_notification (kurz, thread-sicher)
  --> begrenzter Puffer --> OrientationDebouncer (Baseline/Duplikat/Entprellung)
  --> RawEvent --(to_thread)--> TrackingService.record_event --> Storage.transaction
  --> sessions/raw_events in SQLite --> API (/status, /sessions, /reports) --> Dashboard
```

### 1.3 Grundregeln (vollständig in [CLAUDE.md](../CLAUDE.md))

UTC intern (nie naive Zeiten), SQL nur im Storage-Paket und immer parametrisiert, stabile Fehlercodes statt
nackter Ausnahmen, Logging nur über `logging.getLogger(__name__)` mit zentraler Redaktion, **keine
BLE-Schreibzugriffe**, Daten atomar speichern und versioniert laden, Hilfetext an jedem GUI-Feld.

## 2. Fehlerbehandlung (`octaledger.core.errors`, AP-01)

### 2.1 Prinzip

Alle bewusst ausgelösten Fehler sind Unterklassen von `OctaLedgerError`. Jede Klasse
hat

- einen **stabilen Fehlercode** `OL-<BEREICH>-<NNN>` (ändert sich nach Veröffentlichung nie),
- eine **technische Meldung** (Englisch, für Logs) und
- eine **Benutzermeldung** (Deutsch, darf in der GUI unverändert erscheinen).

Fremdfehler (`sqlite3`, `OSError`, Bleak, JSON) werden an der Systemgrenze abgefangen und
mit `raise NeuerFehler(...) from exc` übersetzt, damit die Ursache erhalten bleibt.
`ValidationError` (und damit `ProtocolError`) ist zusätzlich ein `ValueError`.

Beim Anlegen einer Unterklasse prüft `__init_subclass__`, dass der Code dem Muster
entspricht und eindeutig ist; die Klassen stehen in `ERROR_REGISTRY`.

### 2.2 Fehlercodes

| Code | Klasse | Bedeutung |
|---|---|---|
| OL-GENERIC-000 | `OctaLedgerError` | Basisklasse / unerwarteter Fehler |
| OL-CONFIG-001 | `ConfigurationError` | Einstellungen fehlen oder sind ungültig |
| OL-VALID-001 | `ValidationError` | Eingabe verletzt eine Regel |
| OL-STATE-001 | `NotFoundError` | Eintrag nicht gefunden |
| OL-STATE-002 | `ConflictError` | Konflikt mit bestehenden Daten |
| OL-STATE-003 | `InvalidStateError` | Aktion im aktuellen Zustand nicht erlaubt |
| OL-STORAGE-001 | `StorageError` | Datenbank lesen/schreiben fehlgeschlagen |
| OL-STORAGE-002 | `MigrationError` | Migration fehlgeschlagen oder Schema zu neu |
| OL-STORAGE-003 | `DataIntegrityError` | Daten beschädigt/widersprüchlich |
| OL-DATA-001 | `ExportError` | Export/Backup schreiben fehlgeschlagen |
| OL-DATA-002 | `ImportDataError` | Import/Restore lesen/validieren fehlgeschlagen |
| OL-BLE-001 | `ProtocolError` | Unerwartete BLE-Nutzdaten |
| OL-BLE-002 | `BleConnectionError` | Scan/Verbindung/Abonnement fehlgeschlagen |
| OL-BLE-003 | `UnsupportedDeviceError` | Gerät bietet erwarteten Dienst nicht |
| OL-API-001 | `AuthenticationError` | Token fehlt oder falsch |
| OL-API-002 | `ApiUnavailableError` | Lokale API nicht erreichbar |
| OL-INTEG-001 | `IntegrationError` | Aktion nicht ausführbar (Ziel lehnt ab oder Ausgang unbekannt); **wird nicht wiederholt** |
| OL-INTEG-002 | `IntegrationConnectionError` | Ziel nicht erreichbar, die Anfrage hatte sicher keine Wirkung; **wird wiederholt** |
| OL-API-003 | `ForbiddenOriginError` | Host-/Origin-Prüfung abgelehnt |

### 2.3 Verwendung

```python
from octaledger.core.errors import StorageError

try:
    connection.execute(sql, params)
except sqlite3.Error as exc:
    raise StorageError("insert failed", details={"table": "devices"}) from exc
```

`error.to_dict()` liefert `code`, `message` (Deutsch), `technical_message` und `details`
für API-Antworten und die GUI. `details` darf niemals Geheimnisse enthalten.

## 3. Logging (`octaledger.core.logging`, AP-02)

### 3.1 Regeln

- Bibliotheksmodule verwenden nur `logging.getLogger(__name__)` und konfigurieren nie
  Handler. Nur Einstiegspunkte (CLI, Agent, Dashboard) rufen `configure_logging()` auf.
- Stufen: **DEBUG** Programmschritte, **INFO** Zustandswechsel, **WARNING** tolerierte
  Abweichung, **ERROR** fehlgeschlagene Operation, **CRITICAL** Prozess unbrauchbar.
- Zeitstempel sind UTC (`2026-11-20T19:52:01.123Z`).

### 3.2 Bausteine

| Name | Zweck |
|---|---|
| `configure_logging(level, log_dir, console, memory_capacity, max_bytes, backup_count)` | Richtet den Logger `octaledger` ein; mehrfach aufrufbar (ersetzt nur eigene Handler, keine Duplikate bei Streamlit-Reruns) |
| `shutdown_logging()` | Schließt eigene Handler (gibt die Logdatei frei) |
| `log_step(logger, "Beschreibung", **kontext)` | Context-Manager: DEBUG bei Start/Ende mit Dauer, ERROR mit Traceback bei Fehler, Ausnahme wird unverändert weitergereicht |
| `register_secret(wert)` | Registriert einen exakten Geheimwert (z. B. API-Token), der überall maskiert wird |
| `redact(text)` | Maskiert Geheimnisse; wird vom Formatter automatisch angewendet |
| `recent_log_lines()` | Ringpuffer der letzten Zeilen für die Diagnose-Seite |
| `parse_level(wert)` | Wandelt Stufenname in Zahl; `ConfigurationError` bei ungültigem Wert |

### 3.3 Redaktion (Datenschutz)

Der `RedactingFormatter` maskiert den **fertig formatierten** Text inklusive Traceback:

- `token=…`, `"password": "…"`, `Authorization: Bearer …`, `api_key=…`, `secret=…` → `***`
  (ein `:` oder `=` ist nötig, damit normale Sätze wie „invalid token provided"
  unverändert bleiben),
- registrierte Geheimwerte (`register_secret`) → `***`,
- Bluetooth-Adressen → `**:**:**:**:EE:FF` (nur die letzten zwei Bytes),
- UUIDs bleiben lesbar (Dienst-UUIDs sind kein Geheimnis).

### 3.4 Dateien

Rotierende Datei `octaledger.log` (Standard 1 MB, 5 Sicherungen) im Log-Ordner des
Benutzerprofils (siehe §5.1). Ist der Ordner nicht beschreibbar, läuft das
Programm weiter: Es gibt eine WARNING und Logging ohne Datei.

### 3.5 Beispiel

```python
import logging
from octaledger.core.logging import configure_logging, log_step

logger = logging.getLogger(__name__)
configure_logging(level="DEBUG", log_dir=log_directory)

with log_step(logger, "open database", path=str(db_path)):
    connection = open_database(db_path)
```

## 4. Dateizugriff (`octaledger.core.fileio`, AP-03a)

Jede Stelle, die eine Datei schreibt (Einstellungen, CSV, JSON-Backup) oder eine fremde
Datei liest (Import, Restore), nutzt dieses Modul. So gelten überall dieselben Garantien.

| Funktion | Garantie |
|---|---|
| `atomic_write_bytes(path, data, error_cls=…)` | Schreibt in eine temporäre Datei im **selben Ordner**, `flush` + `fsync`, dann `os.replace` (atomar). Absturz/volle Platte lassen nie eine halbe Zieldatei zurück; die alte Version bleibt erhalten. Temp-Datei wird bei Fehlern entfernt. |
| `atomic_write_text(path, text, encoding="utf-8", error_cls=…)` | Wie oben für Text. Zeilenumbrüche werden **nicht** übersetzt (der CSV-Writer steuert sie selbst). `utf-8-sig` erzeugt das Excel-BOM. |
| `read_bytes_limited(path, max_bytes=50 MiB, error_cls=ImportDataError)` | Prüft Existenz, „reguläre Datei" und Größe **vor** dem Lesen; erkennt auch Dateien, die während des Lesens wachsen. |
| `read_text_limited(...)` | Wie oben, plus strikte Dekodierung (ungültige Bytes → Fehler statt Ersatzzeichen). |

`OSError` verlässt das Modul nie: Er wird in die vom Aufrufer gewählte Klasse
(`ExportError`, `StorageError`, `ImportDataError` …) übersetzt, die Ursache bleibt als
`__cause__` erhalten, die Benutzermeldung nennt den Dateinamen.

## 5. Einstellungen und Pfade (`octaledger.core.settings`, AP-03)

### 5.1 Datenablage (`AppPaths`, `resolve_paths`)

Nutzerdaten liegen nie im Projektordner. Rangfolge für das Wurzelverzeichnis:
**Argument → Umgebungsvariable `OCTALEDGER_DATA_DIR` → Benutzerprofil des Betriebssystems**
(`platformdirs`, unter Windows `%LOCALAPPDATA%\OctaLedger`).

```text
<root>/
  settings.toml            Benutzereinstellungen
  data/octaledger.sqlite3  Datenbank
  logs/octaledger.log      rotierende Logdatei
  backups/                 automatische und manuelle Backups
  exports/                 Standardziel für CSV/JSON
```

`resolve_paths()` legt nichts an; `ensure_directories()` erzeugt die Ordner idempotent und
meldet Fehler als `StorageError`.

### 5.2 Einstellungen (`Settings`)

Unveränderliche, **selbstvalidierende** Datenklassen (`__post_init__`): ungültige Werte
können weder aus einer Datei geladen noch im Code erzeugt werden. Änderungen erfolgen mit
`dataclasses.replace(...)`, das erneut validiert.

| Abschnitt | Schlüssel | Standard | Erlaubt |
|---|---|---|---|
| `agent` | `host` | `127.0.0.1` | nur Loopback: `127.0.0.1`, `::1`, `localhost` |
| | `port` | `8765` | 1024–65535 |
| `tracking` | `debounce_ms` | `300` | 0–10000 |
| | `baseline_policy` | `observe_only` | `observe_only`, `adopt_current` |
| | `disconnect_policy` | `mark_uncertain` | `mark_uncertain`, `stop_session` |
| | `neutral_policy` | `observe_only` | `observe_only`, `pause` (experimentell) |
| | `mode` | `single_active_tracker` | `single_active_tracker` |
| `display` | `language` | `de` | `de` |
| | `timezone` | `UTC` | beliebiger IANA-Name (nur Anzeige) |
| | `theme` | `light` | `light`, `dark` |
| | `font_size` | `normal` | `normal`, `large` |
| `logging` | `level` | `INFO` | `DEBUG` … `CRITICAL` |
| | `max_bytes` | `1000000` | 10 000 – 104 857 600 |
| | `backup_count` | `5` | 0–50 |

Der API-Token gehört **nicht** in diese Datei (siehe AP-16).

### 5.3 Laden und Speichern

- `load_settings(datei)`: fehlt die Datei → Standardwerte. Ist sie vorhanden, aber
  unlesbar, kein gültiges TOML, zu groß (> 1 MB), enthält unbekannte Abschnitte/Schlüssel
  oder ungültige Werte → `ConfigurationError` mit klarer deutscher Meldung. Nichts wird
  stillschweigend ignoriert (Tippfehler werden bemerkt).
- Danach gelten die Umgebungsvariablen `OCTALEDGER_HOST` und `OCTALEDGER_PORT` als
  Überschreibung (ebenfalls validiert).
- `save_settings(settings, datei)`: atomar über `core.fileio`; bei Fehler bleibt die alte
  Datei erhalten.
- Vorlage: `config/settings.example.toml`.

## 6. Domänenmodelle (`octaledger.domain.models`, AP-04)

Reine Wertobjekte ohne Kenntnis von BLE, SQL, HTTP oder Streamlit. Alle Modelle sind

- **unveränderlich** (`frozen=True`; Änderungen mit `dataclasses.replace`, das erneut validiert),
- **selbstvalidierend** (`__post_init__` → `ValidationError`): ein inkonsistentes Objekt kann
  nicht existieren, auch nicht durch Import oder Datenbank,
- **UTC-normalisiert**: jede Zeit ist zeitzonenbewusst und wird in UTC umgerechnet; naive
  Zeiten werden abgelehnt.

IDs sind zufällige UUID4-Strings (`new_id()`). Eine Bluetooth-Adresse ist **keine** Identität,
nur ein optionaler Hinweis (`Device.platform_address`).

| Modell | Zweck | Wichtige Regeln |
|---|---|---|
| `Device` | Registrierter Tracker | Alias Pflicht (≤ 100 Zeichen); Modell/Firmware optional; leere Texte → `None` |
| `Activity`, `Project` | Tätigkeit / Projekt | Name Pflicht; Farbe `#RRGGBB` (wird groß geschrieben); `archived` |
| `FaceMapping` | Seite 1–8 eines Geräts → Aktivität/Projekt | `face` ∈ 1..8 (kein `bool`); `revision` ≥ 1 |
| `RawEvent` | Unveränderte Beobachtung (Audit) | Art/Wert-Konsistenz: `baseline`/`face_change`/`neutral` brauchen einen Wert, `neutral` genau `0`, `face_change` 1..8; `disconnect`/`reconnect`/`invalid` dürfen keinen haben |
| `Session` | Zeitabschnitt | Ende ≥ Start; `ended_at=None` = läuft; `device`-Quelle braucht `device_id`; `quality` bestätigt/unsicher |
| `Correction` | Auditeintrag einer Änderung | Grund Pflicht; erzeugt Revision ≥ 2; Original bleibt erhalten |

`EventKind` trennt Baseline, Seitenwechsel, Neutralwert, Trennung, Wiederverbindung und
ungültige Pakete bewusst (Pflichtenheft F-06/F-07). Ungültige Pakete erzeugen nie eine Sitzung.

`Session.duration(now)` misst laufende Sitzungen bis `now`.

### Zeithelfer (`octaledger.domain.time_rules`)

| Funktion | Zweck |
|---|---|
| `utc_now()` | Aktuelle Zeit als zeitzonenbewusste UTC-`datetime` |
| `ensure_utc(wert, name=…)` | Rechnet in UTC um, lehnt naive Zeiten ab |
| `interval_duration(start, ende)` | Dauer; lehnt naive und umgekehrte Intervalle ab |

## 7. Zustandsautomaten (`octaledger.domain.state_machine`, AP-05)

Zwei kleine, **reine und deterministische** Automaten (kein I/O, keine Threads, keine echte
Uhr). Zeit wird als ganzzahlige **Millisekunden einer monotonen Uhr** übergeben
(`time.monotonic_ns() // 1_000_000`); sie ist nur innerhalb eines Prozesses vergleichbar.
Läuft sie rückwärts, wird `ValidationError` ausgelöst.

### 7.1 `OrientationDebouncer` (Baseline, Duplikate, Entprellung)

| Regel | Verhalten |
|---|---|
| 1 Baseline | Der erste Wert nach `reset()` ist ein `BASELINE`-Ereignis (sofort, auch bei `0`). Er startet nie eine Sitzung. |
| 2 Duplikate | Wert = bestätigter Wert → ignoriert (`duplicates_ignored`). Gab es einen anderen Kandidaten, wird er verworfen (Rückkehr vor Stabilität). |
| 3 Entprellung | Ein anderer Wert wird *Kandidat*. Erst nach `debounce_ms` Stabilität wird er bestätigt; ein anderer Wert dazwischen startet die Frist neu (Zwischenflächen beim Drehen zählen nicht). |
| 4 Ereignisart | Bestätigte `0` → `NEUTRAL`, `1..8` → `FACE_CHANGE`. |

- `feed(wert, now_ms)` verarbeitet einen Wert, `tick(now_ms)` bestätigt einen stabil
  gewordenen Kandidaten, `next_deadline_ms()` sagt dem Agenten, wann `tick` fällig ist.
- `OrientationEvent.observed_at_ms` ist der Zeitpunkt, an dem die Seite **zum ersten Mal**
  gesehen wurde (nicht das Ende der Frist) – Sitzungen beginnen so zur wahren Zeit.
- Ein später eintreffender Wert bestätigt zuerst einen abgelaufenen alten Kandidaten und
  wird danach beurteilt (kein Verlust bei verspätetem `tick`).
- `debounce_ms=0` bestätigt sofort. Abnahme A-02 (20 identische Werte → keine zusätzliche
  Änderung) und A-03 (Zwischenfläche unter Stabilitätsfrist → kein Wechsel) sind durch
  Unit-Tests abgedeckt.

### 7.2 `ConnectionStateMachine` (Verbindungslebenszyklus)

```text
idle → scanning → connecting → discovering → subscribing → baseline → ready
ready → disconnected → reconnect_wait → connecting          (jeder Zustand → stopped)
```

- Ungültige Übergänge → `InvalidStateError` (Zustand bleibt unverändert).
- „Verbunden“ ≠ „gültige Orientierung“: nur `READY` (`is_ready`) bedeutet, dass die
  Baseline gelesen wurde.
- Jeder Eintritt in `CONNECTING` vergibt eine neue **Verbindungskennung**. Mit
  `is_current(id)` werden späte Ergebnisse alter Zyklen erkannt und ignoriert.
- `attempt` zählt Fehlversuche vor `READY`; Erreichen von `READY` setzt ihn zurück. Ein
  Verlust im Zustand `READY` zählt nicht als Fehlversuch.
- `STOPPED` (bewusster Benutzerstopp) verhindert Reconnects; nur `idle` (expliziter Neustart)
  ist danach erlaubt.
- `history` hält die letzten 50 Übergänge für die Diagnose.

`reconnect_delay_seconds(attempt, base=1, factor=2, cap=60)` liefert die begrenzte
exponentielle Wartezeit (1, 1, 2, 4, 8, … höchstens 60 s); der Supervisor (AP-13) kann
Jitter ergänzen.

## 8. Intervall-Algebra (`octaledger.domain.time_rules`, AP-06)

Reine Funktionen für Berichte. Ein `Interval` ist ein halboffenes Paar `[start, ende)` in UTC.
Alle Funktionen lehnen naive oder umgekehrte Zeiten mit `ValidationError` ab.

| Funktion | Zweck |
|---|---|
| `parse_timezone(name)` | IANA-Zeitzone laden; unbekannt → `ValidationError` mit deutscher Meldung |
| `local_day_bounds(tag, tz)` | `[Start, Ende)` des lokalen Kalendertags in UTC (23, 24 oder 25 Stunden bei Sommerzeitwechsel) |
| `local_week_bounds(tag, tz, week_starts_on=0)` | Lokale Woche (0 = Montag, ISO; 6 = Sonntag) |
| `split_at_day_boundaries(start, ende, tz)` | Teilt an lokalen Mitternächten in `(Datum, Intervall)`; Teile sind lückenlos, ihre Summe ist die Gesamtdauer; endet ein Intervall genau um Mitternacht, entsteht kein leerer Teil |
| `clip_interval(intervall, fenster)` | Teil innerhalb eines Zeitfensters oder `None` |
| `merge_intervals(liste)` | Vereinigung als sortierte, überschneidungsfreie Spannen (berührende werden verbunden, leere entfallen) |
| `union_duration(liste)` | **Persönliche Arbeitszeit**: überlappende Zeit wird nur einmal gezählt |
| `sum_durations(liste)` | **Gerätezeit**: einfache Summe (Überlappungen je Gerät gezählt) |
| `find_overlaps(paare)` | Paare `(id_a, id_b)` überlappender Intervalle; Berührung ist keine Überlappung |

Pflichtenheft §6: Berichte müssen zwischen *Summe der Gerätezeiten* (`sum_durations`) und
*überschneidungsfreier persönlicher Arbeitszeit* (`union_duration`) unterscheiden – beide
Summen dürfen nie einfach addiert werden.

**Sommerzeit:** Tagesgrenzen werden aus dem lokalen Kalender berechnet, nicht durch Addieren
von 24 Stunden. Beispiele (Europe/Zurich, Jahr 2026): Der 29.03. hat 23 Stunden, der 25.10.
hat 25 Stunden; die Woche vom 23.–29.03. ist eine Stunde kürzer. Die Tests decken beides ab.
Existiert Mitternacht wegen einer Zeitlücke nicht, beginnt der Tag am ersten gültigen Moment.

## 9. Datenbank und Migrationen (`octaledger.infrastructure.storage.database`, AP-07)

### 9.1 Verbindungen und Transaktionen

- **Eine kurzlebige Verbindung pro Vorgang** (`Database.connect()`): SQLite-Verbindungen sind
  billig und nicht thread-sicher. Dank WAL blockieren Leser (API-Threads) den einzigen
  Schreiber (Agent) nicht.
- Pragmas je Verbindung: `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`,
  `busy_timeout=5000`.
- **Explizite Transaktionen** (`Database.transaction()`): Verbindungen laufen im Autocommit
  (`isolation_level=None`); der Kontextmanager führt `BEGIN IMMEDIATE` (Schreibsperre sofort),
  bei Erfolg `COMMIT`, bei jeder Ausnahme `ROLLBACK` aus. `sqlite3`-Fehler werden übersetzt,
  andere Ausnahmen unverändert weitergereicht.

### 9.2 Fehlerübersetzung (`translate_sqlite_error`)

| sqlite3 | OctaLedger-Fehler | Beispiel |
|---|---|---|
| `IntegrityError` | `ConflictError` (OL-STATE-002) | doppelter Name, Überschneidung, noch verwendeter Eintrag |
| „not a database“, „malformed“, „corrupt“ | `DataIntegrityError` (OL-STORAGE-003) | beschädigte Datei |
| „locked“, „busy“ | `StorageError` (OL-STORAGE-001) mit Hinweis „Datenbank belegt“ | gleichzeitiger Schreiber |
| sonstige | `StorageError` | I/O-Fehler |

### 9.3 Schema (Migration `0001_initial.sql`)

| Tabelle | Inhalt | Wichtige Garantien |
|---|---|---|
| `devices` | Tracker | Alias eindeutig (ohne Groß-/Kleinschreibung) |
| `activities`, `projects` | Tätigkeiten, Projekte | Name unter **nicht archivierten** eindeutig; Farbe `#RRGGBB` per CHECK |
| `face_mappings` | Seite 1–8 → Tätigkeit/Projekt | PK (Gerät, Seite); wird mit dem Gerät gelöscht |
| `raw_events` | Beobachtungen | Art und Wert per CHECK; Gerät kann nicht gelöscht werden, solange Ereignisse existieren |
| `sessions` | Zeitabschnitte | Ende ≥ Start; Geräte-Sitzung braucht Gerät; **höchstens eine laufende Sitzung** (Unique-Index); **keine Überschneidungen** (Trigger bei INSERT/UPDATE; Berührung erlaubt) |
| `corrections` | Änderungsprotokoll | Grund Pflicht; wird mit der Sitzung gelöscht |
| `audit_log` | Löschungen/Restore | nachvollziehbare destruktive Aktionen |
| `schema_migrations` | angewendete Migrationen | Version, Name, **SHA-256-Prüfsumme**, Zeitpunkt |

Konventionen: UUID-Strings als Schlüssel; Zeitstempel als UTC-Text mit **fester Breite**
`YYYY-MM-DDTHH:MM:SS.ffffffZ` (Textvergleich = zeitlicher Vergleich); Booleans 0/1 mit CHECK.
Aufbewahrung: referenzierte Tätigkeiten/Projekte/Geräte sind per `ON DELETE RESTRICT`
geschützt – stattdessen archivieren. Der Ausbau auf parallele Gerätezeitachsen (Roadmap
„Später“) erfordert eine neue Migration, die den Überschneidungs-Trigger anpasst.

### 9.4 Migrationen

SQL-Dateien `NNNN_name.sql` im Paket (`storage/migrations/`, als Package-Data ausgeliefert),
lückenlos ab `0001`. `Database.initialize()`:

1. lädt und validiert die Migrationen (Dateiname, lückenlose Versionen),
2. prüft die **Prüfsumme** bereits angewendeter Migrationen (nachträgliche Änderung →
   `MigrationError`),
3. verweigert eine Datenbank, die **neuer** ist als das Programm (unverändert, mit
   Update-Hinweis),
4. legt vor jeder Migration einer **bestehenden** Datenbank ein **verifiziertes Backup**
   `backups/octaledger-pre-migration-vA-to-vB-<UTC>.sqlite3` an,
5. wendet jede ausstehende Migration in **einer Transaktion** an (alles oder nichts);
   schlägt eine fehl, bleibt sie ohne Spuren zurückgerollt, frühere bleiben bestehen.

Migrationsdateien enthalten kein `BEGIN`/`COMMIT`. `split_statements` zerlegt Skripte
korrekt, auch Trigger-Rümpfe mit inneren Semikolons.

### 9.5 Backup und Diagnose

- `Database.backup_to(ziel)`: konsistente Kopie der **laufenden** Datenbank über die
  SQLite-Backup-API; die Kopie wird mit `PRAGMA integrity_check` geprüft und erst dann
  atomar unter dem Zielnamen abgelegt (kein halbes Backup).
- `Database.integrity_check()`: SQLite-Integritätsprüfung plus `foreign_key_check`; leere
  Liste = gesund.

## 10. Repositories (`octaledger.infrastructure.storage.repositories`, AP-08)

Übersetzen zwischen Domänenmodellen und SQL-Zeilen. **Sämtliches SQL der Anwendung liegt in
`database.py` und `repositories.py`**, immer parametrisiert; Services und GUI enthalten kein SQL.

### 10.1 Aufbau

- Jedes Repository bindet **eine** `sqlite3.Connection` und öffnet/committet nichts selbst.
  Die Transaktionsgrenze liegt beim Aufrufer, damit mehrere Aufrufe **gemeinsam** gelingen
  oder scheitern.
- `Storage(database)` ist der Einstiegspunkt:

  ```python
  storage = Storage(database)
  with storage.transaction() as repos:  # atomar: Commit bei Erfolg, Rollback bei Fehler
      repos.sessions.end(running.id, now)
      repos.sessions.add(next_session)
  with storage.read() as repos:  # nur lesen
      sessions = repos.sessions.list_between(start, end)
  ```
- `Repositories` bündelt `devices`, `activities`, `projects`, `mappings`, `events`,
  `sessions`, `audit` für dieselbe Verbindung.
- Mehrschrittige Operationen (Korrektur, Löschen mit Audit) laufen in einem `SAVEPOINT`:
  atomar für sich und korrekt verschachtelt in einer äußeren Transaktion.
- Zeilen, die die Domänenregeln verletzen (z. B. von Hand verändert), werden als
  `DataIntegrityError` gemeldet statt als ungültiges Objekt zurückgegeben.

### 10.2 Zeitkodierung

`to_db_time()` / `from_db_time()` speichern UTC als Text fester Breite
`YYYY-MM-DDTHH:MM:SS.ffffffZ`; Textvergleich entspricht zeitlichem Vergleich (Indizes,
Bereichsabfragen, Trigger). Falsche Texte → `DataIntegrityError`.

### 10.3 Repositories

| Repository | Methoden (Auswahl) | Besonderheiten |
|---|---|---|
| `devices` | `add`, `get`, `require`, `list_all`, `update`, `delete` | Alias eindeutig; Löschen scheitert (`ConflictError`), solange Ereignisse/Sitzungen das Gerät verwenden |
| `activities`, `projects` | `add`, `get`, `require`, `list_all(include_archived)`, `update`, `set_archived`, `delete` | Name unter nicht archivierten eindeutig; verwendete Einträge werden **archiviert** statt gelöscht |
| `mappings` | `assign`, `get`, `list_for_device`, `clear` | `revision` steigt nur, wenn sich das Ziel ändert; gleiche Zuordnung ändert nichts |
| `events` | `add`, `add_many`, `list_for_device(since, limit)`, `count`, `delete_older_than` | Aufbewahrungsregel `delete_older_than` wird im Audit-Log vermerkt |
| `sessions` | `add`, `get`, `require`, `get_running`, `list_between`, `list_all`, `end`, `correct`, `list_corrections`, `delete` | siehe unten |
| `audit` | `add`, `recent` | Append-only-Protokoll destruktiver Aktionen |

`list_between(start, end, device_id, activity_id, project_id)` liefert Sitzungen, die sich mit
`[start, end)` überschneiden – **ungekürzt**; Berichte teilen und kürzen selbst
(`time_rules`). Laufende Sitzungen zählen als „bis in die Zukunft“.

### 10.4 Korrekturen mit Auditspur (`SessionRepository.correct`)

```python
repos.sessions.correct(
    session_id,
    {"ended_at": new_end, "note": "Nachgetragen", "quality": "confirmed"},
    reason="Tracker lag auf der falschen Seite",
)
```

- Erlaubte Felder: `activity_id`, `project_id`, `started_at`, `ended_at`, `note`, `quality`.
  Alles andere → `ValidationError`.
- Nur **tatsächlich geänderte** Felder werden protokolliert (derselbe Zeitpunkt in anderer
  Zeitzone ist keine Änderung). Ändert sich nichts → `ValidationError`.
- Pro geändertem Feld ein `corrections`-Eintrag (alt, neu, Grund, Zeit, Revision); die
  Sitzungs-`revision` steigt um 1. Das Original bleibt rekonstruierbar.
- Der Grund ist Pflicht. Die gesamte Änderung wird revalidiert (Intervall, Enums, IDs) und ist
  atomar; entsteht dadurch eine Überschneidung, wird alles zurückgerollt (`ConflictError`).
- `delete(session_id, reason, audit)` verlangt ebenfalls einen Grund und schreibt in `audit_log`.

## 11. Tracking-Service (`octaledger.application.tracking_service`, AP-09)

Wandelt Tracker-Ereignisse und Benutzeraktionen in **Sitzungen** um, jeweils in einer
atomaren Datenbanktransaktion. Keine BLE-/HTTP-Kenntnis; der Agent liefert `RawEvent`-Objekte,
die API ruft die Benutzeroperationen. Die Zeit kommt aus einer injizierbaren Uhr
(`clock`), alle Tests laufen deterministisch.

Ergänzend (AP-26a): Migration `0003_integrations.sql` (Spalte `devices.mode` und die Tabellen `integrations`, `face_actions`, `integration_jobs`, siehe §31).

Ergänzend (AP-09): Migration `0002_app_state.sql` (Tabelle `app_state`: aktiver Tracker, Pause),
`StateRepository`, `SessionRepository.set_quality/last_ended/list_by_quality`.

### 11.1 Ereignisregeln (`record_event`)

Jedes Ereignis wird **immer gespeichert** (Diagnose, Audit). Danach gilt:

| Ereignis | Wirkung (Standardrichtlinien) | `Outcome` |
|---|---|---|
| beliebig, Gerät **nicht** aktiv | nur gespeichert, nie eine Sitzung (A-07) | `STORED` |
| `FACE_CHANGE` mit Zuordnung | laufende Sitzung beenden, neue starten; gleiche Tätigkeit+Projekt → weiterlaufen | `STARTED` / `SWITCHED` / `CONTINUED` |
| `FACE_CHANGE` ohne Zuordnung | nichts buchen, WARNING | `UNMAPPED` |
| `BASELINE` | `observe_only`: nur speichern. Läuft eine Sitzung dieses Geräts auf derselben Seite → **fortsetzen** (A-04). `adopt_current`: abweichende Seite übernehmen | `STORED` / `CONTINUED` / `SWITCHED` |
| `NEUTRAL` | `observe_only`: nur speichern; `pause`: Sitzung beenden, Pause merken | `STORED` / `ENDED` |
| `DISCONNECT` | `mark_uncertain`: laufende Geräte-Sitzung als *unsicher* markieren; `stop_session`: zum Zeitpunkt des Verlusts beenden (unsicher) | `MARKED_UNCERTAIN` / `ENDED` |
| `RECONNECT`, `INVALID` | nur gespeichert | `STORED` |

**Zeitschutz:** Der Beginn einer neuen Sitzung wird nie vor den Beginn der laufenden bzw. das
Ende der letzten Sitzung gelegt (`_effective`). Uhrsprünge und verspätete Ereignisse erzeugen
höchstens eine Sitzung der Länge 0, aber nie eine Überschneidung (WARNING im Log).

### 11.2 Aktiver Tracker und Übergabe

- `set_active_device(id|None)`, `get_active_device_id()`: Auswahl wird in `app_state`
  gespeichert und überlebt Neustarts; verweist sie auf ein gelöschtes Gerät → `None`.
- `handover(neuer_tracker, at)`: beendet eine laufende **Geräte**-Sitzung des alten Trackers
  und aktiviert den neuen; manuelle Sitzungen laufen weiter. Der neue Tracker startet mit
  seinem nächsten Ereignis → keine unbemerkte doppelte Zeit (A-07).

### 11.3 Manuelle Bedienung

| Methode | Verhalten |
|---|---|
| `start_manual(aktivität, projekt, notiz, at)` | beendet eine laufende Sitzung zuerst; unbekannte Referenzen → `NotFoundError` |
| `stop(at)` | beendet; nichts läuft → `InvalidStateError` |
| `pause()` / `resume()` | Pause beendet die Sitzung und merkt die Tätigkeit; `resume` startet sie neu; jeder Start/Stop löscht die Pause |
| `add_manual_session(...)` | Nachtrag; Ende in der Zukunft (> 1 min) → `ValidationError`; Überschneidung → `ConflictError` |
| `split_session(id, at, grund)` | teilt in zwei Teile (Teil 2 erbt alles; läuft die Sitzung, läuft Teil 2 weiter); `at` muss strikt innerhalb liegen |
| `correct_session(id, änderungen, grund)` | prüft Referenzen, dann auditierte Korrektur (AP-08) |
| `confirm_session(id)` | *unsicher* → *bestätigt* (idempotent, mit Auditeintrag) |
| `delete_session(id, grund)` | Löschen mit Grund und Audit-Log |
| `list_uncertain()` | Sitzungen, die auf Bestätigung warten |
| `status()` | `TrackingStatus`: laufende Sitzung, Tätigkeit, Projekt, Dauer, Pause, aktiver Tracker, Anzahl unsicherer Sitzungen |

### 11.4 Abnahmekriterien mit Testabdeckung

A-04 (Reconnect erzeugt keine neue Sitzung), A-06 (Neustart erhält Daten und markiert den
unklaren Abschnitt), A-07 (Übergabe ohne doppelte Zeit) und A-08 (Korrektur nachvollziehbar)
sind durch Unit-Tests belegt (`tests/unit/test_tracking_service.py`).

## 12. Geräte- und Katalog-Service (`application.device_service`, `application.catalog_service`, AP-10)

### 12.1 `DeviceService`

| Methode | Verhalten |
|---|---|
| `register(alias, platform_address, model, firmware)` | Registriert einen Tracker (interne UUID + Alias). Der **erste** registrierte Tracker wird automatisch aktiver Tracker. Modell/Firmware dürfen unbekannt sein (F-03). |
| `list_devices()` / `get(id)` | `DeviceInfo`: Gerät, Kalibrierung (`mappings` je Seite), `is_active`; `configured_faces`, `is_fully_calibrated` (alle 8 Seiten mit Tätigkeit) |
| `rename(id, alias)` | Alias ändern (eindeutig, ohne Groß-/Kleinschreibung) |
| `update_hardware_info(id, model, firmware, platform_address)` | Ergänzt bekannte Werte; `None` behält den alten Wert |
| `remove(id)` | Löscht ein Gerät **ohne** aufgezeichnete Daten und räumt die Auswahl des aktiven Trackers auf; sonst `ConflictError` mit klarer Meldung |
| `assign_face(id, face, aktivität, projekt)` | Kalibrierung: Seite 1–8 → Tätigkeit/Projekt (Referenzen werden geprüft); `revision` steigt bei Änderung |
| `clear_face(id, face)` | Zuordnung entfernen |
| `last_observed_face(id)` | Zuletzt gesehene Seite (aus gespeicherten Baseline/Seitenwechsel/Neutral-Ereignissen) – Grundlage der geführten Kalibrierung |

Die ausdrückliche Übergabe zwischen Trackern liegt im `TrackingService.handover()`, weil sie
Sitzungen ändert.

### 12.2 `CatalogService` (Tätigkeiten und Projekte)

`create_*`, `list_*(include_archived)`, `update_*`, `archive_*(archived=True/False)`,
`delete_*` jeweils für Tätigkeiten und Projekte.

- Neue Einträge ohne Farbe erhalten die **am seltensten verwendete Farbe** der
  farbenblind-freundlichen Okabe-Ito-Palette (`PALETTE`), damit Diagramme unterscheidbar bleiben.
- Verwendete Einträge (Sitzungen oder Seitenzuordnungen) lassen sich **nicht löschen**;
  `ConflictError` mit dem Hinweis „bitte archivieren“. Archivierte Einträge verschwinden aus den
  Auswahllisten, bleiben aber in alten Auswertungen erhalten; ihr Name wird wieder frei.
- Löschen unbenutzter Einträge wird im Audit-Log protokolliert.

## 13. BLE-Protokoll, Transport-Abstraktion, FakeTransport (`infrastructure.ble`, AP-11)

### 13.1 Sicherheitsregel

OctaLedger **liest und abonniert nur**. Es gibt in der gesamten BLE-Schicht **keine
Schreiboperation** (keine Motor-/LED-/Firmware-Befehle, Pflichtenheft §2). Das ist per
Konstruktion erzwungen: `DeviceTransport` besitzt keine `write`-Methode; ein Test sichert das ab.

### 13.2 `protocol.py`

- Konstanten: Orientierungsdienst `c7e70010-…`, Characteristic `c7e70012-…` (Community-Referenz,
  **kein** Hardwarebeweis); Standarddienste Batterie (`180f`/`2a19`) und Geräteinformation
  (`180a`, Modell `2a24`, Firmware `2a26`) nur lesend und optional.
- `discover_capabilities(services)` prüft, was das Gerät **wirklich** anbietet:
  - Orientierungs-Characteristic fehlt → `UnsupportedDeviceError` (OL-BLE-003); `details['services']`
    listet alle angebotenen Dienste für einen Kompatibilitätsbericht (F-04).
  - ohne `notify` und `indicate` → `UnsupportedDeviceError`; `notify` wird bevorzugt.
  - Ergebnis `DeviceCapabilities`: `orientation_mode`, `can_read_orientation`, `has_battery`,
    `has_model`, `has_firmware`, `service_uuids`. Fehlende optionale Dienste werden toleriert (F-18).
  - UUID-Vergleiche sind groß-/kleinschreibungsunabhängig.
- Decoder (alle mit `ProtocolError` bei Verstoß): `decode_orientation_payload` (genau 1 Byte,
  0–8), `decode_battery_level` (1 Byte, 0–100), `decode_text` (striktes UTF-8, NUL-Padding
  entfernt, nicht leer, ≤ 100 Zeichen, keine Steuerzeichen).

### 13.3 `transport.py`

`DeviceTransport` (Protocol) ist die **einzige** Schnittstelle des Agenten zu einem Tracker:
`connect`, `disconnect`, `discover`, `read`, `start_notify`, `stop_notify`,
`set_disconnected_callback`, `is_connected`. `TransportFactory.create(adresse)` liefert pro
Verbindungsversuch einen frischen Transport. Alle Methoden laufen im **einen** AsyncIO-Loop des
Agenten. Callbacks müssen kurz und synchron sein (validieren, übergeben, zurückkehren); keine
GUI-Aufrufe und nichts Langsames im BLE-Callback.

### 13.4 `fake.py` (nur synthetische Daten)

`FakeTransport` verhält sich wie ein Tracker ohne Hardware: Verbinden dauert (`connect_delay`)
und kann scheitern (`fail_next_connects`), Dienste müssen entdeckt werden, Benachrichtigungen
kommen per Callback (`push`), die Verbindung kann jederzeit abreißen (`drop_link`, löst den
Verlust-Callback genau einmal aus; ein bewusstes `disconnect` löst ihn nicht aus).
`FakeTransportFactory` verwaltet erzeugte Instanzen. Alles hier ist **synthetisch** und darf nie
als echte Arbeitszeitdaten ausgegeben werden (Testplan). Die Tests nutzen `asyncio.run`, es wird
kein `pytest-asyncio` benötigt.

## 14. Bleak-Scanner und -Client (`infrastructure.ble.scanner`, `infrastructure.ble.client`, AP-12)

### 14.1 Scanner

`await scan(timeout=5.0)` sucht **nur auf ausdrückliche Anforderung** (1–30 s) und liefert
`ScanResult(address, name, rssi, service_uuids, is_candidate, label)` mit der Eigenschaft
`looks_like_tracker` (Name enthält „Timeular“ oder beginnt mit „ZEI“, oder Dienst beworben). Er verbindet **nie**
selbstständig (Testplan: „niemals automatisch unbekannte Geräte verbinden“).

- Geräte, die den Orientierungsdienst bewerben, sind **Kandidaten** und stehen zuerst, danach
  Geräte, deren **Name** auf einen Tracker hindeutet (manche Tracker melden den Dienst erst nach
  dem Verbinden; ein echter Würfel erschien im Test als „Timeular Tra…“ ohne Dienst), danach
  nach Signalstärke. **Es wird nichts herausgefiltert**: Namens-/Dienstfilter dürfen andere
  Hardwaregenerationen nicht unbemerkt ausschließen.
- Fehler (Bluetooth aus, kein Adapter, Rechte) → `BleConnectionError` mit deutscher Meldung.
- `discover=` ist injizierbar, damit die Logik ohne Funk testbar ist.

### 14.2 `BleakTransport`

Implementiert `DeviceTransport` auf Basis von Bleak – bewusst dünn:

- übersetzt Bleak-Typen in neutrale (`GattService`/`GattCharacteristic`, Eigenschaften klein
  geschrieben) und jeden Bleak-/OS-Fehler (`BleakError`, `OSError`, `TimeoutError`) in
  `BleConnectionError` (mit `details['stage']`: `connect`, `discover`, `read`, `subscribe`),
- meldet nur **unerwartete** Verbindungsverluste per Callback; ein bewusstes `disconnect()` löst
  ihn nicht aus,
- `disconnect()`/`stop_notify()` sind idempotent und ignorieren Fehler auf bereits defekter
  Verbindung,
- **keine Schreiboperation**; pro Verbindungszyklus entsteht ein **neuer** Transport
  (`BleakTransportFactory`), alte Instanzen werden nie wiederverwendet.

Alle Operationen laufen im **einen** Loop des Agenten (Bleak-Anforderung).

### 14.3 Teststrategie und Grenzen

Die Unit-Tests ersetzen `BleakClient` bzw. `discover` durch Stubs (Datenübersetzung,
Fehlerabbildung, Loss-Callback). **Das Verhalten mit echten Trackern ist damit nicht belegt**
(parallele Verbindungen am Adapter, Aufwecken, Reichweite, Windows-Treiber). Dafür gibt es
`tests/hardware/test_hardware_smoke.py`: standardmäßig übersprungen, nur mit
`OCTALEDGER_HARDWARE_TESTS=1` (Scan) bzw. zusätzlich `OCTALEDGER_HARDWARE_ADDRESS` (Verbinden,
Dienste, Anfangswert lesen). Ergebnisse gehören in die Kompatibilitätsmatrix des Testplans.

## 15. Agent-Supervisor (`octaledger.agent.supervisor`, AP-13)

Besitzt die dauerhafte Verbindung jedes Trackers in **einem** AsyncIO-Loop und macht aus dem
Funkstrom saubere Ereignisse für den `TrackingService`.

### 15.1 Verbindungszyklus eines `DeviceWorker`

```text
connecting → discovering → subscribing → baseline → ready
                 (Verlust)  ↓
            disconnected → reconnect_wait (Backoff 1,1,2,4,… ≤ 60 s) → connecting
```

1. `transport.connect()` (mit Zeitlimit), `discover_capabilities()`, Abo auf die
   Orientierungs-Characteristic, `debouncer.reset()`.
2. Ab dem **zweiten erfolgreichen** Verbinden wird zuerst ein `RECONNECT`-Ereignis gespeichert
   (fehlgeschlagene Versuche melden nichts; der erste Erfolg ist kein Reconnect).
3. Optional und fehlertolerant: Batterie, Modell, Firmware lesen (`on_hardware_info`); Anfangswert
   lesen, falls lesbar (darf die erste Benachrichtigung duplizieren – wird toleriert).
4. Werte laufen durch den `OrientationDebouncer` (AP-05); erst der erste Wert (Baseline) schaltet
   auf `READY`. Kommt in `baseline_timeout` kein Wert, gilt der Zyklus als fehlgeschlagen.
5. Verbindungsverlust nach erfolgter Verbindung → `DISCONNECT`-Ereignis; der Tracking-Service
   entscheidet (unsicher markieren / beenden). Danach Backoff und neuer Zyklus.

### 15.2 Regeln

| Regel | Umsetzung |
|---|---|
| Ein Besitzer pro Gerät | Nur der `DeviceWorker` berührt „seinen“ Transport; jeder Zyklus bekommt eine neue Verbindungskennung und einen **neuen** Transport |
| Kurze Callbacks | Bleak-Callbacks dekodieren/validieren, hängen an einen **begrenzten** Puffer an und wecken den Worker; ungültige Pakete werden als `INVALID`-Ereignis gespeichert |
| Begrenzte Queue, Überlaufregel | `buffer_size` (Standard 100): bei Überlauf wird der **älteste** Wert verworfen und gezählt (`dropped_values`, WARNING) |
| Nichts blockiert den Loop | `record_event` und Hardware-Info laufen in `asyncio.to_thread`, strikt in Reihenfolge |
| Keine erfundene Historie | Verlust → `DISCONNECT`; bewusstes Stoppen → ebenfalls `DISCONNECT` (die Lücke ist unbekannt), danach `STOPPED` ohne Reconnect |
| Nicht unterstützte Geräte | `UnsupportedDeviceError` → Worker endet in `STOPPED` mit lesbarem Fehler, **kein** endloser Reconnect |
| Speicherfehler | Ein `OctaLedgerError` beim Verarbeiten beendet die Verbindung nicht; Fehler wird protokolliert und in `DeviceStatus.last_error` gezeigt |
| Zeit | Beobachtungen tragen monotone Millisekunden; `_wall_time` rechnet sie in Wanduhrzeit (UTC) um, damit Sitzungen zum tatsächlichen Moment beginnen |
| Stoppen ist prompt | Backoff-Wartezeit und Warten auf Werte sind per Stop-Ereignis unterbrechbar |

`SupervisorTuning` bündelt alle Zeit-/Größenwerte (Standard für den Betrieb; Tests nutzen
Millisekunden-Werte).

### 15.3 `AgentSupervisor`

`start_device(id, adresse)` (idempotent; fehlende Adresse → `ValidationError`), `stop_device(id)`,
`shutdown()` (alle Worker bitten zu stoppen, `shutdown_grace` abwarten, Reste abbrechen),
`statuses()`, `status_of(id)`. `DeviceStatus` zeigt Zustand, Verbindungskennung, Fehlversuche,
letzten Fehler/Wert/Zeitpunkt, Batterie, verworfene und doppelte Werte.

**Live-Daten (AP-22):** `DeviceStatus` enthält zusätzlich `raw_value` (letzter Wert direkt vom Funk,
vor der Entprellung), `raw_at`, `pending_value` (Kandidat, der noch auf `debounce_ms` Ruhe wartet),
`debounce_ms` und `recent` (bis zu 30 `LiveEvent(at, kind, value)`; `kind` ist `raw` oder ein
`EventKind`). Der Verlauf liegt nur im Arbeitsspeicher, nichts davon wird gespeichert; ein
unveränderter Wert erzeugt keinen Eintrag; beim Trennen und bei jedem neuen Verbindungszyklus wird
der Rohwert gelöscht (keine veraltete Position anzeigen).

Hinweis (Pflichtenheft §1): Zwei registrierte Geräte bedeuten **nicht automatisch**, dass zwei
gleichzeitige Verbindungen am verwendeten Adapter zuverlässig sind – das muss praktisch getestet
werden. Der Supervisor startet nur Geräte, die ausdrücklich gestartet werden.

Abnahme A-04 (Reconnect erzeugt keine neue Sitzung) ist über die komplette Pipeline
(Fake-Transport → Debouncer → Tracking-Service → Datenbank) getestet; A-02/A-03 ebenfalls.

## 16. Reporting-Service (`octaledger.application.reporting_service`, AP-14)

Aggregiert Sitzungen für Statistik und Zeitjournal. `build_report(...)` ist eine **reine
Funktion** (mit synthetischen, sogar überlappenden Sitzungen testbar); `ReportService` lädt die
Daten und ruft sie auf.

### 16.1 Rechenregeln

1. **Filter** (`ReportFilter`: Fenster `[start, end)` in UTC, optional `device_id`,
   `activity_id`, `project_id`) wählen Sitzungen aus.
2. Jede Sitzung wird auf das Fenster **gekürzt** und an **lokalen Mitternächten** geteilt
   (`split_at_day_boundaries`, Sommerzeit-korrekt). Laufende Sitzungen enden bei „jetzt“ (Uhr
   injizierbar), nie hinter dem Fensterende.
3. **Gerätezeit** = Summe aller Teile (`sum_durations`). **Persönliche Zeit** = Vereinigung
   (`union_duration`), Überschneidungen zählen einmal. `Report.overlap_time = Gerätezeit −
   persönliche Zeit`. Beide Werte werden getrennt ausgewiesen, nie addiert (Pflichtenheft §6).
4. **Unsicherheit** wird nicht versteckt: `uncertain_time` (Gesamt, je Tag und je Anteil) zeigt,
   wie viel Zeit noch bestätigt werden muss.

### 16.2 Ergebnis (`Report`)

| Feld | Inhalt |
|---|---|
| `daily` | je lokalem Kalendertag des Fensters (auch ohne Daten) `DayTotal(day, device_time, personal_time, uncertain_time)` |
| `by_activity`, `by_project` | `Share(id, name, color, duration, uncertain, fraction)`, größte zuerst; Zeit ohne Projekt als „Ohne Projekt“; gelöschte/unbekannte Tätigkeit als „Unbekannt“ |
| `device_time`, `personal_time`, `overlap_time`, `uncertain_time` | Summen |
| `session_count`, `includes_running` | Anzahl berücksichtigter Sitzungen; ob eine laufende dabei ist |

Fenster länger als `MAX_REPORT_DAYS` (400) → `ValidationError` (schützt GUI und Balkendiagramm).

### 16.3 `ReportService`

- `report(filter, timezone_name)`, `day_report(tag, tz, **filter)`, `week_report(tag, tz,
  week_starts_on=0, **filter)`; Tage/Wochen werden aus dem **lokalen Kalender** berechnet
  (23/25-Stunden-Tage, Montag als Wochenanfang).
- `journal(filter)` liefert **ganze** (ungekürzte) Sitzungen mit aufgelösten Namen
  (`JournalEntry`: Tätigkeit, Projekt, Gerätealias, Dauer), neueste zuerst. Die Dauer läuft für
  laufende Sitzungen bis „jetzt“.

## 17. Export, Backup und Restore (`octaledger.application.export_service`, AP-15)

Ergänzend im Storage: `list_all`-Methoden (Ereignisse, Korrekturen, Audit), `StateRepository.items`,
`Storage.snapshot()` (eine konsistente Lesetransaktion, blockiert den Agenten nicht) und
`BackupRepository` (`snapshot()`, `replace_all()` – das gesamte SQL bleibt im Storage-Paket).

### 17.1 CSV-Export (`sessions_csv`, `export_sessions_csv`)

- Exportiert die **aktuellen, korrigierten** Werte (A-08), optional für ein Fenster.
- Spalten (`CSV_COLUMNS`): `session_id`, `started_local`, `ended_local`, `started_utc`,
  `ended_utc`, `duration_seconds`, `duration_hms`, `running`, `activity`, `project`, `device`,
  `source`, `quality`, `revision`, `note`. Lokale Zeit in der gewählten Zeitzone **und** UTC;
  laufende Sitzungen haben kein Ende und werden bis „jetzt“ gemessen (`running=yes`).
- Datei: **UTF-8 mit BOM** (Excel), Zeilenende `CRLF`, Trennzeichen `;` (Standard, deutsches
  Excel), `,` oder Tabulator. Anführungszeichen, Trennzeichen und Zeilenumbrüche in Zellen werden
  korrekt maskiert.
- **Formel-Injection-Schutz:** Jede Benutzertext-Zelle (Tätigkeit, Projekt, Gerät, Notiz), die mit
  `= + - @`, Tab oder Zeilenumbruch beginnt, bekommt ein führendes `'` (`neutralize_cell`).
- Schreiben atomar (`ExportError` bei Problemen). **Dateinamen** werden erzeugt
  (`sessions-<UTC-Zeit>.csv`) oder streng geprüft (`[A-Za-z0-9._-]`, Endung `.csv`/`.json`, kein
  Pfad) – kein Schreiben außerhalb des Export-/Backup-Ordners.

### 17.2 JSON-Backup (`create_backup_text`, `export_backup`)

```json
{ "format": "octaledger-backup", "schema_version": 2, "app_version": "...",
  "exported_at": "2026-01-05T08:00:00.000000Z", "counts": { "sessions": 3, ... },
  "checksum": "<sha256 über data>", "data": { "devices": [...], "activities": [...],
  "projects": [...], "face_mappings": [...], "raw_events": [...], "sessions": [...],
  "corrections": [...], "audit_log": [...], "app_state": {...} } }
```

Enthält Schema, Kennungen, Zuordnungen, Korrekturen und Auditdaten (Datenmodell). Die
**SHA-256-Prüfsumme** über den kanonisierten `data`-Abschnitt erkennt Beschädigung, Abschneiden
und nachträgliche Änderung. Der Snapshot ist konsistent (`Storage.snapshot`).

### 17.3 Validierung und Restore

`inspect_backup(_text)` prüft eine Sicherung **vollständig, ohne etwas zu ändern** (Vorschau mit
Anzahl je Entität). `restore_backup(_text)`:

1. **Datei lesen** (Größenlimit 200 MB, UTF-8/BOM), **JSON parsen** – nichts aus der Datei wird
   je ausgeführt oder als Pfad benutzt.
2. **Prüfen:** Formatkennung, `schema_version` (neuere Version → Update-Hinweis, nichts
   verändert), Prüfsumme, exakt die erwarteten Abschnitte/Felder, **jeder Datensatz gegen die
   Domänenregeln**, eindeutige Kennungen, alle Verweise (Zuordnung → Gerät/Tätigkeit/Projekt,
   Sitzung → Tätigkeit/Projekt/Gerät, Ereignis → Gerät, Korrektur → Sitzung).
3. **Vorher-Backup:** automatische, geprüfte Kopie der aktuellen Datenbank
   `backups/octaledger-pre-restore-<UTC>.sqlite3` (scheitert sie, wird nicht wiederhergestellt).
4. **Ersetzen in EINER Transaktion** (`replace_all`); Regeln der Datenbank (z. B. Überschneidungen,
   doppelte Namen) greifen weiterhin. **Jeder Fehler → vollständiger Rollback**, bisherige Daten
   unverändert, `ImportDataError` (OL-DATA-002) mit `details['cause_code']`.
5. Ein `restore`-Eintrag im Audit-Log hält fest, was wann wiederhergestellt wurde.

Es gibt bewusst nur den Modus „ersetzen“ (kein Zusammenführen), damit das Ergebnis eindeutig ist.

**Abnahme A-09** (Restore in leerer Umgebung) ist als Rundlauftest belegt: alle Entitäten sind
nach dem Restore identisch zum Original. Ein Backup gilt für den Anwender erst als belastbar, nachdem
ein Restore auf *seinem* Rechner erfolgreich getestet wurde.

## 18. API-Sicherheit (`octaledger.api.security`, AP-16a)

### 18.1 Bedrohungsmodell (MVP)

Die API lauscht nur auf Loopback, das allein reicht nicht: Jedes andere Programm desselben Nutzers
**und jede im Browser geöffnete Webseite** kann Anfragen an `127.0.0.1` senden (CSRF, „DNS
Rebinding“). Deshalb gilt:

| Schutz | Umsetzung |
|---|---|
| **Geheimes Token** | 256 Bit Zufall; schützt alle Routen mit Seiteneffekten oder personenbezogenen Daten. Übertragung **nur** im Header `Authorization: Bearer <token>`, **nie** in URLs. Vergleich in konstanter Zeit (`hmac.compare_digest`). |
| **Host-Prüfung** | Der `Host`-Header muss `127.0.0.1`, `localhost` oder `[::1]` **mit genau dem API-Port** nennen. Verhindert DNS-Rebinding (fremder Name, der auf 127.0.0.1 zeigt). Ohne Port → abgelehnt. |
| **Origin-Prüfung** | Fehlt `Origin` (Dashboard-Server, Skripte), ist die Anfrage zulässig; ist er vorhanden, muss er Loopback über `http(s)` sein. `null`, fremde Seiten, `file:`, Zugangsdaten in der URL und absurde Ports werden abgelehnt. |
| **Kein Zustandswechsel über GET** | wird in den Routen (AP-16) durchgesetzt. |
| **Keine Geheimnisse im Log** | das Token wird bei `load_or_create_token` für die Log-Redaktion registriert. |

### 18.2 Token-Verwaltung

- `load_or_create_token(datei, environ)`: Rangfolge **Umgebungsvariable `OCTALEDGER_API_TOKEN`** →
  vorhandene Datei `<Datenablage>/api_token` → **neu erzeugen** (256 Bit, atomar geschrieben,
  POSIX `0600` best effort; unter Windows gilt die ACL des Benutzerprofils).
- `validate_token_format`: 32–256 Zeichen aus `A–Z a–z 0–9 - _ . ~ + / =`; ungültig →
  `ConfigurationError` mit Hinweis, die Token-Datei zu löschen.
- `verify_token` → `AuthenticationError` (OL-API-001); die Meldung verrät nie, ob Token fehlt oder
  falsch ist, und enthält das Token nie. `parse_bearer` extrahiert das Token aus dem Header.
- `check_request_origin(host, origin, port)` → `ForbiddenOriginError` (OL-API-003) mit
  `details['reason']` (`host`/`origin`).

Nicht umgesetzt (bewusst): Ratenbegrenzung für Fehlversuche – bei 256 Bit Zufall ist Raten
aussichtslos; Netzwerkfreigabe (nur Loopback im MVP, siehe `SECURITY.md`).

## 19. Lokale HTTP-API (`octaledger.api`, AP-16)

FastAPI-Anwendung, die der Agent auf Loopback startet. Das Dashboard spricht **ausschließlich**
über diese API mit dem Agenten (kein eigener BLE-Client, kein SQL im GUI).

### 19.1 Aufbau

| Modul | Aufgabe |
|---|---|
| `context.py` | `AppContext` (Services, `SettingsStore`, Token, Port, Log-Zeilen) und `AgentControl` (Protocol: `start_device`, `stop_device`, `device_statuses`, `scan`) – so ist die API ohne Funk testbar |
| `app.py` | `create_app(context)`: Middleware, Fehlerabbildung; Doku-Endpunkte (`/docs`, `/redoc`, `/openapi.json`) sind **abgeschaltet** |
| `routes.py` | Endpunkte; Handler sind einfache `def`-Funktionen (Threadpool, blockierendes SQLite), enthalten **keine** Geschäftslogik |
| `schemas.py` | Strikte Request-Modelle (`extra="forbid"`) und Antwortfunktionen; Zeiten ISO-8601 UTC, Dauern in ganzen Sekunden |
| `security.py` | siehe Abschnitt 18 |

### 19.2 Querschnittsregeln

- **Authentifizierung:** `Authorization: Bearer <token>` für alles außer `GET /api/v1/health`.
  Token nie in URLs (`?token=` wird nicht akzeptiert).
- **Middleware** (vor jeder Route): Host-/Origin-Prüfung (`403`, OL-API-003, auch für `/health`),
  Body-Limit 64 MB (`413`); alle Antworten tragen `Cache-Control: no-store` und
  `X-Content-Type-Options: nosniff`.
- **Kein Zustandswechsel über GET** (Test prüft alle GET-Routen); auch scheinbar lesende Aktionen
  (Scan, Export, Backup) sind `POST`.
- **Fehlerabbildung** (`{"error": {"code", "message", "technical_message", "details"}}`):

| Fehlerklasse | HTTP |
|---|---|
| `AuthenticationError` | 401 |
| `ForbiddenOriginError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError`, `InvalidStateError` | 409 |
| `ValidationError`, `ConfigurationError`, `UnsupportedDeviceError`, `ImportDataError`, Pydantic-Validierung | 422 |
| `BleConnectionError` | 502 |
| `ApiUnavailableError` (kein Agent im Prozess) | 503 |
| `DataIntegrityError`, `StorageError`, Rest | 500 |
| Unerwartete Ausnahme | 500, generisch (`OL-GENERIC-000`), **ohne** Stacktrace/Interna; Details nur im Log |

### 19.3 Endpunkte (alle unter `/api/v1`)

| Methode + Pfad | Zweck |
|---|---|
| `GET /health` | öffentlich: `status`, `api_version`, `version` |
| `GET /status` | Übersicht: laufende Sitzung, aktiver Tracker, Live-Status je Gerät, `agent_running` |
| `GET/POST /devices`, `PATCH/DELETE /devices/{id}` | Geräte auflisten (mit Kalibrierung und Live-Status), registrieren, umbenennen, löschen |
| `PUT/DELETE /devices/{id}/faces/{1..8}` | Seite kalibrieren / Zuordnung entfernen |
| `GET /devices/{id}/observed-face` | zuletzt gesehene Seite (geführte Kalibrierung) |
| `GET /devices/{id}/live` | Live-Ansicht (AP-22): `raw_value`, `pending_value`, `committed_value`, `debounce_ms`, `state`, Batterie, `faces` (Tätigkeit/Projekt je Seite 1–8), `recent` (neueste zuerst) und `tracking` (was gerade läuft). Eine nie gestartete Verbindung liefert leere Werte, nichts wird erfunden |
| `POST /devices/{id}/activate` | ausdrückliche Übergabe an diesen Tracker |
| `POST /devices/{id}/connect`, `/disconnect`, `/address` | Verbindung starten/stoppen, gefundene Adresse speichern (Adresse wird **nie** zurückgegeben, nur `has_address`) |
| `POST /scan` | BLE-Suche (nur auf Anforderung) |
| `PUT /devices/{id}/mode` | Modus des Trackers: `time` (Zeiterfassung) oder `control` (Steuerung), AP-26c |
| `PUT/DELETE /devices/{id}/actions/{1..8}` | Aktion einer Seite im Steuerungsmodus setzen (vom Adapter validiert) / entfernen |
| `GET /adapters` | die Arten von Verbindung samt Formularbeschreibung (Felder, Aktionen, Kopplung, `choices_from`) |
| `GET/POST /integrations`, `PATCH/DELETE /integrations/{id}` | Verbindungen: Einstellungen und **Namen** der gesetzten Zugangsdaten, **nie deren Werte**; Löschen verweigert, solange eine Seite sie nutzt (409) |
| `POST /integrations/{id}/check`, `/probe`, `/pair`, `/discover` | Verbindung testen, eine Aktion **jetzt** ausprobieren, koppeln, Lampen/Szenen auflisten (POST, weil sie das Netzwerk berühren) |
| `GET /jobs?limit=` | Verlauf der gesendeten Aktionen (neueste zuerst, höchstens 200) |
| `GET/POST /activities`, `/projects`; `PATCH/DELETE …/{id}`; `POST …/{id}/archive` | Katalog |
| `POST /tracking/start`, `/stop`, `/pause`, `/resume` | manuelle Steuerung |
| `GET /sessions?start&end&…`, `GET /sessions/uncertain` | Journal / zu prüfende Sitzungen |
| `POST /sessions` | Nachtrag |
| `POST /sessions/{id}/correct`, `/split`, `/confirm`, `/delete` | Korrigieren, Teilen, Bestätigen, Löschen (Grund Pflicht) |
| `GET /reports`, `/reports/day`, `/reports/week` | Berichte (Zeitzone Standard aus den Einstellungen) |
| `POST /export/csv`, `POST /backup` | Datei erzeugen (Export-/Backup-Ordner) und Inhalt zum Download liefern |
| `POST /restore/inspect` | Backup prüfen, **ohne** zu ändern (Vorschau) |
| `POST /restore` | Wiederherstellen; verlangt `"confirm": true`, sonst `409` |
| `GET/PUT /settings` | Einstellungen lesen / validiert speichern (Teilabschnitte; ungültig → 422, nichts übernommen) |
| `GET /diagnostics/logs?limit`, `GET /diagnostics/integrity` | Log-Ausschnitt (redigiert), Datenbank-Integritätsprüfung |

Der API-Vertrag ist über das Präfix `/api/v1` versioniert; Brüche erfordern `/api/v2`.

## 20. Dashboard-Client (`octaledger.dashboard_client.client`, AP-17)

Der **einzige** Weg des Dashboards zum Agenten: kein BLE, kein SQL.

### 20.1 Sicherheitsverhalten

- **Token nur an Loopback:** `ApiClient(base_url, token)` akzeptiert ausschließlich
  `http://127.0.0.1|localhost|[::1]:<Port>`. Jede andere Adresse (fremder Host, `https`, ohne Port,
  ähnlich klingende Namen wie `localhost.evil.com`) → `ConfigurationError`, bevor irgendetwas
  gesendet wird. Ein falsch konfigurierter Client kann das Token also nie an einen anderen Rechner
  schicken.
- Das Token steht nur im Header `Authorization: Bearer …`, nie in der URL und nie im Log; bei
  Verbindungsfehlern wird der Ausnahmetext (kann die URL enthalten) nicht protokolliert.
- `ApiClient.from_settings(agent_settings, data_dir)` baut die URL aus den Einstellungen und liest
  das Token aus `<Datenablage>/api_token`. Das Dashboard **erzeugt nie** ein Token: fehlt die Datei,
  erscheint „Bitte zuerst den Agenten starten“ (`read_token`).

### 20.2 Fehlerverhalten

| Situation | Ergebnis |
|---|---|
| Agent nicht erreichbar / Zeitüberschreitung / anderer `requests`-Fehler | `ApiUnavailableError` (OL-API-002), Ursache als `__cause__` |
| API-Fehlerantwort `{"error": {code, …}}` | die **zum Code passende** Ausnahmeklasse (`error_from_response`) mit Benutzermeldung, technischer Meldung und `details`; unbekannter Code bleibt als Code erhalten, ungültiger Code wird nie übernommen |
| Antwort ohne brauchbaren Fehlerkörper | generischer `OctaLedgerError` mit HTTP-Status |
| `204` | `None` |
| Zeiten ohne Zeitzone | `ValidationError` **lokal**, nichts wird gesendet |
| unbekannte Katalogart | `ValidationError` lokal (erlaubt: `"activities"`, `"projects"`) |

Zeitlimits: `(3 s Verbindung, 30 s Lesen)`; ein hängender Agent friert die Oberfläche nie ein.
**Keine automatischen Wiederholungen:** viele Aufrufe ändern Daten, ein stilles zweites Senden könnte
sie doppelt ausführen.

### 20.3 Methoden

Spiegeln die Endpunkte aus Abschnitt 19 und liefern JSON-artige Werte: `health`,
`is_agent_running` (wirft nie), `status`, `devices`, `register_device`, `rename_device`,
`remove_device`, `assign_face`, `clear_face`, `observed_face`, `live_view`, `set_device_mode`, `assign_action`,
`clear_action`, `adapters`, `integrations`, `create_integration`, `update_integration`, `delete_integration`,
`check_integration`, `probe_integration`, `pair_integration`, `discover_integration`, `jobs`, `activate_device`,
`connect_device`, `disconnect_device`, `set_device_address`, `scan`, `list_items`/`create_item`/
`update_item`/`archive_item`/`delete_item` (für `"activities"`/`"projects"`), `start_tracking`,
`stop_tracking`, `pause_tracking`, `resume_tracking`, `journal`, `uncertain_sessions`,
`add_session`, `correct_session`, `split_session`, `confirm_session`, `delete_session`, `report`,
`day_report`, `week_report`, `export_csv`, `create_backup`, `inspect_restore`, `restore`,
`get_settings`, `update_settings`, `logs`, `integrity`.

### 20.4 Tests

38 Unit-Tests mit einer Fake-Session (URL-Prüfung, Header, Fehlerabbildung, Methoden-Verträge,
Token nicht im Log) und **Integrationstests** (`tests/integration/test_client_server.py`): echter
uvicorn-Server in einem Thread auf freiem Loopback-Port, echter Client über echtes HTTP – ein
kompletter Arbeitsablauf (Geräte, Katalog, Tracking, Korrektur, Teilen, Berichte, Export, Backup,
Restore, Einstellungen), die Überschneidungsregel quer durch den Stack, Fehlertypen und ein
gestoppter Server.

## 21. Dashboard-Grundgerüst (`octaledger.dashboard`, AP-18a)

Die gesamte Oberfläche liegt im installierbaren Paket `octaledger.dashboard` (typgeprüft,
importierbar, automatisch getestet); `dashboard/app.py` startet sie nur. Das Dashboard besitzt
**keinen** BLE-Client und **kein** SQL – alle Daten kommen über den `ApiClient` (Abschnitt 20).

### 21.1 Module

| Modul | Aufgabe |
|---|---|
| `main.py` | `run()` wird bei **jeder** Interaktion ausgeführt (Streamlit-Rerun): Seiteneinstellungen, Logging (einmal je Prozess), Client holen, Theme anwenden, Seitenleiste, Seite zeichnen. Keine langsame Arbeit, keine Schleifen. Zustand in `st.session_state`: `_client`, `_display`, `nav` |
| `theme.py` | helle/dunkle Farbschemata als eingefügtes CSS, genau zwei Schriftstufen (16 px / 20 px), WCAG-Kontrastberechnung |
| `ui.py` | Formatierung (`format_hms`, `format_hm`, `format_local`), `page_help`, `help_popover`, `show_error`, `call` (API-Aufruf, der Fehler anzeigt statt zu werfen), Zustandsbezeichnungen |
| `pages/__init__.py` | `PAGES`: Beschriftung → `render(client, timezone)`; die Reihenfolge ist die Navigationsreihenfolge |
| `pages/overview.py` | Übersicht: laufende Zeit, Start/Pause/Fortsetzen/Stopp, Tracker-Status, Qualitätshinweis |

### 21.2 Hell/Dunkel und Schriftgröße (Pflicht)

- **Zwei Schalter** in der Seitenleiste: „🌙 Dunkel“ ↔ „☀️ Hell“ und „Aa+ Größer“ ↔ „Aa− Kleiner“
  (der Knopf zeigt jeweils das Ziel). Wirkung sofort, ohne Neuladen.
- **Persistenz:** Die Wahl wird über `PUT /settings` in `settings.toml` gespeichert und beim
  nächsten Öffnen angewendet. Ist der Agent nicht erreichbar, gilt sie für die laufende Sitzung
  und die Seitenleiste weist darauf hin.
- Streamlit kann sein natives Theme nicht zur Laufzeit wechseln; deshalb wird CSS eingefügt
  (Hintergrund, Seitenleiste, Eingaben, Knöpfe, Tabellen, `color-scheme`). Die Farbpaare erfüllen
  **WCAG AA** (Text/Hintergrund ≥ 7:1, Primärfarbe und Statusfarben ≥ 4,5:1); ein Test berechnet die
  Verhältnisse, damit eine spätere Farbänderung die Lesbarkeit nicht unbemerkt verschlechtert.
- Farbe ist nie das einzige Signal: Status-Punkte haben immer einen Text.

### 21.3 UX-Regeln, die alle Seiten einhalten

1. **Jedes** Eingabefeld und jeder Knopf hat einen `help=`-Tooltip (ein Test prüft das für die
   Übersicht), jede Seite beginnt mit „ℹ️ So funktioniert diese Seite“.
2. Fehler: verständlicher deutscher Text **plus Fehlercode**, technische Details nur eingeklappt, nie
   ein Stacktrace (`show_error`). Fehlschlagende Aufrufe machen die Seite nie leer (`call`).
3. Leere Zustände erklären den nächsten Schritt („Legen Sie zuerst … eine Tätigkeit an“).
4. **Benutzertexte werden HTML-escaped**, wenn sie in `unsafe_allow_html`-Blöcken erscheinen
   (Test mit `<img onerror=…>`).
5. Agent nicht erreichbar → erklärende Seite mit Fehlercode OL-API-002, Startbefehl und „Neu
   laden“; kein Absturz. Fehlt das Token (Agent lief nie) → Einrichtungshilfe.
6. Dashboard schließen oder neu laden beendet die Erfassung **nicht** (Agent ist ein eigener Prozess).

### 21.4 Übersichtsseite

Laufende Tätigkeit (Farbpunkt, Name, Dauer `h:mm:ss`, Beginn in Ihrer Zeitzone, Projekt, Quelle),
`⏸ Pause`, `⏹ Stopp`, `▶ Fortsetzen`; Hinweis bei *unsicherer* laufender Zeit; Tracker-Box mit
Zustand (`STATE_LABELS`), Batterie und letzter Meldung; Warnung mit Anzahl unsicherer Sitzungen;
Formular „Von Hand starten“ (Tätigkeit, optionales Projekt, Notiz). Der Statusbereich ist ein
`st.fragment(run_every="5s")` und aktualisiert sich selbst.

### 21.5 Tests

`tests/gui/` nutzt `streamlit.testing.v1.AppTest` gegen den **echten** API-Server der gemeinsamen
Fixture `api_server` (`tests/conftest.py`): Rendern ohne Ausnahme, Hilfetexte, Theme-/Schriftumschalter
inkl. Persistenz und Wiederöffnen, Ausfall beim Speichern, Kontrastverhältnisse, Agent weg / Token
fehlt, kompletter Start→Pause→Fortsetzen→Stopp-Ablauf, Projekt und Notiz, HTML-Escaping, Hinweis auf
unsichere Sitzungen, Tracker-Box und die Formatierungshilfen.
Hinweis: AppTest prüft Logik und Elemente, **nicht** das visuelle Erscheinungsbild im Browser.

## 22. Seiten „Geräte“ und „Verwaltung“ (`dashboard.views.devices`, `dashboard.views.catalog`, AP-18b)

### 22.1 Geräte-Seite

| Bereich | Verhalten |
|---|---|
| Tracker registrieren | Formular (Name, max. 100 Zeichen, eindeutig); Fehler (Duplikat, leer) erscheinen mit deutschem Text und Fehlercode |
| Bluetooth-Suche | Nur auf Knopfdruck (≈ 5 s, Spinner); Ergebnisse in `st.session_state["_scan"]`; passende Geräte mit „✅ passender Dienst“, **nichts wird ausgeblendet**; Auswahl + Tracker → „Adresse speichern“. Die Adresse selbst wird **nie angezeigt** (nur `has_address`). Leere Treffer/keine Tracker/fehlender Agent/Bluetooth aus → erklärende Hinweise |
| Tracker-Panel | Zustand mit Statuspunkt **und** Text, Modell/Firmware (oder „unbekannt“), Adresse „gespeichert/noch nicht zugeordnet“, Batterie, letzte Meldung; Knöpfe **Verbinden**, **Trennen**, **Zum aktiven Tracker machen** (deaktiviert beim aktiven) |
| Kalibrierung | Fortschrittsbalken „n von 8 Seiten“; Anzeige der zuletzt gemeldeten Seite („👈 Seite N liegt oben“, neutral, noch keine); Formular mit je Seite 1–8 Tätigkeit + Projekt; **gespeichert werden nur geänderte Seiten** (neue Zuordnung → `assign_face`, auf „nicht belegt“ → `clear_face`) |
| Umbenennen / Löschen | Löschen erst nach Bestätigungs-Haken (Gerät mit Daten bleibt geschützt, Fehlermeldung erklärt es) |

Widget-Schlüssel sind je Gerät/Seite eindeutig (`face_act_<id>_<n>`, `connect_<id>` …), was auch die
Tests nutzen.

### 22.2 Verwaltung

Zwei Reiter **Tätigkeiten** und **Projekte** (gemeinsame Implementierung):

- Anlegen: Name + optional „Eigene Farbe wählen“ (sonst automatische, unterscheidbare Farbe aus der
  Okabe-Ito-Palette).
- Liste (archivierte optional per Schalter) mit Name, Farbwähler, **Speichern**, **Archivieren /
  Wiederherstellen**, **Löschen** (nur nach Bestätigung; verwendete Einträge → Meldung „bitte
  archivieren“).
- Namen werden, wo sie in HTML erscheinen, escaped; in Labels (Markdown) erscheinen sie unverändert,
  weil Streamlit dort kein rohes HTML rendert.

### 22.3 Tests

`tests/gui/test_gui_devices_catalog.py` (22 Tests, `AppTest` gegen den echten Server, `FakeAgent`
aus `tests/conftest.py`): leere Zustände, Registrierung inkl. Duplikat und leerem Namen,
Suche mit/ohne Agent, Adresse speichern (nie angezeigt), Fehlerfälle der Suche, Verbinden/Trennen,
Übergabe, Kalibrierung (nur Änderungen, Löschen einer Seite, „Seite oben“), fehlende Tätigkeiten,
Umbenennen/Löschen mit Bestätigung, Hilfetexte aller Eingaben, Escaping, kompletter Lebenszyklus
von Tätigkeiten/Projekten, eigene Farbe, Schutz verwendeter Einträge, Duplikate, leere Kataloge.

## 23. Seiten „Zeitjournal“ und „Statistik“ (`dashboard.views.journal`, `dashboard.views.statistics`, AP-18c)

### 23.1 Zeitjournal (drei Reiter)

| Reiter | Inhalt |
|---|---|
| **Journal** | Filter Von/Bis (einschließlich, Ihre Zeitzone), Tätigkeit, Projekt, Gerät; Tabelle (Beginn, Ende/„läuft“, Dauer, Tätigkeit, Projekt, Gerät/„von Hand“, Qualität, Revision, Notiz), Summe als Beschriftung; darunter **Sitzung bearbeiten** |
| **Zu prüfen** | alle *unsicheren* Sitzungen mit **Bestätigen**; leer → „Alles bestätigt“ |
| **Nachtragen** | Formular für vergangene Zeiten (Tätigkeit, optionales Projekt, Beginn/Ende, Notiz) |

Sitzung bearbeiten: **Korrigieren** (Tätigkeit, Projekt, Beginn, Ende, Notiz, **Grund Pflicht**;
laufende Sitzungen behalten ihr Ende; „Als bestätigt markieren“ bei unsicheren), **Teilen** (Zeitpunkt +
Grund) und **Löschen** (Grund + Bestätigung). Datum und Uhrzeit werden **in der Anzeigezeitzone**
eingegeben und mit `from_local` in UTC umgerechnet; die API nimmt nur zeitzonenbehaftete Zeiten.
Regelverstöße (Überschneidung, fehlender Grund, Ende in der Zukunft) erscheinen als deutsche Meldung
mit Fehlercode, die Daten bleiben unverändert.

### 23.2 Statistik

- Zeitraum **Tag**, **Woche** (Montag–Sonntag) oder **eigener Zeitraum**; Filter wie im Journal. Ein
  Zeitraum über 400 Tage und ein Ende vor dem Beginn ergeben klare Meldungen statt eines Absturzes.
- Kennzahlen mit Hilfetext: **Persönliche Arbeitszeit**, **Gerätezeit**, **Davon unsicher**,
  **Überschneidung**; Warnung, solange unsichere Zeit enthalten ist; Hinweis auf eine laufende Sitzung.
- Diagramme (Plotly, Template folgt dem gewählten Hell/Dunkel-Schema): Balken **Verlauf pro Tag**
  (nur bei mehr als einem Tag), Ringdiagramme **nach Tätigkeit** und **nach Projekt** in den
  Tätigkeitsfarben. **Jedes Diagramm hat darunter dieselben Daten als Tabelle**
  (Barrierefreiheit, Kopieren).
- Leerer Zeitraum → Hinweis „keine Zeiten“.

### 23.3 Technische Hinweise

- `pandas` ist jetzt direkte Abhängigkeit (Tabellen), `pandas-stubs` Entwicklungsabhängigkeit;
  für das untypisierte `plotly` ist nur der Import von `mypy` ausgenommen (`[[tool.mypy.overrides]]`).
- Alle Knöpfe/Tabellen nutzen `width="stretch"` statt des in Streamlit entfernten
  `use_container_width`.
- **Tests** (`tests/gui/test_gui_journal_statistics.py`, 17): Journal mit Namen/Dauern/Reihenfolge,
  leere und umgekehrte Bereiche, Filter, Korrektur mit Pflichtgrund, Teilen und Löschen, Prüf-Reiter,
  Nachtragen mit Überschneidungsfehler, Hilfetexte; Statistik für Tag/Woche/eigenen Zeitraum, Filter,
  Unsicherheitswarnung, leerer Zustand, 400-Tage-Grenze, Dunkel-Template, Hilfetexte. Die Testdaten
  liegen heute 00:00–03:00 UTC; zwischen 00:00 und 03:30 UTC werden diese Tests übersprungen, weil die
  Sitzungen sonst in der Zukunft lägen.

## 24. Seiten „Daten“, „Einstellungen“ und „Diagnose“ (AP-18d)

Damit sind alle acht Seiten umgesetzt (Navigationsreihenfolge = `PAGES`): Übersicht, Geräte,
Verwaltung, Zeitjournal, Statistik, Daten, Einstellungen, Diagnose.

### 24.1 Daten (`pages/data.py`)

| Reiter | Verhalten |
|---|---|
| **CSV-Export** | alle Zeiten oder Zeitraum; Trennzeichen (Semikolon/Komma/Tabulator); „CSV erzeugen“ schreibt die Datei in den Export-Ordner und bietet sie per `st.download_button` an (UTF-8 **mit BOM**, damit Excel Umlaute richtig liest) |
| **Sicherung** | „Sicherung erstellen“ legt die JSON-Sicherung im Backup-Ordner ab und bietet den Download an |
| **Wiederherstellen** | Datei hochladen **oder** Inhalt einfügen; **Vorschau ohne Änderung** (Version, App-Version, Stand, Anzahl je Entität); „Jetzt wiederherstellen“ bleibt **deaktiviert, bis die Bestätigung gesetzt ist**; danach Hinweis auf die automatische Kopie `octaledger-pre-restore-…`. Ungültige/manipulierte Dateien: deutsche Meldung mit OL-DATA-002, **keine** Änderung |

### 24.2 Einstellungen (`pages/settings.py`)

Ein Formular für Zeitzone (alle IANA-Namen), Entprellung (0–2000 ms, Schritt 50), Verhalten für die erste
Seite nach dem Verbinden, bei Verbindungsverlust und für den Neutralwert (jeweils mit der empfohlenen
Option zuerst bezeichnet; die Pausenregel ist als **experimentell** gekennzeichnet) und die
Protokollstufe. Speichern geht über `PUT /settings` (alles-oder-nichts-Validierung).

- **Zeitzone** wirkt sofort (Sitzungszustand wird aktualisiert).
- **Entprellung, Richtlinien, Protokollstufe** liest der Agent beim **Start**: nach dem Speichern
  erscheint der Hinweis „Neustart des Agenten“ (nur, wenn sich tatsächlich etwas daran geändert hat).
- „Technische Angaben“ (Schnittstelle, Sprache, Modus) sind **nur lesend**: Adresse/Port ändern sich
  über `settings.toml` bzw. Umgebungsvariablen, nie über die Oberfläche (Sicherheit).

### 24.3 Diagnose (`pages/diagnostics.py`)

Gerätekarten (Zustand, Fehlversuche, letzter Wert/Ereignis, Batterie, verworfene Werte, ignorierte
Duplikate, letzte Meldung), „Datenbank prüfen“ (Integritätsprüfung), Protokollausschnitt (1 bis 500
Zeilen, bereits redigiert) und der **anonymisierte Diagnosebericht** als Download.
`build_report` ersetzt Gerätenamen durch „Gerät 1, 2 …“, enthält weder Adressen noch Tätigkeits- oder
Projektnamen, listet Integritätsprobleme und die redigierten Logzeilen (Pflichtenheft F-19).

### 24.4 Tests

`tests/gui/test_gui_data_settings_diagnostics.py` (17): Struktur und Hilfetexte, CSV-Download inkl.
leerer Daten und Zeitraum, Sicherung (Datei + Download), Restore-Vorschau → Bestätigung → Wiederherstellung
(Vorschau ändert nichts), ungültige und manipulierte Sicherung, Einstellungswerte und Hilfetexte,
Zeitzone sofort, Regeln speichern mit Neustart-Hinweis, nur lesende technische Angaben, Diagnose mit
und ohne Live-Status, leere Zustände, Anonymisierung des Berichts und ein Durchlauf über **alle acht
Seiten ohne Ausnahme**. Hinweis: Streamlits `AppTest` kann Datei-Uploads nicht simulieren; der Pfad
„Inhalt einfügen“ nutzt dieselbe Prüf- und Restore-Logik und wird getestet.

## 25. Agent-Laufzeit und Kommandozeile (`octaledger.agent.main`, `octaledger.cli`, AP-19)

### 25.1 Prozessaufbau des Agenten

| Thread | Aufgabe |
|---|---|
| Hauptthread | wartet auf Strg+C bzw. `request_stop()` und fährt danach alles in Reihenfolge herunter |
| **BLE-Thread** | der **eine** AsyncIO-Loop, der alle Tracker-Verbindungen besitzt (Bleak-Anforderung); hier lebt der `AgentSupervisor` |
| API-Thread | uvicorn mit der Loopback-API; deren Handler laufen im Worker-Threadpool |

`AgentRuntime` baut alle Services (Datenbank mit Migration, Storage, Tracking-, Geräte-, Katalog-,
Reporting-, Export-Service, Token, `SettingsStore`) und implementiert `AgentControl`. Die API ruft den
BLE-Teil **nur** darüber auf; `_call()` übergibt Coroutinen thread-sicher per
`run_coroutine_threadsafe`. Das Schließen des Dashboards berührt diesen Prozess nicht (A-05).

- **Start** (`start()`): prüft zuerst den Port (`check_port_free`; belegt → `ConfigurationError`
  „läuft der Agent schon?“, damit nie zwei Schreiber um die Datenbank konkurrieren), startet BLE-Loop und
  API und wartet, bis der Server bereit ist. Danach **Autostart des aktiven Trackers und aller Tracker im Steuerungsmodus**, jeweils nur wenn
  sie eine Adresse haben (ein Steuerungs-Würfel ist nie „der aktive“, muss aber nach dem Start sofort arbeiten); Fehler dabei brechen den Start nicht ab. Mehrere registrierte Geräte bedeuten
  nicht automatisch mehrere zuverlässige gleichzeitige Verbindungen (Pflichtenheft §1) – weitere
  Tracker verbindet der Benutzer ausdrücklich.
- **Herunterfahren** (`shutdown()`, idempotent): API stoppen → Supervisor beendet alle Tracker
  (Verbindung trennen, abschließende `DISCONNECT`-Ereignisse) → BLE-Loop anhalten → Threads joinen.
- `AgentControl`: `start_device`, `stop_device`, `device_statuses`, `scan` (der Scan läuft auf dem
  BLE-Loop und verbindet nie).
- `run_agent(data_dir, log_level, factory)` konfiguriert das Logging (Datei + Konsole, Redaktion),
  startet die Laufzeit und fährt sicher herunter. Die Transportfabrik ist austauschbar (Bleak
  produktiv, Fake in Tests).

**Robustheitsfund durch den End-to-End-Test:** Die Callbacks des Workers dürfen sich nicht darauf
verlassen, auf dem Loop-Thread zu laufen. `asyncio.Event.set()` weckt die Schleife aus einem fremden
Thread nicht. `DeviceWorker._set()` setzt Ereignisse deshalb thread-sicher (`call_soon_threadsafe`),
auch für `request_stop()`.

### 25.2 Kommandozeile (`octaledger <befehl>`)

| Befehl | Zweck |
|---|---|
| `agent [--data-dir D] [--log-level L]` | Agent starten |
| `dashboard [--data-dir D]` | Streamlit-Dashboard starten (`--server.address 127.0.0.1`, `--browser.gatherUsageStats false`: nur lokal, **keine Telemetrie**); Einstiegsskript liegt im Paket (`dashboard/streamlit_app.py`) |
| `status` | läuft der Agent, laufende Tätigkeit, unsichere Sitzungen, Tracker-Zustände |
| `scan [--seconds N]` | Bluetooth-Geräte suchen (nur Anzeige, Adressen werden nicht ausgegeben, verbindet nie) |
| `paths` | Speicherorte anzeigen |
| `backup [--output FILE]` | JSON-Sicherung erstellen (funktioniert auch bei laufendem Agent) |
| `restore FILE [--yes]` | Sicherung prüfen (ohne `--yes` nur Vorschau, Exit-Code 3) bzw. wiederherstellen; **verweigert**, solange der Agent läuft |
| `--decode-test N` | Dekodertest ohne Hardware (wie bisher) |

Exit-Codes: `0` Erfolg, `1` negativer Status (z. B. Agent läuft nicht), `2` Fehler (eine lesbare Zeile
`Fehler [OL-…-nnn]: …`, **nie** ein Stacktrace), `3` Bestätigung nötig, `130` abgebrochen.

### 25.3 Skripte, Konfiguration, CI

- `scripts\start_agent.bat`, `start_dashboard.bat`, `start_all.bat` (Agent im eigenen Fenster, danach
  Dashboard), `run_tests.bat` (Qualitäts-Gate: pytest, ruff check, ruff format --check, mypy).
- `.streamlit/config.toml`: `server.address = 127.0.0.1`, `browser.gatherUsageStats = false`.
- CI (`.github/workflows/ci.yml`): Windows, Python 3.12, pip-Cache, pytest, `ruff check`,
  `ruff format --check`, `mypy`; Hardwaretests laufen dort nie.

### 25.4 Tests

`tests/integration/test_agent_runtime.py` (11) fährt den **ganzen Agenten** (BLE-Thread + API-Thread) mit
synthetischem Tracker: komplette Kette vom Tracker bis zum Dashboard-Client, Verbindungsverlust →
unsicher → Reconnect ohne neue Sitzung (A-04), bewusstes Trennen ohne Wiederverbinden, Scan über den
BLE-Loop, Autostart (aktiver und Steuerungs-Tracker) mit Adresse, Port-Konflikt, geordnetes und idempotentes
Herunterfahren, `wait()`/`request_stop()`. `tests/unit/test_cli.py` (17): alle Befehle, Exit-Codes,
Fehlerdarstellung, Backup/Restore-Rundlauf mit Bestätigung, Restore-Sperre bei laufendem Agent,
Dashboard-Befehl (lokal, ohne Telemetrie).
**Das beweist nicht das Verhalten mit echten Trackern** – dafür sind die manuellen Hardwaretests
(`tests/hardware`, Testplan) vorgesehen.

## 26. Qualitätssicherung, Teststrategie und Erweiterungspunkte (AP-20)

### 26.1 Qualitäts-Gate

`scripts\run_tests.bat` = `pytest` + `ruff check` + `ruff format --check` + `mypy` (strict); dasselbe läuft in
der CI. Stand: 900 bestanden, 2 Hardwaretests übersprungen (805 Unit, 14 Integration, 81 GUI), rund 12 000
Zeilen Quellcode und 8 400 Zeilen Tests. Nachweisstatus der Abnahmekriterien: [TESTPLAN.md](TESTPLAN.md).

### 26.2 Teststrategie (Schichten)

| Ebene | Technik | Besonderheit |
|---|---|---|
| Reine Regeln | direkte Unit-Tests mit injizierter Zeit (`now_ms`, `clock`) | deterministisch, ohne Sleep |
| Persistenz | temporäre SQLite-Dateien | Constraints, Trigger, Migrationen, Backup, Korruption, Sperren |
| Async/BLE | `asyncio.run` + `FakeTransport` | kleine echte Zeiten, beschränktes Polling, mehrfach wiederholt |
| API | `TestClient` mit `base_url=http://127.0.0.1:<port>` | prüft Host/Origin/Token/Fehlerabbildung |
| Integration | echter uvicorn-Server im Thread + echter Client; ganzer Agent | Fixture `api_server` in `tests/conftest.py` |
| GUI | `AppTest` gegen den echten Server | Logik und Elemente, **nicht** das Aussehen im Browser |
| Hardware | manuell, `OCTALEDGER_HARDWARE_TESTS=1` | nur lesen/abonnieren |

Durch die Tests aufgedeckte und behobene Fehler (Auswahl): falsch gebildete Katalogrouten (`/activitys`),
`ConfigurationError` als HTTP 500 statt 422, ein Event-Wecken aus fremden Threads (Worker), ein falsch
HTML-escaptes Label, falsche RECONNECT-Meldung beim ersten erfolgreichen Verbinden.

### 26.3 Bekannte Grenzen

Siehe [QUELLEN_UND_GRENZEN.md](QUELLEN_UND_GRENZEN.md): keine Hardwareprüfung, Protokoll nur aus
Community-Quellen, kein visueller Browsertest, keine Leistungsmessung, keine Rechtsprüfung, Lizenz offen,
F-20 (Integrationen) nicht umgesetzt.

### 26.4 Erweiterungspunkte

| Ziel | Wo ansetzen |
|---|---|
| Neue Integration (MQTT, Home Assistant, Obsidian) | `infrastructure/integrations/` + Tabelle `integration_jobs` (neue Migration), idempotente, begrenzte Aufträge |
| Parallele Gerätezeitachsen | neue Migration (Überschneidungs-Trigger anpassen), `TrackingService` pro Gerät; Berichte unterscheiden Gerätezeit/persönliche Zeit bereits |
| Weitere Sprachen | `SUPPORTED_LANGUAGES` und GUI-Texte (derzeit nur Deutsch) |
| Anderer Transport (z. B. andere Plattform) | `DeviceTransport` implementieren (ohne Schreibzugriff), Fabrik in `run_agent` austauschen |
| Neuer Fehlercode / Migration / Endpunkt / Seite | Kurzanleitungen in [CONTRIBUTING.md](../CONTRIBUTING.md) |

## 27. GUI-Überarbeitung: Design-System, Navigation, Statusleiste (AP-21)

Konzept, Recherche, Quellen und Begründungen: [GUI_KONZEPT.md](GUI_KONZEPT.md). Hier die technische Umsetzung.

### 27.1 Module

| Modul | Aufgabe |
|---|---|
| `dashboard/theme.py` | Design-System: `PALETTES` (hell/dunkel, inkl. `input_border`), `css()` (Inter per `@font-face`, `tabular-nums`, Radien 8/12 px, Fokusring, Karten, Menü-Stile, **keine Schatten**), WCAG-Hilfen |
| `dashboard/nav.py` | `PageDef(slug, title, icon, group, description, render)`, `GROUPS = (Start, Alltag, Einrichten, System)`, `go(slug)` als `on_click`-Callback |
| `dashboard/views/__init__.py` | `PAGES: dict[slug, PageDef]` – die Reihenfolge ist die Menüreihenfolge je Gruppe |
| `dashboard/shell.py` | `status_bar(client)` (Fragment, alle 5 s): laufender Eintrag, `tracker_summary`, Warnungen, Stopp-/Prüfen-Knopf |
| `dashboard/main.py` | gruppiertes Menü (Buttons `nav_<slug>`, aktiver Eintrag `type="primary"`), Darstellungsschalter, Statusleiste, dann die Seite |
| `dashboard/static/` | `Inter-Variable.woff2` (SIL OFL, `OFL.txt`), per Streamlit-Static-Serving unter `/app/static/…` |

### 27.2 Wichtige Entscheidungen im Code

- **Menü als Buttons statt `st.radio`/`st.navigation`:** Gruppenüberschriften, Icons, gefüllte aktive Markierung
  und AppTest-Testbarkeit; Zustand in `st.session_state["nav"]`, Wechsel per `on_click`-Callback (greift vor
  dem nächsten Durchlauf, daher kein Flackern). Eine Seite hinzufügen = ein `PageDef` in `pages/__init__.py`.
- **Lokale Schrift:** `enableStaticServing` ist in `.streamlit/config.toml` **und** per CLI-Flag
  (`octaledger dashboard`) gesetzt; der Ordner `static/` liegt neben dem Einstiegsskript im Paket
  (`[tool.setuptools.package-data]`). Fehlt die Datei, greifen die System-Schriften. Es werden **keine**
  externen Hosts kontaktiert (Test prüft, dass das CSS keine `http(s)://`-Adressen enthält).
- **Statusleiste** zeigt „Tracker liefert keine Werte“ für die Zustände `disconnected`, `reconnect_wait`,
  `stopped`, `idle` oder keinen Live-Status; ohne registrierten Tracker nur ein neutraler Hinweis.
- **Übersicht:** `_first_steps` (5 Schritte, Fortschritt, nächster Schritt als primärer Knopf, ausblendbar),
  `_quick_start` (Rang nach Nutzung der letzten 30 Tage, höchstens vier), `_today` (Tages-/Wochensumme,
  Einträge), Formular im Expander. Fehler der Checkliste brechen die Seite nie (`OctaLedgerError` wird
  verschluckt, echte Fehler zeigt der Rest der Seite).
- **Journal:** Schnellzeiträume setzen per Callback die Datums-Widgets (`journal_from/_to`); **Statistik:**
  Filter im Expander; **Diagnose:** Ampel (`_summary`), die Datenbankprüfung läuft als Callback, damit die Ampel
  sofort den neuen Stand zeigt.
- **Begriff „Eintrag“** ersetzt „Sitzung“ in allen Texten (ein Test verhindert Rückfälle; „Sitzung“ bedeutet
  nur noch die Browser-Sitzung). Das Datenmodell behält den Namen `Session`.
- Streamlit-APIs: `width="stretch"`, `icon=":material/…:"`, `st.container(border=True, key=…)`; Selektoren im CSS
  über `data-testid` und `st-key-*`.

### 27.3 Tests

`tests/gui/test_gui_redesign.py` (23): Menügruppen und Reihenfolge, aktive Seite gefüllt, Icon+Text+Tooltip je
Eintrag, **Seitentitel = Menütext**, Statusleiste auf jeder Seite, Warnung bei fehlender Verbindung (und neutral
ohne Tracker), Stopp aus der Leiste, Sprung zum Prüfen, Checkliste (Fortschritt, Navigation, Ausblenden,
Abschluss), Schnellstart (Klick, Rangfolge, Limit 4), Heute-Block, Schnellzeiträume, Statistik-Filter im
Expander, Diagnose-Ampel, Schrift-Assets (Datei, Lizenz, Referenz, Package-Data, CLI-Flag), **keine externen
Hosts**, Lesbarkeits-CSS (Tabellenziffern, Fokusring, Radien, keine Schatten), Begriffsregel. Die Farbtests
prüfen zusätzlich Rand ≥ 3:1 und gedämpften Text auf der Karte ≥ 4,5:1. Real geprüft: `octaledger dashboard`
liefert `/app/static/Inter-Variable.woff2` mit 200 und `wOF2`-Kopf aus.
**Nicht** geprüft: das visuelle Erscheinungsbild im Browser.

## 28. Live-Ansicht und Würfelgrafik (`dashboard.views.live`, `dashboard.cube`, AP-23)

Die Seite **Würfel live** (Gruppe „Alltag“) macht sichtbar, wie Würfelbewegungen die Software beeinflussen. Sie
liest nur `GET /devices/{id}/live` (AP-22) und ändert nichts.

### 28.1 Module

| Modul | Aufgabe |
|---|---|
| `dashboard/cube.py` | `cube_svg(theme, faces, up=, pending=, selected=, caption=)` erzeugt das SVG des Würfels von oben (Achteck mit acht Keilen, Seite 1 oben, im Uhrzeigersinn). Reine Funktion ohne Streamlit. `FaceLabel(name, color)` beschreibt eine Seite |
| `dashboard/views/live.py` | Seite: Auswahl des Trackers, Fragment `_live` (`run_every="1s"`) mit Bild, drei Schritt-Karten und Verlauf; Helfer `face_labels`, `face_text`, `describe_event`, `pending_face`, `escape_markdown` |

### 28.2 Entscheidungen

- **Schematisch und ehrlich:** Die Nummern sind die *technischen* Seitennummern des Geräts; das Bild behauptet
  nicht, wo eine Nummer aufgedruckt ist. Erst die Kalibrierung ordnet einer Nummer eine Tätigkeit zu.
- **Farbe ist nie das einzige Signal:** oben = dicker Rand **und** ▲ **und** Zahl in der Mitte; „noch nicht
  bestätigt“ = gestrichelter Rand. Hervorgehobene Keile werden zuletzt gezeichnet, damit Nachbarn ihren Rand nicht
  überdecken.
- **Lesbarkeit auf jeder Farbe:** `readable_on` wählt dunkle oder helle Schrift; auf mittleren Tönen (Standardfarbe
  `#5B7C99`) erreicht keine von beiden 4,5:1, deshalb haben alle Beschriftungen einen Rand in der Gegenfarbe
  (`paint-order="stroke"`). Die großen fetten Zahlen erfüllen 3:1 (WCAG für große Schrift).
- **Beschriftung im Keil gestapelt** (Marker, Zahl, Name übereinander): Namen am Rand würden bei den linken und
  rechten Seiten abgeschnitten. Namen werden auf 10 Zeichen gekürzt; die volle Bezeichnung steht in den Karten.
- **Eingaben werden maskiert:** Tätigkeitsnamen gelangen mit `html.escape` ins SVG und mit `escape_markdown` in
  Markdown-Texte (Test mit `<b>x</b>`).
- **Ablauf in drei Karten** erklärt die Kette *Funk → Entprellung → Software*: ① `raw_value`, ② `pending_value`
  mit der Entprellzeit in Sekunden, ③ laufende Tätigkeit samt Dauer; dazu Hinweise („nicht der aktive Tracker“,
  „Seite hat noch keine Tätigkeit“).
- **Verlauf** zeigt bis zu 12 Einträge als Sätze (`describe_event`); er stammt aus dem Arbeitsspeicher des Agenten
  und wird nicht gespeichert.

### 28.3 Tests

`tests/unit/test_cube.py` (15): acht nummerierte Keile, Namen/Farben, ▲ + dicker Rand für „oben“, gestrichelt für
„wartet“, Auswahlring, **Maskierung von Eingaben**, Kürzung, Lesbarkeit auf Standard- und Extremfarben.
`tests/gui/test_gui_live.py` (7): Titel/Hilfe/leerer Zustand, nie gestartetes Gerät wird nicht als live gezeigt,
verbundener Würfel (Seite, Schritte, Verlauf), freie Seite erklärt, nicht aktiver Tracker, Maskierung im Bild,
laufende Zeit. Im Browser (Chromium) in Hell und Dunkel mit simuliertem Würfel angesehen; **nicht** mit echter
Hardware.

## 29. Zuordnungs-Assistent „Seiten zuordnen“ (`dashboard.views.faces`, AP-24)

Ersetzt das Raten in der Dropdown-Tabelle durch einen geführten Ablauf (Gruppe „Einrichten“). Die Tabelle auf der
Seite *Geräte* bleibt als Alternative bestehen. Genutzte API: `devices`, `list_items`, `live_view`,
`assign_face`, `clear_face`, `create_item`, `connect_device` – es gibt **keinen neuen Endpunkt**.

### 29.1 Aufbau

| Teil | Aufgabe |
|---|---|
| `_live_picture` (Fragment, 1 s) | Würfelbild mit `selected` = bearbeitete Seite, `up`/`pending` aus der Live-Ansicht; Knopf „Seite N einrichten“, wenn oben eine andere Seite liegt als die ausgewählte |
| `_editor` (kein Fragment) | Seitenwahl (`st.radio`, Schlüssel `faces_target_<geräte-id>`), Tätigkeit (vorhandene **oder** „Neue Tätigkeit“), Projekt, Speichern/Entfernen |
| `_connection_hint` | Zustand „nicht verbunden“ mit „Jetzt verbinden“ (Adresse bekannt) oder Weg zur Suche |
| `next_free_face`, `assigned_faces`, `is_new` | reine Helfer (getestet) |

### 29.2 Entscheidungen

- **Bild live, Eingabe ruhig:** Ein sich selbst aktualisierendes Fragment würde Text verwerfen, den der Nutzer gerade
  tippt. Deshalb liegt nur das Bild im Fragment; die Seite wird **ausdrücklich** per Knopf übernommen und folgt dem
  Würfel nicht von allein.
- **Streamlit-Regel für Widget-Schlüssel:** Ein Schlüssel darf nach dem Erzeugen seines Widgets im selben Durchlauf
  nicht geändert werden. Wünsche („nächste freie Seite“, „oben liegende Seite“) werden in `faces_pending_target`
  abgelegt und zu Beginn des nächsten Durchlaufs **vor** dem Seitenwähler angewendet.
- **Neue Tätigkeit direkt anlegen:** Existiert noch keine Tätigkeit, ist „Neue Tätigkeit“ vorgewählt. Speichern ist
  gesperrt, bis ein Name eingegeben ist; ein doppelter Name wird mit Fehlercode (`OL-STATE-002`) gemeldet und
  ordnet nichts zu. „Neue Tätigkeit“ wird **per Wert** erkannt (`is_new`), weil Streamlit die Auswahl nicht
  als dasselbe Objekt zurückgibt (Identitätsvergleich schlug im Test fehl).
- **Auch ohne Bluetooth nutzbar** (Seiten von Hand wählen); der Hinweis erklärt, was fehlt.
- **Nach dem Speichern** springt der Assistent zur nächsten freien Seite (zyklisch) und zeigt eine Meldung; sind alle
  acht belegt, folgen *Würfel live ansehen* und *Zur Übersicht*.

### 29.3 Tests

`tests/gui/test_gui_faces.py` (14): reine Helfer (nächste freie Seite, Umbruch, belegte Seiten), Titel/Hilfe/leerer
Zustand, neue Tätigkeit anlegen und Sprung zur nächsten Seite, Speichern gesperrt ohne Namen, vorhandene Tätigkeit
wählen, doppelter Name, Seite entfernen (Tätigkeit bleibt), freie Seite nicht entfernbar, Verbindungshinweis und
„Jetzt verbinden“, unbekannte Adresse, „Seite N einrichten“ mit simuliertem Würfel, Abschluss mit Folgeschritten,
Maskierung im Bild, Hilfetexte an allen Feldern. Im Browser (Chromium) angesehen; nicht mit echter Hardware.

## 30. Startseite, geführte Einrichtung und Handbuch (`dashboard.views.start`, `dashboard.docs_reader`, AP-25)

Jede neue Sitzung öffnet auf der **Startseite** (`DEFAULT_PAGE = "start"`, Gruppe „Start“). Die Tests setzen den
Einstieg über den Hilfsparameter `nav` (`open_app` startet standardmäßig auf der Übersicht).

### 30.1 Aufbau

| Teil | Aufgabe |
|---|---|
| `views/start.py` | Umschalter *Willkommen / Einrichten / Handbuch* (`st.radio` mit Schlüssel `start_section`, damit Knöpfe den Bereich wechseln können, was `st.tabs` nicht erlaubt) |
| `SetupState`, `setup_state(devices)` | Stand der Einrichtung aus den echten API-Daten (aktiver Tracker zählt): Gerät vorhanden, Adresse, Verbindungszustand, belegte Seiten; `next_step` = `connect` / `faces` / `done`. Nichts wird gespeichert |
| `_welcome` | Erklärung, Einsatzmöglichkeiten, „So geht es los“, Banner „Nächster Schritt“; Beispielbild (`EXAMPLE_FACES`, als Beispiel beschriftet) |
| `_setup` | Drei Schritte mit Fortschritt; Schritte ②/③ sind gesperrt, bis ein Gerät existiert |
| `_search_and_connect`, `_use` | **Eine** Suche, **ein** Klick: registrieren (falls noch kein Tracker), Adresse speichern, verbinden. Treffer mit passendem Namen (`looks_like_tracker`) stehen oben und sind markiert; wurde keiner erkannt, erklärt eine Warnung die häufigsten Ursachen (kein Kopplungsmodus, mit Handy/Windows verbunden) |
| `_connection_line` (Fragment, 2 s) | Zustand des Würfels; lädt die Seite einmal neu, sobald er bereit ist, damit die Folgeschritte freigeschaltet werden |
| `dashboard/docs_reader.py` | `docs_dir`, `load_document`, `split_chapters`, `clean_links`, `search` (reine Funktionen) |

### 30.2 Entscheidungen

- **Handbuch = dieselben Markdown-Dateien wie auf GitHub** (einzige Quelle der Wahrheit): `BENUTZERHANDBUCH.md` und
  `INSTALLATION.md` aus `docs/`. Aufgeteilt an den `## `-Überschriften (Codeblöcke werden beachtet), ein Kapitel pro
  Ansicht plus Suche. Das Inhaltsverzeichnis mit Seitenankern entfällt (der Kapitel-Wähler ersetzt es), Verweise auf
  Projektdateien werden zu Text (sie würden im Dashboard ins Leere führen), `https://`-Links bleiben. Fehlt der
  Ordner `docs/` (Installation ohne Projektordner), zeigt die Seite einen Hinweis.
- **Registrierung, Adresse und Verbindung sind für Anwender ein Schritt.** Die technische Dreiteilung bleibt in der
  API und auf der Seite *Geräte*; dort wird das Suchergebnis jetzt auch ohne registrierten Tracker angezeigt
  (Name eingeben, „Registrieren und zuordnen“), statt wie zuvor nur den Hinweis „Registrieren Sie zuerst …“.
- **Erkennung am Namen:** Der echte Würfel meldete sich im Test als „Timeular Tra…“ ohne den Orientierungsdienst in
  der Werbung; ohne Namenshinweis war er unter rund 40 „Unbenannten Geräten“ kaum zu finden (AP-22).
- **Ehrlichkeit:** Das Beispielbild trägt die Beschriftung „Beispiel“; ein Hinweis auf der Willkommensseite nennt,
  dass nicht alle Würfelmodelle erprobt sind. Die Übersicht verweist in ihrer Checkliste jetzt auf Startseite und
  Zuordnungs-Assistent.
- **Kleine Stilkorrekturen** (`theme.py`): gesperrte Schaltflächen sind abgeblendet, Zitate (Hinweise im Handbuch)
  sind in voller Textfarbe lesbar.

### 30.3 Tests

`tests/unit/test_docs_reader.py` (8): Kapitel-Aufteilung, Codeblock-Kommentare, Verweise, Windows-Zeilenenden, Suche,
fehlende/ungültige Dateien, **die mitgelieferten Dokumente** (mindestens fünf Kapitel, keine toten Anker).
`tests/gui/test_gui_start.py` (19): reine Zustandslogik, neue Sitzung öffnet auf der Startseite, Willkommen
(Erklärung, Beispiel), Banner je Stand, Suche und ein Klick (Name, Adresse, Verbindung), eigener Name, Name leer,
nicht erkannter Würfel, Erkennung am Dienst, leere Suche, vorhandener Tracker ohne Adresse wird wiederverwendet,
Schritte schalten frei, Handbuch (Kapitel, Suche, zweites Dokument, fehlende Dokumentation), Hilfetexte. Im Browser
(Chromium) angesehen; nicht mit echter Hardware.

## 31. Steuerungsmodus und Integrationen (AP-26 bis AP-31)

Neben der Zeiterfassung kann ein Würfel **Dinge steuern** (Licht, Szenen, MQTT-Nachrichten, Webhooks). Entscheidungen
(Stand der Planung):

- **Umschalter pro Würfel:** `DeviceMode.TIME` (Standard) oder `DeviceMode.CONTROL`. Die Modi vermischen sich nie auf
  einem Würfel, damit eine Drehung nicht versehentlich Zeit startet **und** ein Licht schaltet.
- **Home Assistant ist die Zentrale für Smarthome-Standards.** Matter und Google Home werden **über Home Assistant**
  erreicht (dort läuft ein Matter-Controller, und Google Home kann Home-Assistant-Geräte steuern). OctaLedger
  verspricht **keine eigene Matter-Unterstützung** (Pflichtenheft §2: keine Matter-Zertifizierung; unter Windows gibt es
  keine unterstützte Matter-Bibliothek für Python).
- **Erste Anbindungen:** Webhook, MQTT, Home Assistant, Philips Hue (AP-27 bis AP-30), alle über denselben Baukasten.
- **Keine Shell-Befehle**, nur ausdrücklich eingerichtete Ziele (Pflichtenheft §8).

### 31.1 Datenmodell (AP-26a)

| Teil | Inhalt |
|---|---|
| `domain.models.DeviceMode`, `Device.mode` | Modus je Tracker; bestehende Tracker bleiben in `time` (Migration mit `DEFAULT 'time'`) |
| `Integration(kind, name, config, enabled)` | Eine Verbindung. `config` enthält **nur Einstellungen ohne Geheimnisse** (JSON-Objekt, höchstens 8 KiB, wird kopiert). Namen sind eindeutig (ohne Groß-/Kleinschreibung) |
| `FaceAction(device_id, face, integration_id, label, params, revision)` | Was eine Seite im Steuerungsmodus tut. `label` ist der Name, den der Anwender der Seite gibt; `revision` zählt Änderungen wie bei `FaceMapping` |
| `IntegrationJob` / `JobStatus` | Ein wartender Auftrag (`pending`, `done`, `failed`, `expired`). Enthält eine **Kopie** von Bezeichnung und Parametern, damit eine spätere Änderung der Seite einen bereits wartenden Auftrag nicht verändert |
| `IntegrationRepository`, `FaceActionRepository`, `JobRepository` | Persistenz (`repos.integrations`, `repos.actions`, `repos.jobs`) |

**Fremdschlüssel:** `face_actions → devices` mit `CASCADE` (Aktionen folgen dem Gerät), `face_actions → integrations` mit
`RESTRICT` (eine benutzte Verbindung lässt sich nicht löschen, erst die Aktion entfernen), `integration_jobs →
integrations` mit `CASCADE`, `integration_jobs → devices` mit `SET NULL` (die Historie bleibt, auch wenn das Gerät
gelöscht wird).

**Warteschlange („Outbox“):** Ein Auftrag wird in **derselben Transaktion** wie das auslösende Rohereignis geschrieben, der
eindeutige `idempotency_key` (die Kennung des Rohereignisses) macht eine Wiederholung unschädlich (`enqueue` liefert
`False`, nichts ändert sich). Jeder Auftrag hat eine **Verfallszeit** (`expires_at`): Ein Lichtschalter, der Minuten zu
spät kommt, ist schädlich. `due(now)` liefert fällige Aufträge, `mark_retry/done/failed/expired` beenden oder verschieben
sie, `expire_overdue` lässt Überfällige verfallen, `delete_finished_before` hält die Historie klein. Die Warteschlange ist
**Laufzeitdaten und nicht Teil der Sicherung** (nach einer Wiederherstellung wird sie geleert).

**Geheimnisse (Tokens, Passwörter) stehen nie in der Datenbank, in der Sicherung, in API-Antworten oder im Protokoll**; sie
liegen in einem eigenen Speicher im Benutzerprofil (AP-26b).

### 31.2 Sicherung Version 2

`BACKUP_SCHEMA_VERSION = 2`: Die Geräte enthalten `mode`, neue Abschnitte `integrations` und `face_actions` (Einstellungen
und Aktionen, **ohne Geheimnisse**; nach einer Wiederherstellung auf einem anderen Rechner müssen Tokens und Passwörter neu
eingegeben werden). **Dateien der Version 1 bleiben lesbar** (alle Tracker im Zeitmodus, keine Verbindungen). Die
Validierung ist unverändert streng (genaue Feldmengen, Eindeutigkeit, Verweise, Prüfsumme) und prüft zusätzlich doppelte
Verbindungsnamen, doppelte Aktionen je Seite und Verweise von Aktionen auf unbekannte Geräte oder Verbindungen. Die
Wiederherstellung leert zuerst Aufträge, Aktionen und Verbindungen (Reihenfolge wegen der Fremdschlüssel).

### 31.3 Tests (AP-26a)

`tests/unit/test_integrations_storage.py` (25): Modelle (Modus, Art/Name/Einstellungen, Kopie der Einstellungen, Größenlimit,
Seite/Bezeichnung/Revision, Auftragsstandards), Gerätemodus speichern und ändern, **Migration lässt bestehende Tracker im
Zeitmodus**, Verbindungen (CRUD, eindeutige Namen, benutzte Verbindung nicht löschbar), Aktionen (zuweisen, Revision,
entfernen, mit dem Gerät löschen), Warteschlange (idempotent, fällig, Wiederholung/erledigt/fehlgeschlagen/verfallen,
Bereinigung, Gerät gelöscht), Sicherung v2 (Rundreise, Wiederherstellung leert die Warteschlange, **v1-Datei lesbar**, acht
ungültige Inhalte werden vor jeder Änderung abgelehnt).

### 31.4 Adapter-Vertrag (`infrastructure.integrations.base`, AP-26b)

Ein *Adapter* kann mit **einer** Art von Ziel sprechen. Alles andere (Speichern, Aktionen pro Seite, Warteschlange,
Wiederholung, Oberfläche) ist allgemein. Damit auch die Oberfläche allgemein bleibt, **beschreibt sich jeder Adapter
selbst** (`AdapterSpec`): welche Einstellungen er braucht (`FieldSpec`: Text, Passwort, Zahl, Ja/Nein, Auswahl; mit
Pflicht, Hilfetext, Standardwert, Grenzen), welche Aktionen er bietet (`ActionSpec`, mit Feldern und dem Hinweis
`idempotent`) und ob er Kopplung (`can_pair`) oder Entdeckung von Lampen/Szenen (`can_discover`) kann. Die Oberfläche
erzeugt daraus Formulare; **ein neuer Adapter braucht keine Änderung an Oberfläche, API oder Speicher**, nur ein Modul und
einen Eintrag in `registry.default_adapters()`.

`Adapter` (abstrakte Klasse): `validate_config`, `validate_action` (Standard: gegen die Spezifikation, **unbekannte Felder
werden abgelehnt**), `check` (Verbindungstest ohne Nebenwirkung), `execute` (blockierend, im Arbeits-Thread), optional
`pair` und `discover`. `validate_fields` prüft Pflicht, Zahlengrenzen, Auswahlwerte, Länge (500 Zeichen) und **verbietet
Zeilenumbrüche** (Schutz vor Header-Einschleusung).

**Wiederholungsregel (wichtig):** Ein Adapter wirft `IntegrationConnectionError` **nur**, wenn die Anfrage **sicher keine
Wirkung** hatte (nicht verbunden, vor dem Senden abgelehnt) – nur das wird wiederholt. Alles andere (auch ein Zeitlimit nach
dem Senden) ist `IntegrationError` und wird **nicht** wiederholt, weil das Wiederholen einer Aktion mit unbekanntem Ausgang ein
Licht zweimal umschalten könnte. Adapter führen keine Shell-Befehle aus, folgen keinen Weiterleitungen auf andere Schemata und
nehmen keine Geheimnisse in Meldungen auf.

### 31.5 Zugangsdaten (`core.secrets.SecretStore`, AP-26b)

Passwörter und Tokens liegen in **einer** Datei `secrets.json` im Datenordner – **nicht** in der Datenbank (also nicht in
Sicherungen), **nicht** in API-Antworten (die API nennt nur, *welche* Zugangsdaten gesetzt sind), **nicht** im Protokoll (jeder
Wert wird beim Speichern und Laden bei `register_secret` angemeldet und überall maskiert). Atomares Schreiben über
`core.fileio`, unter POSIX nur für den Besitzer lesbar; unter Windows schützt der Benutzerprofilordner. **Nicht
verschlüsselt** (wie die Datei `api_token`); eine Verschlüsselung mit dem Windows-Tresor wäre ein späterer Schritt. Ein
fehlgeschlagenes Schreiben hält Arbeitsspeicher und Datei konsistent; eine beschädigte Datei liefert eine klare Meldung **ohne
Dateiinhalt**. Leerer Wert = Zugangsdatum entfernen.

### 31.6 Dienst und Warteschlange (`application.integration_service`, `application.outbox`, AP-26b)

`IntegrationService` (Adapter werden als `kind → Adapter` übergeben, Tests nutzen Attrappen):

- **Verbindungen:** `create` trennt Einstellungen von Zugangsdaten (Pflicht-Zugangsdaten werden verlangt), legt zuerst die
  Verbindung an und speichert danach die Zugangsdaten – schlägt das fehl, wird die Verbindung wieder entfernt (nichts
  Halbfertiges). `update` führt geänderte Werte mit den gespeicherten **zusammen, bevor** geprüft wird; ein leeres Passwortfeld
  behält das gespeicherte. `delete` verweigert, solange eine Seite die Verbindung nutzt, und vergisst danach die Zugangsdaten.
- **Ausprobieren** (im aufrufenden Thread, nie in einer Transaktion): `check`, `probe` (eine Aktion **jetzt** ausführen, nach
  Validierung), `pair`, `discover`.
- **Aktionen pro Seite:** `assign_action` (vom Adapter validiert), `clear_action`, `list_actions`.
- **Senden:** `process_due()` lässt Überfällige verfallen, räumt alte Historie auf (7 Tage), sendet fällige Aufträge in
  Erzeugungsreihenfolge und hält jedes Ergebnis fest. Es wirft nie wegen eines Auftrags; ein **abstürzender Adapter** beendet
  den Auftrag als fehlgeschlagen („Unerwarteter Fehler“, ohne Details und Geheimnisse), der nächste wird trotzdem gesendet.
  Adapteraufrufe geschehen **außerhalb** von Datenbanktransaktionen.

Regeln der Warteschlange (`outbox`): Der Auftrag entsteht **in derselben Transaktion** wie das Rohereignis; der eindeutige
Schlüssel ist die Ereignis-Kennung. **Verfallszeit 30 s** (ein zu spät kommendes Licht ist schädlich), höchstens **50 wartende
Aufträge je Verbindung** (weitere werden als „verfallen“ mit Begründung gespeichert statt unbegrenzt zu wachsen), höchstens
**3 Versuche** mit Pausen von 1 s und 3 s; eine Wiederholung, die erst nach Ablauf der Verfallszeit käme, schlägt sofort
fehl. Aus- oder gelöschte Verbindung → Auftrag verfällt; unbekannte Adapterart → fehlgeschlagen.

### 31.7 Steuerungspfad im Tracking und Moduswechsel (AP-26b)

`TrackingService.record_event`: Ein Tracker im Steuerungsmodus berührt **nie** Zeiteinträge. Nur ein echter Seitenwechsel
(1–8) reiht die Aktion dieser Seite ein (`Outcome.ACTION_QUEUED`, sonst `ACTION_SKIPPED` bei Seite ohne Aktion, ausgeschalteter
Verbindung oder voller Warteschlange); **Baseline (erste Meldung nach dem Verbinden), Zwischenlage, Trennen und Wiederverbinden
lösen nie etwas aus**. Ein Steuerungs-Tracker arbeitet **unabhängig davon, ob er der aktive Tracker ist**; Zeit-Tracker verhalten
sich unverändert.

`DeviceService.set_mode`: Ein Steuerungs-Würfel kann nicht der aktive Zeit-Tracker sein. Stellt man den aktiven Tracker auf
Steuerung, geht die Rolle an einen anderen Zeit-Tracker (falls vorhanden); stellt man einen Tracker auf Zeiterfassung zurück
und niemand ist aktiv, wird er der aktive. **Eine laufende Zeit dieses Trackers muss zuerst gestoppt werden** (sonst
`InvalidStateError`, nichts wird still abgeschnitten); eine laufende manuelle Zeit stört nicht. `TrackingService.handover` weist
einen Steuerungs-Tracker ab. `DeviceInfo` trägt die Aktionen; `configured_faces` zählt im Steuerungsmodus die Aktionen.

### 31.8 Tests (AP-26b)

`tests/unit/test_secret_store.py` (14): Neustart, Namen ohne Werte, Zusammenführen/Entfernen, Löschen, Kopie, **Maskierung im
Protokolltext**, Besitzer-Rechte (POSIX), beschädigte Dateien ohne Inhaltsleck, fehlgeschlagenes Schreiben, Längenlimit, keine
Werte in Logzeilen. `tests/unit/test_integration_service.py` (23): Selbstbeschreibung, Zugangsdaten nur im Speicher, acht
Eingabefehler mit deutschen Meldungen, eindeutige Namen, kein halbes Anlegen, Ändern (leeres Passwort behält), Löschen,
Prüfen/Ausprobieren, Kopplung/Entdeckung, Aktionen (Validierung, Revision), Senden (Erfolg, Reihenfolge, Wiederholung,
Versuchslimit, **dauerhafter Fehler wird nicht wiederholt**, abstürzender Adapter, Verfall, zu späte Wiederholung, ausgeschaltet,
unbekannter Adapter, Historie, Bereinigung). `tests/unit/test_control_mode.py` (18): Auftrag je Seitenwechsel, Idempotenz,
nichts bei Baseline/Zwischenlage/Trennen, Seite ohne Aktion, ausgeschaltet, begrenzte Warteschlange, Kopie der Aktion,
Zeiteinträge bleiben unberührt, aktiver/nicht aktiver Steuerungs-Tracker, Zeit-Tracker unverändert, Moduswechsel (Rolle geben,
laufende Zeit blockiert, manuelle Zeit nicht, Wiederholung, unbekanntes Gerät, Übergabe abgewiesen).

### 31.9 Dispatcher, API und Agent (AP-26c)

**`ActionDispatcher`** (`agent/dispatcher.py`): ein **Daemon-Thread** im Agenten, der alle 0,25 s die fälligen Aufträge abholt
(`IntegrationService.process_due`) und sendet. Gründe: Der BLE-Loop darf nie auf eine Netzwerkanfrage warten, und das Dashboard
ist nicht beteiligt (Schließen des Browsers stoppt nichts). Aufträge werden **nacheinander in Erzeugungsreihenfolge** gesendet
(„an“ dann „aus“ kommt als „an“, dann „aus“ an). Der Thread **überlebt jeden Fehler** (Protokoll, nächste Runde), und das Warten ist ein
`threading.Event`, sodass das Herunterfahren nicht auf das Intervall wartet. Start in `AgentRuntime.start()`, Stopp in
`shutdown()` (nach dem API-Server).

**API:** siehe die Endpunkt-Tabelle in §19.3. Besonderheiten: `GET /adapters` liefert die Selbstbeschreibung der Adapter (die
Oberfläche erzeugt daraus Formulare); Antworten nennen von Zugangsdaten nur `secrets_set` (Namen), `device_out` trägt `mode` und
`actions`, `live_out` trägt `mode` und je Seite `action` (Bezeichnung). `IntegrationError` (auch `…ConnectionError`) wird als
**502** gemeldet (das Ziel hat versagt, nicht OctaLedger), der Code `OL-INTEG-001/002` bleibt erhalten. Fehlt der
Integrationsdienst im Prozess, antworten die Endpunkte mit 503 statt abzustürzen. Der **Dashboard-Client** bietet die passenden
Methoden (siehe §20.3).

**Agent:** `AgentRuntime` baut `SecretStore(<Datenordner>/secrets.json)`, `IntegrationService` (Standard:
`default_adapters()`, Tests übergeben Attrappen über `adapters=`) und den Dispatcher. Der **Autostart** verbindet jetzt den aktiven
Tracker **und jeden Steuerungs-Tracker** mit Adresse; scheitert einer, laufen die anderen und der Agent trotzdem.

### 31.10 Tests (AP-26c)

`tests/unit/test_dispatcher.py` (4): Aktion wird vom Thread gesendet (auch später eintreffende), ein Thread trotz zweifachem
Start und **prompter Stopp** trotz langem Intervall, unerwarteter Fehler beendet den Thread nicht, fehlschlagender Adapter blockiert
den nächsten Auftrag nicht. `tests/unit/test_api.py` (+12): Formularbeschreibung, **Zugangsdaten tauchen nie in API-Antworten oder
Sicherungen auf**, Lebenszyklus, deutsche 422-Meldungen, Test/Ausprobieren/Kopplung/Entdeckung, 502 mit Code, Moduswechsel und
Aktionen (inkl. Live-Ansicht), Fehlerfälle, benutzte Verbindung nicht löschbar (409), Verlaufsgrenzen, 503 ohne Dienst.
`tests/integration/test_agent_runtime.py` (+3, **ganze Kette mit synthetischem Tracker und Attrappen-Adapter**): Drehung →
Aktion gesendet, **Baseline schaltet nichts**, Seite ohne Aktion tut nichts, **keine Zeit erfasst**; ein fehlschlagender
Adapter erscheint im Verlauf (ohne Details) statt unterzugehen; Steuerungs-Tracker verbindet beim Agentenstart selbst.

### 31.11 Webhook-Adapter (`infrastructure.integrations.webhook`, AP-27)

Der allgemeine Adapter für „weitere Standards“ (seit AP-29 nutzt er die gemeinsame HTTP-Logik aus `httpio`, siehe §31.15): eine *Verbindung* ist eine Basisadresse (`http(s)://host:port[/prefix]`) mit
optionalem Zugang, eine *Aktion* ist **eine Anfrage an einen Pfad** (Methode GET/POST/PUT/PATCH/DELETE, Inhaltstyp JSON oder
Text, optionaler Inhalt). Er deckt Node-RED, ESPHome, IFTTT-ähnliche Dienste und eigene Skripte ab.

**Sicherheitsregeln:**

- Nur `http`/`https`, **ohne** Benutzername/Passwort, Abfrage-Teil oder Anker in der Basisadresse; ungültiger Port wird abgelehnt.
  Der Pfad wird **an die Basisadresse angehängt** (muss mit `/` beginnen, `//` ist verboten), eine Aktion kann also nie einen
  anderen Rechner ansprechen. Ein Abfrage-Teil gehört zum Pfad (`/an?x=1`).
- **Weiterleitungen werden nie befolgt** (sie könnten auf ein anderes Schema oder einen anderen Rechner zeigen); eine
  Weiterleitung wird als Fehler gemeldet. **Umgebungs-Proxys werden ignoriert** (`trust_env = False`): eine Anfrage in das eigene
  Netz soll nicht heimlich über einen Proxy laufen.
- Die **Antwort wird nicht gelesen** (`stream=True`, nur Statuszeile), ein feindliches oder riesiges Antwort-Paket kostet nichts.
- Der **Zugangswert ist ein Geheimnis** (getrennt gespeichert, nie im Protokoll, nie in einer Antwort); der Kopfname ist auf
  Buchstaben, Ziffern und `-` beschränkt, Zeilenumbrüche sind in allen Feldern verboten (keine Kopfzeilen-Einschleusung).
- JSON-Inhalt muss gültiges JSON sein, `GET` mit Inhalt wird abgelehnt, Textwerte sind auf 500 Zeichen begrenzt.
- Zertifikatsprüfung bei `https` ist **standardmäßig an** und lässt sich bei selbst erzeugten Zertifikaten ausschalten.

**Wiederholung:** Nur wenn die Anfrage **sicher nicht beim Ziel ankam** (nicht verbindbar, Name nicht auflösbar, Zeitlimit **beim
Verbinden**; erkannt über die Ursache des Fehlers, auf Windows meldet ein geschlossener Port ein Verbindungs-Zeitlimit) →
`IntegrationConnectionError` (wird wiederholt). Jede **Antwort** (auch 4xx/5xx), ein Abbruch **während** der Verbindung und ein
Zeitlimit **nach dem Senden** sind `IntegrationError` und werden **nicht** wiederholt (die Aktion könnte schon ausgeführt sein).
401/403 verweisen auf Zugangskopf und -wert. `check` fragt die Basisadresse einmal per GET und akzeptiert jede Antwort unter 500
als „erreichbar“ (ein 404 beweist, dass das Ziel da ist), 401/403/5xx werden gemeldet.

### 31.12 Tests (AP-27)

`tests/unit/test_adapter_webhook.py` (36, **gegen einen echten lokalen HTTP-Server**): Adressen (angenommen/abgelehnt mit deutscher
Meldung), Kopfname, Geheimnis nicht in den Einstellungen, Aktionsregeln, Anfrage kommt wie konfiguriert an (Methode, Pfad,
Inhalt, Inhaltstyp, Zugangskopf, `User-Agent`), kein Zugangskopf ohne Geheimnis, Basis-Pfad, **Fehlerantworten sind dauerhaft**,
401 verweist auf den Zugang, **Weiterleitung wird nicht befolgt (nur ein Rechner kontaktiert)**, abgelehnte Verbindung und unbekannter
Host werden wiederholt, **Zeitlimit nach dem Senden nicht**, **Umgebungs-Proxys werden ignoriert**, Prüfung (404 = erreichbar,
401/503 gemeldet, unerreichbar), Auslieferung mit dem Programm und **ein eingereihter Auftrag erreicht über den Dienst das Ziel**.
Nicht geprüft: echte Geräte und Dienste (siehe `QUELLEN_UND_GRENZEN.md`).

### 31.13 MQTT-Adapter (`infrastructure.integrations.mqtt`, AP-28)

MQTT ist der Standard des Smarthomes (Mosquitto, Home Assistant, Zigbee2MQTT, Tasmota, ESPHome, Node-RED). Eine Drehung wird zu
**einer veröffentlichten Nachricht** (Thema und Inhalt, z. B. `zigbee2mqtt/schreibtischlampe/set` mit `{"state": "TOGGLE"}`).
Eine *Verbindung* hat Adresse, Port (Standard 1883), optional Benutzername und Passwort (Geheimnis) sowie TLS (Port 8883) mit
einstellbarer Zertifikatsprüfung; die *Aktion* `publish` hat Thema, Inhalt, QoS (0 oder 1, Standard 1) und `retain`.

**Warum das Protokoll hier selbst gesprochen wird (nur Standardbibliothek):** Gebraucht wird nur ein *Veröffentlicher*:
verbinden, ein PUBLISH senden, trennen – wenige Bytes eines einfachen, vollständig spezifizierten Protokolls (MQTT 3.1.1). Das
gibt genau das, was die Warteschlange braucht und eine allgemeine Client-Bibliothek nicht liefert: ein **hartes Zeitlimit für jeden
Schritt** (auch das Verbinden) und die **genaue Antwort auf „ist die Nachricht sicher *nicht* hinausgegangen?“** – die Grundlage der
Wiederholungsregel. Keine neue Abhängigkeit, kein Hintergrund-Thread, nach jeder Aktion bleibt nichts verbunden. Jeder Versuch
nutzt eine frische Client-Kennung (`octaledger-<zufall>`), Clean Session, Keep-Alive 15 s.

**Wiederholungsregel:** Scheitert das **Verbinden/Anmelden** (abgelehnt, nicht erreichbar, Name unbekannt, Zeitlimit, Broker legt
beim Anmelden auf), wurde nichts veröffentlicht → `IntegrationConnectionError` (wird wiederholt). Falsche Zugangsdaten, fehlende
Berechtigung, ein Ziel, das kein MQTT spricht, und ein fehlgeschlagener TLS-Handshake sind **dauerhaft** (`IntegrationError`, mit
verständlicher Meldung je CONNACK-Code). Alles **nach** dem Schreiben des PUBLISH (keine Bestätigung bei QoS 1, Verbindung
abgebrochen) lässt den Ausgang offen und ist **dauerhaft** – ein erneutes „TOGGLE“ könnte das Licht zweimal umschalten.

**Sicherheit und Grenzen:** Antworten des Brokers sind auf 1 KiB begrenzt, Themen dürfen keine Platzhalter (`+`, `#`), kein `$`
am Anfang und keine NUL-Zeichen enthalten, die Adresse darf kein `mqtt://` oder keinen Pfad enthalten. MQTT 3.1.1, **nur Senden**
(kein Abonnieren), QoS 0/1, keine WebSockets, keine Client-Zertifikate, Textinhalte bis 500 Zeichen. `check` meldet sich an und
trennt wieder, ohne etwas zu veröffentlichen.

### 31.14 Tests (AP-28)

`tests/unit/test_adapter_mqtt.py` (44, **gegen einen Fake-Broker auf Protokollebene**, der die Pakete unabhängig vom Adapter parst,
sodass beide sich gegenseitig prüfen): Kodierung der Längenzahl nach Spezifikation und Pakete gegen **von Hand berechnete Bytes**,
Passwort ohne Benutzer wird nicht gesendet, Adress-/Port-/Themen-Regeln, Standardwerte, Nachricht kommt vollständig an (Thema,
Inhalt mit Umlauten, QoS, retain, Anmeldung), QoS 0 ohne Bestätigung, frische Client-Kennung, falsche Zugangsdaten und fehlende
Berechtigung (dauerhaft), nicht erreichbar/unbekannter Host/Broker antwortet nicht/legt auf (werden wiederholt, **nichts
veröffentlicht**), kein MQTT-Broker, **fehlende Bestätigung wird nicht wiederholt** (die Nachricht kam einmal an), Prüfung ohne
Veröffentlichung, TLS (Umhüllung mit der gewählten Prüfung, kein TLS ohne Anforderung, fehlgeschlagener Handshake dauerhaft; mit
einer Attrappe, da ohne Zertifikat kein echter Handshake möglich ist), Auslieferung mit dem Programm und **ein eingereihter Auftrag
wird über den Dienst veröffentlicht**. Nicht geprüft: Mosquitto, Home Assistant oder ein echter Hub, ein echter TLS-Handshake.

### 31.15 Gemeinsame HTTP-Logik (`infrastructure.integrations.httpio`, AP-29)

Webhook und Home Assistant sprechen beide HTTP. Damit die **Einstufung eines Fehlers** (Grundlage der Wiederholungsregel) nur an
**einer** geprüften Stelle steht, liegt sie in `httpio`: `send()` führt eine Anfrage aus und meldet *sicher nicht angekommen*
(nicht verbindbar, Name unbekannt, Zeitlimit **beim Verbinden**; erkannt über die Ursache des Fehlers) als
`IntegrationConnectionError`, alles andere (Abbruch mitten in der Verbindung, Zeitlimit **nach** dem Senden) als
`IntegrationError`. Sichere Voreinstellungen für alle: **keine Weiterleitungen**, **keine Umgebungs-Proxys**, **immer ein
Zeitlimit**, die Antwort wird nur gelesen, wenn ein Adapter es verlangt, und dann **begrenzt** (`read_limited`, 4 MiB).
`check_base_url()` prüft Basisadressen (nur http/https, ohne Zugangsdaten, Abfrage oder Anker, gültiger Port).

### 31.16 Home-Assistant-Adapter (`infrastructure.integrations.homeassistant`, AP-29)

Home Assistant ist die **Zentrale** für die Standards, die OctaLedger nicht selbst spricht: Alles, was dort eingebunden ist
(Matter-Geräte, Google-Home-Anbindung, Zigbee, Hue, KNX), kann eine Würfelseite über einen **Dienstaufruf** schalten. Eine
*Verbindung* ist die Adresse von Home Assistant und ein **langlebiges Zugriffstoken** (Geheimnis, nur als Bearer-Kopf gesendet).
Aktionen: **Einschalten** (bei Lampen optional mit Helligkeit in %), **Ausschalten**, **Umschalten** (nicht idempotent),
**Szene aktivieren**, **Skript ausführen** (nicht idempotent) und **beliebiger Dienst** (`bereich.dienst` mit Gerät und JSON-Daten,
nicht idempotent). Einschalten/Ausschalten/Umschalten nutzen `homeassistant.turn_on/turn_off/toggle`, das für fast alle Arten von
Geräten funktioniert; mit Helligkeit wird `light.turn_on` mit `brightness_pct` aufgerufen.

**Sicherheit:** `bereich` und `dienst` sind auf `[a-z0-9_]` beschränkt und die Geräte-Kennung auf das Format `bereich.name`, sodass
**kein Wert den Anfragepfad verändern kann** (kein `../`). Szene/Skript müssen mit `scene.`/`script.` beginnen, eine Helligkeit gibt
es nur für `light.…`, zusätzliche Daten müssen ein JSON-Objekt sein. Das Token steht nie in einer Meldung (auch eine abgelehnte
Anmeldung nennt es nicht); ohne gespeichertes Token wird **nichts gesendet**. 401/403 verweisen darauf, ein neues Zugriffstoken zu
erstellen, 404 beim Dienstaufruf auf „Bereich“ und „Dienst“.

**Entdecken:** `GET /api/states` liefert Lampen, Schalter, Szenen, Skripte, Hilfsschalter, Ventilatoren, Rollläden und Mediengeräte
(`{"light": [{"id", "name"}]}`, nach Anzeigename sortiert, höchstens 200 je Art, leere Arten fehlen, Sensoren u. a. werden nicht
aufgelistet; ungültige Einträge werden übersprungen), damit die Oberfläche eine Auswahl statt einer Texteingabe bieten kann. `check`
fragt die API-Wurzel, die nur mit gültigem Token antwortet.

### 31.17 Tests (AP-29)

`tests/unit/test_adapter_homeassistant.py` (42, **gegen einen lokalen Nachbau der REST-Schnittstelle**): Token als Geheimnis und
Adressprüfung, fehlerhafte Geräte-Kennungen, Szene/Skript-Präfix, Helligkeit nur für Lampen und im Bereich, **Bereich/Dienst können
den Pfad nicht verändern**, JSON-Daten, unbekannte Felder/Aktionen, **jede der Aktionen ruft den passenden Dienst mit dem richtigen
Inhalt auf**, ohne Token wird nichts gesendet, falsches Token nennt es nicht, unbekannter Dienst, Fehlerantwort dauerhaft,
nicht erreichbar wird wiederholt, **Zeitlimit nach dem Senden nicht**, Weiterleitung nicht befolgt, Prüfung ohne Nebenwirkung,
Entdecken (sortiert, begrenzt, tolerant gegen seltsame Antworten), die gemeinsame Sitzung ignoriert die Umgebung, eine riesige
Antwort wird abgeschnitten, Auslieferung mit dem Programm und **ein eingereihter Auftrag erreicht Home Assistant über den Dienst**.
Nicht geprüft: ein echter Home Assistant (Versionen und Fehlertexte können abweichen), Matter-/Google-Home-Geräte dahinter.

### 31.18 Philips-Hue-Adapter (`infrastructure.integrations.hue`, AP-30)

Steuert die **Hue Bridge im Heimnetz** über deren lokale Schnittstelle (CLIP API v2, `https://<bridge>/clip/v2`): kein Cloud-Konto,
nichts verlässt das Heimnetz. Eine *Verbindung* ist die Adresse der Bridge; der **Anwendungsschlüssel** entsteht einmalig durch
das **Koppeln** (runden Knopf auf der Bridge drücken, dann „Koppeln“) und liegt als Geheimnis im Speicher (nicht erforderlich beim
Anlegen, `pair` setzt ihn). Aktionen: **Lampe schalten**, **Raum oder Zone schalten** (die Lampengruppe des Raums) und **Szene
aktivieren**; Lampe und Raum können einschalten, ausschalten oder umschalten, beim Einschalten optional mit **Helligkeit** (1–100 %)
und **Farbtemperatur** (2000–6500 K, umgerechnet in Mirek und auf den Bereich der Bridge begrenzt). Helligkeit/Farbtemperatur zusammen
mit „aus“ oder „umschalten“ wird abgelehnt.

**Zertifikat-Anheftung (Vertrauen beim ersten Mal):** Statt die Prüfung abzuschalten, merkt sich das Koppeln den **SHA-256-Fingerabdruck**
des Bridge-Zertifikats (als Einstellung `fingerprint`, kein Geheimnis) und jede spätere Anfrage spricht nur mit einem Server, der genau
dieses Zertifikat vorzeigt (`PinnedAdapter`: `assert_fingerprint`, Hostname-Prüfung aus, weil die Bridge per IP angesprochen wird). Ohne
gespeicherten Fingerabdruck **sendet der Adapter über https nichts** („bitte erneut koppeln“). Das Vertrauen entsteht einmal im
Heimnetz beim Koppeln; ein Angreifer im Heimnetz *während des Koppelns* könnte es erschleichen (gleiches Vertrauen wie beim Knopfdruck).

**Weitere Regeln:** Kennungen von Lampe, Raum und Szene müssen echte UUIDs sein (sie werden Teil des Pfades, kein `../`), die Adresse
nur ein Name oder eine IP (optional mit Port), Fehler, die die Bridge **innerhalb einer 200-Antwort** meldet (`errors`), werden nicht
verschluckt, `401/403` führen zum erneuten Koppeln, `404` zur Auswahl über „Entdecken“, jede andere Antwort ist dauerhaft; wiederholt wird
nur, was sicher nicht ankam (siehe §31.15). **Umschalten** liest zuerst den Zustand und setzt dann das Gegenteil (zwei Anfragen; schlägt
das Schreiben fehl, wird es nicht wiederholt). **Entdecken** listet Lampen, Räume (mit der Kennung ihrer *Lampengruppe*) und Szenen nach
Namen (Einträge ohne Kennung werden übersprungen). Konstruktor-Schalter `scheme`/`pin`/`session_for`/`fetch_certificate` machen die
Nahtstellen für Tests austauschbar.

**Grenzen:** keine anderen Gruppen als Räume/Zonen, keine Farbe (nur Helligkeit und Farbtemperatur), keine Sensoren, kein Ereignisstrom,
**keine automatische Suche der Bridge** (die Adresse wird von Hand eingetragen; der Cloud-Suchdienst von Hue würde Daten aus dem Heimnetz
senden).

### 31.19 Tests (AP-30)

`tests/unit/test_adapter_hue.py` (46, **gegen einen lokalen Nachbau der Bridge** über einfaches HTTP): Adressen, Fingerabdruck
(normalisiert/geprüft), Schlüssel als Geheimnis und beim Anlegen nicht verlangt, **Kennungen müssen UUIDs sein**, Aktionsregeln,
Koppeln (ohne Knopf mit Erklärung, mit Knopf liefert den Schlüssel als Geheimnis, mit Anheftung wird der Fingerabdruck gemerkt,
Bridge nicht erreichbar wird wiederholt, verwirrende Antwort), **SHA-256 gegen den bekannten Wert**, die Sitzung heftet nur `https` an,
**ohne Fingerabdruck wird nichts gesendet (nicht einmal eine Sitzung)**, Prüfung ohne Nebenwirkung, abgelehnter Schlüssel nennt ihn nicht,
Lampe mit Helligkeit und Farbtemperatur (Mirek-Umrechnung an den Grenzen), Ausschalten, **Umschalten liest zuerst und kehrt um**, Raum und
Szene, **Fehler in einer 200-Antwort werden gemeldet**, unbekannte Lampe, 429/500/503 dauerhaft, nicht erreichbar wird wiederholt,
Entdecken (sortiert, Gruppen-Kennung, Einträge ohne Kennung übersprungen), Auslieferung und **Koppeln und Schalten über den Dienst**.
Nicht geprüft: eine echte Bridge, ein echter TLS-Handshake mit der Anheftung (dafür fehlt ein Test-Zertifikat; mit der Test-Bibliothek
`trustme` ließe sich das ergänzen).

### 31.20 Oberfläche für Verbindungen (`dashboard.forms`, `dashboard.views.connections`, AP-31a)

Die Seite **Verbindungen** (Gruppe „Einrichten“) verwaltet Verbindungen und enthält **keinen Code für einzelne Adapter**: Die Formulare
entstehen aus der Selbstbeschreibung (`GET /adapters`), die `dashboard/forms.py` in Eingabefelder übersetzt.

- **`render_fields(fields, key_prefix, values, secrets_set, discovered)`** zeichnet je Feld ein Widget (Text, Zahl, Schalter, Auswahl,
  Passwort) und liefert die eingegebenen Werte; leere Texte und leere Zahlen werden weggelassen, Schalter immer gemeldet. **Jedes Feld
  hat einen Hilfetext** (Rückfall: „Angabe für diese Verbindung.“), Pflichtfelder sind mit `*` markiert, Schlüssel sind je
  `key_prefix` eindeutig. Passwortfelder zeigen **nie** einen gespeicherten Wert; ein leeres Feld bedeutet „behalten“ (der Platzhalter
  sagt „gespeichert“).
- **Auswahllisten statt Kennungen (`FieldSpec.choices_from`):** Ein Textfeld kann die **Entdeckungskategorien** nennen, aus denen es
  sich füllen lässt (Hue: `light_id` ← `lights`, `group_id` ← `rooms`, `scene_id` ← `scenes`; Home Assistant: Geräte-Kennung ← Lampen,
  Schalter, Hilfsschalter, Ventilatoren, Rollläden, Mediengeräte bzw. Szenen bzw. Skripte). Nach „Geräte auflisten“ wird daraus eine
  Auswahl mit Namen (bei gemischten Kategorien mit Zusatz wie „(light)“); niemand muss eine UUID abtippen. Die API liefert
  `choices_from` je Feld mit.
- **Seite:** je Verbindung ein Kasten mit Zustand und Zusammenfassung (Einstellungen ohne Geheimnisse, „Passwort: gespeichert ✔“) und
  den Reitern *Prüfen* (testen, koppeln), *Ausprobieren* (auflisten, Aktion wählen, Warnung bei nicht idempotenten Aktionen, „Jetzt
  senden“) und *Einstellungen* (Name, Angaben, ein/aus, Löschen mit Bestätigung). Darunter „Neue Verbindung“ und die Tabelle „Letzte
  Aktionen“. Nach dem Anlegen wird das Formular **einschließlich des Passworts geleert** (ein eingetipptes Passwort bleibt nicht
  stehen; der Test hat das aufgedeckt).

### 31.21 Tests (AP-31a)

`tests/gui/test_gui_connections.py` (21): Titel/Hilfe/leerer Zustand, Anlegen aus der Beschreibung, **Geheimnisse bleiben verborgen**
(Seite, Widgets), fehlende Pflichtfelder mit deutscher Meldung und Code, doppelter Name, Verbindungstest (Erfolg und Misserfolg ohne
Nennung des falschen Werts), Koppeln, **Auswahlliste aus „Entdecken“** und Ausprobieren, fehlendes Feld sendet nichts, Warnung bei
nicht idempotenten Aktionen, Einstellungen ändern (leeres Passwort behält), ein/aus, **Löschen nur mit Bestätigung und nicht, solange
eine Seite die Verbindung nutzt**, Verlauf mit allen Ergebnissen, Hilfetexte an allen Feldern, Seite meldet fehlenden Dienst, und der
Formular-Generator selbst (jede Feldart, Rückgabewerte, gemischte Auswahllisten, Hilfsfunktionen, kein Geheimnis im Widget-Zustand).
Im Browser angesehen; mit dem Test-Adapter, nicht mit einem echten Ziel.

### 31.22 Steuerungsmodus in der Oberfläche (AP-31b)

- **Moduswechsel pro Würfel** in *Seiten zuordnen* (`_mode_switch`): ein Umschalter *Zeit erfassen / Dinge steuern*. Die Umstellung
  läuft in einem **`on_change`-Rückruf** (`_on_mode_change`), der `PUT /devices/{id}/mode` aufruft; scheitert er (zum Beispiel
  `OL-STATE-003`, weil eine Zeit läuft), setzt er den Umschalter **auf den alten Wert zurück** und merkt sich Meldung und Code für die
  nächste Anzeige (ein Widget-Schlüssel darf erst vor dem Erzeugen des Widgets geändert werden; sonst würde der Fehlschlag bei jedem
  Neuladen wiederholt).
- **Aktions-Editor** (`views/faces_actions.py`, ohne adapterspezifischen Code): Verbindung wählen (nur eingeschaltete; ohne eine Hinweis
  mit Weg zu *Verbindungen*), Aktion (aus der Selbstbeschreibung; Warnung bei nicht idempotenten), Felder über `render_fields` (mit
  Auswahllisten nach „Geräte auflisten“), **Name der Seite**, *Jetzt ausprobieren* (`probe`, speichert nichts), *Seite N speichern*
  (springt zur nächsten freien Seite, gleiche Mechanik `faces_pending_target` wie bei Tätigkeiten), *Entfernen*. Der Editor liegt wie der
  Tätigkeits-Editor **außerhalb** des sich erneuernden Fragments. `assigned_faces` zählt im Steuerungsmodus die Aktionen.
- **Bild und Live-Ansicht:** `face_labels` nutzt im Steuerungsmodus die **Aktionsnamen** (feste Farbe `ACTION_COLOR`, der Name unterscheidet).
  Live: ③ heißt „Die Aktion“ (steuert Dinge, keine Zeit; „Seite N: Die Aktion „x“ wird ausgelöst“ bzw. Hinweis auf fehlende Aktion),
  der Verlauf nennt „Die Aktion „x“ wird gesendet“ und darunter stehen **„Letzte Aktionen“** (`GET /jobs`). Zeit-Würfel bleiben unverändert.
- **Geräte-Seite:** Ein Steuerungs-Würfel trägt „🎛 Steuerung“ im Titel, zeigt statt der Tätigkeits-Tabelle einen Hinweis mit Weg zu *Seiten
  zuordnen*, und „Zum aktiven Tracker machen“ ist gesperrt (er erfasst keine Zeit). **Statusleiste:** „Name (Steuerung): Bereit“
  (`GET /status` meldet `mode` je Gerät). **Startseite:** zwei neue Karten („Dinge steuern“, „Offen für weitere Standards“ mit dem Hinweis, dass
  Matter und Google Home über Home Assistant laufen).

### 31.23 Tests (AP-31b)

`tests/gui/test_gui_control.py` (23): Moduswechsel, **laufende Zeit verweigert den Wechsel und der Umschalter springt zurück** (mit Code),
Zurückschalten, Editor ohne Verbindung (Hinweis) und mit ausgeschalteter Verbindung, Seite bekommt eine benannte Aktion und der Assistent geht
weiter (Bild zeigt den Namen), Speichern braucht einen Namen, ungültige Aktion wird gemeldet und nichts gespeichert, **Auswahlliste aus
„Entdecken“** und Ausprobieren (speichert nichts), Warnung bei nicht idempotenten Aktionen, bestehende Aktion anzeigen/entfernen
(Fortschritt zählt Aktionen), Hilfetexte, Live-Ansicht (Aktion benannt, Seite ohne Aktion, letzte Aktionen mit Ergebnis, Zeit-Würfel
unverändert), Geräte-Seite (Steuerungs-Würfel markiert, Zeit-Würfel behält die Tabelle), Statusleiste, Status-API, Startseite, ein
vollständig eingerichteter Steuerungs-Würfel gilt als eingerichtet, Verlaufssätze je Modus. Im Browser (Chromium) angesehen, mit
Test-Adapter und simuliertem Würfel.

### 31.24 Gesamtbild und Grenzen von AP-26 bis AP-31

Reihenfolge einer Drehung im Steuerungsmodus: Würfel (BLE) → Supervisor/Entprellung → `TrackingService.record_event` schreibt Ereignis **und**
Auftrag in einer Transaktion → `ActionDispatcher` (eigener Thread) → `IntegrationService.process_due` → Adapter → Ziel; das Ergebnis steht im
Verlauf. **Nicht geprüft:** echte Geräte, Hubs und Broker (nur lokale Testziele und Attrappen); ein echter TLS-Handshake mit der Hue-Anheftung und
mit MQTT-TLS; ein Dauerbetrieb. **Nicht vorhanden:** eigene Matter- oder Google-Home-Anbindung (über Home Assistant), Verschlüsselung der
Zugangsdaten, Sprachsteuerung, Aktionen mit mehreren Schritten oder Bedingungen, ein Ereignisstrom von den Zielen zurück.
