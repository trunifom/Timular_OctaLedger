# Software-Pflichtenheft: OctaLedger

Version: 0.1, Planungsstand 19. November 2026.
Status: Soll-Spezifikation. Nur die in README aufgeführten Grundfunktionen sind
bereits implementiert. Muss/Soll/Kann bezeichnen Zielprioritäten, keine Lieferzusage.

## 1. Zweck und Zielgruppe

Lokale, nachvollziehbare Arbeitszeiterfassung mit kompatiblen Timeular-/ZEI-
Trackern unter Windows. Die Anwendung liest Orientierung und optional verfügbare
Geräteinformationen, erzeugt Zeitabschnitte und ermöglicht Verwaltung, Korrektur,
Export und grafische Analyse ohne erforderliches Herstellerkonto.

Ausgangsszenario: zwei USB-C-Tracker. Kompatibilität ist pro Exemplar und Firmware
zu prüfen. Zwei registrierte Geräte bedeuten nicht automatisch zwei gleichzeitig
zuverlässig unterstützte Verbindungen am verwendeten Adapter.

## 2. Abgrenzung

„Steuern“ bedeutet zunächst Verbindungen verwalten, Tracker zuweisen und aus
Seitenevents Softwareaktionen auslösen. Keine Zusicherung, Motoren, LEDs oder
Firmware des Trackers zu steuern. Keine undokumentierten BLE-Schreibbefehle.
Keine Smartphone-App, Cloudpflicht, Matter-Zertifizierung, automatische
Rechnungsstellung oder rechtliche Konformitätszusage im MVP.

## 3. Zielumgebung

Windows 11 als erstes Hardware-Testziel, Python ab 3.12 als Projektentscheidung.
Bluetooth-LE-Adapter mit aktiven GATT-Verbindungen. Streamlit im lokalen Browser.
Installation und Updates dürfen Internet benötigen; Kernerfassung soll offline
funktionieren. Konkrete Bibliotheks-/OS-Versionen nach Hardwaretest festschreiben.

## 4. Architektur

Ein Agentenprozess besitzt alle BLE-Clients in einem dauerhaften AsyncIO-Loop.
Pro Gerät ein eigener Zustandsautomat und Verbindungskontext. Eine lokale API
verbindet Streamlit mit dem Agenten. Dashboard-Neuladen beendet keine Erfassung.
SQLite mit Migrationen speichert Beobachtungen, Sitzungen und Korrekturen. Agent
ist einziger regulärer Datenbankschreiber. GUI liest/schreibt über API.

## 5. Funktionale Anforderungen

| ID | Priorität | Anforderung |
|---|---|---|
| F-01 | Muss | Nach BLE-Geräten suchen; Benutzer wählt eigenes Gerät |
| F-02 | Muss | Zwei Geräte mit interner ID und Alias registrieren |
| F-03 | Muss | Modell/Firmware soweit verfügbar anzeigen; unbekannt erlauben |
| F-04 | Muss | Dienst/Characteristic prüfen, Verbindungsschritte anzeigen |
| F-05 | Muss | Acht Seiten pro Tracker individuell kalibrieren |
| F-06 | Muss | Rohwerte validieren, Duplikate und Zwischenflächen behandeln |
| F-07 | Muss | Baseline getrennt von neuem Seitenwechsel verarbeiten |
| F-08 | Muss | Aktivität, Projekt und optionale Notiz zuordnen |
| F-09 | Muss | Zeitabschnitte automatisch starten und wechseln |
| F-10 | Muss | Manuelles Starten, Stoppen und Pause ermöglichen |
| F-11 | Muss | Beobachtungen und bestätigte Änderungen transaktional speichern |
| F-12 | Muss | Ausfälle sichtbar markieren, keine Historie erfinden |
| F-13 | Muss | Sitzungen bearbeiten, teilen und korrigieren; Auditspur erhalten |
| F-14 | Muss | Tages-/Wochenansicht und Projekt-/Aktivitätsfilter anbieten |
| F-15 | Soll | Balken-, Verlauf- und Verteilungsdiagramme darstellen |
| F-16 | Muss | CSV exportieren, versionierten JSON-Backup/Restore anbieten |
| F-17 | Muss | Reconnect mit begrenztem Backoff und Benutzerstopp unterstützen |
| F-18 | Soll | Optionalen Batteriestand anzeigen; fehlenden Dienst tolerieren |
| F-19 | Soll | Diagnosen anonymisiert exportieren |
| F-20 | Kann | Home Assistant, Hue, Obsidian oder MQTT über Adapter ergänzen |

## 6. Zeit- und Mehrgeräteregeln

