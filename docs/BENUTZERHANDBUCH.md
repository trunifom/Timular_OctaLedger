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

## 7. So erkennt OctaLedger Ihre Würfelbewegungen

Damit nicht jedes kurze Wackeln eine neue Tätigkeit startet, gelten diese Regeln:

- **Erste Meldung nach dem Verbinden** ist nur die *Ausgangslage*. Sie startet standardmäßig
  keine Zeiterfassung. Erst wenn Sie den Würfel auf eine andere Seite drehen, beginnt eine
  neue Tätigkeit. (Wer möchte, kann in den Einstellungen „aktuelle Seite übernehmen“ wählen.)
- **Wiederholte Meldungen derselben Seite** werden ignoriert.
- **Entprellung:** Eine Seite zählt erst, wenn der Würfel sie rund 0,3 Sekunden ruhig oben
  hält. Beim Drehen über andere Seiten hinweg werden diese „Durchgangsseiten“ nicht gebucht.
  Die Tätigkeit beginnt trotzdem zu dem Zeitpunkt, an dem die Seite erstmals oben lag.
- **Neutral (0):** Liegt der Würfel auf keiner stabilen Seite, wird das zunächst nur
  vermerkt; es pausiert nichts, solange die Pause-Regel nicht aktiviert ist.

### Verbindungsstatus

| Status | Bedeutung |
|---|---|
| Leerlauf | Keine Verbindung aktiv |
| Suche / Verbinden / Dienste prüfen / Abonnieren | Verbindung wird aufgebaut |
| Ausgangslage lesen | Verbunden, aktuelle Seite wird gelesen |
| **Bereit** | Alles in Ordnung: Drehen wird erfasst |
| Getrennt / Warte auf neuen Versuch | Verbindung verloren; OctaLedger versucht es mit wachsenden Pausen (1 s, 2 s, 4 s … höchstens 60 s) erneut |
| Gestoppt | Sie haben das Gerät bewusst gestoppt; es gibt **keinen** automatischen Neuversuch |

„Verbunden“ heißt noch nicht „bereit“: Erfasst wird erst im Status **Bereit**.

## 8. Zeiten, Mitternacht und Sommerzeit

- **Über Mitternacht:** Eine Sitzung, die z. B. von 22:00 bis 03:00 läuft, wird in Berichten
  automatisch auf beide Tage aufgeteilt (2 Stunden am ersten, 3 Stunden am zweiten Tag).
  Die Gesamtzeit bleibt unverändert.
- **Sommer-/Winterzeit:** Der Tag der Umstellung hat 23 bzw. 25 Stunden. OctaLedger rechnet
  das korrekt; gespeichert wird intern immer in UTC, deshalb gibt es keine doppelten oder
  fehlenden Stunden.
- **Überschneidungen:** Mit zwei Trackern kann es Zeiträume geben, in denen beide Geräte
  zählen. OctaLedger unterscheidet deshalb
  - **Gerätezeit** (Summe aller Geräte) und
  - **Persönliche Arbeitszeit** (Zeit, in der überhaupt gearbeitet wurde, ohne Doppelzählung).

  Für Abrechnung und Auswertung Ihrer Arbeitszeit ist die *persönliche Arbeitszeit* maßgeblich.
- **Wochen** beginnen standardmäßig am Montag.

## 9. Datenbank, Updates und Sicherheit Ihrer Daten

- Ihre Daten liegen in **einer Datei** (`data\octaledger.sqlite3`). Sie wird beim Start
  automatisch angelegt bzw. auf die aktuelle Programmversion gebracht.
