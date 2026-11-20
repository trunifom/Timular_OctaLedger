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

### Bekannt / offen
- Verhalten mit echten Trackern **nicht geprüft** (nur Simulator); Protokoll aus Community-Quellen.
- Keine Lizenz gewählt; kein Release-/Installationsprozess; F-20 (Integrationen) nicht umgesetzt.
