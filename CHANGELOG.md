# Changelog

Format orientiert an *Keep a Changelog*; Versionierung nach PEP 440. Es gibt noch kein Release.

## 0.1.0.dev0 – in Entwicklung

### Hinzugefügt
- **Kern:** Fehlerhierarchie mit stabilen Codes (`OL-<BEREICH>-<NNN>`), zentrales Logging mit
  Geheimnis-Redaktion, atomarer Dateizugriff, validierte Einstellungen und Benutzerprofil-Pfade.
- **Domäne:** unveränderliche, selbstvalidierende Modelle; Zustandsautomaten für Entprellung/Baseline und
  Verbindungslebenszyklus; Intervall-Algebra mit sommerzeitkorrekter Tagesteilung.
- **Datenhaltung:** SQLite mit versionierten Migrationen (Prüfsumme, Backup vor Migration), Repositories,
  Auditspur, Überschneidungs-Trigger.
- **Anwendungslogik:** Tracking-Service (Ereignisregeln, aktiver Tracker, Übergabe, manuelle Steuerung,
  Teilen/Korrigieren), Geräte-/Katalog-Service, Reporting (Gerätezeit vs. persönliche Zeit,
  Unsicherheit), Export (CSV mit Injection-Schutz, JSON-Backup mit Prüfsumme, validierter Restore).
- **Bluetooth:** Protokoll/Capability-Discovery, Transport-Abstraktion **ohne Schreibzugriff**,
  Simulator, Bleak-Scanner und -Transport, Agent-Supervisor mit Reconnect/Backoff/begrenztem Puffer.
- **Agent und API:** Agent-Laufzeit (BLE-Thread + API-Thread), lokale FastAPI-API (Token, Host-/Origin-
  Prüfung), Dashboard-Client (Token nur an Loopback).
- **Dashboard:** acht Seiten (Übersicht, Geräte, Verwaltung, Zeitjournal, Statistik, Daten,
  Einstellungen, Diagnose), Hilfetexte an jedem Feld, Hell-/Dunkel-Umschalter, zwei Schriftgrößen.
- **Werkzeuge:** CLI (`agent`, `dashboard`, `status`, `scan`, `paths`, `backup`, `restore`),
  Startskripte, CI, `constraints-tested.txt`, manuelle Hardware-Smoketests.
- **Dokumentation:** Benutzerhandbuch, Softwaredokumentation, Installationsanleitung, Testplan,
  Fortschrittsprotokoll, verbindliche Agentenregeln (`CLAUDE.md`).

### Hinzugefügt (Musik-Player, AP-61 bis AP-63)
- **Lokaler Player:** Dateien, ganze **Ordner/Alben** und **.m3u-Playlists** (Pfad tippen oder im Windows-Fenster wählen), **einmal / alles wiederholen / ein Titel endlos**, **zufällige Reihenfolge**, Weiter, Zurück, Pause, Springen, Stopp jederzeit; defekte Titel werden übersprungen und genannt. Mit **FFmpeg** (optional) auch AAC/M4A, WMA, Opus, AIFF … und der Ton von Videodateien.
- **Seite „Musik-Player“** neu: „Jetzt läuft“ mit Steuerung, **Alles stoppen**, Reiter *Dieser PC*, *YouTube & YouTube Music*, *Spotify*; API `/player/*` und `/system/pick-path`.
- **Würfelseiten:** Pfad/Ordner mit Wiederholen und Zufall, YouTube mit Wiederholen/Zufall; Halterung **weiterlaufen lassen**.
- **YouTube:** Wiederholen/Zufall, Fehlertexte mit „Auf YouTube öffnen“, optional mit dem eigenen YouTube-Konto. Werbung wird **nicht** entfernt, nichts heruntergeladen.

### Geändert (Qualitätsdurchgang, AP-60)
- Strengere Lint-Regeln (B, UP, BLE, T20, C4, PIE, SIM, S, RUF100) mit begründeten Ausnahmen; alle Funde behoben, `datetime.UTC` überall.
- Nicht abgefangene Ausnahmen (Hauptthread und Threads) landen mit Traceback im Log; das Dashboard zeigt bei einem Seitenfehler eine ruhige Meldung mit Fehlercode statt eines Stacktraces, API-Fehler im Dashboard werden mit Code protokolliert.
- Menü: neue Gruppe **Zeiten** (Zeitjournal, Einträge, Diagramme, Statistik); **Alltag** enthält Übersicht, Würfel live, Musik-Player.
- Ungenutzten Code entfernt; „Eintrag“ statt „Sitzung“ in Meldungen; README/Handbuch/GUI-Konzept auf den Stand gebracht.

