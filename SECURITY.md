# Sicherheit

OctaLedger ist ein **lokales** Programm: Es gibt kein Konto, keinen Server des Projekts und keine Telemetrie. Diese Seite beschreibt, **wovor** OctaLedger schützt,
**wie**, und was bewusst **nicht** abgedeckt ist. Die Architektur dahinter steht in [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md), die Schnittstelle in
[docs/API.md](docs/API.md), Einzelheiten in [docs/SOFTWAREDOKUMENTATION.md](docs/SOFTWAREDOKUMENTATION.md) (§17–20).

**Inhalt**

1. [Was geschützt wird](#1-was-geschützt-wird)
2. [Bedrohungen und Gegenmaßnahmen](#2-bedrohungen-und-gegenmaßnahmen)
3. [Die lokale Schnittstelle](#3-die-lokale-schnittstelle)
4. [Bluetooth](#4-bluetooth)
5. [Steuerungsmodus: Zugangsdaten und Ziele](#5-steuerungsmodus-zugangsdaten-und-ziele)
6. [Daten, Sicherungen, Export](#6-daten-sicherungen-export)
7. [Protokolle](#7-protokolle)
8. [Nicht umgesetzt – und warum](#8-nicht-umgesetzt--und-warum)
9. [Empfehlungen für Anwender](#9-empfehlungen-für-anwender)
10. [Sicherheitsprobleme melden](#10-sicherheitsprobleme-melden)

---

## 1. Was geschützt wird

| Schutzgut | Beispiel |
|---|---|
| **Private Zeitdaten** | wann Sie woran gearbeitet haben |
| **Zugangsdaten** | Home-Assistant-Token, MQTT-Passwort, Hue-Schlüssel, Webhook-Zugang, API-Token |
| **Steuerbare Geräte** | Licht und Steckdosen, die der Würfel schalten kann |
| **Integrität** | Zeiten und Einstellungen sollen nicht unbemerkt verfälscht werden |

## 2. Bedrohungen und Gegenmaßnahmen

| Bedrohung | Gegenmaßnahme |
|---|---|
| **Eine fremde Webseite** im Browser schickt Anfragen an `127.0.0.1` (CSRF) | Token pflicht, `Origin`-Prüfung, Zustandsänderungen nie per GET, keine CORS-Freigabe |
| **DNS-Rebinding** (ein Name zeigt plötzlich auf `127.0.0.1`) | `Host`-Prüfung: nur Loopback-Namen **mit genau dem API-Port** |
| **Andere Rechner im Netz** greifen auf die API zu | Bindung **nur an `127.0.0.1`**, nie an eine Netzwerkkarte |
| **Erraten des Tokens** | 256 Bit Zufall, Vergleich in konstanter Zeit; Fehlermeldung verrät nicht, was falsch war |
| **Manipulierte Eingaben** | strikte Eingabemodelle (unbekannte Felder werden abgelehnt), Grenzen für Längen und Größen, Wertebereiche auch in der Datenbank |
| **Manipulierte Sicherungsdatei** | vollständige Prüfung vor dem Einspielen (Format, Version, Prüfsumme, jedes Feld, Verweise); nichts darin wird ausgeführt oder als Pfad benutzt |
| **Excel-Formeln in Exporten** | CSV-Zellen, die mit `= + - @` oder Steuerzeichen beginnen, werden entschärft |
| **Pfadtricks** bei Export/Sicherung | Dateinamen erzeugt das Programm oder prüft streng (keine Ordner, feste Endung); Schreiben nur in feste Ordner |
| **Absturz mitten im Schreiben** | alle Dateien atomar (temporär schreiben, dann umbenennen); Datenbank transaktional |
| **Zugangsdaten gelangen in Sicherung/Log/Antwort** | getrennter Speicher, Schwärzung im Protokoll, API nennt nur Namen gesetzter Geheimnisse |
| **Eine Aktion wird doppelt oder zu spät ausgelöst** | Warteschlange mit eindeutigem Schlüssel, Verfall nach 30 s, Wiederholung nur wenn die Anfrage sicher nicht ankam |
| **Ein böswilliges Ziel** (Webhook-/Broker-Antwort) | keine Weiterleitungen, keine Umgebungs-Proxys, Zeitlimits, Antwortgrößen begrenzt, Antwort wird nicht ausgewertet |
| **Eine untergeschobene Hue-Bridge** | Zertifikat-Anheftung (SHA-256) beim ersten Verbinden |
| **Unbemerkte Schreibzugriffe auf den Würfel** | die Transportschicht **bietet keinen Schreibzugriff an** |

## 3. Die lokale Schnittstelle

* Bindung nur an Loopback; jede Anfrage durchläuft **Host-Prüfung → Origin-Prüfung → Größenprüfung → Token** (Details und Statuscodes: [docs/API.md](docs/API.md) §2).
* Das **Token** liegt in der Datei `api_token` im Datenordner (einmal zufällig erzeugt, 256 Bit) oder kommt aus `OCTALEDGER_API_TOKEN` (mindestens 32 Zeichen). Es reist
  **nur im `Authorization`-Kopf**, nie in einer Adresse, und ist beim Protokoll angemeldet (wird dort geschwärzt).
* Das Dashboard sendet das Token **nur an Loopback-Adressen** und läuft ohne Telemetrie (`--browser.gatherUsageStats false`).
* Es gibt **keine** automatische API-Dokumentation (`/docs`, `/openapi.json`) und **keinen** Endpunkt, der beliebige Dateien liest oder schreibt.
* Fehlerantworten enthalten **nie** Stacktraces oder Interna; unerwartete Fehler erscheinen nur im Protokoll.

## 4. Bluetooth

OctaLedger **liest und abonniert nur**. Es schreibt nie Werte in den Würfel (kein Umkonfigurieren, kein Firmware-Zugriff). Das ist in der Transportschnittstelle so festgelegt – es
gibt dafür schlicht keine Methode. Bluetooth-Adressen werden im Protokoll nur teilweise gezeigt.

## 5. Steuerungsmodus: Zugangsdaten und Ziele

Der Steuerungsmodus sendet Befehle an Geräte und Dienste; das schafft neue Risiken, die so begrenzt werden:

* **Zugangsdaten** (`password`-Felder) liegen in `secrets.json` im Datenordner – **nicht** in der Datenbank, **nicht** in Sicherungen, **nie** in API-Antworten oder Protokollen
  (jeder Wert wird beim Speichern/Laden für die Schwärzung angemeldet). Die Datei ist **nicht verschlüsselt**; sie ist so geschützt wie Ihr Benutzerprofil (siehe Abschnitt 8).
  Gleiches gilt für `api_token`.
* **Ziele** sind begrenzt: Adressen nur `http`/`https` ohne Benutzername; der Pfad einer Aktion wird an die Basisadresse **angehängt** (nie ein anderer Rechner); MQTT-Themen ohne Platzhalter
  und ohne `$`; keine Weiterleitungen; Umgebungs-Proxys werden ignoriert; jedes Netzwerk-Ereignis hat ein Zeitlimit.
* **Wiederholung ist vorsichtig:** Nur Fehler, die **sicher keine Wirkung** hatten (Verbindung nicht zustande gekommen), werden wiederholt – höchstens 3 Versuche. Eine Aktion verfällt nach **30 s**,
  höchstens 50 warten je Verbindung. Das verhindert, dass ein Netzproblem später eine Flut oder eine Doppelschaltung auslöst.
* **Bewusste Handlung:** Eine Verbindung wird nur von Ihnen angelegt; „Ausprobieren“ und „Testen“ sind eigene Schaltflächen. Nicht idempotente Aktionen (Umschalten) sind markiert.
* **Hue:** Beim ersten Verbinden wird der Fingerabdruck des Bridge-Zertifikats gespeichert („Vertrauen beim ersten Mal“); weicht er später ab, wird die Verbindung verweigert. Ein
  echter TLS-Handshake mit einer Bridge wurde **noch nicht** getestet.
* **TLS-Prüfung** ist bei Webhook und MQTT standardmäßig an; Abschalten ist nur für selbst erzeugte Zertifikate vorgesehen und im Hilfetext erklärt.

### 5a. Fremde Dateien: Kalender-Import und Berichte (AP-42)

- Eine **.ics-Datei** ist fremde Eingabe. OctaLedger liest sie **nur**, nie führt es etwas daraus aus und öffnet nie eine Adresse oder einen Anhang aus der Datei. Grenzen: höchstens 2 MiB, ein Zeitfenster von höchstens 90 Tagen (so kann eine Serie ohne Enddatum nicht unbegrenzt wachsen), höchstens 1000 Termine; jeder Parserfehler wird zu einer verständlichen Meldung. Termine sind nur **Vorschläge**: Gebucht wird erst nach Ihrer Bestätigung, alle gewählten zusammen in einer Transaktion (Überschneidungen brechen alles ab).
- Der **HTML-Bericht** enthält keine Skripte; jeder Text (Namen, Notizen, Kopfzeile) wird maskiert. Das PDF wird nur auf Wunsch erzeugt und nicht auf der Platte abgelegt.

## 6. Daten, Sicherungen, Export

* Datenbank und Dateien liegen im **Benutzerprofil**, nie im Projektordner. Wiederherstellung: vollständig geprüft, automatische Sicherung des alten Stands, **eine** Transaktion.
* **Sicherungen enthalten keine Zugangsdaten** – man kann sie gefahrlos aufbewahren, muss die Zugangsdaten nach einer Wiederherstellung aber neu eingeben.
* Sicherungen und Exporte enthalten Ihre **privaten Arbeitszeiten** und sind **nicht verschlüsselt**; bewahren Sie sie entsprechend auf.

## 7. Protokolle

Tokens, Passwörter, Zugangsdaten und Teile von Bluetooth-Adressen werden **vor dem Schreiben** geschwärzt. Protokolle liegen lokal in `logs/` (rotierend) und werden nirgends hingesendet. Auf der Seite
**Diagnose** kann der Anwender die letzten (geschwärzten) Zeilen einsehen. Teilen Sie Protokolle trotzdem nur nach einem Blick darauf.

## 8. Nicht umgesetzt – und warum

| Nicht umgesetzt | Begründung |
|---|---|
| Zugriff aus dem Netzwerk / Mehrbenutzerbetrieb | bewusst nur Loopback; ein Anwender, ein Rechner |
| Ratenbegrenzung für Fehlversuche | bei 256 Bit Zufall aussichtslos |
| Verschlüsselung der Datenbank, von `secrets.json` und `api_token` im Ruhezustand | Schutz durch das Benutzerprofil/Windows; ein Angreifer mit Zugriff auf Ihr Profil hat ohnehin Zugriff auf Ihre Sitzung. Eine Anbindung an den Windows-Tresor wäre ein möglicher späterer Schritt |
| Signierte Sicherungen | die Prüfsumme erkennt Beschädigung, nicht absichtliche Fälschung durch jemanden mit Dateizugriff |
| Rückmeldung vom Ziel (z. B. Lampenzustand) | Aktionen sind Einbahn |
| Prüfung auf Schadsoftware auf dem Rechner | außerhalb des Umfangs |

## 9. Empfehlungen für Anwender

1. Halten Sie Windows und den Browser aktuell und nutzen Sie ein eigenes Benutzerkonto.
2. Geben Sie `api_token` und `secrets.json` **nie** weiter (auch nicht in Fehlerberichten); entfernen Sie sie aus gemeinsam genutzten Ordnern.
3. Legen Sie für Home Assistant ein **eigenes Zugriffstoken nur für OctaLedger** an – dann lässt es sich jederzeit widerrufen, ohne etwas anderes zu stören.
4. Für MQTT einen **eigenen Benutzer** mit Schreibrecht nur auf die benötigten Themen verwenden.
5. Schalten Sie die TLS-Prüfung nur aus, wenn Sie das Ziel selbst betreiben und wissen warum.
6. Prüfen Sie nach dem Einrichten jeder Aktion mit **Ausprobieren**, was sie tatsächlich bewirkt.
7. Bewahren Sie Sicherungen und Exporte wie Ihre Zeiterfassung selbst auf (privat).

## 10. Sicherheitsprobleme melden

Schreiben Sie **keine Tokens, Zugangsdaten oder privaten Zeitdaten** in öffentliche Issues.
**Offen:** Der Betreiber des Projekts muss vor einer Veröffentlichung einen privaten Meldeweg ergänzen (z. B. GitHub „Security Advisories“ oder eine E-Mail-Adresse) – er ist hier
bewusst nicht erfunden.
