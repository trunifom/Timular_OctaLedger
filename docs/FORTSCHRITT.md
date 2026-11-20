# Fortschrittsprotokoll

Zentrale Liste aller erledigten und offenen Arbeitspakete (AP). Wird nach **jedem**
umgesetzten Feature aktualisiert. Zeitangaben sind lokale Zeit des Entwicklungsrechners.
Der Commit-Hash eines Eintrags wird im jeweils **nächsten** Commit nachgetragen, weil er
vor dem Commit nicht bekannt ist (Eintrag „folgt" = noch nachzutragen).

Verbindliche Arbeitsregeln: [CLAUDE.md](../CLAUDE.md).

## Erledigt

| AP | Beschreibung | Datum | Uhrzeit | Commit |
|---|---|---|---|---|
| AP-00 | Projektregeln (`CLAUDE.md`, `AGENTS.md`) und dieses Fortschrittsprotokoll | 2026-11-20 | 20:52 | folgt |

## Offen (Reihenfolge der Umsetzung)

| AP | Beschreibung | Roadmap |
|---|---|---|
| AP-01 | Fehlerhierarchie mit stabilen Fehlercodes (`core.errors`) | M2 |
| AP-02 | Zentrales Logging mit Redaktion und rotierenden Dateien (`core.logging`) | M2 |
| AP-03 | Einstellungen und Benutzerprofil-Pfade (`core.settings`) | M2 |
| AP-04 | Domänenmodelle (Gerät, Aktivität, Projekt, Ereignis, Sitzung, Korrektur) | M3 |
| AP-05 | Orientierungs-Zustandsautomat: Baseline, Entprellung, Duplikate | M2 |
| AP-06 | Zeitregeln: Tagesgrenzen-Teilung, Überschneidungen, Zeitzonen | M3 |
| AP-07 | SQLite-Datenbank und Migrationen (`storage.database`) | M3 |
| AP-08 | Repositories mit Transaktionen und Auditspur | M3 |
| AP-09 | Tracking-Service: Sitzungslogik, Start/Stop/Pause, Unsicherheit | M3 |
| AP-10 | Device-Service: Registrierung, Kalibrierung, Übergabe | M3 |
| AP-11 | BLE-Protokoll, Transport-Abstraktion und FakeTransport | M2 |
| AP-12 | Bleak-Scanner und -Client (nur manuell hardwaregetestet) | M1 |
| AP-13 | Agent-Supervisor: Reconnect, Backoff, Queues, Shutdown | M2 |
| AP-14 | Reporting-Service: Tages-/Wochenwerte, Filter | M4 |
| AP-15 | Export-Service: CSV, JSON-Backup, Restore | M5 |
| AP-16 | API: Security, Schemas, Routen, App | M4 |
| AP-17 | Dashboard-Client (HTTP) | M4 |
| AP-18 | Streamlit-GUI: Seiten, Hilfetexte, Hell/Dunkel, Schriftgröße | M4 |
| AP-19 | CLI-Erweiterung und CI-Anpassung | M4 |
| AP-20 | Abschlussdokumentation: Benutzerhandbuch, Software, Installation | M5 |

Hinweis: Nicht erledigt und ausdrücklich außerhalb dieses Protokolls bleibt der
**Hardwaretest** mit echten Trackern (Abnahmekriterien A-01 bis A-07 teilweise) sowie die
**Lizenzwahl**.
