# Software-Pflichtenheft: OctaLedger

Version: 0.1, Planungsstand 19. November 2026; Umsetzungsstand siehe Abschnitt 11.
Status: Soll-Spezifikation, **F-01 bis F-20 umgesetzt** (F-20 ohne Obsidian) bis auf die Hardwareprüfung; **F-21 bis F-50 sind geplant** (Abschnitt 12, Reihenfolge und Entwürfe in [UMSETZUNGSPLAN.md](UMSETZUNGSPLAN.md)).
Muss/Soll/Kann bezeichnen Zielprioritäten, keine Lieferzusage.

## 1. Zweck und Zielgruppe

Lokale, nachvollziehbare Arbeitszeiterfassung mit kompatiblen Timeular-/ZEI-
Trackern unter Windows. Die Anwendung liest Orientierung und optional verfügbare
Geräteinformationen, erzeugt Zeitabschnitte und ermöglicht Verwaltung, Korrektur,
Export und grafische Analyse ohne erforderliches Herstellerkonto.

Ausgangsszenario: zwei USB-C-Tracker. Kompatibilität ist pro Exemplar und Firmware
zu prüfen. Zwei registrierte Geräte bedeuten nicht automatisch zwei gleichzeitig
zuverlässig unterstützte Verbindungen am verwendeten Adapter.

## 2. Abgrenzung

„Steuern“ bedeutet zunächst Verbindungen verwalten, Tracker zuweisen und aus
Seitenevents Softwareaktionen auslösen. Keine Zusicherung, Motoren, LEDs oder
Firmware des Trackers zu steuern. Keine undokumentierten BLE-Schreibbefehle.
Keine Smartphone-App, Cloudpflicht, Matter-Zertifizierung, automatische
Rechnungsstellung oder rechtliche Konformitätszusage im MVP.

## 3. Zielumgebung

Windows 11 als erstes Hardware-Testziel, Python ab 3.12 als Projektentscheidung.
Bluetooth-LE-Adapter mit aktiven GATT-Verbindungen. Streamlit im lokalen Browser.
Installation und Updates dürfen Internet benötigen; Kernerfassung soll offline
funktionieren. Konkrete Bibliotheks-/OS-Versionen nach Hardwaretest festschreiben.

## 4. Architektur

Ein Agentenprozess besitzt alle BLE-Clients in einem dauerhaften AsyncIO-Loop.
Pro Gerät ein eigener Zustandsautomat und Verbindungskontext. Eine lokale API
verbindet Streamlit mit dem Agenten. Dashboard-Neuladen beendet keine Erfassung.
SQLite mit Migrationen speichert Beobachtungen, Sitzungen und Korrekturen. Agent
ist einziger regulärer Datenbankschreiber. GUI liest/schreibt über API.

## 5. Funktionale Anforderungen

| ID | Priorität | Anforderung |
|---|---|---|
| F-01 | Muss | Nach BLE-Geräten suchen; Benutzer wählt eigenes Gerät |
| F-02 | Muss | Zwei Geräte mit interner ID und Alias registrieren |
| F-03 | Muss | Modell/Firmware soweit verfügbar anzeigen; unbekannt erlauben |
| F-04 | Muss | Dienst/Characteristic prüfen, Verbindungsschritte anzeigen |
| F-05 | Muss | Acht Seiten pro Tracker individuell kalibrieren |
| F-06 | Muss | Rohwerte validieren, Duplikate und Zwischenflächen behandeln |
| F-07 | Muss | Baseline getrennt von neuem Seitenwechsel verarbeiten |
| F-08 | Muss | Aktivität, Projekt und optionale Notiz zuordnen |
| F-09 | Muss | Zeitabschnitte automatisch starten und wechseln |
| F-10 | Muss | Manuelles Starten, Stoppen und Pause ermöglichen |
| F-11 | Muss | Beobachtungen und bestätigte Änderungen transaktional speichern |
| F-12 | Muss | Ausfälle sichtbar markieren, keine Historie erfinden |
| F-13 | Muss | Sitzungen bearbeiten, teilen und korrigieren; Auditspur erhalten |
| F-14 | Muss | Tages-/Wochenansicht und Projekt-/Aktivitätsfilter anbieten |
| F-15 | Soll | Balken-, Verlauf- und Verteilungsdiagramme darstellen |
| F-16 | Muss | CSV exportieren, versionierten JSON-Backup/Restore anbieten |
| F-17 | Muss | Reconnect mit begrenztem Backoff und Benutzerstopp unterstützen |
| F-18 | Soll | Optionalen Batteriestand anzeigen; fehlenden Dienst tolerieren |
| F-19 | Soll | Diagnosen anonymisiert exportieren |
| F-20 | Kann | Home Assistant, Hue, Obsidian oder MQTT über Adapter ergänzen |

