# Datenmodell und Dateipfade

Ziel: SQLite im Benutzerprofil, nicht im Projektordner. Pfade über platformdirs
ermitteln; Benutzer kann einen bewussten alternativen Datenpfad wählen. Geplante
Unterordner: data/, logs/, backups/, exports/. Pfade: siehe SOFTWAREDOKUMENTATION §5;
Datenbankschema und Migrationen: SOFTWAREDOKUMENTATION §9 (Migration 0001 umgesetzt;
`integration_jobs` folgt mit F-20).

| Entität | Inhalt |
|---|---|
| devices | Interne UUID, Alias, optionale Firmware, Plattformkennung |
| face_mappings | Gerät, technische Seite, Aktivität, Revision |
| activities/projects | Benennung, Farbe, Archivierungsstatus |
| raw_events | UUID, Empfangszeit UTC, Sequenz, Verbindungssitzung, Rohwert |
| sessions | Tätigkeit, Beginn/Ende UTC, Quelle, Gerät, Qualitätskennzeichen |
| corrections | Änderungsgrund, alter/neuer Wert, Zeitpunkt, Revision |
| integration_jobs | Auftrag, Ziel, Status, Versuche, Verfallszeit |

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
