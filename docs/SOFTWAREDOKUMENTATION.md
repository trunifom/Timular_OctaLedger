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