## 6. Zeit- und Mehrgeräteregeln

MVP: eine persönliche aktive Arbeitssitzung, ausgewählter aktiver Tracker.
Zweiter Tracker bleibt registriert, eine Übergabe erfolgt ausdrücklich. Ereignisse
inaktiver Geräte dürfen keine heimlichen konkurrierenden Arbeitssitzungen erzeugen.

Ausbaustufe: unabhängige Geräte-Zeitachsen und optional parallele Beobachtung.
Berichte müssen zwischen Summe von Gerätezeiten und überschneidungsfreier
persönlicher Arbeitszeit unterscheiden. Nicht einfach beide Summen addieren.

Erster gelesener Wert ist Baseline. Standard: kein automatischer Sitzungsbeginn;
Nutzer kann „aktuelle Seite übernehmen“ aktivieren. Entprellung anfangs 300 ms als
konfigurierbarer Startwert, am Gerät zu validieren. Neutralwert 0 zunächst nur als
neutral protokollieren; Pausenregel erst nach Hardwareprüfung konfigurieren.

Bei Verlust bleibt der Zeitraum als unsicher markiert; GUI fordert nach Rückkehr
Bestätigung/Korrektur an. Bewusstes Stoppen verhindert weitere Reconnects.
Zeitpunkte UTC, Anzeige in gewählter IANA-Zeitzone. Monotone Zeit nur innerhalb
desselben Prozesskontexts verwenden. Sommerzeit und Uhrsprünge testen.

## 7. Oberflächen

- Übersicht: aktuelle Tätigkeit, Dauer, aktiver Tracker, Verbindung, Datenqualität.
- Geräte: Suche, Registrierung, Verbinden/Trennen, Eigenschaften und Kalibrierung.
- Verwaltung: Aktivitäten, Projekte, optionale Kunden/Tags später.
- Zeitjournal: Filter, Korrektur, Teilung und Konfliktanzeige.
- Statistik: Tages-/Wochenbalken, Projektanteile, Verlauf; Unsicherheit ausweisen.
- Einstellungen: Zeitzone, Entprellung, Baseline, Datensicherung.
- Diagnose: Fehlerstufen, anonymisierter Export, offene Integrationsaufträge.

## 8. Nichtfunktionale Anforderungen

Keine Pflichtcloud und keine heimliche Telemetrie. Nutzerdaten außerhalb des
Repositories im Benutzerprofil. Datenbankänderungen migrierbar, vor Migration
Backup. Keine BLE- oder Netzwerk-Endlosschleifen im Streamlit-Skript. Keine UI-
Aufrufe aus dem BLE-Callback. Begrenzte Warteschlangen und definierte Überlaufregel.
Fehler sollen benutzerverständlich und intern mit stabilen Codes vorliegen.

API nur Loopback im MVP, Tokenprüfung für alle schützenswerten Routen; keine
Zustandsänderungen über GET. Keine beliebigen Shellbefehle. Herkunfts-/Hostprüfung
und Schutz vor unerwünschten Browseranfragen planen. Tokens nicht in URLs/Logs.

## 9. Daten und Sicherung

