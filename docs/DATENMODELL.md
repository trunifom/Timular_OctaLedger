# Datenmodell und Dateipfade

Ziel: SQLite im Benutzerprofil, nicht im Projektordner. Pfade über platformdirs
ermitteln; Benutzer kann einen bewussten alternativen Datenpfad wählen. Geplante
Unterordner: data/, logs/, backups/, exports/ (umgesetzt, siehe SOFTWAREDOKUMENTATION §5).
Schema und Migrationen: SOFTWAREDOKUMENTATION §9 (Migrationen 0001 bis 0003 umgesetzt).

| Entität | Inhalt |
|---|---|
| devices | Interne UUID, Alias, optionale Firmware, Plattformkennung, **Modus** (`time` = Zeiterfassung, `control` = Steuerung; Migration 0003) |
| face_mappings | Gerät, technische Seite, Aktivität, Revision |
| activities/projects | Benennung, Farbe, Archivierungsstatus |
| raw_events | UUID, Empfangszeit UTC, Sequenz, Verbindungssitzung, Rohwert |
| sessions | Tätigkeit, Beginn/Ende UTC, Quelle, Gerät, Qualitätskennzeichen |
| corrections | Änderungsgrund, alter/neuer Wert, Zeitpunkt, Revision |
| integrations | Verbindung zu etwas Steuerbarem (Art, Name, Einstellungen **ohne Geheimnisse**, aktiv); Migration 0003 |
| face_actions | Gerät, Seite, Verbindung, Bezeichnung, Aktionsparameter, Revision (nur im Steuerungsmodus) |
| integration_jobs | Warteschlange („Outbox“): Auftrag, Ziel, Status, Versuche, Verfallszeit; Laufzeitdaten, **nicht** Teil der Sicherung |
| audit_log | Löschungen, Bereinigungen, Restore (zusätzlich umgesetzt) |
| app_state | aktiver Tracker, Pause (zusätzlich umgesetzt, Migration 0002) |

Gerätekennung nicht mit global stabiler Bluetooth-MAC gleichsetzen. Baseline,
Seitenwechsel und Trennung sind verschiedene Ereignisse. Ungültige Pakete als
Diagnose behandeln, keine Sitzung daraus erzeugen.

Ereignisschema ist versioniert. Korrektur erhält Originalbeobachtung. Für Diagramme
zeitraumübergreifende Sitzungen an Grenzen aufteilen. Überschneidungen nicht
unbemerkt aufsummieren. Sommerzeit und gewählte Anzeigezeitzone berücksichtigen.

CSV dient Analyse; JSON-Backup enthält Schema, Kennungen, Zuordnungen und Auditdaten.
Ein Restore muss Transaktionen, Schema- und Konfliktprüfung besitzen. Keine ungeprüften
Dateipfade oder Befehle aus Importen akzeptieren. Migrationen in geordneter Folge,
Backup vor nicht rückwärtskompatibler Änderung.
