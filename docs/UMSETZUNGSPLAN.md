# OctaLedger – Umsetzungsplan der Erweiterungen (AP-35 bis AP-50)

Dieser Plan beschreibt **der Reihe nach**, was als Nächstes gebaut werden soll – jeweils mit **Warum**, **Was**, **Wo** (Module und Dateien), **Wie** (Entwurf, Daten, Schnittstelle, Oberfläche), **Tests**, **Dokumentation**, **Risiken** und **Abnahme**. Die zugehörigen Anforderungen (F-21 bis F-63) stehen im [Pflichtenheft](PFLICHTENHEFT.md) §12.

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
16. [AP-48 bis AP-50 Musik-Modus (eigenständiger Modus)](#16-ap-48-bis-ap-50-musik-modus-eigenständiger-modus)
17. [AP-47 Optionale Pakete (nur auf Wunsch)](#17-ap-47-optionale-pakete-nur-auf-wunsch)
18. [Bewusst nicht geplant](#18-bewusst-nicht-geplant)
19. [Querschnitt: Tests, Doku, Sicherheit, Hardware](#19-querschnitt-tests-doku-sicherheit-hardware)
20. [AP-51 bis AP-56 Würfel-Cockpit: mehrere Würfel, Batterie, Inspektor](#20-ap-51-bis-ap-56-würfel-cockpit-mehrere-würfel-batterie-inspektor)

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
| PDF | `fpdf2` | 2.9.0 (installiert) | **LGPL-3.0-only** (Korrektur: die Recherche nannte BSD-2; die Paket-Metadaten sagen LGPL) | reines Python; optionales Extra, nur dynamisch geladen |
| ICS | `icalendar` | 7.3.2 (installiert) | BSD-2-Clause (Paket-Metadaten) | – |
| ICS-Serien | `recurring-ical-events` | 3.8.2 (installiert) | **LGPL-3.0-or-later** (Paket-Metadaten) | optionales Extra, nur dynamisch geladen |

Empfehlung der Recherche für **Toast**: `windows-toasts`, falls die Lizenz bestätigt wird, sonst `winotify` (MIT); beide hinter dem `Notifier`-Protokoll (3.3). Für **PDF** empfahl die Recherche `fpdf2` mit gebündelter TTF und Diagrammen als PNG; dieser Plan beginnt trotzdem mit dem **Browser-Druck** (keine Abhängigkeit) und nimmt `fpdf2` als Extra hinzu.

## 2. Reihenfolge und Abhängigkeiten

```text
AP-35 Eingang robuster ──► AP-36 Verlust + Rückfragen ──► AP-38 Arbeitstag ──► AP-39 Tray/Toast/Autostart
        │                          │                              │
        └─► AP-37 Taste + Batterie ┘                              └─► AP-40 Soll-Zeit ──► AP-41 Tags/Budget ──► AP-42 PDF/ICS

AP-43 Hue ──► AP-44 Aktionsketten ──► AP-45 Medien ──► AP-46 Rezepte      (Funktion A, unabhängig von Funktion B)
                                          │
AP-35 ──► AP-45 ──► AP-48 Musik-Modus ──► AP-49 Spotify, AP-50 Browser-Player   (Funktion M, eigenständiger Musik-Modus;
                       (F-62 braucht zusätzlich AP-36)                          darf vor AP-36 bis AP-44 gebaut werden)
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
| 47 | Optionale Pakete | A + B | F-47 bis F-49 | je nach Paket | [HW] |
| 48 | **Musik-Modus Kern** (PC lokal, Home Assistant) | M | F-51 bis F-55, F-57, F-59 bis F-63 | 0009 | [HW] Halterung |
| 49 | **Spotify direkt** | M | F-56 | – | [HW] |
| 50 | **Browser-Player für YouTube Music** | M | F-58 | – | [HW] Browser |
| 51 | **Würfel-Identität und ausgewählter Würfel** (Farbe, Banner, Auswahl überall gleich) | C | F-64, F-65 | 0010 | – |
| 52 | **Batterie-Cockpit** (immer sichtbar, gespeichert, Warnungen, Schätzung) | C | F-66 | 0011 | [HW] |
| 53 | **Funktionsbereiche** (Zeit, Smarthome, Musik unterscheiden und umschalten) | C | F-67 | – | – |
| 54 | **Würfel-Inspektor** (klickbarer Würfel, Einstellungen je Seite, Neuprogrammieren) | C | F-68, F-69 | – | – |
| 55 | **Mehrere Würfel parallel** (Vorrangregeln für Musik und Ziele, Konfliktprotokoll) | C | F-70 | 0012 | [HW] |
| 56 | **Würfel auslesen** (alle lesbaren Daten, Datenblatt; Schreiben nur belegt) | C | F-71, F-72 | 0013 | [HW] |

**Warum diese Reihenfolge:** Zuerst die Fehlerquellen, die **Daten verfälschen** (AP-35/36: falsche oder fehlende Zeiten), dann die Bedienung (Taste, Tray, Erinnerungen), dann die Auswertung (Soll-Zeit, Berichte), zuletzt der Ausbau von Funktion A (Hue, Ketten, Medien). Funktion A, B und der Musik-Modus M sind **unabhängig**; wer zuerst Smarthome möchte, darf AP-43 bis AP-46 vorziehen (sie hängen nur von AP-26 bis AP-31 ab, die schon fertig sind).

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

## 16. AP-48 bis AP-50 Musik-Modus (eigenständiger Modus)

**Anforderungen:** F-51 bis F-63 (Pflichtenheft §12.6). **Auftrag des Anwenders:** Ein **separater, eigenständiger Modus** zur Musiksteuerung: **jede Würfelseite bekommt einen eigenen Titel** (Musikdienste wie Spotify, Radio, YouTube Music …), und **steht der Würfel in seiner Halterung (auf keiner Seite), hält die Musik ganz an.** Wiedergabe-Ziele nach Entscheidung des Anwenders: **am PC (lokaler Player)**, **über Home Assistant (Boxen/Displays, Cast)** und **Spotify direkt**; **YouTube Music** wahlweise **über Home Assistant/Cast** oder **mit einem Player in der App (Browser)**.

### 16.1 Warum ein eigener Modus (und nicht „Steuerungsmodus mit Musikaktion“)
Der Steuerungsmodus löst pro Seite eine **einmalige Aktion** aus („Licht an“). Musik ist **Zustand**: Es spielt etwas, bis etwas anderes spielt oder **die Seite verlassen wird**. Daraus folgen Regeln, die dort fehlen: (1) **Eine Seite ersetzt die vorige** (kein Überlagern), (2) **die Halterung (keine Seite) beendet die Wiedergabe**, (3) ein Wechsel **zwischen verschiedenen Zielen** (Spotify → Radio am PC) muss das **vorherige Ziel stoppen**, sonst spielen zwei Quellen gleichzeitig, (4) „läuft gerade“ muss sichtbar und abrufbar sein. Technisch **wiederverwenden** wir die vorhandene Warteschlange, den Dispatcher, die Adapter und den Verlauf (zuverlässig, einmalig, mit Verfall und Wiederholung) – nur die **Regeln der Auslösung** sind neu.

### 16.2 Gesamtentwurf

**Modus.** `DeviceMode.MUSIC = "music"` als **dritte** Betriebsart je Würfel (neben `time`, `control`). Es gilt dieselbe Trennung wie beim Steuerungsmodus: Ein Musik-Würfel erzeugt **nie** Zeiteinträge, kann nicht der aktive Zeit-Würfel sein, wird beim Start des Agenten wie ein Steuerungs-Würfel automatisch verbunden (`AgentRuntime`). Moduswechsel im Dialog „Wofür benutzen Sie diesen Würfel?“ der Seite *Seiten zuordnen* (dritte Wahl **„Musik“**), ebenso in der Geräte-Anzeige, Statusleiste und Live-Ansicht. Migration: `devices.mode` hat eine CHECK-Bedingung `('time','control')` → Migration (Neuaufbau der Tabelle, Daten übernehmen) erlaubt `'music'`.

**Ziele („Wiedergabe-Ziele“).** Ein Ziel ist eine **Verbindung** (wie bisher, Tabelle `integrations`) einer **musikfähigen Art**. Eine Art ist musikfähig, wenn ihr Adapter die **Musik-Aktionen** `music_play` (Titel/Quelle, Lautstärke), `music_stop` (**ganz anhalten**) und optional `music_pause`/`music_volume` anbietet (`ActionSpec.capability="music"`, damit die Oberfläche musikfähige Verbindungen erkennt). Vorgesehene Ziele:

| Ziel (`kind`) | Wiedergabe | Quellen | Paket |
|---|---|---|---|
| `player` (**PC lokal**) | eigener Player im Agenten (AP-45) | Internetradio-Streams, Dateien aus freigegebenen Ordnern | AP-45 + AP-48 |
| `homeassistant` | `media_player.*` über Home Assistant (Sonos, Cast, AirPlay, Displays) | Stream-Adressen, Medien-IDs (auch `spotify:…`, soweit die HA-Integration sie versteht **[U]**), **YouTube/YouTube Music über Cast** **[U][HW]** | AP-45 + AP-48 |
| `spotify` | Spotify Web API auf einem aktiven Spotify-Gerät | Spotify-Titel/-Alben/-Playlists (Link oder URI) | AP-49 |
| `browser` | **Player in der App** (Dashboard-Seite „Musik-Player“, YouTube-IFrame-Player) | YouTube-/YouTube-Music-Links (Videos/Titel) | AP-50 |

**Titel je Seite.** Eine Seite hat **einen** Titel: Quelle + Ziel + Lautstärke (+ Wiederholen/Zufall, wo das Ziel es kann). Gespeichert wie die Seitenaktionen: `face_actions` mit `params = {"action":"music_play", "source":{…}, "volume":60}` und `label` = Anzeigename („Lofi Radio“). **Kein neues Datenmodell nötig** (und mit AP-44 später auch als Schritt einer Kette möglich). Zusätzlich je Würfel `music_settings` als Zeilen in `app_state` (`music:<device_id>` JSON): `base_action` (**`stop`** = Voreinstellung, `pause`), `stop_delay_ms` (0), `default_volume` (50).

**Quellen-Eingabe und Link-Erkennung** (`domain/music_source.py`, rein, ohne I/O): Der Anwender **fügt einen Link ein**; die Funktion erkennt und normalisiert:
* `https://open.spotify.com/track|album|playlist|artist/<id>` → `spotify:<typ>:<id>` (Ziel `spotify`/`homeassistant`).
* `https://music.youtube.com/watch?v=<id>` und `https://www.youtube.com/watch?v=<id>` / `youtu.be/<id>` (+ `list=<id>`) → `youtube:<id>` (Ziel `browser`/`homeassistant`).
* Stream-Adressen `http(s)://…` → `url:<adresse>` (Ziel `player`/`homeassistant`).
* Datei: Auswahl aus den **freigegebenen Ordnern** (AP-45) → `file:<relativer Pfad>`.
Unerkanntes wird **abgelehnt mit Erklärung** (nie geraten). Alle Adressen gehen durch die **URL-Prüfung** aus AP-45 (nur http/https, SSRF-Schutz, keine Zugangsdaten in der Adresse).

**Auslöse-Regeln** (`application/music_service.py`, reine Entscheidung in `domain/music.py::decide(prev, event, settings) -> list[MusicCommand]`; der `TrackingService` ruft sie für Musik-Würfel, so wie `_control_event` für Steuerungs-Würfel):

| Ereignis | Entscheidung |
|---|---|
| Seitenwechsel auf Seite *n* mit Titel | falls bisher **ein anderes Ziel** spielt: `music_stop` an dieses Ziel; dann `music_play` mit dem Titel von *n* (Aufträge in einer Transaktion mit dem Rohereignis, in dieser Reihenfolge) |
| Seitenwechsel auf Seite ohne Titel | **anhalten** wie in der Halterung (Voreinstellung; die Seite ist eine „Stille-Seite“) |
| **Würfel in der Halterung** (`NEUTRAL`, Rohwert 0 oder 10, siehe AP-35) | `music_stop` (oder `music_pause` je `base_action`) an **alle** Ziele, die dieser Würfel benutzt; nur wenn etwas spielt (`music_now` gesetzt), nach `stop_delay_ms` |
| Verbindungsabbruch | keine sofortige Aktion; **nach der Frist** (AP-36, Housekeeper) `music_stop` – eine Musik, die ohne Würfel weiterläuft, ist unerwartet (F-62) |
| Baseline nach dem Verbinden | löst **nichts** aus (wie überall); liegt der Würfel in der Halterung und `music_now` ist gesetzt, wird gestoppt |
| gleiche Seite nochmals gemeldet (Duplikat) | nichts (Entprellung/Duplikatregel existiert) |

**„Läuft gerade“:** Nach erfolgreichem `music_play` setzt der `IntegrationService` (Ergebnis des Auftrags) `app_state` `music_now:<device_id> = {face, label, target_id, since}`; nach `music_stop` wird es gelöscht. API `GET /music/state` (alle Würfel, mit Titelname), Anzeige in **Würfel live** („♪ Lofi Radio, Seite 3, seit 12:04“), Statusleiste, Tray-Tooltip (AP-39) und Übersicht. Ein fehlgeschlagener Auftrag lässt `music_now` **unverändert** und erscheint im Verlauf.

**Reihenfolge-Garantie.** Der Dispatcher sendet je Würfel **nacheinander in Erzeugungsreihenfolge** (existiert) – „Stopp Spotify, dann Play Radio“ kommen in dieser Reihenfolge an. Wiederholung nur bei „sicher nicht angekommen“ (existiert). **Verfall 30 s** gilt auch hier: Eine Radio-Adresse, die erst nach einer halben Minute gestartet würde, ist falsch (keine „späte“ Musik).

### 16.3 AP-48 Musik-Modus Kern (Ziele: PC lokal, Home Assistant)

**Voraussetzungen:** **AP-35** (Rohwerte 0/10 = Halterung → `NEUTRAL`; **ohne diese Zuordnung erkennt der Modus die Halterung nicht**) und **AP-45** (Player und Home-Assistant-Medienaktionen, URL-Prüfung). Für F-62 zusätzlich AP-36 (Housekeeper).

**Schritt 0 Vorprüfung [HW]:** (1) Am **echten Würfel** prüfen, welcher Rohwert in der Halterung kommt (0 und/oder 10, **oder gar keine Meldung**). **Fällt das aus**, muss die Halterung anders erkannt werden – Rückfalloption: **eine Seite als „Stopp“** festlegen (jede Seite ohne Titel hält an, siehe Tabelle) und im Handbuch erklären. (2) Home-Assistant-Aufrufe für Spotify-/YouTube-Inhalte an der eigenen Installation testen **[U]**.

**Entwurf:** neue Dateien `domain/music.py`, `domain/music_source.py`, `application/music_service.py`; `domain/models.py` (`DeviceMode.MUSIC`); Migration `0009_music_mode.sql` (CHECK-Bedingung von `devices.mode`; Tabelle neu aufbauen); `application/tracking_service.py` (Zweig für `DeviceMode.MUSIC`, neue `Outcome`-Werte `MUSIC_COMMANDED`, `MUSIC_STOPPED`); `application/outbox.py` (Auftragsreihe mit „Stop vor Play“); `application/integration_service.py` (`music_now` setzen/löschen aus dem Ergebnis); `infrastructure/integrations/base.py` (`ActionSpec.capability`), `player.py` und `homeassistant.py` (Musik-Aktionen `music_play`/`music_stop`/`music_pause`/`music_volume`; AP-45 liefert die Grundlage); `api/routes.py` (`PUT /devices/{id}/mode` akzeptiert `music`; `GET /music/state`; `PUT /devices/{id}/music` für `music_settings`; `POST /music/parse` prüft einen eingefügten Link und gibt die erkannte Quelle zurück – **ändert nichts**), Client; `dashboard/views/faces.py`/`faces_actions.py` (Musik-Editor je Seite: Link einfügen oder Sender/Datei wählen → Erkennung anzeigen → Ziel wählen → Lautstärke → *Ausprobieren* (spielt 10 s und stoppt) → Speichern), `live.py`, `shell.py`, `devices.py`, `overview.py`; **Seite „Musik“ unter *Würfel*?** – nein: bewusst **keine neue Seite**, sondern der dritte Modus in **Seiten zuordnen** (ein Ort für „Seiten belegen“), plus Einstellungen „Musik“ (Basis-Verhalten, Standardlautstärke) im erweiterten Bereich des Musik-Würfels.

**Tests:** Reine Logik `decide` (Tabelle oben vollständig, inkl. Zielwechsel, Stille-Seite, Duplikat, Baseline, `stop_delay_ms`, `pause` statt `stop`); `music_source` (Spotify-/YouTube-/Stream-Links, Müll, Injektion, Länge); `TrackingService` (Musik-Würfel erzeugt **nie** Zeit; Seitenwechsel reiht Stop+Play in einer Transaktion ein; Halterung stoppt alle benutzten Ziele nur wenn etwas spielt; Verbindungsabbruch ohne Sofortaktion); Dispatcher (Reihenfolge Stop vor Play, Verfall, Wiederholung); `music_now` gesetzt/gelöscht; API (Parse, State, Moduswechsel, 409 bei laufender Zeit wie beim Steuerungsmodus); GUI (Editor, Erkennung, Ausprobieren, Live-Anzeige); Migration (alte Würfel bleiben `time`/`control`). Alle mit Attrappen-Zielen (Fake-Player, Fake-HA-Server).

**Risiken:** **[HW]** Halterungs-Erkennung (siehe Schritt 0) ist die Kernannahme. Zwei Quellen gleichzeitig bei Fehlern → Stop-Aufträge an alle benutzten Ziele sind die Sicherung. **[U]** Spotify/YouTube über Home Assistant hängt von dessen Integrationen ab.

**Abnahme:** A-30 bis A-33 (Pflichtenheft §12.6).

### 16.4 AP-49 Spotify direkt

**Warum eigenes Paket:** Es braucht **OAuth**, Token-Speicherung und Wartung; deshalb nach dem Kern.

**Schritt 0 Vorprüfung [U]:** Die Spotify-Bedingungen und das aktuelle Anmeldeverfahren **gegen die offizielle Entwicklerdoku prüfen** (Stand 2026): Registrierung einer **eigenen Entwickler-App durch den Anwender** (Client-ID; **kein** Geheimnis nötig bei PKCE), **Redirect-URI** (Loopback-Adresse `http://127.0.0.1:<Port>/…` – ob und wie Spotify sie heute zulässt, ist zu belegen), Scope `user-modify-playback-state` (und `user-read-playback-state` zum Lesen des Geräts), **Premium-Pflicht** (sonst Fehler `PREMIUM_REQUIRED`, belegt aus der Recherche), ein **aktives Gerät** (die Spotify-App am PC muss laufen; sonst `NO_ACTIVE_DEVICE`), `device_id` immer mitgeben (belegt). Endpunkte **[U]**: `PUT /v1/me/player/play` mit `{"uris":[…]}` oder `{"context_uri":…}`, `PUT /v1/me/player/pause`, `PUT /v1/me/player/volume?volume_percent=`, `GET /v1/me/player/devices`.

**Entwurf:** Adapter `spotify` (`infrastructure/integrations/spotify.py`) mit Feldern *Client-ID* (Grundangabe), *Gerät* (Auswahl aus „Geräte auflisten“; leer = aktives), Kopplung `pair()` = **PKCE-Ablauf**: der Agent öffnet für höchstens 2 Minuten einen **Loopback-Empfänger** auf einem zufälligen Port (nur `127.0.0.1`, einmaliger `state`-Wert, schließt nach dem ersten Aufruf), die Oberfläche zeigt den Anmeldelink; das **Refresh-Token** kommt in den `SecretStore` (**unverschlüsselt wie alle Zugangsdaten – ausdrücklich im Hinweis nennen**), Access-Tokens nur im Speicher, automatische Erneuerung. Aktionen `music_play` (Spotify-URI), `music_stop` (= **Pause**, denn Spotify kennt kein „Beenden“ – ehrlich dokumentiert; zusätzlich Position bleibt), `music_volume`. Fehlertexte deutsch mit Handlungshinweis (Premium, Gerät, Abmeldung → „Neu anmelden“).

**Tests:** Gegen einen **Fake-Spotify-Server** (lokale HTTP-Attrappe): PKCE-Austausch, `state`-Prüfung (falsch → abgelehnt), Token-Erneuerung, `PREMIUM_REQUIRED`, `NO_ACTIVE_DEVICE`, Retry-Regeln (nur bei sicherem Nichtankommen), Geheimnisse nie in Meldungen/Protokoll; GUI-Kopplung.

**Risiken:** Bedingungen/Verfahren ändern sich → Schritt 0; Token unverschlüsselt → Hinweis, eigener Widerruf in den Spotify-Kontoeinstellungen erklären; Premium-Pflicht → klare Meldung.

**Abnahme:** A-34. **[HW]** A-34b: Mit echtem Konto spielt eine Seite einen Titel auf dem PC-Gerät, die Halterung pausiert.

### 16.5 AP-50 Browser-Player für YouTube Music (Player in der App)

**Warum und Grenze (ehrlich):** YouTube Music hat **keine offizielle Schnittstelle**; ein Abspielen per Download-Werkzeug ist ausgeschlossen (Nutzungsbedingungen, laut Sekundärquellen). Erlaubt und üblich ist das **Einbetten** über den **YouTube-IFrame-Player** **[U]**. Dafür läuft der Player **im Browser der App** – **er spielt nur, solange die Seite „Musik-Player“ des Dashboards geöffnet ist** (der Agent kann einen Browser nicht fernsteuern). Das ist die Preis-/Wirkungs-Abwägung des Anwenders für „eigener Player in der App“; die Alternative ist YouTube Music über Home Assistant/Cast (AP-48).

**Schritt 0 Vorprüfung [U][HW]:** (1) IFrame-Player-API (`https://www.youtube.com/iframe_api`, `YT.Player`, `loadVideoById`, `stopVideo`/`pauseVideo`, `setVolume`); (2) **Autoplay** wird von Browsern ohne Nutzergeste blockiert → die Seite braucht einmalig einen **Klick „Wiedergabe freischalten“**; ob Streamlits Komponenten-Iframe `autoplay` erlaubt, ist zu prüfen; (3) **nicht jedes Video ist einbettbar** (Fehler 101/150) – YouTube-Music-Titel, die nur dort liegen, evtl. nicht; die Oberfläche zeigt dann „nicht einbettbar“; (4) **Datenschutz:** Der Player lädt Skripte und Inhalte von youtube.com (Google erhält Anfragen). Das widerspricht der Projektregel „keine externen Quellen“ → **Ausnahme nur als ausdrückliches Opt-in** (Einstellung „YouTube-Player in der App erlauben“, Voreinstellung **aus**, mit Datenschutzhinweis).

**Entwurf:** Adapter `browser` (`infrastructure/integrations/browser.py`): hat **kein Netzwerkziel**; `music_play` schreibt den **gewünschten Zustand** `{video_id, list_id?, volume, nonce}` nach `app_state` (`music_browser`), `music_stop` setzt `{stopped, nonce}`; `check()` gelingt immer. API `GET /music/browser-state`. Dashboard-Seite **„Musik-Player“** (Untergruppe *Alltag*, nur sichtbar, wenn das Opt-in aktiv ist): ein Fragment (`st.fragment(run_every=1)`) liest den Zustand; **nur wenn sich `nonce` ändert**, wird die Komponente (`st.components.v1.html`) mit dem neuen Zustand **neu gezeichnet** (gleicher Inhalt = Iframe bleibt, Wiedergabe läuft ungestört); die Komponente enthält den IFrame-Player und stoppt bei `stopped`. **Der API-Token gelangt nie in den Browser:** Das Fragment (serverseitig) liest den Zustand, der Browser bekommt nur `video_id`, `volume`, `nonce`. Ohne geöffnete Seite zeigt die Live-Ansicht „Browser-Player nicht geöffnet – Musik wartet“.

**Tests:** Adapter (Zustand schreiben/stoppen, `nonce` wächst), Link-Parsing von YouTube-/YouTube-Music-Adressen (`watch?v=`, `youtu.be`, `list=`, Müll), API, GUI: Seite nur mit Opt-in sichtbar, Neuzeichnen **nur** bei neuem `nonce` (gleicher Zustand → gleicher Inhalt), Token taucht nicht im erzeugten HTML auf, Datenschutzhinweis vorhanden; HTML-Escaping der IDs (nur `[A-Za-z0-9_-]`, Länge begrenzt).

**Risiken:** **[HW]** Autoplay/Einbettung nur im echten Browser prüfbar; „läuft nur bei geöffneter Seite“ ist eine harte Grenze und wird in Oberfläche und Handbuch ausdrücklich gesagt; Streamlit-Rerender kann die Wiedergabe unterbrechen → Inhaltsgleichheit prüfen (Test).

**Abnahme:** A-35. **[HW]** A-35b: Im echten Browser startet nach „Freischalten“ ein einbettbares Video per Würfeldrehung, die Halterung stoppt es.

## 17. AP-47 Optionale Pakete (nur auf Wunsch)

Jedes Paket wird **nur auf ausdrücklichen Wunsch** begonnen und ist unabhängig. Für jedes steht, **warum es optional ist** und **was vorher geklärt sein muss**.

| Paket | Anforderung | Warum optional | Vorab zu klären |
|---|---|---|---|
| **A) Spotify** → jetzt **AP-49** (Musik-Modus) | F-46 → F-56 | Premium-Konto nötig (sonst Fehler `PREMIUM_REQUIRED`, belegt), OAuth (PKCE) mit Token-Speicherung, ein aktives Spotify-Gerät muss existieren | Entwickler-App-Registrierung durch den Anwender, Scope `user-modify-playback-state`, Token in `secrets.json` (unverschlüsselt!), Umgang mit Ablauf/Refresh; Nutzungsbedingungen |
| **B) Gesten aus der Beschleunigung** | F-47 | Die Beschleunigungs-Characteristic ist **nicht entschlüsselt** **[U][HW]** und nur per READ (Polling) lesbar → Schütteln/Doppelklopfen wäre unzuverlässig | Rohdaten am echten Würfel aufzeichnen (Diagnose), Abtastrate messen, Erkennbarkeit nachweisen; sonst verwerfen |
| **C) App-/Fenster-Auto-Tracker** | F-48 | Sehr datenintensiv; nur **opt-in und lokal** vertretbar | Datenschutz-Konzept (nur Prozessname, nie Fenstertitel/Inhalt; Aufbewahrung; Löschen), Rechtslage (Betriebsrat) |
| **D) Sonos/Cast direkt** | F-49 | Mit Home Assistant überflüssig; pro Hersteller eine Abhängigkeit (SoCo, pychromecast) | Nachweis, dass Home Assistant nicht infrage kommt |
| **E) Zwei-Geräte-Konflikte verfeinern** | – | Nur für Mehr-Würfel-/Mehr-Rechner-Nutzer | Regel „letzte Änderung gewinnt“ plus Überlappungsmarkierung |

