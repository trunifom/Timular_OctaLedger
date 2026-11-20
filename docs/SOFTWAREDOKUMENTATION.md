# Softwaredokumentation (Entwickler)

Diese Datei beschreibt Module, Schnittstellen und Entwurfsentscheidungen des
implementierten Codes. Die Zielarchitektur steht in [ARCHITEKTUR.md](ARCHITEKTUR.md),
die Anforderungen im [Pflichtenheft](PFLICHTENHEFT.md), die Arbeitsregeln in
[CLAUDE.md](../CLAUDE.md). Jedes Arbeitspaket (AP) ergänzt hier seinen Abschnitt.

## 1. Paketübersicht

```text
src/octaledger/
  core/            Querschnitt: Fehler, Logging, Einstellungen
  domain/          reine Regeln und Modelle (kein BLE/HTTP/SQL/Streamlit)
  application/     Anwendungsfälle
  infrastructure/  BLE, SQLite, Integrationen
  agent/           Hintergrundprozess
  api/             lokale HTTP-Schnittstelle
  dashboard_client/ HTTP-Client für das Dashboard
```

Abhängigkeitsrichtung: `domain` ← `application` ← `infrastructure`/`api`/`agent`.
`core` darf von allen Schichten genutzt werden, importiert aber selbst nichts aus ihnen.

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
Benutzerprofils (Pfad kommt mit AP-03). Ist der Ordner nicht beschreibbar, läuft das
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
  with storage.transaction() as repos:      # atomar: Commit bei Erfolg, Rollback bei Fehler
      repos.sessions.end(running.id, now)
      repos.sessions.add(next_session)
  with storage.read() as repos:             # nur lesen
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
`ScanResult(address, name, rssi, service_uuids, is_candidate, label)`. Er verbindet **nie**
selbstständig (Testplan: „niemals automatisch unbekannte Geräte verbinden“).

- Geräte, die den Orientierungsdienst bewerben, sind **Kandidaten** und stehen zuerst, danach
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
{ "format": "octaledger-backup", "schema_version": 1, "app_version": "...",
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
| `POST /devices/{id}/activate` | ausdrückliche Übergabe an diesen Tracker |
| `POST /devices/{id}/connect`, `/disconnect`, `/address` | Verbindung starten/stoppen, gefundene Adresse speichern (Adresse wird **nie** zurückgegeben, nur `has_address`) |
| `POST /scan` | BLE-Suche (nur auf Anforderung) |
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
`remove_device`, `assign_face`, `clear_face`, `observed_face`, `activate_device`,
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

## 22. Seiten „Geräte“ und „Verwaltung“ (`dashboard.pages.devices`, `dashboard.pages.catalog`, AP-18b)

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

## 23. Seiten „Zeitjournal“ und „Statistik“ (`dashboard.pages.journal`, `dashboard.pages.statistics`, AP-18c)

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
