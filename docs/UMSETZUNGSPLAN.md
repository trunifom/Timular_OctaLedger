# OctaLedger – Umsetzungsplan der Erweiterungen (AP-35 bis AP-47)

Dieser Plan beschreibt **der Reihe nach**, was als Nächstes gebaut werden soll – jeweils mit **Warum**, **Was**, **Wo** (Module und Dateien), **Wie** (Entwurf, Daten, Schnittstelle, Oberfläche), **Tests**, **Dokumentation**, **Risiken** und **Abnahme**. Die zugehörigen Anforderungen (F-21 bis F-50) stehen im [Pflichtenheft](PFLICHTENHEFT.md) §12.

**Wie man diesen Plan benutzt:** Die Arbeitspakete (AP) sind so geordnet, dass jedes auf den vorherigen aufbauen darf und **einzeln** committet werden kann (Regeln: [CLAUDE.md](../CLAUDE.md) §2: Implementierung, Tests, Fehlerbehandlung, Logging, Doku, Qualitäts-Gate, danach `docs/FORTSCHRITT.md`). Ein Paket ist erst fertig, wenn seine **Abnahme** erfüllt und die Doku im selben Schritt aktualisiert ist.

**Inhalt**

1. [Grundlagen, Quellenlage und Lesehinweise](#1-grundlagen-quellenlage-und-lesehinweise)
2. [Reihenfolge und Abhängigkeiten](#2-reihenfolge-und-abhängigkeiten)
3. [Gemeinsame Bausteine](#3-gemeinsame-bausteine)
4. [AP-35 Würfel-Eingang robuster](#4-ap-35-würfel-eingang-robuster)
5. [AP-36 Verbindungsverlust mit Frist und Rückfragen-Zentrale](#5-ap-36-verbindungsverlust-mit-frist-und-rückfragen-zentrale)
6. [AP-37 Würfeltaste und Batterie-Warnung](#6-ap-37-würfeltaste-und-batterie-warnung)
7. [AP-38 Arbeitstag: Auto-Stopp, Leerlauf, Erinnerungen](#7-ap-38-arbeitstag-auto-stopp-leerlauf-erinnerungen)
8. [AP-39 Tray-Icon, Benachrichtigungen, Autostart](#8-ap-39-tray-icon-benachrichtigungen-autostart)
9. [AP-40 Soll-Arbeitszeit, Überstunden, Pausenhinweise](#9-ap-40-soll-arbeitszeit-überstunden-pausenhinweise)
10. [AP-41 Tags, Notizvorlagen, Budgets, Stundensatz](#10-ap-41-tags-notizvorlagen-budgets-stundensatz)
11. [AP-42 PDF-Bericht und Kalender-Import](#11-ap-42-pdf-bericht-und-kalender-import)
12. [AP-43 Hue erweitern und Bridge-Suche](#12-ap-43-hue-erweitern-und-bridge-suche)
13. [AP-44 Aktionsketten und Bedingungen](#13-ap-44-aktionsketten-und-bedingungen)
14. [AP-45 Medien: Home-Assistant-Vorlagen und lokaler Player](#14-ap-45-medien-home-assistant-vorlagen-und-lokaler-player)
15. [AP-46 Vorlagen und Rezepte: Node-RED und Open Source](#15-ap-46-vorlagen-und-rezepte-node-red-und-open-source)
16. [AP-47 Optionale Pakete (nur auf Wunsch)](#16-ap-47-optionale-pakete-nur-auf-wunsch)
17. [Bewusst nicht geplant](#17-bewusst-nicht-geplant)
18. [Querschnitt: Tests, Doku, Sicherheit, Hardware](#18-querschnitt-tests-doku-sicherheit-hardware)

---

## 1. Grundlagen, Quellenlage und Lesehinweise

Dieser Plan beruht auf dem **bestehenden Code** (Stand AP-34) und einer Recherche. **Die Quellenlage ist unterschiedlich und wird in jedem Paket ausgewiesen:**

| Kennzeichen | Bedeutung |
|---|---|
| **belegt** | durch eine genannte Quelle oder den vorhandenen Code gestützt |
| **[U]** | **ungeprüft**: Vorwissen oder zusammengefasste Suchergebnisse; **vor der Umsetzung gegen die Primärquelle prüfen** (offizielle Doku, Quelltext, eigenes Gerät) und das Ergebnis in `docs/QUELLEN_UND_GRENZEN.md` festhalten |
| **[HW]** | braucht den **echten Würfel** (oder echte Geräte) zur Abnahme; vorher nur mit Simulator/Testdoppeln prüfbar |

**Wichtige Einschränkungen der Recherche (ehrlich):**

* Die Hue-Entwicklerdoku (developers.meethue.com) liegt hinter einem Login; die Hue-Angaben stammen aus Drittquellen und Vorwissen. **Jede Hue-JSON-Form ist an der eigenen Bridge zu prüfen.**
* Zum **Speicher des Würfels** gibt es **keinen Beleg** für eine auslesbare Historie (nur Abwesenheit von Hinweisen in den Community-Projekten `unixfg/triangles` und `codingforfun/zeipy`). Der Plan geht davon aus, dass Wechsel während einer Trennung **verloren** sind.
* Die UUIDs und Datenformate von **Taste**, **Beschleunigung** und **LED** stammen aus einer einzigen Community-Quelle (`codingforfun/zeipy`, Reverse-Engineering) und sind **[U][HW]**.
* Rechtliche Angaben (Pausen, Arbeitszeit) sind **Information, keine Rechtsberatung**; Schwellen sind gegen Primärquellen (fedlex.admin.ch, eur-lex.europa.eu) zu prüfen.
* Ein zweiter Recherche-Durchlauf (Windows, Bibliotheken, Feiertage, PDF, ICS, Pausenregeln) lief teilweise: **belegt** sind die Versionen und Lizenzen aus den PyPI-Metadaten (Tabelle unten) und EU-Richtlinie 2003/88/EG Art. 4; das **Schweizer Recht** ist nur über Sekundärquellen (ch.ch, WEKA, SECO-Wegleitung) bestätigt, weil fedlex.admin.ch ohne JavaScript keinen Text liefert. Alles Übrige steht als **[U]** und ist im **Schritt 0 („Vorprüfung“)** des jeweiligen Pakets zu klären.
* Die Recherche zum **Würfel selbst** (UUIDs, Taste, Beschleunigung) und zu **Hue/Home-Assistant/Medien** ist ebenfalls überwiegend **[U]** (Vorwissen, Drittquellen); die Hue-Entwicklerdoku war nicht abrufbar.

**Konventionen der Pakete:** Jedes Paket nennt *Schritt 0 Vorprüfung* (was vor dem Bauen zu belegen ist), dann Entwurf, Dateien, Tests, Doku, Risiken, Abnahme. Neue Migrationen werden fortlaufend nummeriert (nächste Nummer: `0004`).

### Belegte Bibliotheken (Stand der Recherche, PyPI-Metadaten)

| Zweck | Bibliothek | Version | Lizenz | Bemerkung |
|---|---|---|---|---|
| Tray | `pystray` | 0.19.5 (Sept. 2023) | LGPL-3.0 | **seit 2023 nicht mehr aktualisiert** (Wartungsrisiko); nur als optionales Extra, hinter einer Schnittstelle |
| Toast | `winotify` | 1.1.0 | MIT | einfach; Aktionsknöpfe nur als Start-/URL-Knöpfe, kein Rückruf **[U]** |
| Toast | `windows-toasts` | 1.3.1 | **auf PyPI nicht angegeben** | Lizenzdatei **vor** der Nutzung prüfen; WinRT-Pakete nötig **[U]** |
| Feiertage | `holidays` | 0.109 | MIT | offline; CH mit Kantonen, DE/AT mit Ländern **[U]**; halbe/kantonale Feiertage als manuelle Overrides |
| PDF | `fpdf2` | 7.3.2 | BSD-2-Clause | reines Python; Umlaute nur mit eingebetteter TTF |
| ICS | `icalendar` | 7.0.x | BSD-2-Clause **[U]** | Version/Lizenz vor Festlegung erneut prüfen |
| ICS-Serien | `recurring-ical-events` | – | – | **[U]** nicht abgefragt |

Empfehlung der Recherche für **Toast**: `windows-toasts`, falls die Lizenz bestätigt wird, sonst `winotify` (MIT); beide hinter dem `Notifier`-Protokoll (3.3). Für **PDF** empfahl die Recherche `fpdf2` mit gebündelter TTF und Diagrammen als PNG; dieser Plan beginnt trotzdem mit dem **Browser-Druck** (keine Abhängigkeit) und nimmt `fpdf2` als Extra hinzu.

## 2. Reihenfolge und Abhängigkeiten

```text
AP-35 Eingang robuster ──► AP-36 Verlust + Rückfragen ──► AP-38 Arbeitstag ──► AP-39 Tray/Toast/Autostart
        │                          │                              │
        └─► AP-37 Taste + Batterie ┘                              └─► AP-40 Soll-Zeit ──► AP-41 Tags/Budget ──► AP-42 PDF/ICS

AP-43 Hue ──► AP-44 Aktionsketten ──► AP-45 Medien ──► AP-46 Rezepte      (Funktion A, unabhängig von Funktion B)
                                                                          AP-47 optional (Spotify, Gesten, App-Tracker, Sonos/Cast)
```

| AP | Titel | Funktion | Anforderungen | Migration | Hardware |
|---|---|---|---|---|---|
| 35 | Würfel-Eingang robuster | B | F-21, F-50 | – | [HW] teilweise |
| 36 | Verbindungsverlust mit Frist, Rückfragen | B | F-22, F-23 | 0004 | – |
| 37 | Würfeltaste, Batterie-Warnung | B + A | F-24, F-25 | 0005 | [HW] |
| 38 | Arbeitstag: Auto-Stopp, Leerlauf, Erinnerungen | B | F-26, F-27, F-28 | – | – |
| 39 | Tray, Benachrichtigungen, Autostart | B | F-29, F-30, F-31 | – | – |
| 40 | Soll-Zeit, Überstunden, Pausenhinweise | B | F-32, F-33 | 0006 | – |
| 41 | Tags, Vorlagen, Budgets, Stundensatz | B | F-34, F-35, F-36 | 0007 | – |
| 42 | PDF-Bericht, ICS-Import | B | F-37, F-38 | – | – |
| 43 | Hue erweitern, Bridge-Suche | A | F-39, F-40 | – | [HW] |
| 44 | Aktionsketten, Bedingungen | A | F-41, F-42 | 0008 | – |
| 45 | Medien (HA-Vorlagen, lokaler Player) | A | F-43, F-44 | – | [HW] |
| 46 | Vorlagen und Rezepte (Node-RED …) | A | F-45 | – | – |
| 47 | Optionale Pakete | A + B | F-46 bis F-49 | je nach Paket | [HW] |

**Warum diese Reihenfolge:** Zuerst die Fehlerquellen, die **Daten verfälschen** (AP-35/36: falsche oder fehlende Zeiten), dann die Bedienung (Taste, Tray, Erinnerungen), dann die Auswertung (Soll-Zeit, Berichte), zuletzt der Ausbau von Funktion A (Hue, Ketten, Medien). Funktion A und B sind **unabhängig**; wer zuerst Smarthome möchte, darf AP-43 bis AP-46 vorziehen (sie hängen nur von AP-26 bis AP-31 ab, die schon fertig sind).

## 3. Gemeinsame Bausteine

Mehrere Pakete brauchen dieselben Grundlagen; sie werden **einmal** gebaut, in dem Paket, das sie zuerst braucht, und dort so allgemein, dass spätere Pakete sie wiederverwenden.

### 3.1 Rückfragen-Zentrale („Attention Items“) – gebaut in AP-36

*Warum:* AP-36 (Lücke nach Verbindungsabbruch), AP-38 (Leerlauf, Auto-Stopp, Erinnerungen), AP-40 (Pausenhinweis) und AP-42 (ICS-Vorschläge) brauchen alle dasselbe: etwas, das **auf eine Entscheidung des Anwenders wartet**, auch wenn das Dashboard gerade geschlossen ist. Eine eigene Tabelle je Fall wäre Wildwuchs.

*Was:* Tabelle `attention_items(id, kind, created_at, session_id?, payload JSON, status, resolved_at?, resolution?)` mit `kind` ∈ `gap` (Lücke nach Verbindungsverlust), `idle` (Leerlauf), `auto_stop` (Auto-Stopp erfolgt, bitte prüfen), `reminder` (Erinnerung), `break_hint`. `status` ∈ `open`, `resolved`, `dismissed`, `expired`. Dienst `AttentionService` (Anwendungsschicht): `raise_item`, `list_open`, `resolve(id, resolution)`, `dismiss(id)`, `expire_old`. API: `GET /attention`, `POST /attention/{id}/resolve`, `POST /attention/{id}/dismiss`. Oberfläche: ein **Banner auf jeder Seite** (Statusleiste, `dashboard/shell.py`) „Es wartet etwas auf Sie (n)“ mit Knopf zur Rückfrage; Details im Zeitjournal und in der Übersicht.

*Regeln:* Ein Eintrag verfällt **nie stillschweigend** zu einer Datenänderung (kein Auto-Löschen von Zeit). Rückfragen sind nicht in der Sicherung nötig (Laufzeitdaten), aber `resolved` wird in der Prüfspur festgehalten.

### 3.2 Zeitgeber im Agenten („Housekeeper“) – gebaut in AP-36

*Warum:* Mehrere Regeln hängen an **Zeit statt an einem Ereignis**: Frist nach Verbindungsverlust, Arbeitsende, Leerlauf, Erinnerungen. Der BLE-Loop darf dafür nicht blockiert werden, und die API-Threads sollen nicht „nebenbei“ Zeit ändern.

*Was:* Ein **Daemon-Thread** `agent/housekeeper.py` nach dem Muster des vorhandenen `ActionDispatcher` (`agent/dispatcher.py`): Takt 5 s, `threading.Event` zum prompten Stoppen, überlebt jeden Fehler (protokollieren, weitermachen), Start/Stopp in `AgentRuntime.start()`/`shutdown()`. Er ruft nur **Anwendungsdienste** auf (`TrackingService.watchdog(now)`, `AttentionService`, später `ReminderService`), nie direkt SQL. Alle Regeln sind **rein funktionale Entscheidungen** (`domain/` bzw. `application/`), die mit injizierter Zeit getestet werden; der Thread ist nur der Taktgeber.

### 3.3 Benachrichtigungs-Ausgang – gebaut in AP-39

Ein `Notifier`-Protokoll (`application/notifier.py`) mit Implementierungen „Dashboard-Banner“ (immer), „Windows-Toast“ und „Tray-Balloon“ (optional, AP-39). Die Dienste erzeugen **Absichten** („Erinnerung: Zeit läuft seit 4 h“); der Notifier entscheidet, wie sie erscheinen. So hängt nichts an einer bestimmten Windows-Bibliothek.

### 3.4 Einstellungen: neue Abschnitte

Neue Abschnitte in `core/settings.py` (`_SECTIONS`, validiert, Standardwerte, `POST /settings/reset` funktioniert automatisch): `work` (Arbeitstag, AP-38/40), `notifications` (AP-39), `tray` (AP-39). Jede Einstellung bekommt im Dashboard (Seite **App**, Grundansicht oder „Erweiterte Einstellungen“) einen Hilfetext **mit Voreinstellung**; der Wächtertest `test_gui_documentation` erzwingt das.

### 3.5 Optionale Abhängigkeiten

Alles, was eine Zusatzbibliothek braucht (Tray, Toast, PDF, ICS, Feiertage, Audio, Zeroconf), kommt als **optionale Extras** in `pyproject.toml` (`[project.optional-dependencies]`: `tray`, `toast`, `pdf`, `ics`, `holidays`, `audio`, `discovery`) und wird **zur Laufzeit** erkannt: Fehlt die Bibliothek, ist die Funktion in der Oberfläche **abgeblendet mit Erklärung** („Zusatzpaket nicht installiert: `pip install octaledger[pdf]`“) statt eines Absturzes. Lizenzen werden vor Aufnahme geprüft und in `docs/QUELLEN_UND_GRENZEN.md` aufgeführt (LGPL-Bibliotheken nur als optionale, dynamisch eingebundene Abhängigkeit).

---

## 4. AP-35 Würfel-Eingang robuster

**Anforderungen:** F-21 (unbekannte/Basis-Werte tolerant, Rohwert protokollieren), F-50 (vor dem Verbinden suchen).

### Warum
Im ersten echten Lauf (Log vom 21.11.2026) trat ein `invalid`-Ereignis ohne Wert auf, und das Verbinden scheiterte dreimal mit „Device … was not found“, bevor es klappte. Beides sind **Eingangsfehler**, die ohne Aufwand die Datenqualität verbessern.

* **Basis-Werte:** Der Decoder (`infrastructure/ble/protocol.py::decode_orientation`) akzeptiert nur 0–8; alles andere wird als `invalid` verworfen. Laut README von `adn77/timeular` (belegt, Auszug) bedeuten die Werte **0 und 10 beide „Tracker liegt in der Basis/Ladestation“**; 9 wird nicht erwähnt. Wenn der Würfel 9 oder 10 meldet, wird das heute als Fehler abgelegt, obwohl es eine sinnvolle Lage ist. **[U][HW]: ob dein Würfel 9/10 meldet, ist am echten Gerät zu bestätigen** (siehe Schritt 0).
* **„Not found“:** Unter Windows/Bleak scheitert das Verbinden über die bloße Adresse oft, wenn das Gerät gerade nicht wirbt. Üblich ist, vorher kurz zu scannen und das gefundene Geräteobjekt zu übergeben **[U]**.

### Schritt 0: Vorprüfung
1. **[HW]** Einen Diagnose-Schalter „Rohwert protokollieren“ bauen (erster Teil des Pakets) und am echten Würfel in die Basis legen, auf jede Seite drehen und notieren: Welche Rohwerte kommen (0–10)? Ergebnis in `docs/BLE_PROTOCOL.md` (Tabelle „beobachtete Werte“).
2. Quelltext von `adn77/timeular` (Program.cs) und `codingforfun/zeipy` auf die Bedeutung von 9/10 prüfen (UUIDs, Wertebereich).

### Entwurf
**a) Rohwert immer mitführen.** `OrientationEvent`/`RawEvent` für `invalid` bekommen im Feld `detail` den **Rohbytes-Hex** (z. B. `len=1 value=0x0A`); das Diagnose-Protokoll zeigt sie (nie im Klartext sensible Daten – es sind nur ein bis zwei Bytes).

**b) Werttabelle statt `0..8`.** `domain/orientation.py` bekommt eine `Position`-Einordnung: `FACE (1..8)`, `BASE (0, 10)`, `UNKNOWN (9, >10)`. Entscheidung:
* `0` und `10` → `EventKind.NEUTRAL` (wie bisher 0; Verhalten laut Einstellung `neutral_policy`).
* `9` und alles andere außerhalb 0–10 → weiterhin `invalid`, **aber mit Rohwert im Detail**.
* Die Zuordnung ist eine **Tabelle** (`BASE_VALUES = frozenset({0, 10})`), damit sie nach der Hardwareprüfung an **einer** Stelle angepasst wird.

**c) Scan vor Verbinden.** `infrastructure/ble/client.py` (`BleakTransport.connect`): Vor `BleakClient(...).connect()` ein kurzer gezielter Scan (`BleakScanner.find_device_by_address(address, timeout=…)`, Timeout einstellbar, Voreinstellung 8 s), das gefundene `BLEDevice` an den Client übergeben. Findet der Scan nichts, bleibt der Fehlertext verständlich („Der Würfel wirbt gerade nicht: einmal drehen oder Knopf drücken“) und der bestehende Backoff greift. Einstellung `agent.scan_before_connect = true` (erweitert).

### Dateien
`domain/orientation.py`, `infrastructure/ble/protocol.py` (Decoder + Konstanten), `agent/supervisor.py` (`_record_invalid`, Detailtext), `infrastructure/ble/client.py`, `core/settings.py` (`AgentSettings.scan_before_connect`, `scan_timeout_seconds`), `dashboard/views/diagnostics.py` (Rohwert-Anzeige), Tests, `docs/BLE_PROTOCOL.md`, `docs/BENUTZERHANDBUCH.md` (Meldungen).

### Tests
Decoder: 0/10 → neutral, 9 → invalid mit Detail, Länge ≠ 1 → invalid mit Detail. Supervisor: Basis-Wert löst `neutral`, kein `invalid`. Transport (Stub): Scan findet → Gerät wird übergeben; Scan findet nicht → klare Meldung. Migration: keine.

### Risiken
Falsche Annahme über 9/10 → Tabelle ist änderbar; Basis-Werte würden bei Pause-Regel „neutral = Pause“ eine Pause auslösen, **Standard bleibt „nur protokollieren“**. Zusätzlicher Scan verlängert den Verbindungsaufbau um bis zu die Timeout-Zeit.

### Abnahme
A-18: Im Simulator führen 0 und 10 zu `neutral`, 9 und 255 zu `invalid` mit Rohwert im Protokoll; ein Verbindungsversuch scannt zuerst. **[HW]** A-18b: Am echten Würfel sind die Rohwerte der Basis dokumentiert.

---

## 5. AP-36 Verbindungsverlust mit Frist und Rückfragen-Zentrale

**Anforderungen:** F-22 (Verlust mit Frist, Wiedereinstieg), F-23 (Rückfragen-Zentrale). Baut die gemeinsamen Bausteine 3.1 und 3.2.

### Warum
Der Standard „als unsicher markieren“ lässt die Zeit **unbegrenzt weiterlaufen**; wer vergisst, dass der Würfel getrennt wurde, bucht Stunden, die nicht stimmen. „Eintrag beenden“ beendet **sofort**, auch bei einem kurzen Funkloch von 2 Sekunden. Best Practice (Recherche, Empfehlung, nicht von einer App belegt): **nicht raten**, den Zustand „Verbindung verloren“ setzen, nach einer **einstellbaren Frist** am **letzten sicheren Kontakt** beenden, bei Rückkehr innerhalb der Frist **fortsetzen**, danach **fragen** (so ähnlich fragen Toggl/Clockify bei Leerlauf: „behalten oder verwerfen?“).

### Schritt 0: Vorprüfung
Den **letzten sicheren Kontakt** definieren: Zeitpunkt des letzten **empfangenen** Rohereignisses (`raw_events.received_at`) oder der letzten Batterie-/Lesemeldung dieses Würfels. (Der Würfel meldet nur bei Seitenwechsel; ein stiller Würfel ist also „in Kontakt“, solange die Verbindung steht – der Zeitpunkt des **Verbindungsabbruchs** ist das letzte sichere Wissen: `EventKind.DISCONNECT.received_at` minus Erkennungsverzug.) **Entscheidung:** Ende = Zeitpunkt des `DISCONNECT`-Ereignisses (Bleak meldet den Abbruch nach dem Supervision-Timeout, typisch einige Sekunden **[U]**; dieser Verzug ist hinzunehmen und wird dokumentiert).

### Entwurf
**Neue Richtlinie** `DisconnectPolicy.GRACE_THEN_STOP` (Standard der neuen Version; bestehende Wahl bleibt gültig):

| Phase | Verhalten |
|---|---|
| Abbruch (`DISCONNECT`) | Eintrag läuft weiter, `quality=uncertain`; in `app_state` wird `link_lost:<device_id> = <Zeitpunkt>` gesetzt |
| Frist läuft | Anzeige in Statusleiste/Übersicht: „Verbindung verloren seit 02:10 – der Eintrag wird nach 10 min beendet“ |
| Rückkehr in der Frist (`BASELINE` nach Reconnect) | Marke löschen; Eintrag läuft weiter (bleibt `uncertain`, bis der Anwender bestätigt); Lücke wird im Journal als Hinweis gezeigt |
| Frist abgelaufen | `TrackingService.watchdog(now)` beendet den Eintrag am `link_lost`-Zeitpunkt (`quality=uncertain`), legt eine Rückfrage `gap` an |
| Rückkehr nach der Frist | Rückfrage `gap` zeigt Lücke „von … bis …“; Antworten: **Lücke behalten** (Eintrag verlängern bis jetzt), **verwerfen** (Eintrag bleibt am Verlustzeitpunkt beendet, Lücke leer), **anderer Tätigkeit zuordnen** (neuer Eintrag mit gewählter Tätigkeit über die Lücke) |

Einstellungen (`tracking`): `disconnect_policy` um `grace_then_stop` erweitert; **neu** `disconnect_grace_seconds` (Voreinstellung **300**, Bereich 0–3600; 0 entspricht `stop_session`). Beides in „Erweiterte Einstellungen“ der Seite **App**; Hilfetexte nennen die Voreinstellung.

**Rückfragen-Zentrale (3.1)** wird hier gebaut und für `gap` benutzt. **Housekeeper (3.2)** wird hier gebaut und ruft `TrackingService.watchdog` alle 5 s.

**Zeitlogik rein:** `domain/link_loss.py` mit `decide(state, now, grace) -> Action` (`KEEP`, `STOP_AT`, `NONE`) – ohne I/O, voll testbar.

### Dateien
`domain/link_loss.py` (neu), `application/attention_service.py` (neu), `application/tracking_service.py` (`watchdog`, Anpassung `_on_disconnect`/`_on_baseline`), `agent/housekeeper.py` (neu), `agent/main.py` (Start/Stopp), `core/settings.py`, `infrastructure/storage/migrations/0004_attention.sql` + `repositories.py` (`AttentionRepository`), `api/routes.py`+`schemas.py` (`/attention…`), `dashboard_client/client.py`, `dashboard/shell.py` (Banner), `dashboard/views/journal.py` und `overview.py` (Rückfrage-Dialogfläche), Tests, Doku (`API.md`, `DATENMODELL.md`, `ARCHITEKTUR.md` §3/§9, Handbuch Kapitel 9 „Verbindungsverhalten“, `GLOSSAR.md`).

### Tests
Reine Logik (`decide`): alle Phasen, Grenzen (Frist 0, Frist genau erreicht). `TrackingService`: Abbruch → weiterlaufend und uncertain; Rückkehr in Frist → weiter; Frist abgelaufen → Ende am Abbruchzeitpunkt + Rückfrage; Rückkehr danach → `resolve` je Antwort (behalten/verwerfen/zuordnen) ändert Daten wie beschrieben und schreibt die Prüfspur; mehrere Würfel unabhängig; Steuerungs-Würfel unberührt. Housekeeper: Thread-Test wie `test_dispatcher.py` (überlebt Fehler, stoppt prompt). API und GUI-Tests für das Banner und die drei Antworten. Migration 0004 (Test leitet die Version aus den Paketdateien ab).

### Risiken
Doppelte Zeitbuchung nach „behalten“, wenn sich Einträge überlappen → die Datenbank-Trigger verhindern Überlappung; die Dienstmethode prüft vorher und meldet verständlich. Neustart des Agenten mitten in der Frist → `link_lost` liegt in `app_state` und überlebt; beim Start prüft der Housekeeper sofort.

### Abnahme
A-19: Bei Verbindungsverlust läuft der Eintrag bis zur Frist weiter und endet danach exakt am Verlustzeitpunkt; kommt der Würfel in der Frist zurück, läuft er weiter; nach der Frist erscheint eine Rückfrage mit den drei Antworten, jede wirkt wie beschrieben; **keine** Zeit wird ohne Rückfrage erfunden oder gelöscht.

---

## 6. AP-37 Würfeltaste und Batterie-Warnung

**Anforderungen:** F-24 (Taste als Eingabe), F-25 (Batterie-Warnung).

### Warum
Der Würfel hat eine **Taste** (belegt in `codingforfun/zeipy`: Characteristic `c7e70021`, INDICATE, ein Byte, 0 = kurzer Druck, 1 = langer Druck **[U][HW]**). Sie ist die einzige zusätzliche **echte** Eingabe, die keinen Schreibzugriff braucht und die **kein anderes Programm** bedient: ideal für „Pause“ (kurz) und „Stopp“ (lang) – ohne Dashboard und ohne Maus. Der **Batteriestand** wird schon gelesen (F-18), aber nirgends als Warnung genutzt; ein leerer Würfel verhält sich wie ein Verbindungsverlust.

### Schritt 0: Vorprüfung
1. **[U]** Quelltext von `codingforfun/zeipy` lesen: exakte UUID, Wertebedeutung, **wann** die Taste meldet (laut Quelle „ausgelöst nach OFF“ – klären, was das heißt).
2. **[HW]** Am echten Würfel Taste kurz/lang drücken und die Rohwerte im Protokoll beobachten (Diagnose-Schalter aus AP-35).
3. Prüfen, ob Bleak/Windows **zwei gleichzeitige Abonnements** (Orientierung + Taste) am selben Gerät zuverlässig hält **[U]**.

### Entwurf
**Protokoll (nur lesen/abonnieren!):** `infrastructure/ble/protocol.py` bekommt `BUTTON_CHARACTERISTIC_UUID`, `decode_button_payload(payload) -> ButtonPress (SHORT|LONG)` und `DeviceCapabilities.has_button` (Fähigkeitenerkennung wie `has_battery`). **Keine Schreiboperation**; die Taste wird nur abonniert (Projektregel „kein Schreiben auf unbekannte Characteristics“ bleibt).

**Agent:** `DeviceWorker` abonniert zusätzlich die Taste, wenn vorhanden; ein Druck wird wie ein Seitenwechsel als `RawEvent(kind=BUTTON, detail="short"|"long")` gespeichert (neuer `EventKind.BUTTON`, Migration **0005** ergänzt die erlaubten `kind`-Werte der CHECK-Bedingung von `raw_events` – SQLite verlangt dafür das Neuanlegen der Tabelle; Migration mit Datenübernahme und Test).

**Zuordnung pro Würfel:** Tabelle `device_buttons(device_id, press, action, params)` (`press` ∈ short/long; `action` ∈ `none`, `pause_resume`, `stop`, `start_last`, `note_marker`, und im **Steuerungsmodus** zusätzlich `integration_action` wie bei Seiten). **Voreinstellung: keine Belegung** (`none`) – nichts geschieht ohne ausdrückliche Wahl. `TrackingService.handle_button(event)` führt `pause_resume`/`stop`/`start_last` über die vorhandenen Methoden (`pause`, `resume`, `stop`, `start_manual`) aus; nur der **aktive** Würfel beeinflusst die Zeit (wie bei Seiten).

**Batterie-Warnung:** Einstellung `notifications.battery_warning_percent` (Voreinstellung 20, 0 = aus). Der Supervisor liest die Batterie bereits (`_read_optional`); zusätzlich alle 10 Minuten erneut lesen (nur lesen) und bei Unterschreitung einmal pro Ladezyklus eine Rückfrage vom Typ `reminder` auslösen (Rückfragen-Zentrale, AP-36) – Banner im Dashboard, später Toast (AP-39).

**Oberfläche:** Seite **Würfel verwalten** → je Würfel Bereich „Taste“ (Auswahl für kurz/lang mit Hilfetext, Hinweis „noch nicht mit Hardware geprüft“); **Würfel live** zeigt Tastendrücke in „Letzte Bewegungen“.

### Dateien
`infrastructure/ble/protocol.py`, `infrastructure/ble/fake.py` (Simulator kann Tastendruck senden), `agent/supervisor.py`, `domain/models.py` (`EventKind.BUTTON`, `ButtonPress`, `DeviceButton`), Migration `0005_buttons.sql`, `repositories.py`, `application/device_service.py` (Zuordnung), `application/tracking_service.py` (`handle_button`), API (`/devices/{id}/buttons/{short|long}`), Client, `dashboard/views/devices.py` und `live.py`, Tests, Doku (`BLE_PROTOCOL.md`, Handbuch, API, Datenmodell, Sicherungsformat: `device_buttons` kommt in Schema 3, Schema 1/2 bleiben lesbar).

### Tests
Decoder (kurz/lang/ungültig), Fähigkeiten, Simulator-Tastendruck → Ereignis, `handle_button` je Aktion, nur aktiver Würfel, Steuerungsmodus-Aktion, Migration 0005 (Daten bleiben), Sicherung Schema 3 und Rückwärtslesen, GUI-Zuordnung, Batterie-Warnung einmalig, Warnung aus bei 0.

### Risiken
**[HW]** Format und Zeitpunkt der Meldung sind nicht bestätigt → bis zur Hardwareprüfung ist das Feature **per Einstellung ausgeschaltet** (`device_buttons` leer). Ein versehentlicher Druck beim Drehen kann stören → Entprellung der Taste (gleicher Druck innerhalb 500 ms ignorieren).

### Abnahme
A-20 (Simulator): Kurzer/langer Druck löst die zugeordnete Aktion aus, ohne Zuordnung nichts. **[HW]** A-20b: Am echten Würfel entsprechen kurz/lang den dokumentierten Werten.

---

## 7. AP-38 Arbeitstag: Auto-Stopp, Leerlauf, Erinnerungen

**Anforderungen:** F-26 (Auto-Stopp am Arbeitsende), F-27 (Leerlauf/Sperrbildschirm), F-28 (Erinnerungen).

### Warum
Die häufigste Fehlbuchung ist der **vergessene Stopp** (und der vergessene Start). Toggl und Clockify bieten Leerlauf-Erkennung und Erinnerungen (belegt, Hilfeseiten); ActivityWatch zählt ab 3 Minuten ohne Eingabe als inaktiv (belegt, FAQ). Entscheidend für den Datenschutz: Die Erkennung nutzt **nur die Zeit seit der letzten Eingabe**, keinerlei Inhalte.

### Schritt 0: Vorprüfung
1. **[U]** `GetLastInputInfo` (user32, per `ctypes`, `LASTINPUTINFO{cbSize, dwTime}`): Leerlaufzeit = aktuelle Tickzeit − `dwTime`; mit `GetTickCount64` oder Maske `& 0xFFFFFFFF` rechnen (32-Bit-Zähler läuft nach etwa 49,7 Tagen über). Der Wert gilt nur für die **eigene Sitzung**: Der Agent muss in der **Benutzersitzung** laufen (nicht als Dienst in Sitzung 0), sonst ist er wertlos → im Handbuch so dokumentieren und den Fehlerfall erkennen (Wert springt nie). Programmatisch erzeugte Eingaben (z. B. Fernsteuerung) zählen mit; **passives Video-/Meeting-Schauen zählt als Leerlauf**.
2. **[U]** Sperrbildschirm und Standby: `WTSRegisterSessionNotification` (`WM_WTSSESSION_CHANGE`: `WTS_SESSION_LOCK` 0x7 / `WTS_SESSION_UNLOCK` 0x8) und `WM_POWERBROADCAST` (`PBT_APMSUSPEND` 0x4 / `PBT_APMRESUMEAUTOMATIC` 0x12) brauchen ein verstecktes Message-Only-Fenster mit eigener Nachrichtenschleife (per `ctypes` umständlich; `pywin32` wäre eine Zusatzabhängigkeit). **Entscheidung: ctypes-only, zuerst die einfache Variante** – ein Heartbeat erkennt Standby über den **Zeitsprung** (Differenz monotone/Wanduhr größer als Schwellwert, ≥ 2× Takt = „System war angehalten“); Sperrbildschirm-Ereignisse nur, wenn die einfache Variante nicht genügt.
3. Rechtlicher/Datenschutz-Hinweis im Handbuch: Es wird **nichts** aufgezeichnet außer „seit wann keine Eingabe“.

### Entwurf
**Einstellungsabschnitt `work`** (Seite **App**, Grundansicht kurz, Rest erweitert; alles mit Voreinstellung im Hilfetext):

| Einstellung | Voreinstellung | Wirkung |
|---|---|---|
| `workday_end` (Zeit, leer = aus) | aus | Zu dieser Uhrzeit endet ein laufender Eintrag (Auto-Stopp), danach Rückfrage `auto_stop` |
| `workdays` (Wochentage) | Mo–Fr | An anderen Tagen kein Auto-Stopp und keine Erinnerung |
| `idle_minutes` (0 = aus) | 0 (aus) | Ohne Eingabe seit n Minuten → Rückfrage `idle` |
| `idle_action` | `ask` | `ask` fragt beim Zurückkehren: **Zeit behalten**, **verwerfen** (Eintrag endet zu Beginn des Leerlaufs), **als Pause buchen** |
| `reminder_no_timer_after` (Zeit, leer = aus) | aus | Läuft zu Arbeitsbeginn+Verzögerung kein Eintrag → Erinnerung „Zeit starten?“ |
| `reminder_running_hours` (0 = aus) | 0 | Läuft ein Eintrag länger als n Stunden → Erinnerung „Noch dabei?“ |

**Leerlauf standardmäßig aus** (datenschutzfreundlich und weil „Video schauen“ als Leerlauf gilt – ActivityWatch warnt davor). **Auto-Stopp beendet nie rückwirkend ohne Spur:** Der Eintrag endet zur eingestellten Zeit, `quality=uncertain`, und die Rückfrage erlaubt, ihn zu verlängern (z. B. „ich habe doch bis 18:30 gearbeitet“).

**Wo:** Neuer Dienst `application/workday_service.py` (reine Entscheidungslogik in `domain/workday.py`: `evaluate(now, last_input, settings, running) -> list[Action]`); der **Housekeeper** (AP-36) ruft ihn im 5-s-Takt; die Eingabe-Zeit liefert ein austauschbarer `InputProbe` (`infrastructure/system/idle_windows.py`, `ctypes`; Testdoppel `FixedInputProbe`). Erinnerungen und Rückfragen laufen über die Rückfragen-Zentrale (3.1); Zustellung später über Notifier (3.3).

### Dateien
`domain/workday.py`, `application/workday_service.py`, `infrastructure/system/__init__.py`, `infrastructure/system/idle_windows.py`, `agent/housekeeper.py` (Erweiterung), `core/settings.py` (`WorkSettings`), `dashboard/views/settings.py` (Abschnitt „Arbeitstag“), Banner/Rückfrage-UI (AP-36), Tests, Doku.

### Tests
Reine Logik: Auto-Stopp zur Zeit, nur an Arbeitstagen, nie wenn nichts läuft; Leerlauf mit Zeitsprung; Rückkehr-Antworten; Erinnerungen genau einmal je Anlass. Probe: Fehler/ungültiger Wert → Funktion pausiert und protokolliert (kein Absturz). GUI: Einstellungen validieren, Reset. Alles mit injizierter Uhr.

### Risiken
Falsche Positive (Leerlauf bei Videos/Lesen) → Voreinstellung aus, klare Rückfrage statt Automatik. Agent nicht in der Benutzersitzung → Erkennen und in der Diagnose melden.

### Abnahme
A-21: Mit Probe-Doppel endet ein Eintrag zur eingestellten Zeit mit Rückfrage; Leerlauf-Rückfrage bietet drei Antworten; Erinnerungen erscheinen einmal; alles ausgeschaltet nach Installation.

---

## 8. AP-39 Tray-Icon, Benachrichtigungen, Autostart

**Anforderungen:** F-29 (Tray-Icon), F-30 (Benachrichtigungen), F-31 (Autostart).

### Warum
Ein Zeiterfasser muss **sichtbar** sagen, dass etwas läuft, ohne dass man das Dashboard öffnet; und er muss **von selbst starten**, sonst fehlt der Agent genau dann, wenn man vergisst, ihn zu starten. Das Tray-Icon ist der Alltagsbeleg, dass die Erfassung läuft.

### Schritt 0: Vorprüfung
1. Bibliothek wählen: `pystray` 0.19.5 (**LGPL-3.0, belegt**; **seit 2023 nicht mehr gepflegt**, Wartungsrisiko; Icon und Tooltip lassen sich über `icon.icon`/`icon.title` und `update_menu()` aktualisieren, Betrieb in eigenem Thread **[U]**), Alternative `infi.systray` (Lizenz **[U]**, wenig gepflegt) oder direkt Win32 `Shell_NotifyIcon` per `ctypes` (keine Abhängigkeit, mehr Code). Entscheidungskriterium: zuverlässiger Betrieb im selben Prozess **neben** dem asyncio-Loop und uvicorn; Kommunikation mit dem Loop nur über `call_soon_threadsafe`. Bei einem gebündelten Paket (z. B. PyInstaller) LGPL-Hinweise beilegen.
2. Toast: `winotify` 1.1.0 (**MIT, belegt**) oder `windows-toasts` 1.3.1 (**Lizenz auf PyPI nicht angegeben – Lizenzdatei prüfen**, WinRT-Pakete **[U]**). Ohne eigene AppUserModelID erscheint der Interpreter als Absender **[U]**; klickbare Aktionen aus einem Hintergrundprozess brauchen idealerweise eine Startmenü-Verknüpfung mit AUMID **[U]** → für v1 genügen **Meldungen ohne Aktionsknöpfe** (Aktion läuft über das Dashboard-Banner/Tray-Menü); Fallback „Tray-Balloon“.
3. **[U]** Autostart: **Startordner-Verknüpfung** (einfach, sichtbar für den Anwender, ohne Registry) gegenüber `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (üblich, per `winreg`). Empfehlung: **Run-Key** (unauffällig, ohne Zusatzdatei), per Schalter einseitig an/aus, mit Anzeige des Zustands.

### Entwurf
**Tray (optional, Extra `tray`):** Prozess-Thread `agent/tray.py`; Symbol zeigt Zustand (grün = läuft, grau = nichts läuft, rot = Würfel getrennt, gelb = Rückfrage offen); Tooltip „Entwicklung 1:23:45“ (alle 5 s aktualisiert); Menü: *Zeit stoppen*, *Pause/Fortsetzen*, *Dashboard öffnen* (`webbrowser.open('http://127.0.0.1:8501')`), *Rückfragen anzeigen*, *Beenden* (ruft das saubere Herunterfahren). Das Menü ruft **Anwendungsdienste**, nie SQL. Einstellung `tray.enabled` (Voreinstellung **an, wenn das Extra installiert ist**).

**Benachrichtigungen (Extra `toast`):** `Notifier`-Implementierung `WindowsToastNotifier`; Einstellungen `notifications.toast` (an/aus), `notifications.quiet_hours` (von/bis, z. B. 22–7 Uhr stumm). Texte deutsch, ohne sensible Inhalte (keine Notizen). **Immer** zusätzlich das Dashboard-Banner (Rückfragen-Zentrale).

**Autostart:** CLI `octaledger autostart on|off|status` und ein Schalter auf der Seite **App** (Abschnitt „Start mit Windows“, nur sichtbar unter Windows): schreibt/entfernt den Run-Key mit dem Befehl `"<python.exe>" -m octaledger agent --quiet` (kein Konsolenfenster: `pythonw.exe`). Zustand wird **gelesen**, nicht angenommen.

### Dateien
`agent/tray.py`, `application/notifier.py`, `infrastructure/system/toast_windows.py`, `infrastructure/system/autostart_windows.py`, `cli.py` (`autostart`), `core/settings.py` (`TraySettings`, `NotificationSettings`), API (`GET/PUT /system/autostart`), Seite **App**, `pyproject.toml` (Extras), Tests (mit Attrappen: Registry-Zugriff hinter Schnittstelle), Doku (`INSTALLATION.md` Autostart, Handbuch, Datenschutz-Hinweis).

### Tests
Registry/Notifier/Tray hinter Schnittstellen mit Attrappen; Autostart-Befehl wird korrekt gebaut (Pfade mit Leerzeichen, Anführungszeichen); „Extra fehlt“ → Funktion abgeblendet; Ruhezeiten; Tooltip-Text; Menüaktionen rufen die richtigen Dienste.

### Risiken
Tray-Bibliothek und uvicorn/asyncio im selben Prozess → eigener Thread, Fehler beenden den Agenten nicht. Antivirus misstraut Run-Key-Einträgen → transparent im Handbuch erklären. LGPL → nur optionale Abhängigkeit.

### Abnahme
A-22: Mit Attrappen entsprechen Symbolzustand, Tooltip und Menü dem Dienstzustand; Autostart lässt sich ein-/ausschalten und liest den echten Zustand zurück. **[HW/Windows]** A-22b: Auf dem echten Windows-Rechner startet der Agent nach Anmeldung, das Symbol erscheint, ein Toast kommt an.

---

## 9. AP-40 Soll-Arbeitszeit, Überstunden, Pausenhinweise

**Anforderungen:** F-32 (Soll/Saldo), F-33 (Pausenhinweise).

### Warum
Wer Zeit erfasst, will wissen: „Habe ich mein Soll erreicht? Wie viele Überstunden habe ich?“ Clockify bietet Targets und einen Anwesenheits-/Überstundenbericht (belegt). Für Überstunden muss der Saldo **Feiertage und Abwesenheit** berücksichtigen (Clockify setzt das Tagessoll bei einem ganzen freien Tag auf 0, belegt). Pausenhinweise helfen, die gesetzlichen Pausen einzuhalten – **als Information, nie als Rechtsberatung und nie als Zwang**.

### Schritt 0: Vorprüfung
1. `holidays` 0.109 (**MIT, belegt**): Offline-Feiertage; Schweiz mit Kantonen (`holidays.CH(subdiv="ZH")`), Deutschland und Österreich mit Ländern **[U]**. Kantonale und **halbe Feiertage** (z. B. 24./31.12.) sind betriebsspezifisch → **manuelle Overrides** (Tabelle `absences`/Tagesabweichung mit `holiday_custom` und `target_minutes`) sind Pflicht; eigene Feiertagsliste als Fallback.
2. **Primärquellen prüfen:** Schweiz **Art. 15 ArG** (nach Sekundärquellen ch.ch, WEKA, SECO-Wegleitung: Pause mind. 15 min bei mehr als 5,5 h, 30 min bei mehr als 7 h, 60 min bei mehr als 9 h, teilbar; Pausen gelten grundsätzlich **nicht** als Arbeitszeit, außer der Arbeitsplatz darf nicht verlassen werden; Pausen am Anfang oder Ende des Tags sind keine echten Pausen) und **ArGV 1 Art. 18** (bei flexiblen Systemen zählt laut WEKA die durchschnittliche Tagesarbeitszeit), **Art. 15a ArG** (11 h Ruhezeit) – den **Wortlaut** auf fedlex.admin.ch (SR 822.11, SR 822.111) manuell prüfen (nicht mit der liechtensteinischen ArGV I verwechseln); EU **Richtlinie 2003/88/EG Art. 4** (**belegt**, EUR-Lex): Ruhepause bei mehr als 6 Stunden täglicher Arbeitszeit, Dauer und Voraussetzungen regeln Tarifverträge oder nationales Recht, Art. 3: 11 h Ruhe. Die geltenden Schwellen stehen danach als **Tabelle mit Quelle und Stand** in `domain/break_rules.py`; **kein automatischer Pausenabzug**.
3. Das Gesetz gilt nur für bestimmte Betriebe/Personen (Selbstständige sind ausgenommen): Hinweis im Handbuch.

### Entwurf
**Datenmodell (Migration 0006):** `work_schedule(valid_from, mon_minutes … sun_minutes, region)` – **versioniert nach Gültigkeit**, damit ein Wechsel (z. B. Teilzeit ab Datum) alte Salden nicht verändert (Minuten statt Prozentfaktor, weil eindeutiger); Tabelle `absences(id, start_date, end_date, kind, target_minutes?, note)` mit `kind` ∈ `vacation`, `sick`, `holiday_custom`, `other` (`target_minutes` überschreibt das Tagessoll, z. B. halber Feiertag); Saldo-Vortrag `balance_carry(date, minutes)`. **Saldo = Σ (Ist − Soll) je lokalem Kalendertag**; Einträge bleiben UTC und werden an den lokalen Tagesgrenzen der gewählten Zone geschnitten (Tage mit 23/25 Stunden), nie Tage addieren.

**Dienst:** `ReportService.balance(start, end, tz)` liefert je Tag *Soll*, *Ist* (persönliche Zeit, ohne Doppelzählung), *Differenz*, Summe und laufenden Saldo; Soll = Wochentagssoll **minus** Feiertag/Abwesenheit (ganzer Tag → 0). Mitternachtsgrenzen und Sommerzeit folgen den vorhandenen lokalen Tagesgrenzen (`domain/time_rules.py`).

**Pausenhinweise:** `domain/break_rules.py::required_break(region, worked_minutes)` und `application/break_hint.py`: Hat ein Tag mehr Arbeitszeit als die Schwelle **ohne** erfasste Pause, entsteht **ein** Hinweis (Typ `break_hint` in der Rückfragen-Zentrale): „Heute 6 h 10 min ohne Pause erfasst (Orientierung: Pause ab 5,5 h). Pause nachtragen?“ mit Knopf „Pause nachtragen“ (legt einen Eintrag der Tätigkeit „Pause“ an, falls vorhanden). Einstellung `work.break_region` ∈ `off` (Voreinstellung), `ch`, `eu`, `custom`.

**Oberfläche:** Seite **Statistik** neuer Reiter „Soll und Saldo“ (Tabelle und Diagramm); Seite **App** Abschnitt „Arbeitszeit“ (Soll je Wochentag, Region für Feiertage, Pausenregion); neue Seite-Unterabschnitte „Abwesenheiten“ (anlegen/löschen) in *Tätigkeiten & Projekte* oder eigener Reiter.

### Dateien
Migration `0006_work.sql`, `repositories.py` (`AbsenceRepository`), `domain/break_rules.py`, `application/reporting_service.py` (`balance`), `application/break_hint.py`, `core/settings.py` (`WorkSettings` erweitert), API (`/absences`, `/reports/balance`), Client, `dashboard/views/statistics.py`, `settings.py`, Tests, Doku, Sicherungsformat Schema 3.

### Tests
Saldo mit Feiertag, Abwesenheit, Teilzeit, Sommerzeitwechsel, Mitternacht, laufender Eintrag; Pausenregeln je Region und Grenzwerte (genau 5,5 h); Hinweis nur einmal je Tag; Abwesenheiten (Überlappung, Löschen); Sicherung/Restore mit Abwesenheiten.

### Risiken
Rechtliche Schwellen veralten oder sind falsch → Tabelle mit Quelle/Stand, Haftungsausschluss in der Oberfläche, **Voreinstellung aus**. Feiertage je Kanton/Land sind fehleranfällig → eigene Liste überschreibt.

### Abnahme
A-23: Saldo berücksichtigt Feiertage/Abwesenheit korrekt in den Testfällen; Pausenhinweis erscheint genau einmal und ist abschaltbar; die Schwellen tragen Quelle und Stand.

---

## 10. AP-41 Tags, Notizvorlagen, Budgets, Stundensatz

**Anforderungen:** F-34 (Tags/Notizvorlagen), F-35 (Budgets), F-36 (Abrechenbar/Stundensatz).

### Warum
Tags und Notizen gehören bei Timeular/EARLY zum Kern der Erfassung (belegt); Budgets mit Warnschwelle und Abrechenbarkeit brauchen vor allem Selbstständige. Alles bleibt **lokal**.

### Schritt 0: Vorprüfung
Entscheiden, ob Tags **je Eintrag** (n:m, flexibel) oder **je Tätigkeit** (einfach) gelten. **Empfehlung:** je Eintrag mit Vorschlag aus der Tätigkeit (Standard-Tags einer Tätigkeit werden beim Start übernommen).

### Entwurf
**Migration 0007:** `tags(id, name UNIQUE NOCASE, color)`, `session_tags(session_id, tag_id)`; `projects` bekommt `budget_minutes INTEGER NULL`, `hourly_rate_cents INTEGER NULL`, `billable INTEGER DEFAULT 0`; `activities` bekommt `default_tag_ids` (Tabelle `activity_tags`) und `note_template TEXT NULL` (Vorlage für Notizen, z. B. „Kunde: \nZiel: “).

**Dienste:** `CatalogService` (Tags CRUD, Standard-Tags), `TrackingService` (Tags beim Start/Korrigieren; Notizvorlage beim manuellen Start vorbelegen), `ReportService` (Filter nach Tag; Budgetverbrauch je Projekt; Betrag = Minuten × Satz, **gerundet im Bericht, nicht in den Rohdaten** – wie Clockify, belegt).

**Budgetwarnung:** bei 80 % und 100 % einmal eine Rückfrage `reminder` (Rückfragen-Zentrale).

**Oberfläche:** Seite *Tätigkeiten & Projekte* (Tags, Projekt-Budget/Satz/abrechenbar), *Zeitjournal* (Tag-Auswahl je Eintrag, Filter), *Statistik* (Reiter „Projekte & Budget“, Beträge nur wenn Satz gesetzt). CSV-Export bekommt Spalten `tags`, `billable`, `amount`.

### Dateien / Tests / Doku
Migration `0007_tags_budgets.sql`, `repositories.py`, `catalog_service.py`, `tracking_service.py`, `reporting_service.py`, `export_service.py` (CSV-Spalten, Sicherung Schema 3/4), API + Client, Views; Tests je Dienst und GUI (Tag-Eindeutigkeit, Standard-Tags, Budgetwarnung einmalig, Rundung nur im Bericht); Doku (Handbuch, API, Datenmodell, CSV-Spaltenliste, Sicherungsformat).

### Risiken
Migration ändert Tabellen (SQLite `ALTER TABLE ADD COLUMN` genügt) → Test mit Bestandsdaten; CSV-Spalten ändern das Format → `schema_version`/Spaltenliste dokumentieren und Tests anpassen.

### Abnahme
A-24: Tags, Vorlagen, Budget und Betrag verhalten sich in den Testfällen wie beschrieben; bestehende Daten bleiben nach der Migration unverändert.

---

## 11. AP-42 PDF-Bericht und Kalender-Import

**Anforderungen:** F-37 (PDF-Bericht), F-38 (ICS-Import als Vorschlag).

### Warum
Berichte für Kunden/Arbeitgeber werden oft als PDF verlangt (bei EARLY ein bezahltes Merkmal, belegt). Kalendertermine als **Vorschläge** für Einträge zu übernehmen spart Nacharbeit (EARLY wandelt Termine in Einträge um, belegt) und passt zu „lokal“, wenn der Anwender jeden Vorschlag **bestätigt**.

### Schritt 0: Vorprüfung
1. PDF-Bibliothek: `fpdf2` 7.3.2 (**BSD-2-Clause, belegt**; reines Python, Umlaute mit eingebetteter TTF – Core-Fonts sind Latin-1, € geht nicht **[U]**; Diagramme als eingebettetes PNG), `reportlab` (BSD **[U]**, Diagramme eingebaut), `weasyprint` (braucht GTK/Pango, unter Windows aufwendig **[U]** – nicht empfohlen) oder **Browser-Druck** (druckoptimierte HTML-Seite, null Abhängigkeiten, aber nicht automatisierbar). **Entscheidung: zuerst Browser-Druck** (Variante 0, kein Extra), danach `fpdf2` als Extra `pdf` mit gebündelter, **lizenzgeprüfter** TTF (Inter ist unter OFL und bereits lokal vorhanden) und Diagrammen als PNG. Die Recherche empfahl `fpdf2` als Hauptweg; der Browser-Druck ist hier nur der **risikoarme erste Schritt**.
2. ICS: `icalendar` 7.0.x (BSD-2-Clause **[U]**, Version/Lizenz vor Festlegung erneut prüfen), Serientermine mit `recurring-ical-events` **[U]** (gibt Vorkommen für ein **Zeitfenster** zurück; Expansion **nur im Fenster**). Zeitzonen: `TZID`/`VTIMEZONE` wird teils nur über Namen aufgelöst; **floating**-Zeiten und **ganztägige** Termine (`DATE` statt `DATETIME`) explizit behandeln, die gewählte Anzeige-Zeitzone als Standard. **Sicherheit beim Parsen fremder Dateien:** Größenlimit, Anzahl der Vorkommen je Regel begrenzen (Endlosregeln ohne `UNTIL`/`COUNT`), Zeitfenster Pflicht, **keine** URLs aus `ATTACH` öffnen, Fehler in eigene Ausnahmen übersetzen.

### Entwurf
**PDF/Druck:** `application/report_render.py` erzeugt ein neutrales Berichtsmodell (Kopf, Zeitraum, Tabelle je Tätigkeit/Projekt, Summe, Saldo, Beträge falls vorhanden, Hinweise zu *unsicheren* Zeiten). Zwei Ausgaben: (a) **druckoptimiertes HTML** im Dashboard (Seite *Statistik* → „Bericht drucken“) und (b) optionales PDF per `fpdf2` (Download-Knopf). Kein Logo/Name ohne Eingabe des Anwenders; Kopfzeilen (Name, Firma) sind Einstellungen, **nie** erfundene Daten.

**ICS-Import:** Seite *Zeitjournal* → „Aus Kalender vorschlagen“: Datei wählen (≤ 2 MiB, ≤ 1000 Termine, Zeitraum ≤ 90 Tage) → `application/ics_import.py` parst **nur lesend**, wandelt in **Vorschläge** `(Beginn, Ende, Titel)` um, erkennt Überlappungen mit vorhandenen Einträgen, lässt je Vorschlag **Tätigkeit/Projekt wählen und bestätigen**; erst „Übernehmen“ legt `manual`-Einträge an (in **einer** Transaktion, mit Prüfspur). Nichts wird automatisch gebucht. Die Datei wird nie ausgeführt oder gespeichert.

### Dateien / Tests / Doku
`application/report_render.py`, `application/ics_import.py`, `dashboard/views/statistics.py`/`journal.py`, `pyproject.toml` (Extras `pdf`, `ics`), API (`POST /import/ics/preview`, `POST /import/ics/apply`), Client; Tests: Berichtsmodell (Summen = Statistik), HTML enthält keine Skripte/Fremdinhalte (Escapen), PDF-Datei beginnt mit `%PDF` und enthält Umlaute (nur mit Extra), ICS: Größenlimit, kaputte Datei, Zeitzonen, RRULE-Begrenzung, Überlappung, Atomarität; Doku (Handbuch, API, Sicherheit: fremde Dateien).

### Risiken
PDF-Aufwand/Schriften → zuerst Browser-Druck; ICS-Komplexität (RRULE) → Zeitraum- und Mengenlimit, bei Zweifel Termin überspringen und melden.

### Abnahme
A-25: Bericht (Druck/PDF) zeigt dieselben Summen wie die Statistik; ICS-Import legt nichts ohne Bestätigung an, behandelt Fehler verständlich und ist atomar.

---

## 12. AP-43 Hue erweitern und Bridge-Suche

**Anforderungen:** F-39 (Helligkeit, Farbtemperatur, Übergang, Szenen-Modus, Umschalten mit Zustand), F-40 (Bridge-Suche).

### Warum
Der Hue-Adapter schaltet heute Lampe/Raum/Szene **ein/aus bzw. aktiviert** Szenen. Im Alltag will man **Helligkeit** („Fokuslicht 80 %“), **Farbtemperatur** (warm/kalt), sanfte **Übergänge** und ein **echtes Umschalten** (an → aus, aus → an). Die IP der Bridge von Hand herauszusuchen ist die größte Hürde beim Einrichten.

### Schritt 0: Vorprüfung ([U]/[HW], alle gegen die eigene Bridge)
* **JSON-Formen** (Drittquellen, nicht offiziell geprüft): `PUT /clip/v2/resource/light/{id}` mit `{"on":{"on":true},"dimming":{"brightness":50.0},"color_temperature":{"mirek":300},"color":{"xy":{"x":0.3,"y":0.3}},"dynamics":{"duration":400}}` (Teilmengen erlaubt); `PUT …/grouped_light/{id}` (Raum/Zone; die `id` steht im Raum-Objekt unter `services`, `rtype` `grouped_light`); `PUT …/scene/{id}` mit `{"recall":{"action":"active|dynamic_palette|static","duration":1000,"dimming":{"brightness":80}}}`. Mirek-Bereich 153–500 **[U]**.
* **Rate-Limits** (Faustwerte, **[U]**): ca. 10 Anfragen/s für `light`, ca. 1/s für `grouped_light`; bei HTTP 429 Backoff.
* **Zustand lesen** für Toggle: `GET …/light/{id}` bzw. `…/grouped_light/{id}` (`on.on`). Ein Ereignisstrom (`/eventstream/clip/v2`, SSE) ist **nicht** nötig (v1).
* **Zertifikat:** Das bestehende Verfahren (Fingerabdruck beim Koppeln, „Vertrauen beim ersten Mal“) bleibt; ob Signify-Root-CA gebündelt werden soll **[U]**, ist eine Option für später.
* **Bridge-Suche:** mDNS `_hue._tcp.local` über `zeroconf` (LGPL **[U]**, optionales Extra `discovery`); Cloud-Fallback `https://discovery.meethue.com` (liefert `id` und `internalipaddress`; braucht Internet; der alte nupnp-Pfad ist laut Hue-Hinweis abgekündigt). **Manuelle IP bleibt Standard.**

### Entwurf
**Aktionen** (`infrastructure/integrations/hue.py`, `ActionSpec` erweitert, alles mit Hilfetext und Voreinstellung):
* Felder je Aktion `light`/`room`: `power` (`on`/`off`/`toggle`), `brightness` (0–100, leer = unverändert), `color_temperature` (`warm`/`neutral`/`cool` oder Kelvin 2000–6500 → Mirek, leer = unverändert, **erweitert**), `transition_ms` (0–10000, Voreinstellung 400, **erweitert**).
* `scene`: zusätzlich `mode` (`active` = Voreinstellung, `dynamic_palette` = dynamisch, **erweitert**), `brightness` (optional).
* `toggle` = **GET Zustand, dann PUT** das Gegenteil (`idempotent=False`, in der Oberfläche markiert; bei Fehler im GET kein PUT).

**Ratenbegrenzung:** Pro Verbindung ein Mindestabstand zwischen Anfragen (`min_interval_ms`, Voreinstellung 100; erweitert); HTTP 429 → als `IntegrationConnectionError` (sicher nicht ausgeführt → Wiederholung durch die Warteschlange).

**Bridge-Suche:** `Adapter.find_targets()` (neue optionale Methode, Standard: leere Liste) und `AdapterSpec.can_find`; Hue implementiert mDNS (wenn `zeroconf` installiert) und Cloud-Fallback (**nur auf Knopfdruck**, mit Hinweis „sendet eine Anfrage ins Internet“). API `POST /adapters/{kind}/find` → `{"items":[{"id","address","name"}]}`; Oberfläche: Knopf „Bridge suchen“ im Formular „Neue Verbindung“ füllt das Feld *Adresse*.

### Dateien / Tests / Doku
`infrastructure/integrations/hue.py` (+ `base.py` für `find_targets`), `api/routes.py`/`schemas.py`/`dashboard_client`, `dashboard/forms.py` und `views/connections.py` (Suchknopf), `pyproject.toml` (Extra `discovery`); Tests mit lokalem Fake-Bridge-Server (wie `test_adapter_hue.py`): JSON-Körper je Option, Toggle liest Zustand zuerst, 429-Verhalten, Mindestabstand, Suche mit Attrappe (mDNS/Cloud), „Extra fehlt“; Doku (Handbuch Kapitel 20, Setup-Anleitung des Adapters, `ADAPTER_ENTWICKLUNG.md` §3 `find_targets`, `QUELLEN_UND_GRENZEN.md`).

### Risiken
**[HW]** Alle Bodies sind an der echten Bridge zu prüfen; bis dahin als „nicht mit echter Bridge geprüft“ kennzeichnen. mDNS wird von manchen Routern/Firewalls blockiert → manuelle IP bleibt. Cloud-Suche verlässt das lokale Netz → nur auf ausdrücklichen Klick.

### Abnahme
A-26: Gegen den Test-Bridge-Server entsprechen die gesendeten Bodies den dokumentierten Formen; Toggle liest zuerst den Zustand. **[HW]** A-26b: An der echten Bridge funktionieren Raum+Helligkeit, Szene (aktiv/dynamisch) und Toggle.

---

## 13. AP-44 Aktionsketten und Bedingungen

**Anforderungen:** F-41 (mehrere Schritte pro Seite), F-42 (einfache Bedingungen: Zeitfenster, Wochentage).

### Warum
„Seite 3 = Fokusmodus“ heißt im Alltag **mehrere Dinge**: Licht auf 80 %, Musik an, Fokus-Timer starten. Home Assistant und Node-RED lösen das mit **Aktionssequenzen** (Liste von Schritten mit Verzögerung und Bedingung). Für OctaLedger genügt ein **schlankes** Modell: eine **geordnete Liste von Schritten** je Seite, optional mit Verzögerung und Zeitfenster.

### Schritt 0: Vorprüfung
Die bestehende Einzelaktion (`face_actions`) und die Warteschlange (`integration_jobs`, Schlüssel = Rohereignis-ID, Verfall 30 s, höchstens 50 wartend) **dürfen nicht brechen**. Klären: Wie interagiert ein **Verzögerungsschritt** mit dem Verfall von 30 s? **Entscheidung:** Die Frist gilt **ab Auslösung der Kette** (`chain_deadline`, Voreinstellung 30 s + Summe der Verzögerungen, höchstens 5 min); verspätete Schritte verfallen einzeln (Status `expired`).

### Entwurf
**Datenmodell (Migration 0008):** Neue Tabelle `face_action_steps(device_id, face, position, integration_id, label, params, delay_ms, continue_on_error, enabled, condition JSON NULL, revision)`; Migration kopiert jede bestehende `face_actions`-Zeile als **Schritt 1**; die Tabelle `face_actions` bleibt als **Sicht/Kompatibilität** erhalten (oder wird nach Test entfernt: Entscheidung in Schritt 0, Empfehlung: behalten bis AP-47, damit Sicherungen Schema 2 lesbar bleiben). `integration_jobs` bekommt `chain_id TEXT`, `step INTEGER`, `not_before TEXT` (frühester Sendezeitpunkt = Auslösung + Verzögerung).

**Auslösung:** `enqueue_face_action` (`application/outbox.py`) legt statt **eines** nun **alle aktivierten Schritte** an: alle in **einer** Transaktion mit dem Rohereignis; `idempotency_key = <Rohereignis-ID>#<Schritt>`; `next_attempt_at = not_before`. Die Bedingung wird **bei der Auslösung** ausgewertet (`domain/conditions.py`: Zeitfenster `von/bis` in lokaler Zeit inkl. über Mitternacht, Wochentage); nicht erfüllte Schritte werden gar nicht angelegt (und im Verlauf als „übersprungen: außerhalb des Zeitfensters“ vermerkt).

**Abbruch:** Ein **neuer Seitenwechsel desselben Würfels** setzt noch **nicht gesendete** Schritte der vorigen Kette auf `expired` („durch neue Seite ersetzt“) – sonst würde „Musik nach 10 s“ nach einem Wechsel noch laufen. **Fehler:** Schlägt ein Schritt endgültig fehl und `continue_on_error=false`, werden die **folgenden** Schritte derselben Kette `expired` („Vorheriger Schritt fehlgeschlagen“).

**Reihenfolge:** Der Dispatcher sendet weiterhin **nacheinander in Erzeugungsreihenfolge** je Würfel; `not_before` verhindert zu frühes Senden.

**Oberfläche:** Editor in **Seiten zuordnen** (Steuerungsmodus): Liste der Schritte (Verbindung, Aktion, Felder wie bisher), „Schritt hinzufügen“, Reihenfolge ändern (hoch/runter), Verzögerung (s), „bei Fehler weitermachen“, Bedingungs-Klappe „Nur zu bestimmten Zeiten“ (erweitert). Die Live-Ansicht zeigt die Kette („① Licht, ② nach 10 s Musik“) und den Fortschritt je Schritt; der Verlauf zeigt Kette und Schritt.

### Dateien
Migration `0008_action_steps.sql`, `domain/models.py` (`ActionStep`), `domain/conditions.py` (neu), `application/outbox.py`, `application/integration_service.py` (`assign_steps`, `process_due` beachtet `not_before`), `infrastructure/storage/repositories.py`, `api/routes.py` (`PUT /devices/{id}/actions/{face}` akzeptiert `steps`; Antwort enthält Schritte; alte Form bleibt für **einen** Schritt gültig), `dashboard/views/faces_actions.py` und `live.py`, `connections.py` (Verlauf), Sicherung Schema 3/4, Tests, Doku.

### Tests
Migration (bestehende Aktion → ein Schritt, Verhalten unverändert); Bedingung (Zeitfenster inkl. Mitternacht, Wochentage, Zeitzone/Sommerzeit); Auslösung legt n Aufträge in **einer** Transaktion an; Idempotenz je Schritt; Verzögerung (`not_before`) mit injizierter Uhr; Abbruch durch neuen Seitenwechsel; Fehler-Folge je `continue_on_error`; Verfall der Kette; Schlange begrenzt (50) zählt Schritte; GUI-Editor (hinzufügen, löschen, Reihenfolge); Rückwärtslesen alter Sicherungen.

### Risiken
Größte Änderung am Kern des Steuerungsmodus → **zuerst** reine Logik und Migration mit Tests, Oberfläche zuletzt. Mehrdeutigkeit „Verfall vs. Verzögerung“ ist oben entschieden und im Handbuch erklärt.

### Abnahme
A-27: Eine Seite mit drei Schritten (sofort, +2 s, +5 s) sendet sie in dieser Reihenfolge zu den richtigen Zeiten, ein Seitenwechsel bricht die unversandten ab, ein Zeitfenster überspringt Schritte außerhalb; bestehende Einzelaktionen funktionieren unverändert.

---

## 14. AP-45 Medien: Home-Assistant-Vorlagen und lokaler Player

**Anforderungen:** F-43 (Musik über Home Assistant), F-44 (lokaler Player).

### Warum
Musik zu triggern ist ein naheliegender Wunsch („Seite 4 = Fokus: Lampe + Lofi-Radio“). Es gibt zwei saubere Wege: **über Home Assistant** (erreicht Sonos, Cast, AirPlay und Smart-Displays, soweit Home Assistant sie kennt) und einen **lokalen Player** auf dem PC (Internetradio-Streams und eigene Dateien). **Nicht** vorgesehen sind YouTube-Download und Scraping (Nutzungsbedingungen, Wartung).

### Schritt 0: Vorprüfung ([U])
1. **Home Assistant:** `POST /api/services/media_player/play_media` mit `{"entity_id":"media_player.x","media_content_id":"<URL>","media_content_type":"music"}`, `volume_set` (`volume_level` 0–1), `media_pause`, `media_play`; Music Assistant: Dienstnamen (`music_assistant.play_media`, `media_type: radio`) gegen die HA-Doku prüfen. Der bestehende Adapter-Dienst **„beliebiger Dienst“** kann das schon; neu sind **Vorlagen mit Entdeckung** (Liste der `media_player`).
2. **Lokaler Player – Bibliothek wählen:** `miniaudio` (MIT **[U]**, reines `pip`-Paket mit enthaltener C-Bibliothek, **MP3/FLAC/WAV/Vorbis**, **kein AAC** **[U]** → viele Internetradios mit AAC wären nicht abspielbar; Stream-Download selbst bauen, Icy-Metadaten beachten); `python-vlc` (VLC muss installiert sein, **alle** Formate, schwerste Abhängigkeit); `python-mpv` (DLL nötig, sehr gut); Windows-MCI per `ctypes` (nur lokale Dateien). **Empfehlung:** Stufe 1 `miniaudio` (Extra `audio`), Stufe 2 „externer Player“ (VLC/mpv als **Subprozess** mit festem Programmpfad aus den Einstellungen) – Subprozess isoliert Abstürze.
3. Lautstärke: nur die **Player-Lautstärke** setzen, die Systemlautstärke nicht ändern (`pycaw` nur optional **[U]**).

### Entwurf
**a) Home-Assistant-Vorlagen** (in `homeassistant.py`): neue Aktionen `media_play` (Medienadresse, Gerät, Lautstärke optional), `media_pause`, `media_stop`, `media_volume` mit `choices_from=("media_player",)` (Entdeckung erweitert um die Kategorie `media_player`). Kein neuer Adapter.

**b) Lokaler Player als Adapter `player`** (`infrastructure/integrations/player.py`): Aktionen `play_url` (Adresse), `play_file` (Dateiwahl aus einer **freigegebenen Ordnerliste** der Einstellungen – nie freie Pfade), `stop`, `volume`. Ausführung in einem eigenen **Worker-Thread/Subprozess** (`agent/audio_worker.py`) mit Befehlswarteschlange (`queue.Queue`); der BLE-Loop und der Dispatcher rufen nur `put_nowait`. Pro Würfel/Verbindung höchstens **ein** laufender Stream; ein neuer Befehl ersetzt den alten. Fehler (Format nicht unterstützt, Stream nicht erreichbar) → verständliche Meldung im Verlauf.

**Sicherheit (Pflicht):** Nur `http`/`https`; keine Zugangsdaten in der Adresse; Host wird aufgelöst und gegen Loopback, Link-Local (169.254.x.x) und Metadaten-Adressen geprüft; **private LAN-Adressen** nur mit Einstellung „LAN-Adressen erlauben“ (Radio im Heimnetz ist legitim); Weiterleitungen begrenzt (≤ 3) und jeweils neu geprüft; Verbindungs-Timeout 5 s, Lese-Timeout, Abbruch bei maximaler Größe/Dauer (Stream-Puffer begrenzt); nur `audio/*`-Content-Types; **keine Download-/Speicherfunktion**. Dateien: nur aus freigegebenen Ordnern, keine Symlink-/`..`-Umgehung (aufgelöster Pfad muss unter dem Ordner liegen), Größenlimit.

**Oberfläche:** Verbindung „Lokaler Player“ (Grundeinstellung: Lautstärke-Voreinstellung; erweitert: erlaubte Ordner, LAN erlauben, externer Player); Aktionsvorlagen „Radiosender abspielen“ mit **Senderliste** (vom Anwender gepflegt; **keine** mitgelieferten Sender, um Rechte-/Aktualitätsfragen zu vermeiden – nur ein Beispiel in der Doku); Hinweis im Handbuch: „Spielen Sie nur Inhalte ab, deren Nutzung Ihnen erlaubt ist.“

### Dateien / Tests / Doku
`infrastructure/integrations/homeassistant.py` (Aktionen + Kategorie), `infrastructure/integrations/player.py`, `agent/audio_worker.py`, `infrastructure/integrations/urlcheck.py` (gemeinsame URL-Prüfung, auch für Webhook nutzbar), `registry.py`, `core/settings.py` (Ordnerliste, LAN-Schalter), `pyproject.toml` (Extra `audio`); Tests: URL-Prüfung (Loopback, Link-Local, Metadaten, Credentials, Schema, Redirects, LAN-Schalter), Dateizugriff (Ordnergrenze, `..`, Symlink), Player mit **Attrappen-Engine** (Befehle, Ersetzen, Stoppen, Fehler), HA-Aktionen gegen den Fake-HA-Server (Bodies), „Extra fehlt“; Doku (Handbuch, Setup-Anleitung, `SECURITY.md`, `QUELLEN_UND_GRENZEN.md`: AAC-Grenze, Rechtehinweis).

### Risiken
**[HW]** Tatsächliche Wiedergabe nur am echten Gerät prüfbar; AAC-Radios laufen mit `miniaudio` evtl. nicht → externer Player als Ausweg und ehrlicher Hinweis. SSRF-Schutz ist sicherheitskritisch → eigene, ausführlich getestete Funktion.

### Abnahme
A-28: Die URL-Prüfung lehnt alle gefährlichen Ziele ab; Befehle erreichen die (Attrappen-)Engine in richtiger Reihenfolge ohne den BLE-Loop zu blockieren; HA-Medienaktionen senden die dokumentierten Bodies. **[HW]** A-28b: Ein MP3-Radiostream und eine lokale Datei spielen am PC; ein HA-`media_player` spielt eine Stream-Adresse.

---

## 15. AP-46 Vorlagen und Rezepte: Node-RED und Open Source

**Anforderungen:** F-45 (Webhook-Vorlagen, Rezepte für Node-RED und weitere).

### Warum
**Node-RED** und die meisten Open-Source-Brücken (Zigbee2MQTT, Tasmota, ESPHome, WLED, Shelly, openHAB, ioBroker) sind **bereits** über **Webhook** und **MQTT** erreichbar. Ein eigener Adapter wäre unnötig; was fehlt, ist **Anleitung** und **Vorlagen**, damit die Einrichtung ein Klick statt Handarbeit wird.

### Schritt 0: Vorprüfung ([U], jeweils gegen die Doku des Projekts und praktisch)
* Node-RED: HTTP-In ist standardmäßig ungeschützt; `httpNodeAuth` (Basic Auth, **ein** Benutzer) oder eigene Prüfung im Flow (Header) oder Reverse Proxy (laut Node-RED-Doku). Beispiel-Flow-JSON **erst nach praktischem Test** veröffentlichen.
* WLED: JSON-HTTP `POST /json/state` **[U]**; Shelly Gen2: `GET/POST /rpc/Switch.Set?id=0&on=true` **[U]**; openHAB: `POST /rest/items/<item>` mit Text-Body **[U]**; ioBroker `simple-api` **[U]**; Zigbee2MQTT: Thema `zigbee2mqtt/<name>/set` (bereits im MQTT-Setup-Text).

### Entwurf
**Vorlagen (Presets) in der Selbstbeschreibung:** `AdapterSpec.presets: tuple[Preset, ...]` mit `Preset(id, label, description, params)`; die Oberfläche (`dashboard/forms.py`/`faces_actions.py`) zeigt ein Auswahlfeld **„Vorlage“** über den Aktionsfeldern und füllt sie (der Anwender kann danach alles ändern). Webhook-Vorlagen: „Node-RED (HTTP-In, POST JSON)“, „WLED an/aus“, „Shelly Gen2 an/aus“, „openHAB Item setzen“, „Home-Assistant-Webhook“; MQTT-Vorlagen: „Zigbee2MQTT Lampe an/aus“, „Tasmota Power“, „ESPHome“. Jede Vorlage nennt in der Beschreibung, **was am Ziel nötig ist**.

**Nutzlast mit Platzhaltern (Webhook/MQTT):** optional `{face}`, `{label}`, `{device}`, `{time}` im Inhalt (rein textuelle Ersetzung mit Whitelist, **keine** Ausdrücke) – damit ein Node-RED-Flow eine Seite unterscheiden kann: `{"device":"{device}","face":{face},"label":"{label}","time":"{time}"}`.

**Rezeptbuch** `docs/REZEPTE.md` (neues Dokument): Node-RED (Flow-JSON, HTTP und MQTT, Absicherung), Zigbee2MQTT, WLED, Shelly, openHAB, ioBroker, Home-Assistant-Webhook, jeweils **Voraussetzung → Schritte in OctaLedger → Test → typische Fehler**; „nicht mit echtem Ziel geprüft“-Kennzeichnung je Rezept, bis geprüft.

### Dateien / Tests / Doku
`infrastructure/integrations/base.py` (`Preset`), `webhook.py`/`mqtt.py` (Vorlagen, Platzhalter-Ersetzung), `dashboard/forms.py`/`faces_actions.py`/`connections.py` (Vorlagenauswahl), `docs/REZEPTE.md`; Tests: Platzhalter nur Whitelist (unbekannter Platzhalter → Fehler, keine Ausdrucksauswertung), Vorlage füllt Felder und validiert, GUI-Auswahl; Doku (`ADAPTER_ENTWICKLUNG.md` §3 `presets`, Handbuch, Docs-Übersicht, `ORDNERSTRUKTUR.md`).

### Risiken
Rezepte veralten → mit Stand und „geprüft am“ versehen. Platzhalter dürfen **keine** Einschleusung (Header-/JSON-Injection) ermöglichen → JSON-Platzhalter werden **escaped** eingesetzt (`json.dumps`), Header-Platzhalter sind nicht erlaubt.

### Abnahme
A-29: Eine Vorlage füllt die Felder; Platzhalter werden nur aus der Whitelist ersetzt und JSON-sicher eingesetzt; `docs/REZEPTE.md` ist vollständig verlinkt und in der App lesbar.

---

## 16. AP-47 Optionale Pakete (nur auf Wunsch)

Jedes Paket wird **nur auf ausdrücklichen Wunsch** begonnen und ist unabhängig. Für jedes steht, **warum es optional ist** und **was vorher geklärt sein muss**.

| Paket | Anforderung | Warum optional | Vorab zu klären |
|---|---|---|---|
| **A) Spotify** | F-46 | Premium-Konto nötig (sonst Fehler `PREMIUM_REQUIRED`, belegt), OAuth (PKCE) mit Token-Speicherung, ein aktives Spotify-Gerät muss existieren | Entwickler-App-Registrierung durch den Anwender, Scope `user-modify-playback-state`, Token in `secrets.json` (unverschlüsselt!), Umgang mit Ablauf/Refresh; Nutzungsbedingungen |
| **B) Gesten aus der Beschleunigung** | F-47 | Die Beschleunigungs-Characteristic ist **nicht entschlüsselt** **[U][HW]** und nur per READ (Polling) lesbar → Schütteln/Doppelklopfen wäre unzuverlässig | Rohdaten am echten Würfel aufzeichnen (Diagnose), Abtastrate messen, Erkennbarkeit nachweisen; sonst verwerfen |
| **C) App-/Fenster-Auto-Tracker** | F-48 | Sehr datenintensiv; nur **opt-in und lokal** vertretbar | Datenschutz-Konzept (nur Prozessname, nie Fenstertitel/Inhalt; Aufbewahrung; Löschen), Rechtslage (Betriebsrat) |
| **D) Sonos/Cast direkt** | F-49 | Mit Home Assistant überflüssig; pro Hersteller eine Abhängigkeit (SoCo, pychromecast) | Nachweis, dass Home Assistant nicht infrage kommt |
| **E) Zwei-Geräte-Konflikte verfeinern** | – | Nur für Mehr-Würfel-/Mehr-Rechner-Nutzer | Regel „letzte Änderung gewinnt“ plus Überlappungsmarkierung |

## 17. Bewusst nicht geplant

* **LED des Würfels setzen**: Die Characteristic ist belegt (zeipy, `c7e70022`), aber das Format ist **[U]**, und **Schreibzugriffe auf den Würfel sind ausgeschlossen** (Projektregel; eine Nachbarschaft schaltet in den Firmware-Update-Modus). Eine Ausnahme bräuchte eine ausdrückliche Entscheidung samt Hardwareprüfung.
* **Firmware-Update, Umbenennen des Würfels (Schreiben des Gerätenamens)**: Schreibzugriff, nicht geplant.
* **YouTube-/Streaming-Dienst-Download (yt-dlp, Scraping)**: Nutzungsbedingungen und Wartungsaufwand (laut Recherche aus Sekundärquellen; nicht gegen den Originaltext geprüft).
* **Alexa direkt**: keine lokale API; nur über Home Assistant.
* **Cloud-Synchronisation, Mehrbenutzer, Netzwerkfreigabe der API**: widerspricht „lokal“ und dem Sicherheitskonzept.
* **Eigene Matter-/Google-Home-Anbindung**: bleibt über Home Assistant.
* **Auslesen eines Würfel-Speichers**: nach heutigem Wissen **nicht möglich** (kein Beleg einer Historie); falls die Hardwareprüfung etwas anderes zeigt, wird ein eigenes Paket geplant.

## 18. Querschnitt: Tests, Doku, Sicherheit, Hardware

**Tests (für jedes Paket):** Unit-Tests der reinen Logik mit injizierter Zeit; Dienst-Tests mit temporärer Datenbank; API-Tests (`TestClient`); GUI-Tests (`AppTest` gegen den echten API-Server, Fixture `api_server`); Wächtertests laufen automatisch (Docstrings, Endpunkte in `API.md`, Dateien in `ORDNERSTRUKTUR.md`, Hilfetexte an jedem Knopf/Feld). Hardware- und echte-Ziel-Tests sind **manuell** und stehen als Abnahmen mit **[HW]** im Testplan (`docs/TESTPLAN.md`, neue Abnahmen A-18 bis A-29).

**Dokumentation (für jedes Paket, im selben Schritt):** `API.md` (neue Endpunkte), `DATENMODELL.md` (Migration, Sicherungsformat), `ARCHITEKTUR.md` (neue Bausteine/Threads), `BENUTZERHANDBUCH.md` (Bedienung, Meldungen), `GLOSSAR.md` (neue Begriffe), `SOFTWAREDOKUMENTATION.md` (neuer Abschnitt), `SECURITY.md` (neue Risiken), `QUELLEN_UND_GRENZEN.md` (ungeprüfte Punkte), `CHANGELOG.md`, `FORTSCHRITT.md` (mit Hash im **nächsten** Commit), in der Oberfläche: Hilfetexte mit Voreinstellung, „So funktioniert diese Seite“.

**Sicherung/Format:** Jede Änderung am Datenbestand erhöht die Sicherungsversion **nur wenn nötig** (Schema 3 ab AP-37: `device_buttons`; spätere Pakete ergänzen Abschnitte); ältere Versionen bleiben **lesbar** (fehlende Abschnitte = leer), und `schema_version` wird beim Laden validiert.

**Sicherheit (Querschnitt):** Alle neuen Eingaben strikt validiert (`extra="forbid"`), alle neuen Netzwerkziele mit Zeitlimits, Größenlimits, ohne Weiterleitungen/Proxys, SSRF-Schutz für beliebige Adressen; **keine** neuen BLE-Schreibzugriffe; Zugangsdaten nur im `SecretStore`; fremde Dateien (ICS, Sicherungen) nie ausführen; optionale Zusatzbibliotheken mit geprüfter Lizenz.

**Ehrlichkeitsregel:** Nichts wird als „hardwaregeprüft“ oder „mit echtem Ziel geprüft“ bezeichnet, bevor es so geprüft wurde; jedes [U] wird beim Bauen durch Primärquelle oder Test ersetzt und das Ergebnis dokumentiert.