Speichern: Geräte, Fähigkeiten, Zuordnungen, Aktivitäten, Projekte, Rohereignisse,
Sitzungen, Korrekturen, Konfiguration, Integrationsaufträge. Originalbeobachtungen
nicht still überschreiben. Lösch-/Aufbewahrungsregeln explizit einführen.
Backup ist erst nach erfolgreicher Wiederherstellung als belastbar einzustufen.
CSV-Ausgabe muss Zeitzone, Encoding und sichere Textbehandlung dokumentieren.

## 10. Abnahmekriterien

| ID | Nachweis |
|---|---|
| A-01 | Alle acht Flächen beider Tracker nachvollziehbar kalibriert |
| A-02 | 20 identische Rohwerte ergeben keinen zusätzlichen Tätigkeitswechsel |
| A-03 | Zwischenfläche unter Stabilitätsfrist löst keinen Wechsel aus |
| A-04 | Reconnect erzeugt keine unbeabsichtigte neue Sitzung |
| A-05 | Dashboard-Rerun und Schließen lassen Agentenerfassung weiterlaufen |
| A-06 | Prozessneustart erhält bestätigte Daten und markiert unklaren Abschnitt |
| A-07 | Geräteübergabe erzeugt keine unbemerkte doppelte persönliche Zeit |
| A-08 | Korrektur bleibt nachvollziehbar, Export entspricht korrigierter Ansicht |
| A-09 | JSON-Backup wird in leerer Testumgebung erfolgreich restauriert |
| A-10 | Keine Tokens/echten Arbeitsdaten im Git-Repository |
| A-11 | pytest, Ruff und mypy bestehen in deklarierter Testumgebung |

Keine erfundenen Leistungs- oder Batteriezahlen. Latenz, CPU und Langzeitstabilität
im Hardwaretest messen. Betriebliche Rechtskonformität separat prüfen.

## 11. Umsetzungsstand und Nachverfolgung

✅ = umgesetzt und automatisch getestet (Simulator); ⏳ = mit echter Hardware noch nicht geprüft.

| ID | Stand | Umsetzung |
|---|---|---|
| F-01 | ✅ ⏳ | `infrastructure/ble/scanner`, Geräte-Seite „Suche“, `octaledger scan` (nur auf Anforderung, verbindet nie) |
| F-02 | ✅ | `DeviceService.register`, Alias eindeutig, erster Tracker wird aktiv |
| F-03 | ✅ ⏳ | Modell/Firmware aus der Geräteinformation, „unbekannt“ erlaubt |
| F-04 | ✅ ⏳ | `discover_capabilities`, Verbindungszustände in Übersicht/Geräte/Diagnose |
| F-05 | ✅ ⏳ | Kalibrierung je Seite 1–8 mit „liegt oben“-Anzeige (Geräte-Seite) |
| F-06 | ✅ | `OrientationDebouncer`: Validierung, Duplikate, Zwischenflächen |
| F-07 | ✅ | Baseline getrennt von Seitenwechsel (`EventKind.BASELINE`, Richtlinie `baseline_policy`) |
| F-08 | ✅ | Tätigkeit, Projekt, optionale Notiz je Sitzung |
| F-09 | ✅ | `TrackingService.record_event` (Start/Wechsel) |
| F-10 | ✅ | manuell Start/Stopp/Pause/Fortsetzen (Übersicht) |
| F-11 | ✅ | alle Schreibvorgänge in atomaren Transaktionen (`Storage.transaction`) |
| F-12 | ✅ | Verbindungsverlust → `unsicher`, nichts erfunden; Bestätigung im Journal |
| F-13 | ✅ | Korrigieren, Teilen, Löschen mit Pflichtgrund und Auditspur |
| F-14 | ✅ | Tages-/Wochenansicht, Filter nach Tätigkeit/Projekt/Gerät |
| F-15 | ✅ | Verlaufs-Balken pro Tag, Ringdiagramme nach Tätigkeit/Projekt (plus Tabellen) |
| F-16 | ✅ | CSV-Export; versioniertes JSON-Backup mit Prüfsumme; validierter Restore |
| F-17 | ✅ ⏳ | Reconnect mit begrenztem Backoff; bewusster Stopp beendet Reconnect |
| F-18 | ✅ ⏳ | optionaler Batteriestand; fehlender Dienst wird toleriert |
| F-19 | ✅ | anonymisierter Diagnosebericht (Diagnose-Seite) |
| F-20 | ✅ ⏳ teilweise | Steuerungsmodus mit Adaptern für **Home Assistant, Hue, MQTT und Webhook** (`infrastructure/integrations`); **Obsidian ist nicht umgesetzt** (nur über den Webhook-Adapter denkbar). Matter und Google Home nur über Home Assistant. Nur gegen Testziele geprüft ⏳ |