## 18. Bewusst nicht geplant

* **LED des Würfels setzen**: Die Characteristic ist belegt (zeipy, `c7e70022`), aber das Format ist **[U]**, und **Schreibzugriffe auf den Würfel sind ausgeschlossen** (Projektregel; eine Nachbarschaft schaltet in den Firmware-Update-Modus). Eine Ausnahme bräuchte eine ausdrückliche Entscheidung samt Hardwareprüfung.
* **Firmware-Update, Umbenennen des Würfels (Schreiben des Gerätenamens)**: Schreibzugriff, nicht geplant.
* **YouTube-/Streaming-Dienst-Download (yt-dlp, Scraping)**: Nutzungsbedingungen und Wartungsaufwand (laut Recherche aus Sekundärquellen; nicht gegen den Originaltext geprüft).
* **Alexa direkt**: keine lokale API; nur über Home Assistant.
* **Cloud-Synchronisation, Mehrbenutzer, Netzwerkfreigabe der API**: widerspricht „lokal“ und dem Sicherheitskonzept.
* **Eigene Matter-/Google-Home-Anbindung**: bleibt über Home Assistant.
* **Auslesen eines Würfel-Speichers**: nach heutigem Wissen **nicht möglich** (kein Beleg einer Historie); falls die Hardwareprüfung etwas anderes zeigt, wird ein eigenes Paket geplant.

