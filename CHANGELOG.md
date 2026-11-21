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