### Hinzugefügt (Diagramme, AP-59)
- Neue Seite **Diagramme** mit 17 interaktiven Plotly-Diagrammen in fünf Gruppen (Verlauf, Anteile, Muster, Dauer, Zeitstrahl): gestapelte Balken je Tag/Woche/Monat, Trend mit Durchschnitt, aufsummierte Linien, Arbeitsbeginn/-ende, Ring, Sonnenstrahl, Treemap, Fluss, Zeit je Tag, zwei Wärmekarten, Wochentagsvergleich, Matrix, Histogramm, Boxplot, Streudiagramm, Zeitstrahl.
- Zoomen, Schwebetext, Legende, Bereichsregler; **Klick auf ein Element** listet die Einträge dahinter; zu jedem Diagramm die Zahlen als Tabelle und CSV; Kennzahlen; dieselbe Filterleiste wie *Einträge* (eigenständig).

### Hinzugefügt (Einträge verwalten, AP-57/58)
- **Sammelbearbeitung** (`POST /entries/edit`, `/entries/delete`, `GET /entries/history`): Tätigkeit, Projekt, Tags, Notiz, Qualität und Zeit (verschieben) vieler Einträge in **einer** Transaktion (alles oder nichts), Grund Pflicht, jede Änderung in der Prüfspur; Löschen mit automatischer Sicherung; laufende Einträge bleiben unberührt.
- Neue Seite **Einträge**: Suche (alle Wörter), Filter nach Zeitraum, Tätigkeit, Projekt, Gerät, Tags (beliebig/alle/keiner), Qualität, Quelle, Dauer, Wochentag und Tageszeit; **Suchprotokoll**; Tabelle mit allen Werten und Mehrfachauswahl (oder „alle Treffer“); Aktionen zuordnen, taggen, verschieben, Notiz/Qualität, löschen; **Änderungsprotokoll** mit Vorher/Nachher.

### Hinzugefügt (Würfel auslesen, AP-56)
- Neue Seite **Würfel-Datenblatt**: liest alle lesbaren Angaben des verbundenen Würfels (nur lesen), zeigt Rohwert, Länge und – nur wo bekannt – die Bedeutung; unbekannte Angaben ohne erfundene Deutung, nicht lesbare werden nicht angefasst, der Firmware-Update-Dienst nie.
- **Aufzeichnung** der Rohdaten des Beschleunigungssensors (5–30 s, nur auf Knopfdruck); Speicherung (Migration 0013, `device_snapshots`, 20 je Würfel, in der Sicherung), Export als JSON und CSV (Formeln entschärft); API `POST /devices/{id}/readout`, `GET /devices/{id}/snapshots`, `GET`/`DELETE /snapshots/{id}`.
- Einstellbare Werte (LED, Empfindlichkeit, Energiemodus) bewusst **nicht** umgesetzt: keine belegte Quelle.

### Hinzugefügt (Mehrere Würfel parallel, AP-55)
- **Ein Titel je Musik-Ziel, Besitzer-Regel:** Wer zuletzt startet, übernimmt (die Musik des anderen ist ersetzt); **ein Stopp wirkt nur durch den Besitzer** – auch ein schon eingereihter Stopp eines anderen Würfels wird beim Senden verworfen. Ziel = Verbindung (bei Home Assistant mit Mediengerät). Übersicht „Wer steuert was?“ (`GET /music/owners`).
- **Konflikte:** Verschiedene Befehle zweier Würfel an dasselbe Gerät innerhalb von 5 s werden in Eingangsreihenfolge gesendet und im Verlauf markiert (Migration 0012, `integration_jobs.note`); derselbe Befehl zweimal ist kein Konflikt.
- Bewusst nicht gebaut: mehrere gleichzeitige Zeit-Würfel (es gibt einen laufenden Eintrag), „ältere Befehle verwerfen“.