## 19. Querschnitt: Tests, Doku, Sicherheit, Hardware

**Tests (für jedes Paket):** Unit-Tests der reinen Logik mit injizierter Zeit; Dienst-Tests mit temporärer Datenbank; API-Tests (`TestClient`); GUI-Tests (`AppTest` gegen den echten API-Server, Fixture `api_server`); Wächtertests laufen automatisch (Docstrings, Endpunkte in `API.md`, Dateien in `ORDNERSTRUKTUR.md`, Hilfetexte an jedem Knopf/Feld). Hardware- und echte-Ziel-Tests sind **manuell** und stehen als Abnahmen mit **[HW]** im Testplan (`docs/TESTPLAN.md`, neue Abnahmen A-18 bis A-35).

**Dokumentation (für jedes Paket, im selben Schritt):** `API.md` (neue Endpunkte), `DATENMODELL.md` (Migration, Sicherungsformat), `ARCHITEKTUR.md` (neue Bausteine/Threads), `BENUTZERHANDBUCH.md` (Bedienung, Meldungen), `GLOSSAR.md` (neue Begriffe), `SOFTWAREDOKUMENTATION.md` (neuer Abschnitt), `SECURITY.md` (neue Risiken), `QUELLEN_UND_GRENZEN.md` (ungeprüfte Punkte), `CHANGELOG.md`, `FORTSCHRITT.md` (mit Hash im **nächsten** Commit), in der Oberfläche: Hilfetexte mit Voreinstellung, „So funktioniert diese Seite“.