- **Automatische Sicherung vor Updates:** Bevor OctaLedger die Datenbank einer neuen Version
  anpasst, wird eine geprüfte Kopie im Ordner `backups\` abgelegt
  (`octaledger-pre-migration-…`). Schlägt das Update fehl, bleibt Ihre Datenbank unverändert.
- **Neuere Datenbank, älteres Programm:** Stammt die Datenbank von einer neueren Version,
  startet das Programm nicht und verändert nichts. Bitte aktualisieren Sie OctaLedger.
- **Keine Überschneidungen:** Sie können nicht zwei Zeitabschnitte buchen, die sich zeitlich
  überlappen, und es läuft immer höchstens eine Sitzung. Aneinander grenzende Abschnitte
  (Ende = nächster Beginn) sind erlaubt.
- **Namen sind eindeutig:** Tätigkeiten, Projekte und Geräte dürfen nicht doppelt heißen
  (Groß-/Kleinschreibung zählt nicht). Archivierte Einträge geben ihren Namen wieder frei.
- **Verwendete Einträge löschen:** Eine Tätigkeit oder ein Projekt, das schon in gebuchten
  Zeiten vorkommt, kann nicht gelöscht werden – **archivieren** Sie es stattdessen.
- **Fehlermeldung „Die Änderung widerspricht bestehenden Daten“** (`OL-STATE-002`) bedeutet:
  doppelter Name, Überschneidung oder noch verwendeter Eintrag.
- **Fehlermeldung „Datenbank belegt“** ist vorübergehend; einen Moment warten und wiederholen.
- **Beschädigte Datei** (`OL-STORAGE-003`): Stellen Sie eine Sicherung aus `backups\` wieder
  her (siehe Abschnitt Backup/Restore).

## 10. Zeiten korrigieren und löschen

- **Nichts geht still verloren:** Jede Änderung an einer gebuchten Zeit (Tätigkeit, Projekt,
  Beginn, Ende, Notiz, Qualität) wird mit **Grund**, Zeitpunkt sowie altem und neuem Wert
  protokolliert. Die Sitzung erhält eine neue Versionsnummer („Revision“).
- **Grund ist Pflicht** – bei Korrekturen und beim Löschen. Beispiel: „Tracker lag auf der
  falschen Seite“.
- Nur **echte** Änderungen werden protokolliert. Wenn Sie nichts ändern, meldet OctaLedger
  „Es wurde nichts geändert“.
- Eine Korrektur, die zu einer **Überschneidung** mit einer anderen Sitzung führen würde, wird
  vollständig abgelehnt; Ihre Daten bleiben unverändert.
- **Löschen** einer Sitzung ist möglich, wird aber im Protokoll („Audit-Log“) mit Grund
  vermerkt. Alte Tracker-Rohdaten können nach einer Aufbewahrungsfrist bereinigt werden;
  auch das wird protokolliert.
- **Tätigkeiten/Projekte** mit gebuchten Zeiten lassen sich nicht löschen. Archivieren Sie sie:
  Sie verschwinden aus den Auswahllisten, alte Auswertungen bleiben korrekt.
- **Zuordnung einer Würfelseite ändern:** Die Zuordnung bekommt eine neue Revision; bereits
  gebuchte Zeiten bleiben unverändert.

## 11. Zeiterfassung im Alltag

### Automatisch mit dem Würfel
- **Seite drehen** → die bisherige Tätigkeit endet, die neue beginnt (zu dem Zeitpunkt, an dem
  die Seite oben lag). Dreht man auf dieselbe Tätigkeit, läuft die Zeit einfach weiter.
- **Seite ohne Tätigkeit:** Nichts wird gebucht, die laufende Zeit bleibt unverändert.
  Weisen Sie der Seite im Bereich *Geräte* eine Tätigkeit zu.
- **Zwei Tracker:** Nur der **aktive Tracker** erzeugt Zeiten. Der zweite Tracker bleibt
  registriert, seine Bewegungen werden nur protokolliert. Mit **Übergabe** wechseln Sie
  ausdrücklich den aktiven Tracker; die Zeit des alten Trackers endet dabei, es entsteht keine
  doppelte Arbeitszeit.

### Verbindung weg und wieder da
- Bricht die Verbindung ab, wird die laufende Zeit **nicht erfunden oder gelöscht**, sondern
  als **unsicher** markiert (oder beendet, je nach Einstellung).
- Nach dem Wiederverbinden läuft die Zeit auf derselben Seite **ohne neue Sitzung** weiter.
- Unsichere Zeiten finden Sie unter *Zeitjournal → Zu prüfen*. **Bestätigen** Sie sie, wenn der
  Zeitraum stimmt, oder **korrigieren** Sie Beginn/Ende.

### Von Hand
| Aktion | Bedeutung |
|---|---|
| **Starten** | Beginnt eine Tätigkeit sofort; eine laufende wird vorher beendet |
| **Stoppen** | Beendet die laufende Zeit |
| **Pause / Fortsetzen** | Pause beendet die Zeit und merkt sich die Tätigkeit; *Fortsetzen* startet sie wieder |
| **Nachtragen** | Eine vergangene Zeit eintragen (Ende darf nicht in der Zukunft liegen, keine Überschneidung) |
| **Teilen** | Eine Sitzung an einem Zeitpunkt in zwei Teile trennen (z. B. vergessene Pause) |
| **Korrigieren / Löschen** | Immer mit Begründung, nachvollziehbar protokolliert |

Nach einem **Neustart** von Programm oder Rechner bleiben alle bestätigten Daten erhalten; ein
Zeitraum mit unklarer Verbindung bleibt als *unsicher* gekennzeichnet.

## 12. Geräte einrichten und Seiten zuordnen

### Tracker registrieren
1. Öffnen Sie im Dashboard den Bereich **Geräte**.
2. Geben Sie dem Tracker einen **Namen** (z. B. „Tracker Büro“). Namen müssen eindeutig sein.
3. Der **erste** registrierte Tracker wird automatisch zum **aktiven Tracker**. Nur er erzeugt
   Zeiten. Weitere Tracker bleiben registriert; mit **Übergabe** wechseln Sie bewusst.
4. Modell und Firmware zeigt OctaLedger an, sobald sie vom Gerät gemeldet werden; sind sie
   unbekannt, ist das in Ordnung.

### Seiten kalibrieren (jede der 8 Seiten einzeln)
1. Halten Sie **eine Seite des Würfels oben**.
2. OctaLedger zeigt Ihnen die **technische Nummer** dieser Seite (1–8), sobald der Würfel sie
   gemeldet hat.
3. Wählen Sie die **Tätigkeit** (und optional das **Projekt**) für diese Seite.
4. Wiederholen Sie das für alle acht Seiten. Eine Fortschrittsanzeige zeigt, wie viele Seiten
   schon zugeordnet sind. Eine Seite ohne Tätigkeit bucht nichts.

Tipp: Kleben Sie einen kleinen Aufkleber oder schreiben Sie die Seitennummer auf eine Karte,
damit Sie die Zuordnung später im Alltag wiederfinden.

### Tätigkeiten und Projekte verwalten (Bereich **Verwaltung**)
- Anlegen, umbenennen, Farbe ändern. Ohne eigene Farbe vergibt OctaLedger automatisch
  gut unterscheidbare Farben.
- **Archivieren statt Löschen:** Wird eine Tätigkeit/ein Projekt bereits verwendet, lässt sie/es
  sich nicht löschen („Bitte archivieren Sie sie stattdessen“). Archivierte Einträge sind aus
  den Auswahllisten verschwunden, aber alte Zeiten und Auswertungen bleiben korrekt. Sie
  können sie jederzeit wiederherstellen.
- Ein **Gerät** löschen ist nur möglich, solange es keine aufgezeichneten Daten hat.