Abnahmekriterien A-01 bis A-11: Nachweisstatus in [TESTPLAN.md](TESTPLAN.md).

## 12. Erweiterungen: Funktion A (Steuern) und Funktion B (Zeit erfassen), geplant

Dieser Abschnitt legt fest, **was als Nächstes gebaut wird**. Für jede Anforderung nennt [UMSETZUNGSPLAN.md](UMSETZUNGSPLAN.md) das **Warum**, das **Wo** (Module/Dateien), das **Wie** (Entwurf, Daten, Schnittstelle, Oberfläche), die Tests und die Risiken – in der Reihenfolge der Arbeitspakete AP-35 bis AP-47.

**Kennzeichen:** „Muss/Soll/Kann“ wie in Abschnitt 5 (Zielpriorität, keine Lieferzusage). **[U]** = Grundlage ist ungeprüft und vor der Umsetzung gegen die Primärquelle zu belegen. **[HW]** = Abnahme braucht den echten Würfel bzw. echte Geräte. **Stand** aller Zeilen: ⏳ geplant, noch nichts umgesetzt.

### 12.1 Zeiterfassung (Funktion B)

| ID | Priorität | Anforderung | AP | Hinweise |
|---|---|---|---|---|
| F-21 | Muss | Würfelwerte außerhalb der Seiten 1–8 tolerant behandeln: **0 und 10 = „in der Basis“ (neutral)**, 9 und alles andere bleibt `invalid`, **jeder Rohwert wird im Protokoll festgehalten**; die Zuordnung ist eine änderbare Tabelle | 35 | 0/10 nach `adn77/timeular` (Auszug), **[U][HW]** am eigenen Würfel bestätigen |
| F-50 | Soll | Vor dem Verbinden gezielt nach dem Würfel suchen (Windows/Bleak), damit „Device … was not found“ seltener auftritt; verständliche Meldung, wenn er nicht wirbt | 35 | **[U]** übliche Praxis, abschaltbar |
| F-22 | Muss | **Verbindungsverlust mit Frist:** Eintrag läuft weiter (unsicher), endet nach einstellbarer Frist (Voreinstellung 5 min) **am Verlustzeitpunkt**, setzt bei Rückkehr in der Frist fort; danach Rückfrage „Lücke behalten / verwerfen / anderer Tätigkeit zuordnen“; nie Zeit ohne Rückfrage erfinden oder löschen | 36 | Empfehlung aus der Recherche (nicht von einer App belegt) |
| F-23 | Muss | **Rückfragen-Zentrale:** Dinge, die auf eine Entscheidung warten (Lücke, Leerlauf, Auto-Stopp, Erinnerung, Pausenhinweis), werden dauerhaft gespeichert, sind auf jeder Seite als Banner sichtbar und überleben ein geschlossenes Dashboard | 36 | gemeinsamer Baustein (Plan 3.1) |
| F-24 | Soll | **Würfeltaste** (kurz/lang) als Eingabe, pro Würfel frei belegbar (Pause/Fortsetzen, Stopp, letzte Tätigkeit starten, im Steuerungsmodus eine Aktion); **ohne Belegung geschieht nichts**; nur Lesen/Abonnieren, kein Schreibzugriff | 37 | **[U][HW]** Characteristic `c7e70021`, 0 = kurz, 1 = lang (nur eine Community-Quelle) |
| F-25 | Soll | **Batterie-Warnung** (Schwelle einstellbar, Voreinstellung 20 %, einmal je Ladezyklus) als Rückfrage/Benachrichtigung | 37 | Batterie wird bereits gelesen (F-18) |
| F-26 | Muss | **Auto-Stopp am Arbeitsende** (Uhrzeit und Wochentage einstellbar, Voreinstellung aus); der Eintrag endet zur eingestellten Zeit als „unsicher“, eine Rückfrage erlaubt das Verlängern | 38 | |
| F-27 | Soll | **Leerlauf-Erkennung** (Minuten einstellbar, Voreinstellung **aus**): bei Rückkehr fragen „Zeit behalten / verwerfen / als Pause buchen“; nur die Zeit seit der letzten Eingabe, keine Inhalte | 38 | **[U]** `GetLastInputInfo` per ctypes; Agent muss in der Benutzersitzung laufen |
| F-28 | Soll | **Erinnerungen** (kein Eintrag läuft zur Arbeitszeit; Eintrag läuft sehr lange), jede abschaltbar, jede Erinnerung genau einmal je Anlass | 38 | |
| F-29 | Soll | **Tray-Icon** mit Zustandsfarbe, laufender Zeit im Tooltip und Menü (Stopp, Pause, Dashboard öffnen, Rückfragen, Beenden) | 39 | optionales Extra `tray`; `pystray` ist LGPL und seit 2023 ungepflegt |
| F-30 | Soll | **Windows-Benachrichtigungen** für Rückfragen und Erinnerungen, mit Ruhezeiten; immer zusätzlich das Dashboard-Banner | 39 | optionales Extra `toast`; Lizenz von `windows-toasts` zuerst prüfen |
| F-31 | Soll | **Autostart mit Windows** ein-/ausschaltbar (CLI und Oberfläche), Zustand wird gelesen statt angenommen | 39 | Run-Key unter HKCU **[U]** |
| F-32 | Soll | **Soll-Arbeitszeit und Saldo:** Tagessoll je Wochentag (versioniert nach Gültigkeit), Feiertage (Region) und Abwesenheiten, Saldo-Vortrag, Überstunden-Saldo in der Statistik | 40 | `holidays` (MIT); halbe/kantonale Feiertage als manuelle Overrides |
| F-33 | Soll | **Pausenhinweise** nach Region (aus/CH/EU/eigene), **nur Information, keine Rechtsberatung, kein automatischer Pausenabzug**; Schwellen mit Quelle und Stand | 40 | CH nur über Sekundärquellen belegt, Wortlaut prüfen; EU Art. 4 belegt |
| F-34 | Soll | **Tags** je Eintrag (mit Standard-Tags je Tätigkeit) und **Notizvorlagen** je Tätigkeit; Filter nach Tag | 41 | |
| F-35 | Kann | **Projektbudgets** (Minuten) mit Warnung bei 80 % und 100 % | 41 | |
| F-36 | Kann | **Abrechenbar und Stundensatz** je Projekt; Beträge nur im Bericht, **gerundet im Bericht, nie in den Rohdaten** | 41 | |
| F-37 | Soll | **Bericht als Druckansicht und als PDF** (Summen identisch zur Statistik; unsichere Zeiten ausgewiesen; Kopfdaten nur aus Eingaben) | 42 | Browser-Druck zuerst; `fpdf2` (BSD-2) als Extra |
| F-38 | Kann | **Kalender-Import (ICS) als Vorschläge**, die der Anwender je Eintrag bestätigt; nichts wird automatisch gebucht; harte Grenzen für Größe, Menge, Zeitraum | 42 | `icalendar` **[U]**, Serientermine nur im Zeitfenster |