**Sicherung/Format:** Jede Änderung am Datenbestand erhöht die Sicherungsversion **nur wenn nötig** (Schema 3 ab AP-37: `device_buttons`; spätere Pakete ergänzen Abschnitte); ältere Versionen bleiben **lesbar** (fehlende Abschnitte = leer), und `schema_version` wird beim Laden validiert.

**Sicherheit (Querschnitt):** Alle neuen Eingaben strikt validiert (`extra="forbid"`), alle neuen Netzwerkziele mit Zeitlimits, Größenlimits, ohne Weiterleitungen/Proxys, SSRF-Schutz für beliebige Adressen; **keine** neuen BLE-Schreibzugriffe; Zugangsdaten nur im `SecretStore`; fremde Dateien (ICS, Sicherungen) nie ausführen; optionale Zusatzbibliotheken mit geprüfter Lizenz.

**Ehrlichkeitsregel:** Nichts wird als „hardwaregeprüft“ oder „mit echtem Ziel geprüft“ bezeichnet, bevor es so geprüft wurde; jedes [U] wird beim Bauen durch Primärquelle oder Test ersetzt und das Ergebnis dokumentiert.


## 20. AP-51 bis AP-56 Würfel-Cockpit: mehrere Würfel, Batterie, Inspektor

**Auftrag des Anwenders (2026-11-22):** Die Bedienung soll **klarer zwischen den Funktionsbereichen** (Zeiterfassung, Smarthome, Musik) unterscheiden und das Umschalten erleichtern; die **bisherigen Einstellungen eines Würfels** sollen **jederzeit sichtbar** sein; im **Würfelbild** sollen die Seiten **anklickbar** sein (Einstellungen ansehen, neu programmieren); der **Batteriestand** soll **immer sichtbar**, **gespeichert/protokolliert** und ein baldiges Ende **angekündigt** werden; **alles Lesbare vom Würfel** soll lesbar und als Daten nutzbar sein, einstellbare Werte (Genauigkeit des Beschleunigungssensors, Energiemodus, LED) sollen geprüft werden; **mehrere Würfel** sollen **unterscheidbar** sein und **gleichzeitig** programmiert, gesteuert und dargestellt werden können, mit **geregelten Konflikten** (eine Musik gleichzeitig, widersprüchliche Lampenbefehle).

