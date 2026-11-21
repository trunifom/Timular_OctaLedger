# Fortschrittsprotokoll

Zentrale Liste aller erledigten und offenen Arbeitspakete (AP). Wird nach **jedem**
umgesetzten Feature aktualisiert. Zeitangaben sind lokale Zeit des Entwicklungsrechners.
Der Commit-Hash eines Eintrags wird im jeweils **nächsten** Commit nachgetragen, weil er
vor dem Commit nicht bekannt ist (Eintrag „folgt" = noch nachzutragen).

Verbindliche Arbeitsregeln: [CLAUDE.md](../CLAUDE.md).

## Erledigt

| AP | Beschreibung | Datum | Uhrzeit | Commit |
|---|---|---|---|---|
| AP-00 | Projektregeln (`CLAUDE.md`, `AGENTS.md`) und dieses Fortschrittsprotokoll | 2026-11-20 | 20:52 | 0ba9ca3 |
| AP-01 | Fehlerhierarchie mit stabilen Fehlercodes (`core.errors`), Umstellung von Decoder und Zeitregeln, Doku-Grundgerüst (Software/Installation/Benutzer) | 2026-11-20 | 20:52 | 1022b45 |
| AP-02 | Zentrales Logging (`core.logging`): Redaktion von Geheimnissen, rotierende Datei, Ringpuffer, `log_step` | 2026-11-20 | 20:54 | b9b13cd |
| AP-03a | Sicheres Dateischreiben/-lesen (`core.fileio`): atomares Schreiben, größenbegrenztes Lesen, Fehlerübersetzung | 2026-11-20 | 20:55 | 21f6273 |
| AP-03 | Einstellungen und Benutzerprofil-Pfade (`core.settings`): validierte Settings, TOML laden/speichern, Umgebungs-Overrides, `tzdata` | 2026-11-20 | 20:59 | d908a2f |
| AP-04 | Domänenmodelle (`domain.models`): Device, Activity, Project, FaceMapping, RawEvent, Session, Correction; Zeithelfer `utc_now`/`ensure_utc` | 2026-11-20 | 21:01 | bb76d6d |
| AP-05 | Zustandsautomaten (`domain.state_machine`): Baseline, Duplikate, Entprellung, Verbindungslebenszyklus, Backoff | 2026-11-20 | 21:03 | 8e75d02 |
| AP-06 | Zeitregeln (`domain.time_rules`): Tagesgrenzen/Sommerzeit, Wochen, Vereinigung, Überschneidungen | 2026-11-20 | 21:04 | 11b7289 |
| AP-07 | SQLite-Schicht (`storage.database`): Schema 0001, Migrationen mit Prüfsumme/Backup, Transaktionen, Backup, Integritätsprüfung | 2026-11-20 | 21:09 | c15119c |
| AP-08 | Repositories (`storage.repositories`): Storage-Fassade, Savepoints, auditierte Korrekturen, Audit-Log, Aufbewahrung | 2026-11-20 | 21:12 | 59d2467 |
| AP-09 | Tracking-Service (`application.tracking_service`): Ereignisregeln, aktiver Tracker/Übergabe, manuelle Steuerung, Teilen/Korrigieren; Migration 0002 | 2026-11-20 | 21:18 | e948fda |
| AP-10 | Geräte-/Katalog-Service (`application.device_service`, `catalog_service`): Registrierung, Kalibrierung, Tätigkeiten/Projekte, Palette | 2026-11-20 | 21:20 | 0792632 |
| AP-11 | BLE-Protokoll, Transport-Abstraktion, FakeTransport (`infrastructure.ble`): Capability-Discovery, Decoder, kein Schreibzugriff | 2026-11-20 | 21:22 | 88dd6c5 |
| AP-12 | Bleak-Scanner und -Transport (`ble.scanner`, `ble.client`) mit Stub-Tests und Opt-in-Hardwaretests (Hardware nicht verifiziert) | 2026-11-20 | 21:24 | ab25903 |
| AP-13 | Agent-Supervisor (`agent.supervisor`): DeviceWorker, Reconnect/Backoff, begrenzter Puffer, Shutdown, Statusanzeige | 2026-11-20 | 21:28 | b3b4476 |
| AP-14 | Reporting-Service (`application.reporting_service`): Tages-/Wochenberichte, Filter, Gerätezeit vs. persönliche Zeit, Unsicherheit, Journal | 2026-11-20 | 21:30 | 1257bb0 |
| AP-15 | Export-Service (`application.export_service`): CSV mit Injection-Schutz, JSON-Backup mit Prüfsumme, validierter atomarer Restore | 2026-11-20 | 21:37 | 90f814a |
| AP-16a | API-Sicherheit (`api.security`): Token (Env/Datei/Erzeugung), Bearer-Prüfung, Host-/Origin-Validierung, Log-Redaktion | 2026-11-20 | 21:39 | 54e58e9 |
| AP-16 | Lokale HTTP-API (`api`): Routen, Schemas, Fehlerabbildung, Middleware, SettingsStore; deckte 2 echte Fehler auf (behoben) | 2026-11-20 | 21:46 | ccdb007 |
| AP-17 | Dashboard-Client (`dashboard_client.client`): Token nur an Loopback, Fehlerabbildung per Code, Integrationstests über echtes HTTP | 2026-11-20 | 21:50 | 2a0a1a5 |
| AP-18a | GUI-Grundgerüst (`dashboard`): Hell/Dunkel + Schriftgröße (WCAG AA), UI-Helfer, Übersichtsseite, AppTest-GUI-Tests | 2026-11-20 | 22:00 | 1b134db |
| AP-18b | GUI-Seiten Geräte (Registrierung, Suche, Kalibrierung, Übergabe) und Verwaltung (Tätigkeiten/Projekte) | 2026-11-20 | 22:16 | 75df345 |
| AP-18c | GUI-Seiten Zeitjournal (Filter, Korrigieren/Teilen/Löschen, Zu prüfen, Nachtragen) und Statistik (Kennzahlen, Diagramme mit Tabellen) | 2026-11-20 | 22:30 | b7048af |
| AP-18d | GUI-Seiten Daten (Export/Sicherung/Restore mit Vorschau), Einstellungen, Diagnose (anonymisierter Bericht) | 2026-11-20 | 22:39 | f4ae3de |
| AP-19 | Agent-Laufzeit (`agent.main`), erweiterte CLI, Start-Skripte, CI; End-to-End-Tests; Thread-Sicherheit im Worker | 2026-11-20 | 22:48 | 78184d2 |
| AP-20 | Abschlussdokumentation: Benutzerhandbuch neu geordnet, Installation, Softwaredoku, Testplan mit Abnahmestatus, README, Grenzen; `constraints-tested.txt` | 2026-11-20 | 22:57 | 4099b39 |
| AP-21 | GUI-Überarbeitung auf Basis der UX-Recherche: gruppiertes Menü, Statusleiste, neue Übersicht, Design-System mit lokaler Schrift (`docs/GUI_KONZEPT.md`) | 2026-11-20 | 23:26 | 709bb86 |
| AP-21a | Fehlerbehebung GUI: Seitenmodule in `views/` (Streamlit-Automenü entfernt), Streamlit-Design an Hell/Dunkel angepasst (lesbare Felder, Tabellen, Tabs, Buttons) | 2026-11-21 | 12:40 | 2e601af |
| AP-21b | Speichern von Dateien wiederholt kurz, wenn Windows das Ziel sperrt (`WinError 5`) | 2026-11-21 | 12:40 | 4433caa |
| AP-22 | Live-Daten: Rohwert, wartender Wert und Verlauf im Agenten (`DeviceStatus`, `LiveEvent`), Endpunkt `GET /devices/{id}/live`, Client `live_view`; Würfel-Erkennung am Namen im Scanner | 2026-11-21 | 13:10 | 3fb93f0 |
| AP-23 | Seite „Würfel live“: schematische Würfelgrafik (SVG), Fluss Funk → Prüfung → Software, Verlauf in Sätzen (`dashboard.cube`, `views.live`) | 2026-11-21 | 14:00 | ee7d4fa |
| AP-24 | Assistent „Seiten zuordnen“: Würfelbild mit Live-Anzeige, Seite auswählen, vorhandene oder neue Tätigkeit zuordnen, Sprung zur nächsten freien Seite (`views.faces`) | 2026-11-21 | 14:40 | 16573f2 |
| AP-24a | Tests laufen im temporären Profilordner (nicht im echten Benutzerprofil, kein Konflikt mit laufendem Agent) | 2026-11-21 | 14:20 | bcb5d20 |
| AP-25 | Startseite (Willkommen, geführte Einrichtung mit einem Klick, Handbuch zum Nachlesen), Standardseite, Suchergebnis auch ohne Tracker auf der Geräte-Seite (`views.start`, `docs_reader`) | 2026-11-21 | 15:30 | 8e515a6 |
| AP-26a | Steuerungsmodus: Datenmodell (Modus je Tracker, Verbindungen, Aktionen pro Seite, Warteschlange „Outbox“), Migration 0003, Sicherung v2 (v1 bleibt lesbar, keine Geheimnisse) | 2026-11-21 | 16:30 | 80b347f |
| AP-26b | Baukasten: Adapter-Vertrag mit Selbstbeschreibung, Zugangsdaten-Speicher, Integrationsdienst (Verbindungen, Aktionen pro Seite, Senden mit Wiederholung/Verfall), Steuerungspfad im Tracking, Moduswechsel | 2026-11-21 | 17:30 | 1444606 |
| AP-26c | Steuerungsmodus im Betrieb: Dispatcher-Thread im Agenten, API (Verbindungen, Aktionen pro Seite, Moduswechsel, Verlauf), Client, Autostart der Steuerungs-Tracker | 2026-11-21 | 18:40 | 003a312 |
| AP-27 | Webhook-Adapter: Web-Anfrage an beliebige Adresse (keine Weiterleitungen, keine Proxys, Antwort ungelesen, Wiederholung nur wenn sicher nicht angekommen), gegen echten lokalen Server getestet | 2026-11-21 | 19:30 | 76e676a |
| AP-28 | MQTT-Adapter: Nachricht an einen Broker veröffentlichen (MQTT 3.1.1, nur Standardbibliothek, hartes Zeitlimit, Wiederholung nur wenn sicher nichts gesendet wurde, TLS, QoS 0/1), gegen Fake-Broker auf Protokollebene getestet | 2026-11-21 | 20:10 | f956bb6 |
| AP-29 | Home-Assistant-Adapter: Einschalten/Ausschalten/Umschalten, Szene, Skript, beliebiger Dienst, Entdecken von Geräten (Weg zu Matter und Google Home); gemeinsame HTTP-Logik `httpio` | 2026-11-21 | 20:50 | 627e447 |
| AP-30 | Philips-Hue-Adapter: Lampe/Raum/Szene über die Bridge im Heimnetz, Koppeln, Entdecken, Zertifikat-Anheftung (Vertrauen beim ersten Mal); echter TLS-Handshake nicht getestet | 2026-11-21 | 21:40 | babe4c5 |
| AP-31a | Oberfläche „Verbindungen“: Formulare aus der Selbstbeschreibung der Adapter (`forms`), Testen/Koppeln/Ausprobieren/Entdecken mit Auswahllisten, Verlauf der Aktionen | 2026-11-21 | 22:30 | f83d227 |
| AP-31b | Steuerungsmodus in der Oberfläche: Moduswechsel pro Würfel, Aktions-Editor in „Seiten zuordnen“, Live-Ansicht und Geräte-Seite für Steuerungs-Würfel, Startseite und neues Handbuchkapitel 20 | 2026-11-21 | 23:30 | 76a1443 |
| AP-32a | Quelltext-Dokumentation: Docstrings für die letzten verschachtelten Hilfsfunktionen (jede Funktion und Klasse ist dokumentiert) | 2026-11-21 | 15:30 | 07b7755 |
| AP-32b | Dokumentation: API-Referenz (jeder Endpunkt), Architektur und Datenmodell neu, Sicherheit, Glossar, Adapter-Anleitung, Dokumentationsübersicht, Wächtertests (`test_documentation`), Skript für die Ordnerstruktur | 2026-11-21 | 15:40 | 242fcff |
| AP-32c | Dokumentation Teil 2: README mit Screenshots, Startseite „So funktioniert’s“, zehn Dokumente im Handbuch der App, Wächtertests für die Oberfläche, Handbuch/Installation/BLE/Konzept/Pflichtenheft/Roadmap/Testplan/Changelog aktualisiert, Metrik-Abschneiden behoben | 2026-11-21 | 16:10 | 146a4a2 |
| AP-33a | Datenverwaltung: `DataService` (Vorschau, Löschen mit Sicherung und Zahlenbestätigung, Würfel entfernen, Zurücksetzen), neue Endpunkte, Client; Adapter mit erweiterten Feldern und Anleitungen | 2026-11-21 | 16:50 | 1d89f84 |
| AP-33b | Oberfläche der Datenverwaltung: Reiter „Löschen“, Würfel verwalten (Kopplung aufheben, entfernen) | 2026-11-21 | 17:10 | dd275fb |
| AP-34 | Einstellungsbereiche getrennt: Würfel verwalten · App · Darstellung · Smarthome & Verbindungen, neue Menügruppen, Hilfetext an jedem Knopf, Handbuch und Doku angepasst | 2026-11-21 | 17:45 | 677827f |

## Offen

Alle Arbeitspakete (AP-00 bis AP-34) sind umgesetzt. Offen ist nur, was **kein Entwicklungsagent erledigen
kann** oder bewusst nicht im Umfang liegt:

| ID | Thema | Wer | Hinweis |
|---|---|---|---|
| HW-01 | **Hardwaretest** mit den echten USB-C-Trackern (Abnahmekriterien A-01, A-02–A-05, A-07 mit Hardwarebezug) | Anwender | Anleitung `docs/INSTALLATION.md` §5; Ergebnisse in die Matrix in `docs/TESTPLAN.md`; danach Entprellzeit und Neutralwert festlegen |
| LIC-01 | **Lizenz wählen** (Projekt hat bewusst keine) und Namens-/Markenfreiheit prüfen | Projektinhaber | vor jeder Veröffentlichung; ohne Lizenz ist öffentlicher Code nicht frei nachnutzbar |
| SEC-01 | privaten **Meldeweg** für Sicherheitsprobleme in `SECURITY.md` ergänzen | Projektinhaber | vor Veröffentlichung |
| VIS-01 | **Visueller Browsertest** aller Dashboard-Seiten (Layout, Farben, kleine Bildschirme) | Anwender | AppTest prüft nur Logik/Elemente |
| REL-01 | Release-Prozess, Installer, Windows-Autostart | optional | Roadmap „Später“ |
| F-20 | Obsidian-Anbindung (Home Assistant, Hue, MQTT, Webhook sind umgesetzt) | optional („Kann“) | nur über den Webhook-Adapter denkbar; ein eigener Adapter folgt der Anleitung `docs/ADAPTER_ENTWICKLUNG.md` |
| ECHT-01 | **Anbindungen mit echten Zielen** ausprobieren (Home Assistant, Hue-Bridge, MQTT-Broker) | Anwender | bisher nur gegen Testziele geprüft; Ergebnis in `docs/QUELLEN_UND_GRENZEN.md` und `docs/TESTPLAN.md` (A-17) festhalten |

Veröffentlichen (`git push`) übernimmt der Projektinhaber selbst; Agenten pushen nie.
