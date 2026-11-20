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