**Stand der Umsetzung (2026-11-22):** AP-51 bis AP-56 sind umgesetzt (Einzelheiten und Abweichungen in `docs/FORTSCHRITT.md` und den Abschnitten 36 bis 41 der Softwaredokumentation). Abweichungen vom Plan: **keine gleichzeitigen Zeit-Würfel** (ein laufender Eintrag), **kein „ältere Befehle verwerfen“**, **kein Schreiben** am Würfel (keine Quelle), die Bereichsfarben stehen als Rahmen der Bereichs-Pille.

### 20.1 Ist-Stand

* Mehrere Würfel sind **fachlich möglich** (ein Arbeiter je Würfel, Tabelle `devices`), aber **jede Seite wählt ihren Würfel selbst** (Auswahlfeld „Tracker“ mit ⭐ für den *aktiven Zeit-Würfel*). Es gibt **keine durchgehende Identität** (Farbe), **keine gemeinsame Auswahl**, keine Übersicht aller Würfel nebeneinander.
* Der **Batteriestand** wird gelesen (beim Verbinden, alle 10 Minuten) und einmal unter der Grenze gemeldet, aber **nicht gespeichert**, nicht dauerhaft sichtbar, ohne Prognose.
* Das Würfelbild (SVG) ist **nicht anklickbar**; die Einstellungen einer Seite sieht man nur im Editor der jeweiligen Betriebsart.
* Der Würfel wird **nur gelesen** (keine Schreiboperation in der BLE-Schicht, per Konstruktion getestet).

### 20.2 Recherche: was der Würfel sendet und was einstellbar ist (Stand 2026-11-22)

**Es gibt keine offizielle Bluetooth-Dokumentation des Herstellers**, die gefunden wurde (offiziell ist nur die Cloud-Schnittstelle, kein Bluetooth). Alles Folgende ist **Community-Wissen** (Quellen: `codingforfun/zeipy`, `maslovw/timeular-local`, `adn77/timeular`, `zntrio/timeular`, Blog von LeMaRiva) und **am eigenen Würfel zu bestätigen**. Teile der Quellen **widersprechen sich**.

| Dienst / Characteristic | Eigenschaften | Bedeutung (Community) | Verwendung in OctaLedger |
|---|---|---|---|
| `1800` Gerätename `2A00` | lesen, schreiben | Name des Geräts | nur lesen |
| `180A` `2A24/2A25/2A26/2A27/2A28/2A29/2A23/2A50` | lesen | Modell, **Seriennummer**, Firmware, Hardware, Software, Hersteller, System-ID, PnP-ID | **lesen** (Datenblatt, Unterscheidung mehrerer Würfel) |
| `180F` Batterie `2A19` | lesen, Benachrichtigung | Prozent | **lesen** (AP-52) |
| `1804` Tx Power `2A07` | lesen | Sendeleistung | lesen (Datenblatt) |
| `c7e70012` | lesen, Anzeige | Seite oben (1–8, 0 neutral, **auch andere Werte** wie 9/11/13, siehe BLE_PROTOCOL) | wie bisher |
| `c7e70011` | lesen | **Beschleunigungssensor**; Format **unsicher** (3 × uint16 laut einer, 3 × int32 laut anderer Quelle) | **nur lesen**, Länge prüfen, Roh-Aufzeichnung (AP-56) |
| `c7e70021` | Anzeige | Taste, 1 Byte (0 kurz, 1 lang); „1“ auch beim Ausschalten beobachtet | wie bisher |
| `c7e70022` | schreiben | „LED-Steuerung“ laut zeipy, **kein Datenformat bekannt** | **nicht schreiben** |
| `c7e70030/32` | schreiben, Benachrichtigung | beim Abonnieren ca. 169 Byte, vermutlich Kalibrierung je Seite; **nur eine Quelle** | höchstens lesen/mitschneiden |
| `c7e70041/42` | schreiben | Zweck unbekannt | **nicht schreiben** |
| `c7e70001` | schreiben, Benachrichtigung | „wechselt in den Firmware-Lade-Modus (DFU)“ | **niemals schreiben** (Risiko: Würfel im Bootloader) |