MVP: eine persönliche aktive Arbeitssitzung, ausgewählter aktiver Tracker.
Zweiter Tracker bleibt registriert, eine Übergabe erfolgt ausdrücklich. Ereignisse
inaktiver Geräte dürfen keine heimlichen konkurrierenden Arbeitssitzungen erzeugen.

Ausbaustufe: unabhängige Geräte-Zeitachsen und optional parallele Beobachtung.
Berichte müssen zwischen Summe von Gerätezeiten und überschneidungsfreier
persönlicher Arbeitszeit unterscheiden. Nicht einfach beide Summen addieren.

Erster gelesener Wert ist Baseline. Standard: kein automatischer Sitzungsbeginn;
Nutzer kann „aktuelle Seite übernehmen“ aktivieren. Entprellung anfangs 300 ms als
konfigurierbarer Startwert, am Gerät zu validieren. Neutralwert 0 zunächst nur als
neutral protokollieren; Pausenregel erst nach Hardwareprüfung konfigurieren.

Bei Verlust bleibt der Zeitraum als unsicher markiert; GUI fordert nach Rückkehr
Bestätigung/Korrektur an. Bewusstes Stoppen verhindert weitere Reconnects.
Zeitpunkte UTC, Anzeige in gewählter IANA-Zeitzone. Monotone Zeit nur innerhalb
desselben Prozesskontexts verwenden. Sommerzeit und Uhrsprünge testen.

## 7. Oberflächen

- Übersicht: aktuelle Tätigkeit, Dauer, aktiver Tracker, Verbindung, Datenqualität.
- Geräte: Suche, Registrierung, Verbinden/Trennen, Eigenschaften und Kalibrierung.
- Verwaltung: Aktivitäten, Projekte, optionale Kunden/Tags später.
- Zeitjournal: Filter, Korrektur, Teilung und Konfliktanzeige.
- Statistik: Tages-/Wochenbalken, Projektanteile, Verlauf; Unsicherheit ausweisen.
- Einstellungen: Zeitzone, Entprellung, Baseline, Datensicherung.
- Diagnose: Fehlerstufen, anonymisierter Export, offene Integrationsaufträge.

## 8. Nichtfunktionale Anforderungen

Keine Pflichtcloud und keine heimliche Telemetrie. Nutzerdaten außerhalb des
Repositories im Benutzerprofil. Datenbankänderungen migrierbar, vor Migration
Backup. Keine BLE- oder Netzwerk-Endlosschleifen im Streamlit-Skript. Keine UI-
Aufrufe aus dem BLE-Callback. Begrenzte Warteschlangen und definierte Überlaufregel.
Fehler sollen benutzerverständlich und intern mit stabilen Codes vorliegen.

API nur Loopback im MVP, Tokenprüfung für alle schützenswerten Routen; keine
Zustandsänderungen über GET. Keine beliebigen Shellbefehle. Herkunfts-/Hostprüfung
und Schutz vor unerwünschten Browseranfragen planen. Tokens nicht in URLs/Logs.

## 9. Daten und Sicherung

Speichern: Geräte, Fähigkeiten, Zuordnungen, Aktivitäten, Projekte, Rohereignisse,
Sitzungen, Korrekturen, Konfiguration, Integrationsaufträge. Originalbeobachtungen
nicht still überschreiben. Lösch-/Aufbewahrungsregeln explizit einführen.
Backup ist erst nach erfolgreicher Wiederherstellung als belastbar einzustufen.
CSV-Ausgabe muss Zeitzone, Encoding und sichere Textbehandlung dokumentieren.

## 10. Abnahmekriterien

| ID | Nachweis |
|---|---|
| A-01 | Alle acht Flächen beider Tracker nachvollziehbar kalibriert |
| A-02 | 20 identische Rohwerte ergeben keinen zusätzlichen Tätigkeitswechsel |
| A-03 | Zwischenfläche unter Stabilitätsfrist löst keinen Wechsel aus |
| A-04 | Reconnect erzeugt keine unbeabsichtigte neue Sitzung |
| A-05 | Dashboard-Rerun und Schließen lassen Agentenerfassung weiterlaufen |
| A-06 | Prozessneustart erhält bestätigte Daten und markiert unklaren Abschnitt |
| A-07 | Geräteübergabe erzeugt keine unbemerkte doppelte persönliche Zeit |
| A-08 | Korrektur bleibt nachvollziehbar, Export entspricht korrigierter Ansicht |
| A-09 | JSON-Backup wird in leerer Testumgebung erfolgreich restauriert |
| A-10 | Keine Tokens/echten Arbeitsdaten im Git-Repository |
| A-11 | pytest, Ruff und mypy bestehen in deklarierter Testumgebung |

Keine erfundenen Leistungs- oder Batteriezahlen. Latenz, CPU und Langzeitstabilität
im Hardwaretest messen. Betriebliche Rechtskonformität separat prüfen.
