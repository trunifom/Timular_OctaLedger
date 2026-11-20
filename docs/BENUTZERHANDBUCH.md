# Benutzerhandbuch

Dieses Handbuch richtet sich an Anwender von OctaLedger. Es wächst mit den
Funktionen; was noch nicht umgesetzt ist, steht in [FORTSCHRITT.md](FORTSCHRITT.md).

## 1. Was ist OctaLedger?

OctaLedger erfasst Arbeitszeit lokal auf Ihrem Rechner mit einem kompatiblen
Timeular-/ZEI-Würfel. Sie drehen den Würfel auf die Seite einer Tätigkeit, OctaLedger
startet die Zeit und speichert sie in einer lokalen Datenbank. Es wird kein
Herstellerkonto und keine Cloud benötigt.

## 2. Wenn eine Fehlermeldung erscheint

Fehlermeldungen enthalten einen **Fehlercode** wie `OL-BLE-002`. Nennen Sie diesen Code,
wenn Sie Hilfe suchen. Die Bedeutung aller Codes steht in der Tabelle unten.

| Code | Bedeutung | Was Sie tun können |
|---|---|---|
| OL-CONFIG-001 | Einstellungen ungültig | Einstellungsdatei prüfen oder zurücksetzen |
| OL-VALID-001 | Eingabe ungültig | Angaben im Formular prüfen |
| OL-STATE-001 | Eintrag nicht gefunden | Liste neu laden |
| OL-STATE-002 | Konflikt mit bestehenden Daten | Überschneidungen oder Duplikate beheben |
| OL-STATE-003 | Aktion jetzt nicht möglich | Zuerst die vorherige Aktion abschließen |
| OL-STORAGE-001 | Datenbank nicht les-/schreibbar | Speicherplatz und Rechte prüfen |
| OL-STORAGE-002 | Datenbank-Update fehlgeschlagen | Ihre Daten sind unverändert; Support kontaktieren |
| OL-STORAGE-003 | Daten beschädigt | Backup wiederherstellen |
| OL-DATA-001 | Export fehlgeschlagen | Zielordner und Speicherplatz prüfen |
| OL-DATA-002 | Import fehlgeschlagen | Datei prüfen; es wurde nichts verändert |
| OL-BLE-001 | Unerwartete Tracker-Daten | Tracker neu verbinden |
| OL-BLE-002 | Bluetooth-Verbindung fehlgeschlagen | Bluetooth einschalten, näher an den Tracker gehen |
| OL-BLE-003 | Gerät nicht unterstützt | Anderes Gerät wählen |
| OL-API-001 | Anmeldung an Schnittstelle fehlgeschlagen | Agent und Dashboard mit demselben Token starten |
| OL-API-002 | Agent nicht erreichbar | Agent starten |
| OL-API-003 | Anfrage abgelehnt | Dashboard nur lokal im Browser öffnen |

## 3. Protokolldatei (Logfile)

OctaLedger schreibt wichtige Ereignisse in eine Protokolldatei (`octaledger.log`) im
Ordner `logs` Ihres Benutzerprofils. Sie hilft bei der Fehlersuche.

- Passwörter, Tokens und die ersten Teile von Bluetooth-Adressen werden **automatisch
  unkenntlich gemacht** (`***`), bevor etwas gespeichert wird.
- Die Datei wird automatisch rotiert (ca. 1 MB je Datei, 5 alte Dateien); sie wächst
  nicht unbegrenzt.
- Mit der Protokollstufe `DEBUG` (Einstellung) werden zusätzlich alle Programmschritte
  aufgezeichnet. Für den Alltag genügt `INFO`.
- Wenn Sie ein Problem melden: Prüfen Sie die Datei vor dem Versenden trotzdem kurz auf
  persönliche Angaben (z. B. Projektnamen).

## 4. Wie OctaLedger Dateien schützt

