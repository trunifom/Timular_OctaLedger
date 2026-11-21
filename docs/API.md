# OctaLedger – Referenz der lokalen Schnittstelle (REST-API)

Diese Seite beschreibt **jeden Endpunkt** der lokalen API, die der Agent bereitstellt und über die das Dashboard (und jedes
eigene Skript) mit OctaLedger spricht. Sie ist die Referenz für Entwickler; Anwender brauchen sie nicht.

**Inhalt**

1. [Grundlagen](#1-grundlagen)
2. [Anmeldung und Schutzmaßnahmen](#2-anmeldung-und-schutzmaßnahmen)
3. [Fehlerformat und Statuscodes](#3-fehlerformat-und-statuscodes)
4. [Zeit- und Datenformate](#4-zeit--und-datenformate)
5. [Übersicht und Gesundheit](#5-übersicht-und-gesundheit)
6. [Geräte (Würfel)](#6-geräte-würfel)
7. [Steuerungsmodus: Verbindungen und Aktionen](#7-steuerungsmodus-verbindungen-und-aktionen)
8. [Aktivitäten und Projekte](#8-aktivitäten-und-projekte)
9. [Zeiterfassung und Sitzungen](#9-zeiterfassung-und-sitzungen)
10. [Berichte](#10-berichte)
11. [Export, Sicherung, Wiederherstellung](#11-export-sicherung-wiederherstellung)
12. [Einstellungen und Diagnose](#12-einstellungen-und-diagnose)
13. [Beispiele](#13-beispiele)
14. [Der Python-Client des Dashboards](#14-der-python-client-des-dashboards)
15. [Versionierung](#15-versionierung)

---

## 1. Grundlagen

| Eigenschaft | Wert |
|---|---|
| Basisadresse | `http://127.0.0.1:<Port>/api/v1` (Standardport **8765**, einstellbar über `--port` oder `OCTALEDGER_PORT`) |
| Erreichbarkeit | **nur auf dem eigenen Rechner** (`127.0.0.1`); der Server bindet nie an eine Netzwerkkarte |
| Format | JSON (`Content-Type: application/json`), Zeichensatz UTF-8 |
| Größtes Anfragevolumen | 64 MiB (nur die Wiederherstellung einer Sicherung ist so groß), sonst Antwort **413** |
| Antwort-Kopfzeilen | `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` |
| Automatische Dokumentation | **bewusst abgeschaltet** (`/docs`, `/redoc`, `/openapi.json` gibt es nicht): Diese Datei ist die Referenz |

Alle Endpunkte liegen unter dem Präfix `/api/v1`, **außer** `GET /api/v1/health` – er ist der einzige ohne Anmeldung.
Die Tabellen unten nennen den Pfad **relativ zu diesem Präfix**.

Die Schnittstelle ist eine **dünne Schicht** über den Diensten der Anwendungsschicht (siehe `ARCHITEKTUR.md`): Sie prüft Eingaben,
ruft genau einen Dienst auf und übersetzt Ergebnis oder Fehler. Geschäftsregeln stehen nicht hier.

## 2. Anmeldung und Schutzmaßnahmen

Weil jede Webseite im Browser Anfragen an `127.0.0.1` auslösen kann (CSRF, „DNS-Rebinding“), schützt OctaLedger die API
mehrfach. Jede Anfrage durchläuft diese Prüfungen **in dieser Reihenfolge**:

1. **Host-Kopfzeile:** muss `127.0.0.1`, `localhost` oder `[::1]` **mit genau dem API-Port** nennen; sonst **403** (`OL-API-003`).
2. **Origin-Kopfzeile:** fehlt sie (Skripte, der Server des Dashboards), ist das in Ordnung; nennt sie eine fremde Seite oder `null`, gibt es **403**.
3. **Größe:** `Content-Length` über 64 MiB → **413**.
4. **Token:** Kopfzeile `Authorization: Bearer <Token>` (außer `/health`). Fehlt sie oder ist sie falsch, antwortet die API mit **401**
   (`OL-API-001`) – die Meldung verrät nicht, *was* falsch war. Der Vergleich geschieht in konstanter Zeit (`hmac.compare_digest`).

Das **Token** ist ein zufälliges Geheimnis (256 Bit). Der Agent erzeugt es **einmal** und legt es als Datei `api_token` im Datenordner ab
(oder übernimmt `OCTALEDGER_API_TOKEN`, mindestens 32 Zeichen); es reist nur in der Kopfzeile – **nie in einer Adresse**, nie im Protokoll.
Das Dashboard (`octaledger dashboard`) liest dieselbe Datei. Wer die API selbst anspricht, nimmt den Inhalt dieser Datei (Ort: `octaledger paths`).

Zusätzlich gilt: Es gibt **keine** CORS-Freigabe, **keine** Weiterleitungen und **keinen** Endpunkt, der Dateien auf dem Rechner liest oder
schreibt, deren Name vom Aufrufer kommt (Export und Sicherung schreiben in feste Ordner des Datenverzeichnisses).

## 3. Fehlerformat und Statuscodes

Jeder Fehler hat denselben Aufbau:

```json
{
  "error": {
    "code": "OL-STATE-001",
    "message": "Die Aktivität wurde nicht gefunden.",
    "technical_message": "Activity 'abc' not found",
    "details": {}
  }
}
```

* `code` – stabiler, maschinenlesbarer Fehlercode (siehe Tabelle),
* `message` – **deutscher Text für Anwender**, kann direkt angezeigt werden,
* `technical_message` – englischer Text für Entwickler und Protokoll,
* `details` – zusätzliche Angaben (z. B. bei 422 die betroffenen Felder unter `fields`).

| Status | Bedeutung | Fehlercodes |
|---|---|---|
| 200 / 201 / 204 | Erfolg (201 = angelegt, 204 = ohne Inhalt) | – |
| 401 | Token fehlt oder ist falsch | `OL-API-001` |
| 403 | fremder Host/Origin | `OL-API-003` |
| 404 | Objekt gibt es nicht | `OL-STATE-001` |
| 409 | Konflikt oder unzulässiger Zustand (z. B. Name doppelt, Verbindung noch benutzt, Sitzung läuft schon) | `OL-STATE-002`, `OL-STATE-003` |
| 413 | Anfrage zu groß | `OL-VALID-001` |
| 422 | ungültige Eingabe, ungültige Einstellung, falsche Sicherungsdatei, nicht unterstützter Würfel | `OL-VALID-001`, `OL-CONFIG-001`, `OL-DATA-002`, `OL-BLE-001`, `OL-BLE-003` |
| 500 | Datenbank beschädigt oder unerwarteter Fehler (ohne Innenleben in der Antwort) | `OL-STORAGE-003`, `OL-GENERIC-000` |
| 502 | **ein Gegenüber hat versagt**: Bluetooth-Verbindung oder eine Anbindung (Webhook, MQTT, Home Assistant, Hue) | `OL-BLE-002`, `OL-INTEG-001`, `OL-INTEG-002` |
| 503 | Dienst in diesem Prozess nicht vorhanden (API ohne Agent bzw. ohne Steuerungsmodus) | `OL-API-002` |

Die Eingabe wird **streng** geprüft: Unbekannte Felder in einer Anfrage führen zu **422** (so fallen Tippfehler auf). Die Fehlerliste enthält bei
422 die Feldnamen und deutsche Hinweise.

## 4. Zeit- und Datenformate

* **Zeitstempel** sind ISO-8601 mit Zeitzone, in Antworten stets **UTC** (`2026-11-21T08:30:00+00:00`). Eingaben **müssen** eine Zeitzone enthalten (`…Z` oder `+01:00`); Zeiten ohne Zeitzone
  werden mit **422** abgelehnt, statt sie still zu raten. Das Dashboard rechnet für die Anzeige in die eingestellte Zeitzone um.
* **Dauern** sind ganze **Sekunden** (`*_seconds`).
* **IDs** sind Texte (UUID); **Seiten** sind Zahlen 1–8.
* **Farben** sind `#rrggbb`.
* **Tage** (`day`) sind `YYYY-MM-DD` im Kalender der angegebenen Zeitzone (`tz`, Standard: die eingestellte Anzeigezeitzone).

## 5. Übersicht und Gesundheit

| Methode und Pfad | Zweck | Antwort |
|---|---|---|
| `GET /health` | Lebenszeichen, **ohne Token** | `{"status":"ok","api_version":1,"version":"…"}` |
| `GET /status` | Übersicht: laufende Sitzung, Geräte mit Modus und Live-Zustand | siehe unten |

`GET /status` liefert:

```json
{
  "tracking": {
    "running": {"id": "…", "activity_id": "…", "started_at": "…", "running": true, "duration_seconds": 1234, "…": "…"},
    "activity": {"id": "…", "name": "Entwicklung", "color": "#3b82f6", "archived": false},
    "project": null,
    "elapsed_seconds": 1234,
    "paused": false,
    "active_device_id": "…",
    "uncertain_count": 0
  },
  "devices": [{"id": "…", "alias": "Würfel", "is_active": true, "mode": "time", "live": {"state": "connected", "…": "…"}}],
  "agent_running": true,
  "server_time": "2026-11-21T08:30:00+00:00"
}
```

## 6. Geräte (Würfel)

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `GET /devices` | alle Würfel mit Belegung und Live-Zustand | – | Liste von **Gerät** |
| `POST /devices` | Würfel anlegen (der erste wird „aktiv“) | `{"alias", "platform_address"?}` | **Gerät**, 201 |
| `PATCH /devices/{id}` | umbenennen | `{"alias"}` | **Gerät** |
| `DELETE /devices/{id}` | entfernen (nur ohne erfasste Daten, sonst 409) | – | 204 |
| `PUT /devices/{id}/faces/{1..8}` | Seite einer Aktivität (und Projekt) zuordnen | `{"activity_id"?, "project_id"?}` | **Gerät** |
| `DELETE /devices/{id}/faces/{1..8}` | Zuordnung einer Seite löschen | – | **Gerät** |
| `GET /devices/{id}/observed-face` | zuletzt gesehene Seite (für das geführte Zuordnen) | – | `{"face", "received_at", "kind"}` oder `{"face": null}` |
| `GET /devices/{id}/live` | Live-Ansicht: Position, Entprellung, Bewegungen, Wirkung | – | siehe unten |
| `GET /devices/{id}/buttons` | Aktionen der Würfeltaste (kurz/lang) | – | `{"buttons": {"short": …\|null, "long": …\|null}}` |
| `PUT /devices/{id}/buttons/{short\|long}` | Aktion einer Tastenart festlegen (`pause_resume`, `stop`, `start_last`) oder mit `none` löschen | `{"action"}` | wie oben; 422 bei unbekannter Taste/Aktion |
| `PUT /devices/{id}/mode` | Modus umschalten: `time` oder `control` | `{"mode"}` | **Gerät** |
| `POST /devices/{id}/activate` | Übergabe: diesen Würfel zum aktiven machen | – | `{"ended_session": …\|null}` |
| `POST /devices/{id}/connect` | Bluetooth-Verbindung starten (Adresse nötig) | – | `{"started": true}` |
| `POST /devices/{id}/disconnect` | Verbindung absichtlich beenden (kein Wiederverbinden) | – | `{"stopped": true}` |
| `POST /devices/{id}/unpair` | Koppeln aufheben: Verbindung beenden und Bluetooth-Adresse vergessen; Würfel und Daten bleiben | – | **Gerät** |
| `POST /devices/{id}/remove` | Würfel entfernen; `delete_data=true` löscht auch alles, was mit ihm erfasst wurde (nach automatischer Sicherung) | `{"delete_data"?: false}` | `{"sessions","raw_events","safety_backup"}` |
| `POST /devices/{id}/address` | Adresse aus einer Suche speichern | `{"platform_address"}` | **Gerät** |
| `POST /scan` | Bluetooth-Suche (nur auf Anforderung, verbindet nie selbst) | `{"seconds"?: 5.0}` | Liste von Treffern |

`connect`, `disconnect` und `scan` brauchen den BLE-Agenten; läuft die API ohne ihn, antworten sie mit **503**.

**Moduswechsel (`PUT /devices/{id}/mode`):** Läuft gerade eine **vom Würfel erzeugte** Sitzung dieses Würfels, antwortet die API mit **409** (zuerst beenden). Ist der Würfel der aktive
Tracker und wird auf `control` gestellt, geht die Rolle „aktiv“ an einen anderen Zeit-Würfel über (oder an keinen); ein Steuerungs-Würfel kann nicht per `activate` aktiv werden. Das Setzen des
bereits gültigen Modus ist harmlos. Zurück auf `time` macht den Würfel zum aktiven Tracker, wenn keiner aktiv ist.

**Gerät** (Antwort von fast allen Geräte-Endpunkten):

```json
{
  "id": "…", "alias": "Würfel", "has_address": true, "model": "ZEI", "firmware": "…",
  "created_at": "…", "is_active": true,
  "mode": "time",
  "configured_faces": 3, "fully_calibrated": false,
  "faces":   {"1": {"activity_id": "…", "project_id": null, "revision": 1}},
  "actions": {"2": {"integration_id": "…", "label": "Licht an", "params": {"…": "…"}}},
  "status": {"state": "connected", "connection_id": 1, "attempt": 0, "last_error": null,
             "last_value": 3, "last_event_at": "…", "battery_percent": 87,
             "dropped_values": 0, "duplicates_ignored": 2}
}
```

`status` ist `null`, solange der Würfel in diesem Agentenlauf nie gestartet wurde. Mögliche `state`-Werte (Zustandsautomat, siehe `ARCHITEKTUR.md`): `idle`, `scanning`, `connecting`, `discovering`, `subscribing`,
`baseline`, `ready`, `disconnected`, `reconnect_wait`, `stopped`.

**Live-Ansicht** (`GET /devices/{id}/live`): `raw_value` (zuletzt Gesehenes), `committed_value` (nach Entprellung übernommen),
`pending_value` (wartet noch auf Ablauf der Entprellzeit `debounce_ms`), `battery_percent`, `mode`, `faces` (je Seite
Aktivität/Projekt **oder** `action.label` im Steuerungsmodus) und `recent` (die letzten Bewegungen mit ihrer Wirkung – gestartet, beendet,
Aktion gesendet, ignoriert, …).

## 7. Steuerungsmodus: Verbindungen und Aktionen

Diese Endpunkte antworten mit **503**, wenn der Prozess ohne Steuerungsmodus läuft (z. B. in Tests ohne Integrationsdienst).
**Geheimnisse** (Passwörter, Token, Schlüssel) werden angenommen, in den getrennten Geheimnisspeicher geschrieben und **nie** wieder ausgegeben: Antworten nennen nur
die *Namen* gesetzter Geheimnisse (`secrets_set`).

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `PUT /devices/{id}/actions/{1..8}` | Seite im Steuerungsmodus eine Aktion **oder eine Kette von Schritten** geben (vom Adapter geprüft; die Einzelform setzt die Kette auf einen Schritt zurück) | `{"integration_id", "label", "params"}` **oder** `{"steps": [{"integration_id", "label", "params", "delay_ms"?, "continue_on_error"?, "enabled"?, "condition"?: {"start","end","weekdays"}}]}` (1 bis 10 Schritte, Verzögerungen zusammen ≤ 5 min) | **Gerät** |
| `GET /devices/{id}/chains` | die Schritte jeder Seite mit Aktion (eine einzelne Aktion = ein Schritt) | – | `{"1": [{position, integration_id, label, params, delay_ms, continue_on_error, enabled, condition}], …}` |
| `DELETE /devices/{id}/actions/{1..8}` | Aktion einer Seite entfernen | – | **Gerät** |
| `GET /adapters` | die Arten von Verbindung samt Formularbeschreibung | – | Liste von **Adapter** |
| `GET /integrations` | alle Verbindungen | – | Liste von **Verbindung** |
| `POST /integrations` | Verbindung anlegen | `{"kind", "name", "values"}` | **Verbindung**, 201 |
| `PATCH /integrations/{id}` | Name, Einstellungen, Geheimnisse (leer = behalten), Aktivierung ändern | `{"name"?, "values"?, "enabled"?}` | **Verbindung** |
| `DELETE /integrations/{id}` | löschen (409, solange eine Seite sie nutzt) | – | 204 |
| `POST /integrations/{id}/check` | Verbindung testen, ohne Nebenwirkung | – | `{"message"}` |
| `POST /integrations/{id}/probe` | eine Aktion **jetzt** ausprobieren | `{"params"}` | `{"message"}` |
| `POST /integrations/{id}/pair` | einmalige Kopplung (z. B. Hue-Bridge-Taste) | – | `{"message"}` |
| `POST /adapters/{kind}/find` | das Zielgerät im Netz suchen (z. B. Hue Bridge); `online` fragt zusätzlich einen Internetdienst (nur auf ausdrücklichen Wunsch) | `{"online": false}` | `{"items": [{id, address, name}]}`; 422, wenn die Art keine Suche kann |
| `POST /integrations/{id}/discover` | Lampen, Szenen, Geräte zur Auswahl auflisten | – | `{"items": […]}` |
| `GET /jobs?limit=50` | Verlauf der gesendeten Aktionen, neueste zuerst (1–200) | – | Liste von **Auftrag** |

`check`, `probe`, `pair` und `discover` sind **POST**, weil sie das Netzwerk berühren. Schlägt das Gegenüber fehl, antwortet die API mit **502**
und dem Code `OL-INTEG-001` (oder `OL-INTEG-002`, wenn die Anfrage **sicher nicht angekommen** ist – nur dann wiederholt der Versand von selbst).

**Adapter:** `{kind, title, description, config_fields[], actions[], can_pair, pair_help, can_discover}`. Ein *Feld* hat
`{name, label, kind, required, help, default, placeholder, choices[], minimum, maximum, choices_from[]}`; `kind` ist einer von `text`,
`password` (Geheimnis), `int`, `bool`, `choice`; `choices_from` nennt die Felder, aus denen `discover` Auswahllisten füllt.
Eine *Aktion* hat `{id, label, description, idempotent, fields[]}`. Aus dieser Beschreibung erzeugt das Dashboard seine Formulare
(`dashboard/forms.py`) – ein neuer Adapter braucht deshalb **keine** Änderung an der Oberfläche.

**Verbindung:** `{id, kind, name, config{}, enabled, secrets_set[], created_at}`.

**Auftrag:** `{id, integration, label, face, status, attempts, error, created_at, finished_at}`; `status` ist `pending`,
`done`, `failed` oder `expired` (nach 30 s nicht mehr gesendet – ein verspätetes „Licht an“ wäre überraschend).

## 8. Aktivitäten und Projekte

Aktivitäten und Projekte haben **dieselben fünf Endpunkte**; ersetzen Sie `{art}` durch `activities` oder `projects`.

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `GET /activities` · `GET /projects` | auflisten (`?include_archived=true` zeigt auch Archivierte) | – | Liste von `{id, name, color, archived}` |
| `POST /activities` · `POST /projects` | anlegen (Farbe wird automatisch gewählt, wenn sie fehlt) | `{"name", "color"?}` | Objekt, 201 |
| `PATCH /activities/{id}` · `PATCH /projects/{id}` | umbenennen/umfärben | `{"name"?, "color"?}` | Objekt |
| `POST /activities/{id}/archive` · `POST /projects/{id}/archive` | archivieren oder mit `archived=false` zurückholen | `{"archived"?: true}` | Objekt |
| `DELETE /activities/{id}` · `DELETE /projects/{id}` | löschen (nur wenn unbenutzt, sonst 409: archivieren) | – | 204 |

Namen sind unter den nicht archivierten Einträgen eindeutig (ohne Beachtung von Groß-/Kleinschreibung); ein doppelter Name ergibt **409**.

## 9. Zeiterfassung und Sitzungen

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `POST /tracking/start` | manuelle Sitzung jetzt starten | `{"activity_id", "project_id"?, "note"?}` | **Sitzung** |
| `POST /tracking/stop` | laufende Sitzung beenden | – | **Sitzung** |
| `POST /tracking/pause` | Pause: Sitzung beenden und Aktivität merken | – | **Sitzung** |
| `POST /tracking/resume` | gemerkte Aktivität fortsetzen | – | **Sitzung** |
| `GET /sessions?start=&end=` | Journal: ganze Sitzungen im Zeitfenster, neueste zuerst (+ Filter `device_id`, `activity_id`, `project_id`) | – | Liste von **Journalzeile** |
| `GET /sessions/uncertain` | Sitzungen, die auf Bestätigung warten | – | Liste von **Sitzung** |
| `POST /sessions` | nachträgliche, abgeschlossene Sitzung anlegen | `{"activity_id", "start", "end", "project_id"?, "note"?}` | **Sitzung**, 201 |
| `POST /sessions/{id}/correct` | korrigieren (mit Prüfspur) | `{"changes": {…}, "reason"}` | **Sitzung** |
| `POST /sessions/{id}/split` | in zwei Sitzungen teilen | `{"at", "reason"}` | Liste mit zwei **Sitzungen** |
| `POST /sessions/{id}/confirm` | unsichere Sitzung bestätigen | – | **Sitzung** |
| `POST /sessions/{id}/delete` | löschen (Begründung Pflicht, protokolliert) | `{"reason"}` | 204 |

**Sitzung:** `{id, activity_id, project_id, device_id, started_at, ended_at, running, duration_seconds, source, quality, note,
revision}`. `source` ist `device` oder `manual`; `quality` ist `confirmed` oder `uncertain`. Eine laufende Sitzung hat
`ended_at: null` und wird bis „jetzt“ gemessen.

`correct` erlaubt in `changes` u. a. `started_at`, `ended_at`, `activity_id`, `project_id`, `note`; Zeitfelder sind ISO-Texte. Jede
Korrektur schreibt Vorher/Nachher, Begründung und Zeitpunkt in die Prüfspur (siehe `DATENMODELL.md`).

**Journalzeile** = Sitzung plus `activity_name`, `project_name`, `device_alias`.

### Musik-Modus (AP-48)

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `PUT /devices/{id}/mode` | akzeptiert jetzt auch `music` (dritte Betriebsart) | `{"mode": "music"}` | **Gerät** |
| `GET /music/state` | für jeden Musik-Würfel: was spielt gerade (`null` = nichts) | – | `{devices: [{device_id, alias, playing: {face, label, integration_id, since}\|null, lost_since}]}` |
| `POST /music/parse` | einen eingefügten Link erkennen (ändert nichts) | `{"text"}` | `{kind, uri, description, ref}`; 422 mit Erklärung bei Unbekanntem |
| `GET /devices/{id}/music` | Verhalten des Würfels | – | `{base_action: stop\|pause, stop_delay_ms, default_volume}` |
| `PUT /devices/{id}/music` | Verhalten speichern | `{base_action, stop_delay_ms (0–60000), default_volume (0–100)}` | wie oben |
| `PUT /devices/{id}/music/faces/{1..8}` | einer Seite einen Titel aus einem Link geben (vom Adapter des Ziels geprüft) | `{"integration_id", "link", "label", "volume"?, "options"?: {"entity_id"}}` | `{steps, device}`; 422 bei unpassendem Ziel/Link, 409 wenn der Würfel nicht im Musik-Modus ist |

| `GET /music/browser-state` | gewünschter Zustand des Players in der App (AP-50), von der Seite „Musik-Player“ jede Sekunde gelesen | – | `{playing, video_id, list_id, volume, nonce}` |

Eine Seite **ohne** Titel ist eine „Stille-Seite“ (sie beendet die Musik). `GET /adapters` nennt je Art `music_capable`.

### Bericht und Kalender-Import (AP-42)

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `POST /reports/render` | druckbarer Bericht für lokale Tage (gleiche Summen wie die Statistik) | `{"first","last","format": "html"\|"pdf","tz"?}` | `{format, filename, content}`; `content` ist bei `pdf` base64; 422 bei anderem Format, 400/503 ohne Zusatzpaket `pdf` |
| `POST /import/ics/preview` | Termine einer Kalenderdatei als **Vorschläge** lesen (bucht nichts, speichert nichts) | `{"content": "<ICS-Text, ≤ 2 MiB>", "first","last","tz"?}` | `{proposals: [{index, start, end, title, overlaps}], skipped: {Grund: Anzahl}}` |
| `POST /import/ics/apply` | die bestätigten Termine buchen (alle oder keinen) | `{"entries": [{"start","end","activity_id","project_id"?,"note"?}]}` (≤ 200) | `{created}`, 201; 409 bei Überschneidung, 422 bei Zukunft/leer |

`GET /system/capabilities` nennt jetzt auch `pdf`, `ics` und `holidays`.

### Tags, Notizvorlagen, Budgets (AP-41)

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `GET /tags` | alle Tags | – | Liste `{id, name, color}` |
| `POST /tags` | Tag anlegen (Name eindeutig, ohne Groß-/Kleinschreibung; sonst 409) | `{"name", "color"?}` | Tag, 201 |
| `PUT /tags/{id}` | umbenennen/umfärben | `{"name"?, "color"?}` | Tag |
| `DELETE /tags/{id}` | Tag löschen (verschwindet überall, die Einträge bleiben) | – | 204 |
| `PUT /sessions/{id}/tags` | Tags eines Eintrags ersetzen (Prüfspur) | `{"tag_ids": []}` | Liste der Tags |
| `GET /activities/{id}/defaults` | Standard-Tags und Notizvorlage einer Tätigkeit | – | `{tags, note_template}` |
| `PUT /activities/{id}/defaults` | setzen (neue Einträge der Tätigkeit bekommen die Tags automatisch) | `{"tag_ids": [], "note_template"?}` | wie oben |
| `GET /projects/{id}/billing` | Budget, Stundensatz, abrechenbar | – | `{project_id, budget_minutes, hourly_rate_cents, billable}` |
| `PUT /projects/{id}/billing` | setzen (alles leer/false entfernt die Angaben) | `{"budget_minutes"?, "hourly_rate_cents"?, "billable"}` | wie oben; 422 bei ungültigen Werten |
| `GET /reports/budgets` | Zeit, Budgetanteil und Betrag je Projekt mit Angaben | – | Liste `{project_id, name, color, used_seconds, budget_minutes, fraction, hourly_rate_cents, amount_cents, billable}` |

`GET /sessions` und `GET /reports*`-Journalzeilen enthalten jetzt `tags`, `billable` und `amount_cents`; `GET /sessions` akzeptiert zusätzlich `tag_id`. Beträge werden **nur im Bericht berechnet** (Minuten × Satz, auf ganze Rappen/Cent gerundet), nie in den Einträgen gespeichert. Der CSV-Export hat die Spalten `tags`, `billable`, `amount` am Ende.

### Soll, Saldo, Abwesenheiten (AP-40)

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `GET /schedule` | Soll je Wochentag, eine Version je Gültig-ab-Datum | – | Liste `{valid_from, minutes: [Mo…So]}` |
| `PUT /schedule` | Version anlegen/ersetzen | `{"valid_from": "2026-01-01", "minutes": [480,480,480,480,480,0,0]}` | Liste; 422 bei ≠ 7 Werten oder Werten außerhalb 0–1440 |
| `DELETE /schedule/{valid_from}` | Version löschen | – | Liste |
| `GET /absences` | Abwesenheiten | – | Liste `{id, start, end, kind, target_minutes, note}` |
| `POST /absences` | Abwesenheit eintragen (`kind`: `vacation`, `sick`, `holiday_custom`, `other`; `target_minutes` leer = ganzer Tag frei) | `{"start","end","kind","target_minutes"?,"note"?}` | Abwesenheit, 201 |
| `DELETE /absences/{id}` | löschen | – | 204; 404 wenn unbekannt |
| `GET /reports/balance?first=&last=&tz=` | Soll, Ist, Differenz und laufender Saldo je lokalem Tag | – | `{has_schedule, includes_running, target_seconds, actual_seconds, difference_seconds, days: [{day, target_seconds, actual_seconds, difference_seconds, balance_seconds, reason}]}` |

Das Soll eines Tages: Abwesenheit (ihr Wert, sonst 0) vor Feiertag (0) vor Wochentagswert der gültigen Version (sonst 0). Ist = persönliche Zeit ohne Doppelzählung, an den lokalen Tagesgrenzen der Zone geschnitten.

### System (AP-39)

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `GET /system/autostart` | Start mit Windows: echter Zustand aus der Registry | – | `{available, enabled, current, command}` |
| `PUT /system/autostart` | ein-/ausschalten (nur Windows; sonst 409) | `{"enabled": true\|false}` | wie oben |
| `GET /system/capabilities` | welche optionalen Zusatzpakete installiert sind | – | `{tray, toast}` |

### Rückfragen (Attention Items, AP-36)

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `GET /attention` | offene Rückfragen und Verbindungen, die verloren sind, aber noch in der Frist | – | `{items: [Rückfrage], link_lost: [{device_id, alias, since, stops_at, grace_seconds}], server_time}` |
| `POST /attention/{id}/resolve` | eine Lückenfrage beantworten | `{"action": "keep"\|"discard"\|"assign", "activity_id"?, "project_id"?}` | **Rückfrage** |
| `POST /attention/{id}/dismiss` | Rückfrage schließen, ohne etwas zu ändern | – | **Rückfrage** |

**Rückfrage:** `{id, kind, status, created_at, resolved_at, resolution, session_id, payload}`. `kind` ist heute `gap` (Lücke nach Verbindungsverlust; `payload`: `device_id`, `lost_at`, `returned_at` oder `null`, `activity_id`, `project_id`); `idle`, `auto_stop`, `reminder`, `break_hint` sind für spätere Pakete reserviert. `status`: `open`, `resolved`, `dismissed`, `expired`.

**Antworten je Art** (`POST /attention/{id}/resolve`, Body `{action, …}`): `gap`: `keep`, `discard`, `assign` (mit `activity_id`); `idle` (Leerlauf; `payload.idle_since`): `keep` (Zeit zählt), `discard` (Eintrag endet zu Beginn des Leerlaufs), `pause` (wie discard und Pause merken); `auto_stop` (Auto-Stopp am Arbeitsende; `payload.ended_at`): `keep` oder `extend` mit `until` (ISO-Zeit, nach dem automatischen Ende, nicht in der Zukunft; 409, wenn die Zeit von einem anderen Eintrag belegt ist). `reminder` (Erinnerung, z. B. `payload.reason` = `battery`, `no_timer`, `running_long`) wird nur mit `…/dismiss` geschlossen (`resolve` ergibt 409).

`keep` bei `gap` verlängert den beendeten Eintrag bis zur Rückkehr (ohne Rückkehr: bis jetzt), `discard` lässt die Lücke leer, `assign` bucht sie auf die angegebene Tätigkeit (Pflicht, sonst 422). Die Lücke überlappt nie den nächsten Eintrag; ist sie ganz belegt, antwortet die API 409. Eine schon beantwortete Rückfrage ergibt 409, eine unbekannte 404. Jede Antwort steht in der Prüfspur.

Hinweis: Im **Steuerungsmodus** eines Würfels entstehen **keine** Sitzungen – seine Drehungen lösen Aktionen aus (Abschnitt 7).

## 10. Berichte

| Methode und Pfad | Zweck |
|---|---|
| `GET /reports?start=&end=&tz=` | Bericht für ein beliebiges Zeitfenster |
| `GET /reports/day?day=&tz=` | ein lokaler Kalendertag |
| `GET /reports/week?day=&tz=&week_starts_on=0` | die lokale Woche, die `day` enthält (`week_starts_on`: 0 = Montag … 6 = Sonntag) |

Alle drei akzeptieren die Filter `device_id`, `activity_id`, `project_id`. Die Antwort:

```json
{
  "window": ["…", "…"], "timezone": "Europe/Zurich",
  "daily": [{"day": "2026-11-21", "device_seconds": 0, "personal_seconds": 0, "uncertain_seconds": 0}],
  "by_activity": [{"id": "…", "name": "…", "color": "#…", "seconds": 0, "percent": 0.0}],
  "by_project": [],
  "device_seconds": 0, "personal_seconds": 0, "overlap_seconds": 0, "uncertain_seconds": 0,
  "session_count": 0, "includes_running": false
}
```

Zeiten mehrerer Würfel, die sich überlappen, werden **nicht doppelt gezählt**: `overlap_seconds` weist die Überschneidung aus.

## 11. Export, Sicherung, Wiederherstellung

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `POST /export/csv` | CSV in den Export-Ordner schreiben und den Inhalt zurückgeben | `{"tz"?, "delimiter"?, "start"?, "end"?}` | `{"filename","rows","size","content"}` |
| `POST /backup` | JSON-Sicherung (Schema 2) in den Sicherungsordner schreiben | – | `{"filename","records","size","content"}` |
| `POST /restore/inspect` | Sicherung **vollständig prüfen, ohne etwas zu ändern** | `{"content"}` | `{"schema_version","app_version","exported_at","counts"}` |
| `POST /restore` | alle Daten durch eine geprüfte Sicherung ersetzen | `{"content", "confirm": true}` | `{"restored": {…}, "pre_restore_backup": "…"}` |

Die CSV beginnt mit einer BOM (Excel), das Trennzeichen ist standardmäßig `;`. Vor einer Wiederherstellung legt OctaLedger **automatisch eine
Sicherung des bisherigen Stands** an (`pre_restore_backup`). Ohne `confirm: true` antwortet `restore` mit **409**. Geheimnisse
(`secrets.json`) sind **nicht** Teil der Sicherung.

### Daten löschen (Datenverwaltung)

Löschen ist unwiderruflich und folgt deshalb immer demselben Muster: **erst Vorschau, dann Bestätigung mit der gezeigten Zahl, vor dem Löschen eine automatische Sicherung** (Datei im Sicherungsordner, Name in der
Antwort), alles in **einer** Transaktion, eine Zusammenfassung in der Prüfspur. Laufende Einträge werden von Sammeloperationen **nie** gelöscht. „Rückgängig“ heißt: die genannte Sicherung wiederherstellen.

| Methode und Pfad | Zweck | Anfrage | Antwort |
|---|---|---|---|
| `GET /data/overview` | Wie viel ist gespeichert? | – | `{"sessions","running_sessions","raw_events","devices","activities","projects","integrations","first_session","last_session"}` |
| `POST /data/entries/preview` | Was würde das Löschen eines Zeitraums treffen? (ändert nichts) | `{"start"?, "end"?}` (Ende ausgeschlossen) | `{"count","with_note","first","last","running_left_out"}` |
| `POST /data/entries/delete` | Einträge eines Zeitraums löschen | `{"start"?, "end"?, "expected_count", "include_events"?}` | `{"sessions","raw_events","safety_backup"}` |
| `POST /data/reset` | **alles** löschen (Einträge, Würfel, Tätigkeiten, Projekte, Verbindungen, Zugangsdaten; Einstellungen auf Standard) | `{"confirm_text": "ALLES LÖSCHEN", "reset_settings"?: true}` | `{"counts","safety_backup","settings_reset"}` |

`expected_count` muss die Zahl aus der Vorschau sein; hat sie sich geändert, antwortet die API mit **409** und löscht nichts. Beim Zurücksetzen muss der Bestätigungstext **genau** stimmen (sonst **409**).

## 12. Einstellungen und Diagnose

| Methode und Pfad | Zweck | Antwort |
|---|---|---|
| `GET /settings` | aktuelle Einstellungen als verschachtelte Abschnitte | Objekt je Abschnitt |
| `PUT /settings` | prüfen und speichern (Teilabschnitte behalten die übrigen Werte): `{"settings": {"abschnitt": {"schluessel": wert}}}` | gespeicherte Einstellungen |
| `POST /settings/reset` | Standardwerte wiederherstellen: `{"section"?}` – ein Abschnitt (`agent`, `tracking`, `display`, `logging`) oder, ohne Angabe, alle | gespeicherte Einstellungen |
| `GET /diagnostics/logs?limit=200` | die letzten (bereits geschwärzten) Protokollzeilen (1–1000) | `{"lines": […]}` |
| `GET /diagnostics/integrity` | Integritätsprüfung der Datenbank | `{"ok": true, "problems": []}` |

Ungültige Einstellungen (unbekannter Abschnitt oder Schlüssel, Wert außerhalb des Bereichs) ergeben **422** mit deutschem Text und ändern nichts.

## 13. Beispiele

Token und Port stammen aus dem Startbefehl; hier als Umgebungsvariablen:

```powershell
$h = @{ Authorization = "Bearer $env:OCTALEDGER_API_TOKEN" }
$api = "http://127.0.0.1:8765/api/v1"

# Übersicht
Invoke-RestMethod "$api/status" -Headers $h

# Aktivität anlegen und eine Sitzung starten
$a = Invoke-RestMethod "$api/activities" -Method Post -Headers $h `
       -ContentType application/json -Body '{"name":"Lesen"}'
Invoke-RestMethod "$api/tracking/start" -Method Post -Headers $h `
       -ContentType application/json -Body (@{activity_id = $a.id} | ConvertTo-Json)

# Würfel in den Steuerungsmodus schalten
Invoke-RestMethod "$api/devices/<ID>/mode" -Method Put -Headers $h `
       -ContentType application/json -Body '{"mode":"control"}'
```

```python
import os, httpx

client = httpx.Client(
    base_url="http://127.0.0.1:8765/api/v1",
    headers={"Authorization": f"Bearer {os.environ['OCTALEDGER_API_TOKEN']}"},
)
print(client.get("/status").json()["tracking"]["elapsed_seconds"])
```

Fehler lesen: bei Status ≥ 400 enthält der Rumpf `{"error": {"code", "message", …}}`; zeigen Sie `message` an und werten Sie `code` aus.

## 14. Der Python-Client des Dashboards

Das Dashboard spricht **ausschließlich** über diese API (`dashboard_client/client.py`, Klasse `ApiClient`), es greift nie auf die
Datenbank zu. Jede Methode des Clients entspricht einem Endpunkt (z. B. `devices()` → `GET /devices`, `set_device_mode()` →
`PUT /devices/{id}/mode`); ein Fehlerrumpf wird zur passenden `OctaLedgerError`-Unterklasse (gewählt über den Fehlercode, mit deutscher `user_message`); ein nicht erreichbarer
Agent oder eine Zeitüberschreitung zu `ApiUnavailableError`. Der Client wiederholt **nie** schreibende Anfragen von selbst (eine Doppelbuchung wäre schlimmer als ein Fehler).

## 15. Versionierung

Die Version steht im Pfad (`/api/v1`) und in `GET /health` (`api_version`). Innerhalb von **v1** werden Felder nur **hinzugefügt**, nie
entfernt oder umgedeutet; Clients sollen unbekannte Felder ignorieren. Eine unverträgliche Änderung würde `/api/v2` neben `/api/v1` einführen.
