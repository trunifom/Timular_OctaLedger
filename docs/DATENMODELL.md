# OctaLedger – Datenmodell, Dateien und Sicherungsformat

Dieses Dokument beschreibt, **was OctaLedger speichert und wo**: die Dateien im Benutzerprofil, jede Tabelle der SQLite-Datenbank
(Migrationen `0001`–`0008`), die Regeln, die die Datenbank selbst durchsetzt, die Zeitkodierung, das Format der JSON-Sicherung und
die CSV-Spalten. Begriffe erklärt das [Glossar](GLOSSAR.md); den Zusammenhang der Bausteine die [Architektur](ARCHITEKTUR.md).

**Inhalt**

1. [Dateien und Ordner](#1-dateien-und-ordner)
2. [Überblick der Tabellen](#2-überblick-der-tabellen)
3. [Tabellen im Detail](#3-tabellen-im-detail)
4. [Regeln, die die Datenbank selbst durchsetzt](#4-regeln-die-die-datenbank-selbst-durchsetzt)
5. [Zeit und Zeitzonen](#5-zeit-und-zeitzonen)
6. [Migrationen](#6-migrationen)
7. [Das Sicherungsformat (JSON, Schema 3)](#7-das-sicherungsformat-json-schema-3)
8. [CSV-Export](#8-csv-export)
9. [Aufbewahrung und Löschen](#9-aufbewahrung-und-löschen)
10. [Was nicht in der Datenbank steht](#10-was-nicht-in-der-datenbank-steht)

---

## 1. Dateien und Ordner

Alles liegt im **Benutzerprofil**, nie im Projektordner. Den Ort zeigt `octaledger paths`; ein anderer Ort wird mit `--data-dir` oder der
Umgebungsvariable `OCTALEDGER_DATA_DIR` gewählt. Unter Windows ist der Standard ein Ordner unter `%LOCALAPPDATA%`
(über `platformdirs` ermittelt).

```text
<Datenordner>/
  api_token                    Anmelde-Token der lokalen API (zufällig, 256 Bit)
  secrets.json                 Zugangsdaten der Verbindungen (Passwörter, Token) – nicht verschlüsselt
  settings.toml                Einstellungen
  data/octaledger.sqlite3      die Datenbank (WAL-Modus: zusätzlich -wal und -shm während des Betriebs)
  logs/                        rotierende Protokolldateien (Zugangsdaten geschwärzt)
  backups/                     JSON-Sicherungen, Kopien vor Migration/Wiederherstellung
  exports/                     CSV-Exporte
```

Alle Dateien werden **atomar** geschrieben (erst temporäre Datei, dann umbenennen), damit ein Absturz nie eine halbe Datei hinterlässt.

## 2. Überblick der Tabellen

```text
devices ──< face_mappings >── activities
   │                    └───── projects
   ├──< face_actions >── integrations ──< integration_jobs
   ├──< raw_events
   └──< sessions >── activities / projects
            └──< corrections
audit_log      app_state     (allein stehend)
```

| Tabelle | Zweck | Migration |
|---|---|---|
| `devices` | Würfel: Alias, Bluetooth-Kennung, Modell, Firmware, **Modus** | 0001, Modus 0003 |
| `activities`, `projects` | Tätigkeiten und Projekte (Name, Farbe, archiviert) | 0001 |
| `face_mappings` | Zeiterfassung: welche Seite welcher Tätigkeit/welchem Projekt entspricht | 0001 |
| `raw_events` | jede Beobachtung eines Würfels (Rohwert), unverändert | 0001 |
| `sessions` | die erfassten Zeitabschnitte | 0001 |
| `corrections` | Prüfspur jeder Änderung einer Sitzung | 0001 |
| `audit_log` | Löschungen, Bereinigungen, Wiederherstellungen | 0001 |
| `app_state` | kleiner dauerhafter Zustand (aktiver Würfel, Pause) | 0002 |
| `integrations` | **Steuerungsmodus:** Verbindungen (Art, Name, Einstellungen ohne Geheimnisse) | 0003 |
| `face_actions` | **Steuerungsmodus:** welche Aktion eine Seite auslöst (ab 0008: der **erste Schritt** der Kette, als Spiegel) | 0003 |
| `face_action_steps` | **Steuerungsmodus:** alle Schritte der Kette einer Seite (Verzögerung, bei Fehler weitermachen, aktiv, Bedingung) | 0008 |
| `integration_jobs` | **Steuerungsmodus:** Warteschlange („Outbox“) und Verlauf | 0003 |
| `device_buttons` | welche Aktion ein kurzer/langer Tastendruck des Würfels auslöst (keine Zeile = nichts) | 0005 |
| `tags`, `session_tags`, `activity_tags`, `activity_notes` | Tags, Tags je Eintrag, Standard-Tags und Notizvorlage je Tätigkeit | 0007 |
| `project_billing` | Budget (Minuten), Stundensatz (Rappen/Cent), abrechenbar je Projekt | 0007 |
| `work_schedule` | Soll je Wochentag in Minuten, versioniert nach Gültig-ab-Datum | 0006 |
| `absences` | Ferien, Krankheit, eigene Feiertage (ein Zeitraum, optional abweichendes Tagessoll) | 0006 |
| `attention_items` | **Rückfragen-Zentrale:** Fragen, die auf eine Entscheidung warten (Lücke nach Verbindungsverlust …) | 0004 |

## 3. Tabellen im Detail

Zeitfelder sind Texte im Format `YYYY-MM-DDTHH:MM:SS.ffffffZ` (UTC, siehe Abschnitt 5). `CHECK` bedeutet: Die Datenbank lehnt andere Werte ab.

### `devices`

| Spalte | Typ | Bedeutung |
|---|---|---|
| `id` | TEXT, Primärschlüssel | interne UUID (nicht die Bluetooth-Adresse) |
| `alias` | TEXT | Name (1–100 Zeichen), **eindeutig** ohne Beachtung der Schreibweise |
| `platform_address` | TEXT, optional | Bluetooth-Kennung auf diesem Rechner (keine global stabile MAC!) |
| `model`, `firmware` | TEXT, optional | aus dem Würfel gelesen |
| `created_at` | TEXT | Anlegezeit |
| `mode` | TEXT | `time` (Standard) oder `control` – siehe Migration 0003 |

### `activities` / `projects`

`id`, `name` (1–100), `color` (`#RRGGBB`, Großbuchstaben), `archived` (0/1). Der Name ist **unter den nicht archivierten Einträgen eindeutig**
(ohne Beachtung der Schreibweise); archivierte Einträge geben ihren Namen frei. Benutzte Einträge lassen sich nicht löschen
(`ON DELETE RESTRICT`), nur archivieren.

### `face_mappings`

Primärschlüssel `(device_id, face)`; `face` 1–8; `activity_id` und `project_id` optional (`RESTRICT`); `revision` ≥ 1 zählt Änderungen.
Wird ein Würfel gelöscht, verschwinden seine Zuordnungen (`CASCADE`). Gilt nur im Modus `time`.

### `raw_events`

Jede Beobachtung, **bevor** etwas daraus folgt: `id`, `device_id`, `kind` (`baseline`, `face_change`, `neutral`, `disconnect`, `reconnect`, `invalid`),
`raw_value` (0–8 oder leer), `sequence`, `connection_id` (welcher Verbindungszyklus), `received_at`, `detail`. Index auf `(device_id, received_at)`.
Rohereignisse bleiben bei Korrekturen **unverändert** – sie sind der Beleg.

### `sessions`

| Spalte | Bedeutung |
|---|---|
| `id` | UUID |
| `activity_id` | Pflicht (`RESTRICT`) |
| `project_id`, `device_id` | optional |
| `started_at`, `ended_at` | Beginn/Ende; `ended_at` leer = läuft noch |
| `source` | `device` (vom Würfel) oder `manual` (von Hand) |
| `quality` | `confirmed` oder `uncertain` (Teil der Zeit unbekannt, z. B. Verbindungsabbruch; Anwender soll bestätigen) |
| `note` | freier Text |
| `revision` | ≥ 1, steigt mit jeder Korrektur |

### `corrections`

Prüfspur: `session_id` (`CASCADE`), `field_name`, `old_value`, `new_value`, `reason` (Pflicht, nicht leer), `revision` (≥ 2), `corrected_at`.

### `audit_log`

`at`, `action` (z. B. `purge`, `restore`, `delete`), `entity`, `entity_id`, `detail`. Wird nur ergänzt, nie geändert.

### `app_state`

Schlüssel/Wert (`key` 1–100 Zeichen, `value` Text, meist JSON, `updated_at`): u. a. **der aktive Würfel** und **ob pausiert ist**. Überlebt Neustarts.

Zusätzlich je Würfel ein Schlüssel `link_lost:<device_id>` (JSON `{at, stopped, session}`): Die Verbindung riss um `at`; `stopped` zeigt, ob die Frist schon abgelaufen und der Eintrag beendet ist. Der Schlüssel verschwindet bei Rückkehr in der Frist, nach einer Handlung des Anwenders oder wenn der Würfel nach der Frist zurückkommt; er überlebt einen Neustart des Agenten.

### Tags und Abrechnung (0007)

`tags(id, name [eindeutig, ohne Groß-/Kleinschreibung], color)`, `session_tags(session_id, tag_id)` (löscht sich mit Eintrag oder Tag), `activity_tags(activity_id, tag_id)`, `activity_notes(activity_id, template ≤ 500 Zeichen)`, `project_billing(project_id, budget_minutes, hourly_rate_cents, billable)`. **Geld steht nie in den Einträgen**: Der Betrag wird im Bericht aus Minuten und Satz berechnet und dort gerundet. Alle fünf Tabellen sind Teil der Sicherung (Schema 3, `tables`).

### `work_schedule` und `absences` (0006)

`work_schedule`: `valid_from` (lokales Datum, Schlüssel), `mon_minutes` … `sun_minutes` (0–1440). Eine neue Version ändert frühere Tage nicht. `absences`: `id`, `start_date`, `end_date` (einschließlich, lokale Daten), `kind` (`vacation`, `sick`, `holiday_custom`, `other`), `target_minutes` (leer = 0), `note`. Beide Tabellen sind Teil der Sicherung (Schema 3, Abschnitt `tables`).

### `device_buttons` (0005)

`device_id` (löscht sich mit dem Würfel), `press` (`short`/`long`), `action` (`pause_resume`, `stop`, `start_last`). Ohne Zeile geschieht beim Druck nichts. Teil der Sicherung ab Schema 3 (Abschnitt `tables`). Migration 0005 baut außerdem `raw_events` neu auf, damit die Ereignisart `button` erlaubt ist; alle Zeilen werden unverändert übernommen.

### `attention_items` (0004)

`id`, `kind` (`gap`, `idle`, `auto_stop`, `reminder`, `break_hint`), `created_at`, `session_id` (löscht die Frage mit dem Eintrag), `payload` (JSON, nie Geheimnisse), `status` (`open`, `resolved`, `dismissed`, `expired`), `resolved_at`, `resolution`. Laufzeitdaten: **nicht** in der Sicherung. Eine Frage ändert nie von selbst Zeitdaten; offene Fragen verfallen nach 30 Tagen zu `expired`.

### `integrations` (0003)

| Spalte | Bedeutung |
|---|---|
| `id` | UUID |
| `kind` | Art der Verbindung (`webhook`, `mqtt`, `homeassistant`, `hue`) |
| `name` | 1–100 Zeichen, **eindeutig** (ohne Beachtung der Schreibweise) |
| `config` | JSON der Einstellungen – **ohne Geheimnisse** (diese liegen in `secrets.json`) |
| `enabled` | 0/1 |
| `created_at` | Anlegezeit |

### `face_action_steps` (0008)

`(device_id, face, position)` ist der Schlüssel; `position` 0 ist der erste Schritt. Spalten: `integration_id`, `label`, `params` (JSON), `delay_ms` (0–300000), `continue_on_error`, `enabled`, `condition` (JSON `{start, end, weekdays}` oder leer). Die Migration kopiert jede vorhandene Aktion als Schritt 0. `face_actions` bleibt als Spiegel von Schritt 0 bestehen: Ältere Sicherungen und Daten ohne Schrittzeile funktionieren weiter (eine Seite ohne Schritte nutzt ihre `face_actions`-Zeile als einzigen Schritt). `integration_jobs` hat dazu die Spalten `chain_id` (die auslösende Drehung), `step` und `continue_on_error`. Die Schritte sind Teil der Sicherung (Schema 3, `tables`).

### `face_actions` (0003)

Primärschlüssel `(device_id, face)`; `integration_id` (`RESTRICT`: eine **benutzte Verbindung lässt sich nicht löschen**), `label` (1–100, erscheint in der
Live-Ansicht), `params` (JSON, vom Adapter geprüft), `revision`. Wird der Würfel gelöscht, verschwinden seine Aktionen (`CASCADE`).

### `integration_jobs` (0003)

Die Warteschlange und zugleich der Verlauf der gesendeten Aktionen:

| Spalte | Bedeutung |
|---|---|
| `id` | UUID |
| `idempotency_key` | **eindeutig**; = ID des auslösenden Rohereignisses → derselbe Auslöser erzeugt nie zwei Aufträge |
| `integration_id` | Ziel (`CASCADE`) |
| `device_id`, `face` | Herkunft (bei gelöschtem Würfel leer) |
| `label`, `params` | Kopie der Aktion zum Zeitpunkt des Auslösens |
| `status` | `pending`, `done`, `failed`, `expired` |
| `attempts`, `last_error` | Versuche und letzter Fehlertext (ohne Geheimnisse) |
| `created_at`, `expires_at`, `next_attempt_at`, `finished_at` | Zeiten; `expires_at` = Erstellung + 30 s |

Indizes: `(status, next_attempt_at)` für „was ist fällig?“ und `(integration_id, status)` für die Begrenzung auf 50 wartende Aufträge je Verbindung.
Aufträge sind **Laufzeitdaten** und gehören nicht zur Sicherung.

## 4. Regeln, die die Datenbank selbst durchsetzt

Diese Regeln stehen in SQL, nicht nur im Code – ein Programmfehler kann sie nicht verletzen:

| Regel | Mittel |
|---|---|
| höchstens **eine laufende Sitzung** | eindeutiger Index `ux_sessions_single_running` auf Sitzungen ohne Ende |
| **keine überlappenden Sitzungen** | Trigger `trg_sessions_no_overlap_insert` und `…_update` |
| Ende nicht vor Beginn | `CHECK (ended_at IS NULL OR ended_at >= started_at)` |
| Würfel-Sitzungen haben einen Würfel | `CHECK (source <> 'device' OR device_id IS NOT NULL)` |
| Seiten nur 1–8, Rohwerte nur 0–8 | `CHECK`-Bedingungen |
| gültige Farben | `CHECK (color GLOB '#[0-9A-F]…')` |
| eindeutige Namen | Indizes mit `COLLATE NOCASE` |
| benutzte Dinge nicht löschbar | Fremdschlüssel mit `ON DELETE RESTRICT` |
| kein doppelter Auftrag | `UNIQUE (idempotency_key)` |

Fremdschlüssel sind eingeschaltet (`PRAGMA foreign_keys = ON`).

## 5. Zeit und Zeitzonen

* **Gespeichert wird immer UTC**, als Text `YYYY-MM-DDTHH:MM:SS.ffffffZ` (sortierbar, eindeutig). Es gibt keine „lokalen“ Zeiten in der Datenbank.
* **Angezeigt** wird in der Zeitzone aus den Einstellungen (Standard: die des Rechners). Sommerzeitumstellungen werden dabei korrekt behandelt; Tagesgrenzen werden
  im **lokalen** Kalender berechnet (ein Tag kann 23 oder 25 Stunden haben).
* **Sitzungen über Mitternacht** werden für Tages-Diagramme an der Grenze aufgeteilt, in der Datenbank bleibt es **eine** Sitzung.
* Berichte unterscheiden **Gerätezeit** (Summe aller Sitzungen) und **persönliche Zeit** (Vereinigung der Zeitintervalle): Überschneidungen würden sonst doppelt zählen.

## 6. Migrationen

Die Dateien liegen im Paket (`infrastructure/storage/migrations/NNNN_name.sql`), sind **lückenlos nummeriert** und werden als Package-Data ausgeliefert.
Jede läuft in **einer Transaktion** (kein `BEGIN`/`COMMIT` in der Datei). Vor einer Migration legt OctaLedger eine **Kopie der Datenbank** an.
Eine Datenbank, die neuer ist als das Programm, wird **nicht** angefasst (Fehler `OL-STORAGE-002`).

| Nr. | Datei | Inhalt |
|---|---|---|
| 0001 | `0001_initial.sql` | Grundschema: Geräte, Katalog, Zuordnungen, Rohereignisse, Sitzungen samt Regeln, Korrekturen, Auditspur |
| 0002 | `0002_app_state.sql` | `app_state` (aktiver Würfel, Pause) |
| 0008 | `0008_action_steps.sql` | `face_action_steps` (bestehende Aktionen werden Schritt 0), Spalten `chain_id`, `step`, `continue_on_error` bei `integration_jobs` |
| 0003 | `0003_integrations.sql` | Spalte `devices.mode` (bestehende Würfel bleiben `time`), `integrations`, `face_actions`, `integration_jobs` |

## 7. Das Sicherungsformat (JSON, Schema 3)

`octaledger backup` und die Seite **Daten** erzeugen eine JSON-Datei:

```json
{
  "format": "octaledger-backup",
  "schema_version": 3,
  "app_version": "0.1.0",
  "exported_at": "2026-11-21T08:30:00.000000Z",
  "counts": {"devices": 1, "sessions": 120, "…": 0},
  "checksum": "<SHA-256 über den Abschnitt data>",
  "data": {
    "devices": [], "activities": [], "projects": [], "face_mappings": [],
    "integrations": [], "face_actions": [],
    "raw_events": [], "sessions": [], "corrections": [], "audit_log": [],
    "app_state": {},
    "tables": {"device_buttons": [], "work_schedule": [], "absences": [], "tags": [], "session_tags": [], "activity_tags": [], "activity_notes": [], "project_billing": []}
  }
}
```

* **Schema 3** enthält zusätzlich den Abschnitt `tables` mit den einfachen Tabellen `device_buttons`, `work_schedule`, `absences`, `tags`, `session_tags`, `activity_tags`, `activity_notes` und `project_billing` (Spalten und Reihenfolge: `SIMPLE_TABLES` in `repositories.py`; beim Wiederherstellen prüft die Datenbank selbst jede Zeile, ein Fehler bricht alles ab). Ältere Dateien bleiben lesbar.
* **Schema 2** enthält zusätzlich `integrations` und `face_actions`; **Schema 1** (ohne Steuerungsmodus) bleibt lesbar – fehlende Abschnitte gelten als leer.
* **Nicht enthalten:** `secrets.json` (Zugangsdaten) und `integration_jobs` (Laufzeitdaten). Nach einer Wiederherstellung auf einem anderen Rechner trägt man
  die Zugangsdaten der Verbindungen neu ein – eine bewusste Abwägung, damit eine Sicherung gefahrlos aufbewahrt werden kann.
* **Prüfung vor dem Einspielen** (`POST /restore/inspect`, ändert nichts): Format, Version, Prüfsumme, jedes Feld jedes Datensatzes (genau die erwarteten
  Felder – nicht mehr, nicht weniger), Eindeutigkeit und Verweise. Erst danach folgt `POST /restore`.
* **Einspielen:** automatische Sicherung des bisherigen Stands, dann Ersetzen in **einer Transaktion**; bei jedem Fehler bleibt der alte Stand unverändert.
* Nichts in einer Sicherung wird ausgeführt oder als Dateipfad benutzt.

## 8. CSV-Export

UTF-8 **mit BOM** (öffnet sich in Excel korrekt), Trennzeichen `;` (wählbar: `,` oder Tabulator), eine Zeile je Sitzung. Spalten:

`session_id`, `started_local`, `ended_local`, `started_utc`, `ended_utc`, `duration_seconds`, `duration_hms`, `running`, `activity`, `project`,
`device`, `source`, `quality`, `revision`, `note`, `tags` (Namen, mit Komma getrennt), `billable` (`yes`/`no`), `amount` (Betrag aus Minuten × Satz, auf zwei Stellen gerundet, leer ohne Satz).

Texte, die mit `=`, `+`, `-`, `@` oder einem Steuerzeichen beginnen, erhalten ein vorangestelltes `'` – so kann eine Zelle in Excel **nie als Formel**
ausgeführt werden (Schutz vor Formel-Injektion). Dateinamen erzeugt das Programm; sie bleiben im Ordner `exports/`.

## 9. Aufbewahrung und Löschen

* Rohereignisse und Sitzungen bleiben, bis der Anwender sie löscht. Eine ausdrückliche Bereinigung alter Rohereignisse (`delete_older_than`) wird in der
  Auditspur festgehalten.
* Das **Löschen einer Sitzung** verlangt eine Begründung und wird protokolliert.
* Erledigte **Aufträge** des Steuerungsmodus werden **7 Tage** für den Verlauf aufbewahrt, dann entfernt.
* Ein Würfel **mit erfassten Daten** lässt sich nicht entfernen; eine **benutzte** Tätigkeit oder ein benutztes Projekt wird archiviert statt gelöscht.

## 10. Was nicht in der Datenbank steht

| Was | Wo | Warum |
|---|---|---|
| Zugangsdaten der Verbindungen | `secrets.json` | getrennt halten; Sicherungen und Datenbank bleiben weitergebbar |
| API-Token | `api_token` | gehört zum Prozess, nicht zu den Daten |
| Einstellungen | `settings.toml` | von Hand les- und änderbar, atomar geschrieben |
| Protokolle | `logs/` | rotierend, geschwärzt |