### Hinzugefügt (Würfel-Inspektor, AP-54)
- Neue Seite **Würfel-Inspektor**: anklickbares Würfelbild (Streamlit-Komponente v2, ohne Bauwerkzeug) **und** gleichwertige Zahlenknöpfe 1–8; **Seitenblatt** in Klartext je Bereich (Zeit: Tätigkeit, Projekt, Schlagworte, Notizvorlage; Smarthome: jeder Schritt der Kette mit Werten, Wartezeit, Fehlerverhalten, Bedingung; Musik: Titel, Ziel, Lautstärke, Halterung).
- **Neu programmieren** (springt mit der Seite in den Editor), **Seite leeren**, Tabelle **Alle Seiten auf einen Blick**, Text-Export.
- Neue reine Bausteine `dashboard/face_sheet.py` und `cube.face_at`.

### Hinzugefügt (Funktionsbereiche, AP-53)
- **Bereich** jedes Würfels (Zeit, Smarthome, Musik) als Pille mit Symbol und Text in Banner, Wähler und Karten; Knopf **Bereich ändern** im Banner; Umschalter mit Hinweis, dass Einstellungen anderer Bereiche erhalten bleiben.
- **Bereichsfilter** in der Seitenleiste: filtert den Würfel-Wähler und blendet nur für andere Bereiche geltende Menüpunkte aus (`PageDef.areas`); die aktuelle Seite bleibt sichtbar.

### Hinzugefügt (Batterie-Cockpit, AP-52)
- **Batterie immer sichtbar:** eine Zeile je Würfel unter der Statusleiste (Balken, Prozent, Stufe als Text, bei fehlender Verbindung der zuletzt gemessene Wert), Warnung auf jeder Seite bei *schwach* und *fast leer*; Karten in der Übersicht.
- **Verlauf gespeichert** (Migration 0011, `battery_log`; Änderung oder alle 6 Stunden, 400 Tage, in der Sicherung), Kurve und **ehrlich gekennzeichnete Schätzung** der Restdauer; `GET /devices/{id}/battery`, `battery` in `GET /status`.
- Stufenwechsel nach unten stehen einmal im Protokoll (WARNING, *fast leer* ERROR), auch über einen Neustart hinweg.

### Hinzugefügt (Würfel-Identität, AP-51)
- Jeder Würfel hat **Nummer, Name und Farbe** (Migration 0010, `devices.color`; automatische, unterscheidbare Palette; änderbar über `PATCH /devices/{id}`); API-Felder `number`, `color`, `color_name`, `badge`; Sicherung mit optionalem Feld `color`.
- **Ausgewählter Würfel** in der Seitenleiste (gilt auf allen Seiten), **Banner** „Sie bearbeiten: …“ auf *Seiten zuordnen* und *Würfel live*, Übersicht mit Nummer und Bereich, Farbwahl auf *Würfel verwalten*. Die Auswahlfelder „Tracker“ der einzelnen Seiten entfallen.

### Geändert (Log-Auswertung vom 2026-11-22)
- **Musik-Player sicherer:** Statt des YouTube-Skripts (`iframe_api`) im Dashboard gibt es nur noch einen eingebetteten Rahmen von `youtube-nocookie.com`; Lautstärke/Start per `postMessage`. Kein fremdes Skript hat damit Zugriff auf das Dashboard.
- **Unbekannte Rohwerte (0x09/0x0B/0x0D beim Rollen):** nur das erste Vorkommen je Wert und Verbindung wird als `invalid`-Ereignis gespeichert, der Rest gezählt und beim Verbindungsende im Protokoll zusammengefasst.
- **Ruhender Würfel:** Sendet er nach dem Verbinden keinen Wert, bleibt OctaLedger verbunden, liest den Wert alle 3 s erneut und zeigt „Drehen Sie ihn einmal, dann geht es weiter.“ Vorher wurde alle 10 s neu verbunden (mit falschen Verbindungsabbrüchen im Verlauf).
- Veraltetes `st.components.v1.html` durch `st.iframe` ersetzt (Musik-Player, Bericht-Vorschau): Streamlit meldete die Entfernung und schrieb sekündlich eine Warnung ins Protokoll.
- Scheitert das Lesen des Anfangswerts eines Würfels, steht der Grund jetzt als Warnung im Protokoll (vorher nur im Debug-Pegel).

### Hinzugefügt (Player in der App, AP-50)
- Neue Verbindungsart `browser` (Musik-Ziel ohne Netzwerkziel) und Seite **Musik-Player**: YouTube-/YouTube-Music-Titel im eingebetteten Player, nur bei geöffneter Seite, erst nach ausdrücklicher Zustimmung zum Laden von youtube.com; API `GET /music/browser-state`.
- Korrektur: `spotify_play` zählt nun als Wiedergabe-Aktion („läuft gerade“).