**Antworten auf die Fragen des Anwenders:**
* **Mehr Daten als die Lage?** Ja, lesbar sind **Batterie, Modell, Firmware, Seriennummer, Sendeleistung, Taste** und vermutlich der **Beschleunigungssensor** (Format ungeklärt). Es gibt **keine** belegten Ereignisse für „Doppelklopfen/Schütteln“; die Lageänderung selbst ist das Ereignis.
* **Beeinflussbar?** **Belegt ist nichts.** Genauigkeit des Beschleunigungssensors, Energiemodus/Schlafzeit: **kein Hinweis** auf eine Einstellung. **LED:** Es gibt eine Characteristic, deren Datenformat **unbekannt** ist. Der Würfel schläft in der Halterung von selbst und wacht beim Kippen auf. Deshalb werden diese Werte in OctaLedger **nur gezeigt, nicht verändert** (AP-56), bis eine belastbare Quelle vorliegt.
* **Mehrere Würfel unterscheiden:** **Seriennummer `2A25`** (lesen) und die **Bluetooth-Adresse**; welche der beiden die Werbedaten enthalten, ist **unbekannt**. OctaLedger kennt die Adresse und vergibt **Namen, Nummer und Farbe** (AP-51).
* **Gleichzeitige Verbindungen:** wie viele Würfel Windows mit dem vorhandenen Bluetooth-Adapter gleichzeitig hält, ist **nicht belegt** und am Gerät zu prüfen (nur der Würfel selbst: solange eine andere App verbunden ist, wirbt er nicht).
* **Batterie:** laut Blog **Knopfzelle** (Typ unbestätigt: CR2032 genannt), rote LED bei schwacher Batterie; Aktualisierungsrate des Prozentwerts **unbekannt**.

### 20.3 AP-51 Würfel-Identität und ausgewählter Würfel

* **Begriffe:** *Ausgewählter Würfel* = der Würfel, den man gerade ansieht/bearbeitet (Sitzungs-Auswahl, überall gleich); *Aktiver Zeit-Würfel* (⭐) = der Würfel, der die Zeiterfassung steuert (Einstellung „ein aktiver Tracker“, unverändert). Beides wird in der Oberfläche **nie** vermischt.
* **Identität:** jeder Würfel bekommt **Namen, laufende Nummer und Farbe** (Migration 0010: `devices.color`, automatisch aus einer festen, gut unterscheidbaren Palette vergeben, änderbar). Die Farbe erscheint **zusammen mit Name und Nummer** (nie Farbe allein) am Banner, im Menü, im Würfelbild (Rahmen), im Verlauf und in Auswahllisten.
* **Auswahl:** ein Würfel-Wähler **in der Seitenleiste** (immer sichtbar); alle würfelbezogenen Seiten benutzen **dieselbe** Auswahl. Ein **Banner** oben: „Sie bearbeiten: ● Regenbogen (Würfel 2 · Musik)“.
* **Übersicht:** die Übersichtsseite zeigt **alle Würfel als Karten** (Name, Farbe, Bereich, Verbindung, Batterie, Lage, was läuft).
* **Tests:** Farbvergabe (eindeutig, stabil), Auswahl bleibt über Seitenwechsel, Banner, Karten; Sicherungsformat nimmt `color` auf.

### 20.4 AP-52 Batterie-Cockpit

* **Speichern:** Tabelle `battery_log` (Migration 0011: Würfel, Zeit, Prozent); ein Eintrag **nur bei Änderung oder spätestens alle 6 Stunden**, Aufbewahrung 400 Tage, Teil der Sicherung.
* **Immer sichtbar:** in der **Statusleiste für jeden Würfel** (Symbol **und** Zahl), im Banner und in den Karten; **Stufen** (≥ 40 % gut, 20–39 % „bald tauschen“, 10–19 % „schwach“, < 10 % „fast leer“) **mit Text**.
* **Prognose (ehrlich):** aus dem gespeicherten Verlauf nur eine **Schätzung** der Restdauer (Steigung über mindestens 3 Tage und 5 Punkte), sonst „noch keine Schätzung“.
* **Warnungen:** WARNING im Protokoll einmal je Stufe, Eintrag unter „Hinweise“, Toast/Tray wie bisher; Stufenwechsel bleiben im Verlauf.
* **Grenze [HW]:** Meldefrequenz und Genauigkeit des Würfels sind unbekannt; die Prozentwerte sind **die des Würfels**.

### 20.5 AP-53 Funktionsbereiche unterscheiden und umschalten

* Drei **Bereiche** mit **eigener Farbe, eigenem Symbol und Text**: **Zeit**, **Smarthome**, **Musik**. Jeder Würfel hat **genau einen** Bereich (die vorhandene Betriebsart), **groß** gezeigt (Banner, Karte, Bild).
* **Umschalten an einer Stelle:** im **Banner des ausgewählten Würfels** mit Erklärung und Folgen („Zeit läuft noch – erst beenden“).
* **Bereichsfilter** in der Seitenleiste (Alle · Zeit · Smarthome · Musik): filtert Würfel-Wähler, Karten und bereichsbezogene Menüeinträge; Voreinstellung „Alle“.
* **Tests:** Umschalten mit Sperre bei laufender Zeit, Filterwirkung, Beschriftungen, Hilfetexte.

### 20.6 AP-54 Würfel-Inspektor (anklickbarer Würfel)

* Neue Seite **„Würfel-Inspektor“** (Gruppe *Würfel*): links das **Würfelbild**, rechts das **Seitenblatt** der gewählten Seite.
* **Anklickbar:** mit **`st.components.v2`** (in Streamlit 1.67 vorhanden, ohne Bauwerkzeug und ohne fremde Quellen) ist das SVG anklickbar, **und** es gibt immer eine **gleichwertige Knopfreihe 1–8** (Tastatur, Bildschirmleser, Tests, Rückfall ohne Komponente).
* **Seitenblatt (alles im Detail):** **Zeit** – Tätigkeit, Projekt, Tags, Notizvorlage, Bedingungen; **Smarthome** – die **ganze Aktionskette** (je Schritt: Verbindung, Aktion, Werte, Verzögerung, Fehlerverhalten, Bedingung) in Klartext; **Musik** – Titel, Ziel, Lautstärke, Halterungs-Verhalten; **leer** – „Noch nichts zugeordnet“. Knöpfe: **Neu programmieren** (springt in den passenden Editor mit vorgewählter Seite), **Entfernen**.
* **Alle Seiten auf einen Blick:** Klartext-Tabelle der 8 Seiten und der Halterung; kopier- und exportierbar („Einstellungen des Würfels“).
* **Tests:** Klartext-Erzeuger (reine Funktion) je Bereich, Auswahl über Knopf, Rückfall, Sprung zum Editor.

### 20.7 AP-55 Mehrere Würfel parallel

* **Zeit:** „ein aktiver Tracker“ bleibt Voreinstellung. Ob **mehrere Zeit-Würfel** gleichzeitig sinnvoll auswertbar sind (Journal/Statistik/Bericht je Würfel), wird **beim Bauen geklärt**, nicht vorab versprochen.
* **Musik, eine Wiedergabe je Ziel:** pro **Ziel** (Lokaler Player, ein Home-Assistant-Lautsprecher, Spotify-Konto, Browser-Player) läuft **nur ein Titel**. **Der zuletzt gestartete gewinnt**; „läuft gerade“ gehört dem Würfel, der zuletzt gestartet hat (`music_owner:<Ziel>`). **Ein Stopp durch die Halterung wirkt nur, wenn der Würfel Besitzer ist** (sonst beendete Würfel A die Musik von Würfel B). Ein Besitzwechsel steht im Verlauf.
* **Smarthome, widersprüchliche Befehle:** Aufträge an **dasselbe Ziel-Objekt** von **verschiedenen Würfeln** innerhalb eines **Konfliktfensters** (Voreinstellung 5 s) werden **in Eingangsreihenfolge** gesendet (der letzte gewinnt) und als **Konflikt im Verlauf** markiert; wahlweise „ältere verwerfen“. Keine stillschweigende Zusammenführung.
* **Anzeige:** Übersicht „**Wer steuert was?**“ (Ziel → Besitzer, seit wann).
* **Tests:** zwei Fake-Würfel mit gleichem Ziel: Besitz, Stopp nur durch Besitzer, Konflikt-Markierung, Unabhängigkeit verschiedener Ziele.

