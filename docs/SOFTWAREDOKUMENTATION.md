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
