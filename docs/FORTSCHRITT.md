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
| AP-18b | GUI-Seiten Geräte (Registrierung, Suche, Kalibrierung, Übergabe) und Verwaltung (Tätigkeiten/Projekte) | 2026-11-20 | 22:16 | folgt |

## Offen (Reihenfolge der Umsetzung)

| AP | Beschreibung | Roadmap |
|---|---|---|
| AP-18 | Streamlit-GUI: Seiten, Hilfetexte, Hell/Dunkel, Schriftgröße | M4 |
| AP-19 | CLI-Erweiterung und CI-Anpassung | M4 |
| AP-20 | Abschlussdokumentation: Benutzerhandbuch, Software, Installation | M5 |

Hinweis: Nicht erledigt und ausdrücklich außerhalb dieses Protokolls bleibt der
**Hardwaretest** mit echten Trackern (Abnahmekriterien A-01 bis A-07 teilweise) sowie die
**Lizenzwahl**.