### Hinzugefügt (Spotify direkt, AP-49)
- Neue Verbindungsart `spotify` (Musik-Ziel): Wiedergabe von Titel/Album/Playlist/Künstler/Podcast, Pause (= Stopp) und Lautstärke über die Spotify Web API; Kopplung per Browser mit PKCE über einen lokalen Rückkanal (`127.0.0.1`, einmaliger `state`, kein Client Secret), Zugangstoken nur im Speicher, Berechtigung im Geheimnis-Speicher.
- Dashboard-Client: Kopplung darf bis zu 150 s warten (`PAIR_TIMEOUT`).

### Hinzugefügt (Musik-Modus, AP-48)
- Dritte Betriebsart **Musik** je Würfel (Migration 0009, gespeichert als `control` + Kennzeichen): jede Seite ein Titel aus einem eingefügten Link (Spotify, YouTube, Stream), die Halterung und Seiten ohne Titel beenden die Musik, ein Zielwechsel stoppt das alte Ziel zuerst, eine neue Seite ersetzt nicht gesendete Befehle.
- Ziele: Lokaler Player und Home Assistant (`ActionSpec.capability`, `Adapter.music_play_params/music_stop_params`); „Läuft gerade“ (`music_now`) erst nach tatsächlich gesendetem Befehl; Anhalten nach der Frist bei Verbindungsverlust (Housekeeper).
- API: `GET /music/state`, `POST /music/parse`, `GET/PUT /devices/{id}/music`, `PUT /devices/{id}/music/faces/{face}`; Oberfläche: Musik-Editor, Halterungs-Einstellungen, „♪“-Anzeige in *Würfel live*.

### Hinzugefügt (Vorlagen und Rezepte, AP-46)
- `AdapterSpec.presets` und Auswahl „Vorlage“ im Aktionseditor; Vorlagen für Webhook (Node-RED, WLED, Shelly, openHAB, Home-Assistant-Webhook) und MQTT (Zigbee2MQTT, Tasmota, Node-RED), alle als „nicht an echtem Ziel geprüft“ gekennzeichnet.
- Platzhalter `{device}`, `{face}`, `{label}`, `{time}` in Webhook-Inhalt und MQTT-Nachricht (Whitelist, ohne Ausdrücke, bei JSON maskiert).
- Neues Dokument `docs/REZEPTE.md` (auch in der App lesbar).

### Hinzugefügt (Medien, AP-45)
- Home Assistant: Aktionen *Musik abspielen*, *pausieren*, *beenden*, *Lautstärke setzen* für `media_player`.
- Neue Verbindungsart **Lokaler Player** (Extra `audio`): Stream/Datei abspielen, stoppen, Lautstärke; eigener Arbeits-Thread, Warteschlange, Engine hinter einer Schnittstelle.
- Gemeinsame Adressprüfung gegen SSRF (`urlcheck`): Loopback/Link-Local/Metadaten immer verboten, Heimnetz nur mit Schalter, Weiterleitungen einzeln geprüft; Dateien nur aus freigegebenen Ordnern.

### Hinzugefügt (Aktionsketten und Bedingungen, AP-44)
- Eine Seite im Steuerungsmodus kann **mehrere Schritte** haben, mit Verzögerung, „bei Fehler weitermachen“, „aktiv“ und einer Bedingung (Zeitfenster inkl. über Mitternacht, Wochentage). Migration 0008; `PUT /devices/{id}/actions/{face}` akzeptiert `steps`, `GET /devices/{id}/chains`.
- Ein neuer Seitenwechsel verwirft noch nicht gesendete, verzögerte Schritte; ein fehlgeschlagener Schritt bricht die folgenden ab (außer „weitermachen“). Bestehende Einzelaktionen und ältere Sicherungen funktionieren unverändert.
- Fix: Der Dispatcher prüft vor dem Senden den aktuellen Zustand eines Auftrags (ein früherer Auftrag derselben Runde kann ihn abgebrochen haben).

### Hinzugefügt (Hue erweitert und Bridge-Suche, AP-43)
- Hue: Übergang (`transition_ms`), Szenen-Modus (`active`/`dynamic_palette`/`static`) und Szenen-Helligkeit, Mindestabstand der Anfragen (`min_interval_ms`), HTTP 429 wird später wiederholt.
- Bridge-Suche (`Adapter.find_targets`, `can_find`, `POST /adapters/{kind}/find`): im Heimnetz per mDNS (Extra `discovery`) und nur auf Klick über Philips' Dienst; nur private Adressen werden akzeptiert.