### 12.2 Steuern (Funktion A)

| ID | Priorität | Anforderung | AP | Hinweise |
|---|---|---|---|---|
| F-39 | Soll | **Hue erweitern:** Helligkeit, Farbtemperatur, Übergangszeit, Szenen-Modus (aktiv/dynamisch), **echtes Umschalten** (Zustand lesen, dann das Gegenteil setzen), Mindestabstand zwischen Anfragen und Wiederholung bei „zu viele Anfragen“ | 43 | **[U][HW]** alle JSON-Formen an der eigenen Bridge prüfen (Hue-Doku war nicht abrufbar) |
| F-40 | Kann | **Bridge-Suche** per mDNS (optionales Extra) und auf ausdrücklichen Klick per Cloud-Dienst; manuelle IP bleibt Standard | 43 | `zeroconf` LGPL **[U]**; Cloud-Suche verlässt das lokale Netz |
| F-41 | Soll | **Aktionsketten:** mehrere Schritte je Würfelseite in fester Reihenfolge mit Verzögerung und „bei Fehler weitermachen“; ein neuer Seitenwechsel bricht noch nicht gesendete Schritte ab; bestehende Einzelaktionen bleiben als Kette mit einem Schritt gültig | 44 | größte Änderung am Kern des Steuerungsmodus |
| F-42 | Kann | **Einfache Bedingungen** je Schritt: Zeitfenster (auch über Mitternacht) und Wochentage in lokaler Zeit | 44 | |
| F-43 | Soll | **Musik über Home Assistant:** Aktionen „Medien abspielen/Pause/Stopp/Lautstärke“ mit Auswahl der `media_player` | 45 | deckt Sonos, Cast, AirPlay, Displays ab, soweit Home Assistant sie kennt **[U]** |
| F-44 | Kann | **Lokaler Player** am PC für Internetradio-Streams und Dateien aus freigegebenen Ordnern (Lautstärke, Stopp); strenge Adressprüfung (SSRF-Schutz), keine Download-Funktion | 45 | `miniaudio` kann **kein AAC** **[U]**; externer Player als Ausweg |
| F-45 | Soll | **Vorlagen und Rezepte** für Node-RED, Zigbee2MQTT, WLED, Shelly, openHAB, ioBroker, Home-Assistant-Webhook; **Platzhalter** `{face}`, `{label}`, `{device}`, `{time}` in Webhook/MQTT-Inhalten (nur Whitelist, JSON-sicher) | 46 | Rezepte mit „geprüft am“; Node-RED-Flow erst nach praktischem Test |