### 20.8 AP-56 Würfel auslesen (Datenblatt) und Grenzen des Einstellens

* **Lesen (sicher):** ein **Auslesen** je Würfel liest **alle lesbaren Characteristics** (nur READ, kein Schreiben) und speichert einen **Schnappschuss** (`device_snapshots`, Migration 0013) – angezeigt als **„Datenblatt“** (Dienste, Rechte, Werte, Modell, Firmware, **Seriennummer**, Batterie) mit **Export** (JSON/CSV). Unbekannte Characteristics erscheinen mit Rohwert, **ohne erfundene Deutung**.
* **Aufzeichnen:** ein **Aufzeichnungsmodus** für den Beschleunigungssensor `c7e70011` (nur lesen, nur auf Knopfdruck, begrenzte Dauer, Datei im Benutzerprofil, **Länge der Antwort wird geprüft**, bevor irgendetwas gedeutet wird).
* **Einstellbare Werte:** **kein Schreiben.** Für LED, Beschleunigungs-Genauigkeit und Energiemodus gibt es **keine belegte Quelle**; die Datenblatt-Ansicht sagt das ehrlich. Eine Schreibfunktion entsteht **nur**, wenn später eine **Primärquelle** und ein **Test am Gerät** vorliegen (dann mit doppelter Bestätigung, altem Wert und Rückweg). `c7e70001` (Firmware-Lade-Modus) wird **nie** beschrieben. Projektregel bleibt: **keine BLE-Schreiboperation auf unbekannte Characteristics.**

### 20.9 Reihenfolge, Abhängigkeiten, Abnahme

AP-51 → AP-52 → AP-53 → AP-54 → AP-55 → AP-56. AP-51 (Identität/Auswahl) ist die Grundlage; AP-54 setzt die gemeinsame Auswahl voraus; AP-55 setzt Identität und Bereiche voraus; AP-56 hängt am meisten von der echten Hardware ab und folgt zuletzt.

**A-36:** Zwei Würfel sind in Name, Nummer **und** Farbe unterscheidbar; die Auswahl gilt auf allen Seiten; das Banner nennt den bearbeiteten Würfel. **A-37:** Der Batteriestand jedes Würfels ist ständig sichtbar, wird gespeichert und warnt je Stufe einmal. **A-38:** Der Bereich eines Würfels ist am Bild erkennbar und an einer Stelle umschaltbar. **A-39:** Ein Klick auf eine Seite im Würfelbild (oder die Knopfreihe) zeigt die vollständige Einstellung der Seite. **A-40:** Zwei Musik-Würfel mit gleichem Ziel stören sich nicht: Stopp nur durch den Besitzer. **A-41 [HW]:** Das Datenblatt eines echten Würfels listet alle lesbaren Characteristics.


## 21. Einträge verwalten und Diagramme (AP-57 bis AP-59)

**Ausgangslage:** Das Zeitjournal kann Einträge einzeln korrigieren, teilen, löschen und mit Tags versehen und nach Zeitraum, Tätigkeit, Projekt, Gerät und Tag filtern. Es fehlen: Volltextsuche, weitere Filter, **Mehrfachauswahl mit Sammelaktionen**, ein **Änderungsprotokoll** und viel mehr **Diagramme** (bisher: wenige Balken-/Kreisdiagramme in der Statistik).

**Entscheidungen**
* **Sammelaktionen sind alles oder nichts** (eine Transaktion). Jede geänderte Angabe jedes Eintrags landet in der bestehenden Prüfspur (`corrections`), das Löschen nach einer **automatischen Sicherung** mit Eintrag im Audit-Protokoll. Ein **Grund ist Pflicht**.
* **Laufende Einträge** werden nie verschoben oder gelöscht (sie werden noch aufgezeichnet); sie werden gezählt und genannt, nie stillschweigend geändert.
* **„Person“ und „Tag“** sind dasselbe: ein Tag (z. B. `PERSON-B`, `TAG-1`). Bereiche markiert man über Filter + „alle Treffer auswählen“.
* **Suchen und Filtern** läuft in der Oberfläche über die geladenen Einträge (rein, getestet), weil alles lokal liegt; der Zeitraum wird beim Laden eingegrenzt. Kein neues Datenformat.
* **Kein Rückgängig-Knopf:** Rückweg ist die Sicherung vor dem Löschen (Seite *Daten*) und die alten Werte im Änderungsprotokoll.

### 21.1 AP-57 Sammelbearbeitung (Backend)
* `application/entry_service.py`: `apply` (Tätigkeit, Projekt, Notiz setzen/anhängen/leeren, **Zeit verschieben**, Qualität, Tags hinzufügen/entfernen/ersetzen), `delete`, `history` (Korrekturen und Audit-Einträge zusammen, mit Namen statt Kennungen).
* Repository `delete_many` (parametrisiert, in Blöcken, ein Sammel-Audit-Eintrag).
* API `POST /entries/edit`, `POST /entries/delete`, `GET /entries/history`; Client-Methoden `bulk_edit`, `bulk_delete`, `entry_history`.
* **Tests:** Änderung aller Felder, Wiederholung = „unverändert“, Verschieben ohne Zwischen-Überlappung, Rollback bei Konflikt, Zukunft verboten, Tags, Pflichtgrund, laufende Einträge, Sicherung und Audit, Verlauf.

### 21.2 AP-58 Seite „Einträge“ (Oberfläche)
* Neue Seite **Einträge** (Gruppe *Alltag*): **Suche** (Notiz, Tätigkeit, Projekt, Tags, Gerät), **Filter** (Zeitraum mit Schnellwahl, Tätigkeit, Projekt, Gerät, Tags **beliebig/alle/keiner**, Qualität, Quelle, Dauer von–bis, Wochentage, Tageszeit), **Suchprotokoll** (zuletzt benutzte Filter, mit einem Klick erneut anwenden, in der Sitzung).
* **Tabelle** mit allen Werten (Beginn, Ende, Dauer, Tätigkeit, Projekt, Tags, Gerät, Quelle, Qualität, Revision, Notiz, Betrag), sortierbar, **Zeilen anklickbar** (Mehrfachauswahl) plus „alle Treffer auswählen“ / „Auswahl aufheben“; Zusammenfassung der Auswahl (Anzahl, Summe, Zeitspanne).
* **Sammelaktionen** auf der Auswahl: zuordnen (Tätigkeit/Projekt), **Tags** hinzufügen/entfernen/ersetzen, Notiz, **verschieben** (± Minuten/Stunden/Tage), bestätigen/als unsicher markieren, **löschen** (mit Vorschau, Grund und Zahlenbestätigung).
* **Änderungsprotokoll** (Reiter): wer/was/wann/Grund mit altem und neuem Wert, filterbar.
* Das einzelne Bearbeiten (korrigieren, teilen, löschen) bleibt im Journal erreichbar; die neue Seite ersetzt es nicht.