### Hinzugefügt (Bericht und Kalender-Import, AP-42)
- Druckbarer Bericht (HTML ohne Skripte; PDF mit dem Extra `pdf`) mit denselben Summen wie die Statistik; Kopfzeile aus `report.author/organization`.
- Kalender-Import (.ics, Extra `ics`) als Vorschläge mit Bestätigung, atomar gebucht; Grenzen 2 MiB, 90 Tage, 1000 Termine.
- **Korrektur:** `fpdf2` ist LGPL-3.0 (nicht BSD-2 wie geplant) und `recurring-ical-events` LGPL-3.0; beide bleiben optionale, dynamisch geladene Extras.

### Hinzugefügt (Tags, Vorlagen, Budgets, AP-41)
- Tags je Eintrag (Filter im Journal), Standard-Tags und Notizvorlage je Tätigkeit, Budget/Stundensatz/abrechenbar je Projekt mit Warnung bei 80 % und 100 %, Auswertung „Projekte & Budget“. Migration 0007.
- CSV-Export: neue Spalten `tags`, `billable`, `amount` (am Ende). Beträge nur im Bericht berechnet und gerundet.

### Hinzugefügt (Soll, Saldo, Pausenhinweise, AP-40)
- Soll je Wochentag (versioniert nach Gültig-ab-Datum), Abwesenheiten, optionale gesetzliche Feiertage (Extra `holidays`), Saldo je lokalem Tag (Reiter „Soll und Saldo“ auf *Statistik*, `GET /reports/balance`). Migration 0006.
- Pausenhinweise (Voreinstellung aus; Orientierung, keine Rechtsberatung) als Rückfrage `break_hint`.
- **Sicherung Schema 3:** einfache Tabellen (`device_buttons`, `work_schedule`, `absences`) im Abschnitt `tables`; Schema 1 und 2 bleiben lesbar.

### Hinzugefügt (Tray, Hinweise, Autostart, AP-39)
- Autostart über den Benutzer-Run-Schlüssel (`octaledger autostart on|off|status`, `GET/PUT /system/autostart`, Schalter unter *App*), Zustand wird gelesen.
- Tray-Symbol (optionales Extra `tray`, Zustand als Farbe, Tooltip, Menü) und Windows-Hinweise (optionales Extra `toast`, Ruhezeit) für neue Rückfragen; Einstellungen `tray`, `notifications.toast/quiet_*`.

### Hinzugefügt (Arbeitstag, AP-38)
- Einstellungen `work` (alles aus): Arbeitsende mit Auto-Stopp und Rückfrage, Arbeitstage, Leerlauf-Erkennung (`GetLastInputInfo`, nur die Dauer), Erinnerungen „Zeit starten?“ und „Noch dabei?“.
- Rückfragen `idle` und `auto_stop` mit Antworten in der Oberfläche und über `POST /attention/{id}/resolve`.

### Hinzugefügt (Würfeltaste und Batterie-Warnung, AP-37)
- Die Taste des Würfels wird abonniert (nur lesen): kurz/lang als Ereignis `button`; je Würfel belegbar mit Pause/Fortsetzen, Beenden, Letzte Tätigkeit starten (Voreinstellung: nichts). Migration 0005, `GET/PUT /devices/{id}/buttons`.
- Batterie wird alle 10 Minuten gelesen; Einstellung `notifications.battery_warning_percent` (20) löst einmal pro Entladung eine Erinnerung aus.

### Hinzugefügt (Hilfe beim Verbinden)
- Hue: verständliche Fehlermeldungen je Ursache (Zeitüberschreitung, abgelehnt, Name nicht auflösbar) und ausführliche Fehlersuche in der Anleitung; Home Assistant: Anleitung zu Adresse, Token und Fehlern; neue **Testverbindung (Probelauf)** zum Üben ohne Geräte.