### 12.3 Optional, nur auf ausdrücklichen Wunsch

| ID | Priorität | Anforderung | AP | Vorab zu klären |
|---|---|---|---|---|
| F-46 | Kann | **Spotify** steuern (Wiedergabe auf einem Gerät) | 47 | Premium-Pflicht, OAuth (PKCE), Token in `secrets.json` (unverschlüsselt), Nutzungsbedingungen |
| F-47 | Kann | **Gesten** (Schütteln, Doppelklopfen) aus der Beschleunigung | 47 | Characteristic nicht entschlüsselt, nur per READ **[U][HW]**; sonst verwerfen |
| F-48 | Kann | **App-Auto-Tracker** (opt-in, lokal, nur Prozessname) | 47 | Datenschutz-Konzept, Rechtslage |
| F-49 | Kann | **Sonos/Cast direkt** (ohne Home Assistant) | 47 | Nachweis, dass Home Assistant nicht infrage kommt |

### 12.4 Ausdrücklich nicht vorgesehen

Schreibzugriffe auf den Würfel (LED, Gerätename, Firmware-Update), Auslesen eines Würfel-Speichers (nach heutigem Wissen nicht belegt), YouTube-/Streaming-Download, direkte Alexa-Anbindung, Cloud-Synchronisation, Mehrbenutzerbetrieb, Netzwerkfreigabe der API, eigener Matter-/Google-Home-Zugang. Begründungen: [UMSETZUNGSPLAN.md](UMSETZUNGSPLAN.md) §17.