### 21.3 AP-59 Diagramme
* Neue Seite **Diagramme** (Gruppe *Alltag*) mit einer Auswahl vieler **interaktiver** Plotly-Diagramme auf den gefilterten Einträgen (gleiche Filterleiste): Stapelbalken je Tag/Woche/Monat nach Tätigkeit oder Projekt, Kreis/Ring, Sonnenstrahl (Tätigkeit → Projekt), Treemap, Wärmekarte Wochentag × Stunde, Kalender-Wärmekarte, Zeitstrahl/Gantt der Einträge, kumulierte Linie, Verlauf mit Bereichsregler, Histogramm und Boxplot der Dauer, Streudiagramm Tageszeit × Dauer, Tag-Vergleich.
* **Interaktiv:** Zoomen, Schwebetext, Legende ein-/ausblenden, Bereichsregler; **Klick auf ein Element** (Balken, Kreisstück) filtert die Tabelle darunter auf genau diese Einträge. Zu jedem Diagramm gibt es die **Daten als Tabelle** und einen Export (PNG über die Plotly-Leiste, CSV).
* Die Diagramme sind **reine Funktionen** (Einträge → Figur) und einzeln getestet; die Farben kommen aus dem Design-System (hell/dunkel), nie Farbe allein (Beschriftung und Schwebetext).
* Ehrlich: die Auswertung beruht auf den **Geräte-Einträgen** (Überlappungen werden hier nicht herausgerechnet; die Statistik-Seite bleibt für die „persönliche Arbeitszeit“ maßgeblich); die Diagramme weisen darauf hin.

**Reihenfolge:** AP-57 → AP-58 → AP-59. **Abnahme A-42:** Mehrere Einträge lassen sich auswählen und gemeinsam zuordnen, taggen, verschieben und löschen (alles oder nichts, mit Grund, Sicherung und Protokoll). **A-43:** Suche und Filter grenzen Einträge nach allen genannten Angaben ein; das Suchprotokoll wendet frühere Filter wieder an. **A-44:** Jedes Diagramm hat eine Tabelle zu den Daten, ein Klick auf ein Element filtert die Einträge.

**Stand:** AP-57, AP-58 und AP-59 sind umgesetzt (siehe `docs/FORTSCHRITT.md`). Die Diagramm-Galerie umfasst 17 Diagramme in fünf Gruppen; Klick-zu-Einträge gibt es bei elf davon. Am echten Browser noch zu prüfen: Klick auf Diagramm-Elemente, Darstellung der Wärmekarten in Dunkel, Geschwindigkeit bei sehr vielen Einträgen.


## 22. AP-60 Qualitätsdurchgang

Befund (Werkzeuge: erweiterte Ruff-Regeln, mypy strict, Suche nach nicht referenziertem Code, Durchsicht von Logging und Fehlerbehandlung): Der Code ist im Kern sauber (jedes breite `except` begründet, einheitliche API-Fehler, Logs ohne Geheimnisse). Lücken waren: nicht abgefangene Fehler im Dashboard (Traceback sichtbar) und in Threads (nur Konsole), Dashboard-Fehler ohne Logeintrag, zu schmale Lint-Regeln (28 veraltete `noqa`, 17 alte `timezone.utc`), toter Code, ein überladenes Menü „Alltag“, veraltete Zahlen in README/GUI-Konzept, „Sitzung“ statt „Eintrag“ in Meldungen. Umsetzung und Entscheidungen: `docs/SOFTWAREDOKUMENTATION.md` §45.


## 23. Musik-Player: lokal, YouTube, YouTube Music, Spotify (AP-61 bis AP-63)

**Wunsch:** ein umfassender Player, der lokale Musik, YouTube, YouTube Music und Spotify abspielt und steuert; lokal Datei, Ordner oder Album, einmal oder endlos, jederzeit stoppbar (App oder Würfelbewegung); viele Formate; schön, intuitiv, fehlerfrei; YouTube möglichst ohne Einschränkungen und Werbung.

**Entscheidungen**
* **Eine Wiedergabe-Logik für Würfel und App:** `PlayerService` und der Musik-Modus nutzen dieselben Adapter; die Seite startet nur „ohne Würfel“.
* **Warteschlange im Audio-Worker** (`domain/playlist.py`, rein): Reihenfolge, Zufall, Wiederholen (einmal/alles/ein Titel); das Ende eines Titels meldet die Engine, ein Titel einer ersetzten Wiedergabe wird erkannt und ignoriert; defekte Titel werden übersprungen und genannt.
* **FFmpeg optional** als Kindprozess (Liste statt Shell, Pfad geprüft, Web-Streams werden von OctaLedger selbst geöffnet und hineingepumpt, nie als Adresse übergeben).
* **Freie lokale Pfade** (statt nur freigegebener Ordner): absolut, lokales Laufwerk, keine Netzwerk-/Gerätepfade, abspielbare Endungen, Tiefe und Anzahl begrenzt; die Freigabe-Ordner der Verbindung funktionieren unverändert.
* **Auswahlfenster** in einem Kindprozess (`tkinter`), nie im Agenten; Abbruch und Fehler führen zum Tippen des Pfads.
* **Halterung „weiterlaufen“:** Musik läuft in der Halterung (und bei Verbindungsverlust) weiter; nur App oder Stille-Seite beenden sie. „Bewegung stoppt“ ist die Regel: jede andere Seite ersetzt, eine Seite ohne Titel beendet.
* **YouTube:** Wiederholen/Zufall (Einzelvideo über `loop`+`playlist`, Playlists über die API-Befehle), Fehlercodes in Klartext mit „Auf YouTube öffnen“, optional youtube.com statt youtube-nocookie.com für ein angemeldetes Konto. **Werbung entfernen und Herunterladen** sind ausdrücklich **nicht** Teil: sie verstoßen gegen die Nutzungsbedingungen.

### 23.1 AP-61 lokale Engine
`media_formats`, `playlist`, `audio/paths`, `audio/ffmpeg`, Engine (Pause, Ende-Meldung, PCM), Worker (Warteschlange, Status), Adapter (`play_path`, `pause`, `resume`, `next`, `previous`, Steuerung, `status`), Quelle `local:`, Halterung `continue`.
### 23.2 AP-62 Seite „Musik-Player“
`PlayerService`, API `/player/*`, `/system/pick-path`, Seite mit „Jetzt läuft“, drei Quellen-Reitern, „Alles stoppen“.
### 23.3 AP-63 Würfelseiten und YouTube
Pfad/Wiederholen/Zufall im Titel-Editor mit Auswahlfenster, Halterungs-Verhalten, YouTube-Optionen und Fehlertexte.

**Abnahme A-45:** Eine Datei, ein Ordner und eine Playlist spielen einmal, in Endlosschleife und zufällig; Weiter/Zurück/Pause/Stopp wirken sofort. **A-46:** Ein Würfel startet einen Ordner als Endlosschleife; sie endet durch „Alles stoppen“ oder durch eine andere Seite. **A-47 [HW]:** Echte Wiedergabe von MP3/FLAC/WAV/OGG und (mit FFmpeg) M4A/MP4 an Ihrem Gerät; YouTube-Player im Browser; Auswahlfenster.