### Hinzugefügt (Verbindungsverlust mit Frist und Rückfragen, AP-36)
- Neue Richtlinie `grace_then_stop` (jetzt Voreinstellung) mit `disconnect_grace_seconds` (300): Die Zeit läuft nach einem Verlust weiter und endet nach der Frist am Moment des Verlusts.
- Rückfragen-Zentrale (`attention_items`, Migration 0004, `GET /attention`, `…/resolve`, `…/dismiss`) und Panel unter der Statusleiste mit den Antworten behalten, leer lassen, zuordnen, nichts tun.
- Housekeeper-Thread im Agenten (alle 5 s) für zeitgesteuerte Regeln.

### Geändert (Würfel-Eingang, AP-35)
- Der Basis-Wert **10** wird wie 0 als neutral erkannt (`BASE_VALUES`); ungültige Pakete nennen den Rohwert im Protokoll.
- Vor dem Verbinden sucht der Agent den Würfel kurz (`[agent] scan_before_connect`, `scan_timeout_seconds`), mit klarer Meldung, wenn er nicht wirbt.

### Hinzugefügt (Live-Ansicht, Startseite, Einrichtungsassistent)
- **Würfel live:** Echtzeit-Ansicht mit SVG-Würfel, Entprellzustand, letzten Bewegungen und deren Wirkung.
- **Startseite:** Erklärung des Würfels, geführte Einrichtung mit einem Klick (Suchen, Registrieren, Zuordnen, Verbinden),
  nächster Schritt aus dem echten Einrichtungsstand, das Handbuch zum Nachlesen im Programm.
- **Seiten zuordnen:** Assistent, der anzeigt, welche Seite oben liegt, und jeder Seite eine Tätigkeit gibt.
- Der Agent verbindet beim Start den aktiven Tracker automatisch (wenn eine Adresse gespeichert ist).

### Hinzugefügt (Steuerungsmodus, AP-26 bis AP-31)
- **Modus pro Würfel:** *Zeit* (Standard) oder *Steuerung*; im Steuerungsmodus löst jede Seite eine **Aktion** aus und es entstehen keine Zeiten.
  Migration `0003` (`devices.mode`, `integrations`, `face_actions`, `integration_jobs`), Sicherungsformat Schema 2 (Schema 1 bleibt lesbar).
- **Warteschlange („Outbox“) und Dispatcher-Thread:** Aktion und Rohereignis in einer Transaktion, eindeutiger Schlüssel, Verfall nach 30 s,
  höchstens 50 wartende Aufträge je Verbindung, Wiederholung nur bei sicherem Nichtankommen (höchstens 3 Versuche).
- **Adapter-Baukasten** mit Selbstbeschreibung (`AdapterSpec`): Formulare und Prüfung entstehen daraus; **Webhook**, **MQTT** (eigener
  MQTT-3.1.1-Sender), **Home Assistant** (Hub für Matter und Google Home), **Philips Hue** (CLIP v2, Zertifikat-Anheftung); gemeinsame sichere HTTP-Logik `httpio`.
- **Geheimnisspeicher** `secrets.json`: nie in Datenbank, Sicherung, API-Antwort oder Protokoll.
- **API:** `/adapters`, `/integrations` (+ `check`, `probe`, `pair`, `discover`), `/jobs`, `/devices/{id}/mode`, `/devices/{id}/actions/{face}`.
- **Oberfläche:** Seite *Verbindungen*, Moduswechsel pro Würfel, Aktions-Editor in *Seiten zuordnen*, Live-Ansicht und Geräteseite für Steuerungs-Würfel.

### Geplant (Dokumentation, kein Code)
- **Musik-Modus** als dritte Betriebsart je Würfel (Pflichtenheft §12.6, Umsetzungsplan AP-48 bis AP-50): jede Seite ein Titel (Radio, Datei, Home Assistant/Cast, Spotify, YouTube Music über Cast oder Player in der App), die **Halterung hält die Musik ganz an**.
- Recherche zu Funktionen für Zeiterfassung und Steuerung; **Pflichtenheft §12** (F-21 bis F-63, Abnahmen A-18 bis A-35) und **`docs/UMSETZUNGSPLAN.md`** (AP-35 bis AP-50 der Reihe nach, mit Warum, Wo, Wie, Tests, Risiken).
- Fund aus dem ersten echten Lauf: Der Decoder verwarf Werte außerhalb 0–8 als `invalid`; laut Community-Quelle bedeuten 0 und 10 „Würfel in der Basis“ (AP-35).