### 12.5 Neue Abnahmekriterien

| ID | Nachweis | Paket |
|---|---|---|
| A-12 bis A-17 | Steuerungsmodus (siehe [TESTPLAN.md](TESTPLAN.md)) | 26–31 |
| A-18 | Werte 0 und 10 ergeben `neutral`, 9 und 255 `invalid` **mit Rohwert im Protokoll**; ein Verbindungsversuch scannt zuerst. **[HW]** A-18b: Rohwerte der Basis am echten Würfel dokumentiert | 35 |
| A-19 | Bei Verbindungsverlust läuft der Eintrag bis zur Frist weiter und endet danach exakt am Verlustzeitpunkt; Rückkehr in der Frist setzt fort; nach der Frist erscheint eine Rückfrage mit drei Antworten, jede wirkt wie beschrieben; **keine Zeit wird ohne Rückfrage erfunden oder gelöscht** | 36 |
| A-20 | Kurzer/langer Tastendruck (Simulator) löst die zugeordnete Aktion aus, ohne Zuordnung nichts. **[HW]** A-20b: Werte am echten Würfel wie dokumentiert | 37 |
| A-21 | Mit Probe-Doppel endet ein Eintrag zur eingestellten Zeit mit Rückfrage; die Leerlauf-Rückfrage bietet drei Antworten; Erinnerungen erscheinen genau einmal; nach der Installation ist alles aus | 38 |
| A-22 | Symbolzustand, Tooltip und Menü entsprechen dem Dienstzustand; Autostart lässt sich ein-/ausschalten und liest den echten Zustand zurück. **[HW/Windows]** A-22b: Start nach Anmeldung, Symbol, Toast auf dem echten Rechner | 39 |
| A-23 | Saldo berücksichtigt Feiertage und Abwesenheit in den Testfällen korrekt; Pausenhinweis erscheint genau einmal und ist abschaltbar; die Schwellen tragen Quelle und Stand | 40 |
| A-24 | Tags, Vorlagen, Budget und Betrag verhalten sich wie beschrieben; bestehende Daten bleiben nach der Migration unverändert | 41 |
| A-25 | Bericht zeigt dieselben Summen wie die Statistik; ICS-Import legt nichts ohne Bestätigung an, behandelt Fehler verständlich und ist atomar | 42 |
| A-26 | Gegen den Test-Bridge-Server entsprechen die gesendeten Bodies den dokumentierten Formen; Toggle liest zuerst den Zustand. **[HW]** A-26b: An der echten Bridge funktionieren Raum+Helligkeit, Szene (aktiv/dynamisch) und Toggle | 43 |
| A-27 | Eine Seite mit drei Schritten (sofort, +2 s, +5 s) sendet sie in dieser Reihenfolge zu den richtigen Zeiten; ein Seitenwechsel bricht unversandte ab; ein Zeitfenster überspringt Schritte außerhalb; bestehende Einzelaktionen funktionieren unverändert | 44 |
| A-28 | Die URL-Prüfung lehnt alle gefährlichen Ziele ab; Befehle erreichen die (Attrappen-)Engine in richtiger Reihenfolge ohne den BLE-Loop zu blockieren; HA-Medienaktionen senden die dokumentierten Bodies. **[HW]** A-28b: MP3-Stream und lokale Datei spielen am PC; ein HA-`media_player` spielt eine Stream-Adresse | 45 |
| A-29 | Eine Vorlage füllt die Felder; Platzhalter werden nur aus der Whitelist ersetzt und JSON-sicher eingesetzt; `docs/REZEPTE.md` ist vollständig verlinkt und in der App lesbar | 46 |

Alle neuen Pakete erfüllen zusätzlich die Querschnittsregeln des Plans (§18): strikte Eingabeprüfung, Zeit-/Größenlimits, keine neuen BLE-Schreibzugriffe, Zugangsdaten nur im Geheimnisspeicher, Hilfetext mit Voreinstellung an jedem Feld.
