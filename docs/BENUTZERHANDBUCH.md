# Benutzerhandbuch

Dieses Handbuch richtet sich an **Anwender** von OctaLedger. Installation und Start:
[INSTALLATION.md](INSTALLATION.md). Technische Details für Entwickler:
[SOFTWAREDOKUMENTATION.md](SOFTWAREDOKUMENTATION.md).

> **Ehrlicher Stand:** Die komplette Software ist umgesetzt und automatisch getestet – der
> Tracker-Teil jedoch bisher **nur mit einem Simulator**, noch nicht mit echten Würfeln. Das
> Bluetooth-Protokoll stammt aus Community-Quellen und muss an Ihrem Exemplar bestätigt werden.
> Prüfen Sie deshalb bei der ersten Nutzung in Ruhe, ob jede Seite die richtige Tätigkeit startet
> (Abschnitt „Geräte einrichten“), und lesen Sie das Ergebnis in [TESTPLAN.md](TESTPLAN.md) ein.

**Inhalt**

1. [Was ist OctaLedger?](#1-was-ist-octaledger)
2. [Grundbegriffe](#2-grundbegriffe)
3. [Schnellstart in 10 Minuten](#3-schnellstart-in-10-minuten)
4. [Programm starten und beenden](#4-programm-starten-und-beenden)
5. [Das Dashboard bedienen](#5-das-dashboard-bedienen)
6. [Geräte einrichten und Seiten zuordnen](#6-geräte-einrichten-und-seiten-zuordnen)
7. [Zeiterfassung im Alltag](#7-zeiterfassung-im-alltag)
8. [So erkennt OctaLedger Ihre Würfelbewegungen](#8-so-erkennt-octaledger-ihre-würfelbewegungen)
9. [Verbindungsverhalten im Alltag](#9-verbindungsverhalten-im-alltag)
10. [Zeiten korrigieren und löschen](#10-zeiten-korrigieren-und-löschen)
11. [Auswertungen lesen (Statistik und Zeitjournal)](#11-auswertungen-lesen-statistik-und-zeitjournal)
12. [Zeiten, Mitternacht und Sommerzeit](#12-zeiten-mitternacht-und-sommerzeit)
13. [Daten sichern, exportieren und wiederherstellen](#13-daten-sichern-exportieren-und-wiederherstellen)
14. [Einstellungen und Speicherort](#14-einstellungen-und-speicherort)
15. [Datenbank, Updates und Sicherheit Ihrer Daten](#15-datenbank-updates-und-sicherheit-ihrer-daten)
16. [Protokolldatei (Logfile)](#16-protokolldatei-logfile)
17. [Wie OctaLedger Dateien schützt](#17-wie-octaledger-dateien-schützt)
18. [Wenn eine Fehlermeldung erscheint](#18-wenn-eine-fehlermeldung-erscheint)
19. [Häufige Fragen](#19-häufige-fragen)

## 1. Was ist OctaLedger?

OctaLedger erfasst Arbeitszeit lokal auf Ihrem Rechner mit einem kompatiblen
Timeular-/ZEI-Würfel. Sie drehen den Würfel auf die Seite einer Tätigkeit, OctaLedger
startet die Zeit und speichert sie in einer lokalen Datenbank. Es wird kein
Herstellerkonto und keine Cloud benötigt.

## 2. Grundbegriffe

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

## 3. Schnellstart in 10 Minuten

Voraussetzung: OctaLedger ist installiert (siehe [INSTALLATION.md](INSTALLATION.md)) und Ihr
Würfel ist geladen.

1. **Starten:** Doppelklick auf `scripts\start_all.bat`. Es öffnen sich der Agent (kleines
   Fenster, bitte offen lassen) und das Dashboard im Browser.
2. **Tätigkeiten anlegen:** Bereich **Verwaltung** → Reiter *Tätigkeiten* → z. B. „Meeting“,
   „Entwicklung“, „Pause“ anlegen (mindestens eine pro Würfelseite, die Sie nutzen).
3. **Tracker registrieren:** Bereich **Geräte** → Namen eingeben → *Registrieren*.
4. **Würfel finden:** Würfel einmal drehen (weckt ihn), *Nach Geräten suchen*, Ihr Gerät und den
   Tracker wählen, *Adresse speichern*, danach *Verbinden*. Im Kasten erscheint **Bereit**.
5. **Seiten zuordnen:** Eine Seite nach oben halten – „👈 Seite N liegt oben“ erscheint –, Tätigkeit
   wählen; für alle genutzten Seiten wiederholen, dann *Kalibrierung speichern*.
6. **Arbeiten:** Würfel auf die Seite der aktuellen Tätigkeit legen. In der **Übersicht** läuft die
   Zeit. Drehen Sie auf eine andere Seite, wechselt die Tätigkeit.
7. **Auswerten:** Bereich **Statistik** (Tag/Woche) und **Zeitjournal** (Korrekturen).
8. **Sichern:** Bereich **Daten** → *Sicherung erstellen* und die Datei an einem anderen Ort ablegen.

Ohne Würfel geht es auch: Auf der **Übersicht** startet *Von Hand starten* jede Tätigkeit.

## 4. Programm starten und beenden

**Zwei Teile, ein Ziel:** Der **Agent** erfasst die Zeit im Hintergrund, das **Dashboard** ist die
Anzeige im Browser. Das Dashboard darf jederzeit geschlossen werden – der Agent erfasst weiter.

| Aktion | So geht es |
|---|---|
| Alles starten | Doppelklick auf `scripts\start_all.bat` |
| Nur den Agenten starten | `scripts\start_agent.bat` (Fenster offen lassen) |
| Nur das Dashboard starten | `scripts\start_dashboard.bat` → Browser öffnet `http://127.0.0.1:8501` |
| Beenden | Im Agent-Fenster **Strg+C** drücken (der Tracker wird sauber getrennt) |

**Befehle in der Eingabeaufforderung** (im Projektordner, mit aktivierter Umgebung bzw.
`.venv\Scripts\python.exe -m octaledger …`):

- `octaledger status` – läuft der Agent? Was läuft gerade? Wie ist der Tracker verbunden?
- `octaledger scan` – Bluetooth-Geräte in der Nähe anzeigen (verbindet nichts).
- `octaledger paths` – zeigt, wo Ihre Daten liegen.
- `octaledger backup` – erstellt eine Sicherung (auch bei laufendem Agent).
- `octaledger restore DATEI` – prüft eine Sicherung und zeigt eine Vorschau; mit `--yes` wird
  wiederhergestellt. Das geht nur, **solange der Agent nicht läuft**.

Meldungen erscheinen als eine verständliche Zeile mit Fehlercode, z. B.
`Fehler [OL-CONFIG-001]: …` – ohne technische Stacktraces.

**Telemetrie:** OctaLedger sendet keine Nutzungsdaten. Das Dashboard läuft ausschließlich lokal.

### Typische Meldungen beim Start
- **„Der Port 8765 ist bereits belegt“:** Der Agent läuft schon (nicht ein zweites Mal starten), oder
  ein anderes Programm nutzt den Port. Dann in `settings.toml` einen anderen `port` eintragen.
- **„Es gibt noch kein API-Token“** (im Dashboard): Den Agenten starten – er legt das Token beim ersten
  Start an.
- **Mit dem aktiven Tracker verbindet der Agent von selbst**, sobald für ihn eine Bluetooth-Adresse
  gespeichert ist. Weitere Tracker verbinden Sie bewusst im Bereich *Geräte*.

## 5. Das Dashboard bedienen

### Die Seitenleiste
- **Bereich** wählen: links in der Liste. Jeder Bereich beginnt mit **„ℹ️ So funktioniert diese
  Seite“** – klicken Sie darauf, wenn Sie nicht weiterwissen.
- **🌙 Dunkel / ☀️ Hell:** wechselt die Darstellung. Ihre Wahl wird gespeichert.
- **Aa+ Größer / Aa− Kleiner:** wechselt zwischen normaler und größerer Schrift (für entspanntes
  Lesen oder kleine Bildschirme). Ihre Wahl wird gespeichert.
- Unten sehen Sie, ob der **Agent läuft** (🟢) oder nicht erreichbar ist (🔴).
- Fahren Sie mit der Maus über einen Knopf oder ein Eingabefeld: ein kleiner **Hilfetext** erklärt,
  wozu es dient.

### Bereich „Übersicht“
- Großer Kasten: **was gerade läuft** (Tätigkeit, Dauer, Beginn). Mit **⏸ Pause** und **⏹ Stopp**
  steuern Sie die laufende Zeit; nach einer Pause geht es mit **▶ Fortsetzen** weiter.
- **Tracker:** zeigt, ob Ihr Würfel verbunden ist (Bereit), Batteriestand und die letzte Meldung.
- **Gelbe Warnung „unsicher“:** Eine Zeit ist nicht sicher (z. B. Verbindung unterbrochen). Öffnen
  Sie das Zeitjournal und bestätigen oder korrigieren Sie sie.
- **Von Hand starten:** Tätigkeit wählen (und optional Projekt und Notiz), **▶ Start**.
- Die Anzeige aktualisiert sich alle 5 Sekunden; **🔄 Neu laden** sofort.

### Wenn „Agent nicht erreichbar“ erscheint
Der Agent läuft nicht (Fehlercode `OL-API-002`). Starten Sie ihn mit `octaledger agent` und klicken
Sie auf **Neu laden**. Ihre Daten sind sicher; es wird nur nichts erfasst, solange der Agent fehlt.

### Bereich „Geräte“ – Schritt für Schritt
1. **Tracker registrieren:** Namen eingeben (z. B. „Tracker Büro“), **➕ Registrieren**. Der erste
   Tracker wird automatisch der **aktive** (⭐); nur er erzeugt Zeiten.
2. **Bluetooth-Suche:** Würfel einmal drehen (weckt ihn), dann **🔍 Nach Geräten suchen**. Wählen Sie
   Ihr Gerät – Geräte mit **✅ passender Dienst** sind die wahrscheinlichsten – und den Tracker, dem
   es gehört, dann **💾 Adresse speichern**. OctaLedger verbindet nie von selbst mit unbekannten
   Geräten, und die Adresse wird aus Datenschutzgründen nicht angezeigt.
3. **🔗 Verbinden:** baut die Verbindung auf. Im Kasten sehen Sie den Zustand (Bereit, Verbinde …),
   den Batteriestand und die letzte Meldung. **⛔ Trennen** beendet sie bewusst (kein automatischer
   Neuversuch).
4. **Seiten zuordnen (Kalibrierung):** Halten Sie eine Seite nach oben; „👈 Aktuell liegt **Seite N**
   oben“ zeigt die technische Nummer. Wählen Sie für jede der acht Seiten eine Tätigkeit (und
   optional ein Projekt), dann **💾 Kalibrierung speichern**. Der Balken zeigt, wie viele Seiten
   fertig sind. „– nicht belegt –“ bucht nichts.
5. **⭐ Zum aktiven Tracker machen:** bewusste Übergabe an den zweiten Tracker (die Zeit des alten
   Trackers endet, es entsteht keine doppelte Zeit).
6. **Umbenennen oder löschen:** Löschen geht nur, solange noch keine Daten aufgezeichnet wurden.

### Bereich „Verwaltung“
- Reiter **Tätigkeiten** und **Projekte**: neuen Namen eingeben, **➕ anlegen**. Ohne eigene Farbe
  wählt OctaLedger gut unterscheidbare Farben.
- Zu jedem Eintrag: Name und Farbe ändern (**💾 Speichern**), **📦 Archivieren** (verschwindet aus
  den Auswahllisten, alte Auswertungen bleiben) oder **🗑 Löschen** (nur wenn nirgends verwendet; sonst
  erscheint „Bitte archivieren Sie sie stattdessen“). Mit **Archivierte anzeigen** finden Sie
  archivierte Einträge zum **♻️ Wiederherstellen**.

### Bereich „Zeitjournal“
- **Journal:** Zeitraum und Filter wählen; die Tabelle zeigt Ihre Sitzungen (neueste zuerst). Darunter
  wählen Sie eine **Sitzung** und dann:
  - **Korrigieren:** Tätigkeit, Projekt, Beginn, Ende oder Notiz ändern – und einen **Grund** angeben
    (Pflicht). Bei *unsicheren* Zeiten gibt es zusätzlich **✅ Als bestätigt markieren**.
  - **Teilen:** zerlegt eine Sitzung an einem Zeitpunkt in zwei Teile (z. B. vergessene Pause).
  - **Löschen:** mit Grund und Bestätigung; wird im Protokoll festgehalten.
- **Zu prüfen:** alle unsicheren Zeiten. **✅ Bestätigen**, wenn der Zeitraum stimmt; sonst im Reiter
  *Journal* korrigieren.
- **Nachtragen:** Tätigkeit, Beginn und Ende einer vergangenen Zeit eintragen. Das Ende darf nicht in
  der Zukunft liegen, und es darf keine Überschneidung mit vorhandenen Zeiten geben – sonst erscheint
  eine verständliche Meldung und nichts wird gespeichert.
- Datum und Uhrzeit geben Sie immer in **Ihrer Zeitzone** ein (Einstellungen).

### Bereich „Statistik“
1. **Zeitraum** wählen: *Tag*, *Woche* (Montag bis Sonntag) oder *Eigener Zeitraum*, dazu das Datum.
2. Optional nach **Tätigkeit**, **Projekt** oder **Gerät** filtern.
3. Oben stehen die **Kennzahlen**:
   *Persönliche Arbeitszeit* (ohne Doppelzählung – die Zahl für Ihre Arbeitszeit), *Gerätezeit*,
   *Davon unsicher* und *Überschneidung*. Fahren Sie mit der Maus über eine Kennzahl für eine Erklärung.
4. Darunter **Diagramme**: Verlauf pro Tag (bei Woche/eigenem Zeitraum) sowie die Verteilung nach
   Tätigkeit und nach Projekt in den Farben der Tätigkeiten. **Unter jedem Diagramm steht dieselbe
   Information als Tabelle.**
5. Eine **gelbe Warnung** zeigt, wie viel Zeit noch unbestätigt ist – bestätigen Sie sie im Zeitjournal.

### Bereich „Daten“
- **CSV-Export:** *Alle Zeiten* oder einen Zeitraum wählen, Trennzeichen festlegen (für deutsches Excel:
  Semikolon), **📄 CSV erzeugen**, danach **⬇️ CSV herunterladen**. Die Datei ist zusätzlich im
  Ordner `exports` gespeichert.
- **Sicherung:** **💾 Sicherung erstellen** und herunterladen. Kopieren Sie die Datei auf einen
  **anderen Datenträger** (USB-Stick, Netzlaufwerk, Cloud nach Ihrer Wahl) und wiederholen Sie das
  regelmäßig.
- **Wiederherstellen:** Sicherungsdatei auswählen (oder den Inhalt einfügen). OctaLedger **prüft die
  Datei vollständig und zeigt eine Vorschau – dabei wird nichts verändert**. Erst wenn Sie bestätigen
  („Ich habe verstanden …“), wird **♻️ Jetzt wiederherstellen** freigeschaltet. Vorher legt OctaLedger
  automatisch eine Kopie des aktuellen Stands an. Ist die Datei beschädigt, verändert oder von einer
  neueren Programmversion, erscheint eine verständliche Meldung und **nichts** wird geändert.

### Bereich „Einstellungen“
- **Zeitzone:** gilt sofort. **Entprellung** (empfohlen 300 ms), **Erste Seite nach dem Verbinden**,
  **Bei Verbindungsverlust**, **Neutralwert** und **Protokollstufe** gelten nach einem **Neustart des
  Agenten** (`octaledger agent`) – ein Hinweis erinnert Sie daran.
- Bei jeder Einstellung zeigt das **Fragezeichen** eine Erklärung, und die empfohlene Wahl ist
  gekennzeichnet. Die Neutralwert-Pause ist **experimentell**.
- Adresse und Port der lokalen Schnittstelle können Sie hier bewusst **nicht** ändern (Sicherheit).

### Bereich „Diagnose“
- **Geräte:** Verbindungszustand, Fehlversuche, letzter Wert, Batterie, verworfene Werte.
- **🔎 Datenbank prüfen:** Prüft die Datei auf Beschädigungen.
- **Protokoll:** die letzten Ereignisse des Agenten (Geheimnisse sind automatisch unkenntlich gemacht).
- **⬇️ Diagnosebericht (anonymisiert):** Textdatei **ohne** Gerätenamen, Bluetooth-Adressen und
  Tätigkeiten. Diese Datei können Sie bei einem Problem gefahrlos mitschicken.

## 6. Geräte einrichten und Seiten zuordnen

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

## 7. Zeiterfassung im Alltag

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

## 8. So erkennt OctaLedger Ihre Würfelbewegungen

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

## 9. Verbindungsverhalten im Alltag

- **Automatisch wieder verbinden:** Reißt die Bluetooth-Verbindung ab (Tracker außer Reichweite,
  Tracker schläft, Bluetooth kurz aus), versucht OctaLedger es selbstständig erneut – zuerst nach
  1 Sekunde, dann mit wachsenden Pausen (2, 4, 8 … höchstens 60 Sekunden), damit nichts blockiert.
- **Zeit ohne Verbindung** wird nicht erfunden: Die laufende Zeit wird als **unsicher**
  gekennzeichnet (oder beendet, je nach Einstellung). Nach der Rückkehr läuft sie auf derselben Seite
  einfach weiter; Sie bestätigen oder korrigieren den unklaren Abschnitt im Zeitjournal.
- **Bewusst stoppen:** Wenn Sie ein Gerät selbst stoppen, gibt es **keine** weiteren
  Verbindungsversuche. Auch dieser Zeitpunkt wird als Lücke gekennzeichnet.
- **Nicht unterstütztes Gerät:** Bietet ein Gerät den erwarteten Dienst nicht an, versucht
  OctaLedger es nicht endlos erneut, sondern zeigt eine verständliche Meldung (Fehlercode
  `OL-BLE-003`). Wählen Sie dann ein anderes Gerät.
- **Kein Anfangswert:** Sendet der Tracker nach dem Verbinden keine Seite, bricht OctaLedger nach
  ein paar Sekunden ab und versucht es erneut. Drehen Sie den Würfel einmal.
- **Dashboard schließen oder neu laden** beendet die Erfassung **nicht**: Der Agent läuft im
  Hintergrund weiter.
- **Zwei Tracker:** Beide dürfen registriert sein; ob zwei Verbindungen gleichzeitig am eigenen
  Bluetooth-Adapter zuverlässig laufen, muss praktisch geprüft werden. Bei Problemen genügt der
  aktive Tracker.
- Unter **Diagnose** sehen Sie je Gerät Verbindungsstatus, Anzahl Fehlversuche, letzten Fehler,
  Batteriestand (wenn das Gerät ihn meldet) und die Zahl ignorierter doppelter Meldungen.

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

## 11. Auswertungen lesen (Statistik und Zeitjournal)

- **Tag und Woche:** Wählen Sie einen Tag oder eine Woche (Montag bis Sonntag). Alle Zeiten
  werden in **Ihrer** Zeitzone angezeigt, gespeichert wird intern in UTC.
- **Filter:** Sie können nach **Tätigkeit**, **Projekt** und **Gerät** filtern. Die Summen
  beziehen sich immer auf das, was der Filter übrig lässt.
- **Anteile:** Die Balken und Kreise zeigen, wie sich die Zeit auf Tätigkeiten bzw. Projekte
  verteilt. Zeit ohne Projekt erscheint als „Ohne Projekt“.
- **Gerätezeit und persönliche Arbeitszeit:**
  - *Gerätezeit* = Summe der Zeiten aller Tracker.
  - *Persönliche Arbeitszeit* = Zeit, in der Sie gearbeitet haben, **ohne Doppelzählung**.
  - Sind beide gleich, gab es keine Überschneidungen. Sind sie verschieden, zeigt die Differenz
    („Überschneidung“), wie viel Zeit mehrfach gezählt worden wäre. Verwenden Sie für Ihre
    Arbeitszeit die **persönliche** Zahl.
- **Unsichere Zeit:** Der Bereich „davon unsicher“ zeigt, wie viel der Summe noch nicht von
  Ihnen bestätigt wurde (z. B. nach einem Verbindungsabbruch). Bestätigen Sie solche Sitzungen
  im Zeitjournal, damit die Auswertung belastbar wird.
- **Laufende Zeit** wird bis zum aktuellen Moment mitgerechnet und ist als „läuft“ markiert.
- **Zeitjournal:** Listet ganze Sitzungen (neueste zuerst) mit Tätigkeit, Projekt, Gerät und
  Dauer. Sitzungen, die über Mitternacht gehen, erscheinen hier als eine Zeile, in der Statistik
  aber aufgeteilt auf die betroffenen Tage.
- Der Zeitraum darf höchstens 400 Tage umfassen.

## 12. Zeiten, Mitternacht und Sommerzeit

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

## 13. Daten sichern, exportieren und wiederherstellen

### CSV-Export (für Excel, LibreOffice, Auswertungen)
- Bereich **Daten → Export**: Zeitraum wählen (oder alles), Zeitzone und Trennzeichen wählen
  (Standard `;` für deutsches Excel), **Exportieren**.
- Die Datei enthält Ihre Sitzungen so, **wie sie nach Korrekturen jetzt gelten**: Beginn/Ende in
  Ihrer Zeitzone und in UTC, Dauer in Sekunden und als `h:mm:ss`, Tätigkeit, Projekt, Gerät,
  Qualität (bestätigt/unsicher), Revision und Notiz.
- Laufende Sitzungen sind mit `running = yes` markiert und bis zum Exportzeitpunkt gerechnet.
- **Sicherheit:** Beginnt ein Text (z. B. eine Notiz) mit `=`, `+`, `-` oder `@`, setzt
  OctaLedger ein `'` davor, damit Excel ihn nicht als Formel ausführt.
- Die Dateien liegen im Ordner `exports\` Ihrer Datenablage.

### Vollständige Sicherung (JSON-Backup)
- **Daten → Sicherung erstellen** speichert alles (Geräte, Seitenzuordnungen, Tätigkeiten,
  Projekte, Sitzungen, Korrekturen, Rohereignisse, Protokoll) in einer Datei im Ordner
  `backups\`. Die Datei hat eine **Prüfsumme**: Beschädigung oder nachträgliche Änderung wird beim
  Wiederherstellen erkannt.
- Machen Sie Sicherungen regelmäßig und kopieren Sie sie auf einen **anderen** Datenträger.

### Wiederherstellen
1. **Daten → Wiederherstellen**, Sicherungsdatei wählen.
2. OctaLedger zeigt eine **Vorschau** (Anzahl Geräte, Sitzungen …) und prüft die Datei
   vollständig. **Dabei wird nichts verändert.**
3. Nach Ihrer Bestätigung legt OctaLedger zuerst **automatisch eine Kopie Ihres aktuellen Stands**
   an (`octaledger-pre-restore-…`) und ersetzt dann alle Daten **in einem Schritt**.
4. Bei **jedem** Problem wird alles zurückgenommen – Ihre bisherigen Daten bleiben unverändert und
   Sie erhalten eine verständliche Meldung (`OL-DATA-002`).
- Eine Sicherung einer **neueren** Programmversion lässt sich nicht einlesen („bitte Programm
  aktualisieren“).
- **Wichtig:** Testen Sie das Wiederherstellen einmal in Ruhe, bevor Sie sich auf eine Sicherung
  verlassen. Erst ein erfolgreich getestetes Backup ist ein belastbares Backup.

## 14. Einstellungen und Speicherort

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

## 15. Datenbank, Updates und Sicherheit Ihrer Daten

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

## 16. Protokolldatei (Logfile)

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

## 17. Wie OctaLedger Dateien schützt

- **Speichern ist atomar:** Einstellungen, Exporte und Backups werden zuerst in eine
  temporäre Datei geschrieben und erst danach an den Zielort verschoben. Bricht der
  Rechner mittendrin ab, bleibt Ihre vorherige Datei vollständig erhalten.
- **Importieren ist vorsichtig:** Dateien über 50 MB oder mit ungültigem Textformat werden
  abgelehnt, bevor irgendetwas verändert wird.
- Meldungen nennen immer den Dateinamen, z. B. „Die Datei ‚export.csv‘ konnte nicht
  gespeichert werden (Rechte, Speicherplatz oder Pfad prüfen)“.

## 18. Wenn eine Fehlermeldung erscheint

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

## 19. Häufige Fragen

**Muss das Dashboard offen bleiben?** Nein. Der Agent erfasst im Hintergrund weiter. Nur wenn der Agent
beendet wird, wird nichts mehr erfasst.

**Was passiert bei Stromausfall oder Absturz?** Bestätigte Daten bleiben erhalten (die Datenbank
schreibt transaktional). Die laufende Zeit ist danach als *unsicher* markiert, bis Sie sie bestätigen.

**Schickt OctaLedger Daten ins Internet?** Nein. Es gibt keine Cloud, kein Konto und keine Telemetrie.
Internet wird nur zum Installieren und für Updates benötigt.

**Kann ich die Hersteller-App parallel nutzen?** Ein Tracker hat meist nur *eine* aktive
Bluetooth-Verbindung. Schließen Sie die Hersteller-App, wenn sich OctaLedger nicht verbinden lässt.

**Kann ich zwei Würfel benutzen?** Ja, beide können registriert sein. Nur der **aktive** Tracker erzeugt
Zeiten; mit *Zum aktiven Tracker machen* wechseln Sie bewusst. Ob zwei gleichzeitige
Bluetooth-Verbindungen an Ihrem Adapter zuverlässig laufen, müssen Sie ausprobieren.

**Wo sind meine Daten?** Im Benutzerprofil (`octaledger paths` zeigt den Ort), nie im Programmordner.

**Eine Zeit ist falsch gebucht – was tun?** *Zeitjournal* → Sitzung wählen → *Korrigieren* (mit Grund),
*Teilen* oder *Löschen*. Nichts geht still verloren; jede Änderung wird protokolliert.

**Eine Seite des Würfels bucht nichts.** Der Seite ist keine Tätigkeit zugeordnet (Bereich *Geräte*,
Kalibrierung) oder der Würfel liegt auf keiner stabilen Seite (neutral).

**Die Zeiten stimmen nicht mit der Uhr überein.** Prüfen Sie in den *Einstellungen* die **Zeitzone**.