### Hinzugefügt (Einstellungen, Würfel- und Datenverwaltung; AP-33, AP-34)
- **Eine Seite pro Art von Einstellung** (Recherche: Struktur guter Settings-Seiten, Integrations-Einrichtung, destruktive Aktionen, Navigation): *Würfel verwalten*, *App*,
  *Darstellung*, *Smarthome & Verbindungen*; neue Menügruppen *Würfel* und *Einstellungen*.
- **Grund- und erweiterte Ansicht:** Adapter beschreiben `advanced`-Felder und eine deutsche Anleitung (`setup_guide`); die Formulare zeigen erst die Grundangaben, dann einen
  eingeklappten Bereich „Erweiterte Einstellungen“; Anleitungen sagen, wo man Adresse und Token findet.
- **App-Einstellungen** mit Grundansicht, erweiterten Einstellungen, Voreinstellungen im Hilfetext und „Auf Voreinstellungen zurücksetzen“; **Darstellung** (Hell/Dunkel, Schrift)
  wirkt sofort.
- **Datenverwaltung:** Einträge eines Zeitraums oder alle löschen (Vorschau, Bestätigung mit der Zahl, bei „alle“ Eintippen, automatische Sicherung vorher), **alles zurücksetzen**
  (Gefahrenzone), **Würfel entfernen** (mit oder ohne Daten) und **Kopplung aufheben**. Neue Endpunkte `/data/…`, `/devices/{id}/remove`, `/devices/{id}/unpair`, `/settings/reset`.
- Jede Schaltfläche hat jetzt einen Hilfetext (per Wächtertest erzwungen); Verbindungen zeigen das letzte Testergebnis und löschen in zwei Schritten.

### Geändert
- Menünamen: *Geräte* → *Würfel verwalten*, *Verwaltung* → *Tätigkeiten & Projekte*, *Einstellungen* → *App*, *Verbindungen* → *Smarthome & Verbindungen*; *Daten* und *Diagnose*
  bilden die Gruppe *System*.

### Hinzugefügt (Dokumentation)
- **Neue Dokumente:** `docs/API.md` (jeder Endpunkt), `docs/GLOSSAR.md`, `docs/ADAPTER_ENTWICKLUNG.md` (Anleitung mit Beispiel),
  `docs/README.md` (Wegweiser nach Zielgruppe), Screenshots in `docs/images/`.
- **Neu geschrieben:** `README.md`, `docs/ARCHITEKTUR.md`, `docs/DATENMODELL.md`, `SECURITY.md`; `CONTRIBUTING.md` um Adapter und Dokumentationspflichten erweitert.
- **Quelltext:** Docstring an jedem Modul, jeder Klasse und jeder Funktion.
- **In der Oberfläche:** Startseite mit Abschnitt „So funktioniert’s“; das Handbuch bietet jetzt zehn Dokumente (Anwender und Entwickler).
- **Wächtertests** (`tests/unit/test_documentation.py`, `tests/unit/test_gui_documentation.py`): Docstrings überall, jeder Endpunkt in `API.md`, jede Datei in
  `ORDNERSTRUKTUR.md`, keine toten Verweise, jedes Eingabefeld mit Hilfetext, jede Seite mit „So funktioniert diese Seite“.
- `scripts/update_ordnerstruktur.py` erzeugt die Dateiliste der Ordnerstruktur.

### Behoben
- Lange Kennzahlen (z. B. „34 h 20 min“) wurden in der Statistik mit „…“ abgeschnitten.

### Geändert (GUI-Überarbeitung)
- Neues Design-System (ruhige Neutralflächen, eine Primärfarbe, Karten statt Schatten, WCAG-AA, Inter lokal),
  gruppiertes Menü *Alltag / Einrichten / System* mit Symbolen und markierter aktiver Seite, globale
  Statusleiste mit Verbindungswarnung, neue Übersicht (Erste Schritte, Schnellstart, Heute), Schnellzeiträume im
  Journal, Filter der Statistik eingeklappt, Diagnose-Ampel, Begriff „Eintrag“. Siehe `docs/GUI_KONZEPT.md`.

### Bekannt / offen
- Verhalten mit echten Trackern **nicht geprüft** (nur Simulator); Protokoll aus Community-Quellen.
- Anbindungen des Steuerungsmodus nur gegen lokale Testziele geprüft, nicht gegen echte Geräte; Hue-TLS-Handshake ungeprüft.
- Obsidian (Teil von F-20) ist nicht umgesetzt; Matter und Google Home nur über Home Assistant.
- Keine Lizenz gewählt; kein Release-/Installationsprozess.