- **Speichern ist atomar:** Einstellungen, Exporte und Backups werden zuerst in eine
  temporäre Datei geschrieben und erst danach an den Zielort verschoben. Bricht der
  Rechner mittendrin ab, bleibt Ihre vorherige Datei vollständig erhalten.
- **Importieren ist vorsichtig:** Dateien über 50 MB oder mit ungültigem Textformat werden
  abgelehnt, bevor irgendetwas verändert wird.
- Meldungen nennen immer den Dateinamen, z. B. „Die Datei ‚export.csv‘ konnte nicht
  gespeichert werden (Rechte, Speicherplatz oder Pfad prüfen)“.

## 5. Einstellungen und Speicherort

### Wo liegen meine Daten?

Standardmäßig im Benutzerprofil, unter Windows in `%LOCALAPPDATA%\OctaLedger`:

| Ordner/Datei | Inhalt |
|---|---|
| `data\octaledger.sqlite3` | Ihre Zeitdaten (Datenbank) |
| `settings.toml` | Ihre Einstellungen |
| `logs\` | Protokolldateien |
| `backups\` | Sicherungen |
| `exports\` | Exportierte Dateien (CSV/JSON) |

Einen anderen Speicherort können Sie mit der Umgebungsvariablen `OCTALEDGER_DATA_DIR`
festlegen. Ihre Daten werden **nie** im Programmordner gespeichert.

### Wichtige Einstellungen

| Einstellung | Bedeutung | Empfehlung |
|---|---|---|
| Zeitzone | In welcher Zeitzone Zeiten angezeigt werden (gespeichert wird immer UTC) | Ihre eigene wählen, z. B. `Europe/Zurich` |
| Entprellung (ms) | So lange muss eine Seite oben liegen, bevor sie zählt; verhindert Fehlwechsel beim Drehen | 300 |
| Erste Seite nach Verbindung | `observe_only`: nur merken, nicht automatisch starten. `adopt_current`: aktuelle Seite sofort als Start übernehmen | `observe_only` |
| Bei Verbindungsverlust | `mark_uncertain`: Zeitraum als unsicher markieren, Sie bestätigen danach | `mark_uncertain` |
| Darstellung | Hell/Dunkel und Schriftgröße normal/groß | nach Geschmack |

Ungültige Einstellungen werden **nicht stillschweigend ignoriert**: Das Programm nennt die
Einstellung und was erlaubt ist (Fehlercode `OL-CONFIG-001`). Löschen Sie `settings.toml`,
um auf die Standardwerte zurückzusetzen.

## 6. Grundbegriffe

| Begriff | Bedeutung |
|---|---|
| **Tracker / Gerät** | Ihr Würfel. Sie geben ihm einen Namen (Alias), z. B. „Tracker Büro“. |
| **Seite** | Eine der acht Flächen des Würfels, technisch 1 bis 8. Neutral (0) bedeutet: keine stabile Seite. |
| **Tätigkeit (Aktivität)** | Was Sie tun, z. B. „Meeting“. Jeder Seite wird eine Tätigkeit zugeordnet. |
| **Projekt** | Optional: wofür Sie die Zeit buchen. |
| **Sitzung (Zeitabschnitt)** | Ein Zeitraum mit Beginn und Ende für eine Tätigkeit. Läuft die Sitzung noch, hat sie kein Ende. |
| **Qualität** | *bestätigt* oder *unsicher*. Unsicher heißt: ein Teil des Zeitraums ist nicht sicher (z. B. Verbindung abgebrochen). Sie sollten solche Sitzungen prüfen. |
| **Korrektur** | Jede nachträgliche Änderung einer Sitzung wird mit Grund protokolliert; das Original bleibt nachvollziehbar. |

Regeln für Eingaben: Namen dürfen nicht leer sein und höchstens 100 Zeichen haben,
Notizen höchstens 2000 Zeichen. Farben werden als `#RRGGBB` angegeben (z. B. `#2A9D8F`).
Zeiten werden intern immer in UTC gespeichert und in Ihrer Zeitzone angezeigt.
