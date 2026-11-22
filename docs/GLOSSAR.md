# OctaLedger – Glossar

Alle Fachbegriffe von OctaLedger an einem Ort, alphabetisch. **Für Anwender** stehen die wichtigsten Begriffe auch im Benutzerhandbuch (Kapitel 2).
Verweise wie „→ Würfel“ führen zu einem anderen Eintrag.

**Inhalt**

[A](#a) · [B](#b) · [C](#c) · [D](#d) · [E](#e) · [F](#f) · [G](#g) · [H](#h) · [I](#i) · [J](#j) · [K](#k) · [L](#l) · [M](#m) · [N](#n) · [O](#o) · [P](#p) · [Q](#q) · [R](#r) · [S](#s) · [T](#t) · [U](#u) · [V](#v) · [W](#w) · [Z](#z)

---

## A

**Adapter** – Baustein des Steuerungsmodus, der mit einer Art von Gegenstelle spricht (Webhook, MQTT, Home Assistant, Hue). Beschreibt sich selbst
(→ Selbstbeschreibung). Anleitung: [ADAPTER_ENTWICKLUNG.md](ADAPTER_ENTWICKLUNG.md).

**Agent** – das Hintergrundprogramm (`octaledger agent`). Hält die Bluetooth-Verbindung zum Würfel, erkennt Drehungen, speichert alles und stellt die lokale
→ API bereit. Es ist **kein KI-Agent** und enthält kein Sprachmodell: Es ist ein gewöhnlicher Dienst, der „im Auftrag“ des Anwenders dauerhaft arbeitet.
Das Dashboard darf geschlossen werden, der Agent erfasst weiter.

**Aktion** – im → Steuerungsmodus das, was eine Würfelseite auslöst (z. B. „Licht an“, „Szene Abend“, „Nachricht senden“). Gehört zu einer → Verbindung und wird vom → Adapter geprüft.

**Aktivität (Tätigkeit)** – was Sie tun („Meeting“, „Entwicklung“). Jeder Seite im → Zeitmodus wird eine Tätigkeit zugeordnet.

**Alias** – der Name, den Sie einem Würfel geben („Würfel Büro“).

**API** – die lokale Schnittstelle (`http://127.0.0.1:8765/api/v1`), über die das Dashboard mit dem Agenten spricht. Nur vom eigenen Rechner erreichbar, durch ein → Token
geschützt. Referenz: [API.md](API.md).

**Archivieren** – eine → Aktivität oder ein → Projekt ausblenden, ohne die damit erfassten Zeiten zu verlieren. Benutzte Einträge lassen sich nur archivieren, nicht löschen.

**Audit-Spur (Prüfspur)** – Protokoll in der Datenbank, das Löschungen, Bereinigungen, Wiederherstellungen und → Korrekturen festhält.

## B

**Baseline** – die erste Lagemeldung nach dem (Wieder-)Verbinden. Sie wird nur **gelesen**, startet aber nie eine Sitzung und löst nie eine Aktion aus: Erst eine echte
Drehung zählt.

**Bleak** – die Python-Bibliothek, über die OctaLedger Bluetooth Low Energy nutzt.

**BLE (Bluetooth Low Energy)** – der stromsparende Bluetooth-Standard, den der Würfel verwendet. OctaLedger **liest nur** vom Würfel und abonniert Meldungen; es schreibt nie hinein.

**Backoff** – wachsende Wartezeit zwischen Wiederverbindungsversuchen (mit Obergrenze), damit ein abwesender Würfel nicht pausenlos angefragt wird.

## C

**CLIP v2** – die aktuelle Programmierschnittstelle der Philips-Hue-Bridge, die der Hue-Adapter nutzt.

**CSV** – Tabellendatei für Excel & Co. (Export der Sitzungen, UTF-8 mit BOM, Trennzeichen `;`).

## D

**Dashboard** – die Oberfläche im Browser (Streamlit, `http://127.0.0.1:8501`). Zeigt Daten und nimmt Eingaben entgegen, erfasst aber nichts selbst.

**Datenordner** – der Ort im Benutzerprofil, an dem Datenbank, Einstellungen, Token, Zugangsdaten, Protokolle, Sicherungen und Exporte liegen (`octaledger paths`).

**Frist (bei Verbindungsverlust)** – die Zeit, die ein Eintrag nach einem Verbindungsverlust weiterläuft (Voreinstellung 5 min). Danach endet er am Moment des Verlusts und es wird eine → Rückfrage gestellt.

**Leerlauf** – die Zeit, in der keine Taste und keine Maus bewegt wurde. OctaLedger misst nur diese Dauer (standardmäßig aus) und fragt dann nach.

**Arbeitstag** – die Einstellungen für Arbeitsende (Auto-Stopp), Arbeitstage, Leerlauf und Erinnerungen.

**Batterie-Stufe** – gut (ab 40 %), bald tauschen (20–39 %), schwach (10–19 %), fast leer (unter 10 %); steht immer mit Zahl und Text da, nie nur als Farbe.

**Ausgewählter Würfel** – der Würfel, den die Oberfläche gerade zeigt und bearbeitet (Wähler in der Seitenleiste, gilt auf allen Seiten). Nicht zu verwechseln mit dem **aktiven Zeit-Würfel** (⭐), der die Zeiterfassung steuert.

**Würfel-Identität** – Name, Nummer und Farbe eines Würfels; die Farbe steht nie allein, Nummer und Name stehen dabei.

**Musik-Modus** – dritte Betriebsart eines Würfels: Jede Seite spielt einen Titel, die Halterung (keine Seite oben) beendet die Musik. Erzeugt nie Zeiteinträge.

**Stille-Seite** – eine Seite eines Musik-Würfels ohne Titel; sie beendet die Musik wie die Halterung.

**Halterung** – die Plastikhalterung (Ladestation): Steht der Würfel darin, liegt keine Seite oben (neutral).

**Vorlage (Preset)** – fertig ausgefüllte Werte einer Aktion für ein bekanntes Ziel (z. B. Node-RED, WLED). Sie füllt nur das Formular; alles bleibt änderbar.

**Platzhalter** – `{device}`, `{face}`, `{label}`, `{time}` im Inhalt einer Nachricht; werden beim Senden durch Würfelname, Seite, Seitenname und Zeit ersetzt.

**Aktionskette** – die geordneten Schritte, die eine Würfelseite im Steuerungsmodus auslöst (je Schritt: Verbindung, Aktion, Verzögerung, optional ein Zeitfenster). Ein neuer Seitenwechsel verwirft die noch nicht gesendeten Schritte der vorigen Kette.

**Housekeeper** – der Hintergrund-Thread im Agenten, der zeitgesteuerte Regeln prüft (Frist nach Verbindungsverlust, später Arbeitstag und Erinnerungen).

**Rückfrage** – eine Frage, die auf Ihre Entscheidung wartet, z. B. was in einer Lücke nach einem Verbindungsverlust war. Sie ändert nie von selbst Zeitdaten.

**Dispatcher** – der Hintergrund-Thread im Agenten, der die wartenden → Aufträge des Steuerungsmodus nacheinander sendet.

**Duplikat** – eine Würfelmeldung, die denselben Wert wie zuvor wiederholt; sie wird gezählt und ignoriert.

## E

**Entfernen (Würfel)** – einen Würfel samt Seitenzuordnung und Aktionen aus OctaLedger löschen; hat er Daten, nur mit ausdrücklicher Entscheidung und nach einer automatischen Sicherung. Das Gegenstück ohne Löschen ist **Kopplung aufheben**.

**Entprellen** – eine Seite muss kurz stabil liegen, bevor sie als neue Seite gilt. Schützt vor Fehlwechseln, wenn der Würfel beim Drehen über andere Seiten kippt.

**Eintrag** – umgangssprachlich für → Sitzung.

## F

**Erweiterte Einstellungen** – eingeklappter Bereich bei den App-Einstellungen und bei jeder Verbindung mit seltener nötigen Angaben (z. B. Zertifikatsprüfung, QoS). Die Voreinstellungen passen für die üblichen Fälle; der Bereich klappt von selbst auf, wenn ein gespeicherter Wert davon abweicht.

**Fragment** – Streamlit-Technik, mit der Teile einer Seite (Würfel live, Verlauf) sich selbst aktualisieren, ohne die ganze Seite neu zu laden.

## G

**Geheimnis** – Passwort, Token oder Schlüssel einer → Verbindung. Wird getrennt in `secrets.json` gespeichert, nie in der Datenbank, Sicherung, API-Antwort oder dem Protokoll.

**Gefahrenzone** – der eingeklappte Bereich unten im Reiter „Löschen“ mit „Alles zurücksetzen“; verlangt das Eintippen von „ALLES LÖSCHEN“.

**Gerät (Tracker)** – ein registrierter Würfel.

**Gerätezeit / persönliche Zeit** – in Berichten: Summe aller Sitzungen (Gerätezeit) gegenüber der Vereinigung der Zeitintervalle (persönliche Zeit). Überschneidungen zählen so nicht doppelt.

## H

**Home Assistant** – eine verbreitete, lokal laufende Smarthome-Zentrale. Für OctaLedger der **Hub**, über den auch → Matter- und Google-Home-Geräte erreichbar sind.

**Hue (Philips Hue)** – Lampensystem mit einer „Bridge“ im Heimnetz; eigener Adapter mit → Kopplung.

## I

**Idempotent** – eine Aktion, die mehrfach ausgeführt dasselbe bewirkt wie einmal („Licht **an**“ ja, „Licht **umschalten**“ nein). Nicht idempotente Aktionen werden in der Oberfläche markiert.

**Integration** – im Code der Begriff für eine → Verbindung (Tabelle `integrations`).

## J

**Job** → Auftrag.

## K

**Kalibrierung** – das Zuordnen der acht Seiten zu Tätigkeiten oder Aktionen. Die Seite **Seiten zuordnen** führt Schritt für Schritt durch.

**Kopplung aufheben** – die Verbindung zu einem Würfel beenden und seine Bluetooth-Adresse vergessen; Würfel, Seiten und Daten bleiben (erneutes Koppeln ist jederzeit möglich).

**Kopplung (Pairing)** – ein einmaliger Schritt, der einer Verbindung Zugang verschafft (bei Hue: die Bridge-Taste drücken, dann „Koppeln“).

**Korrektur** – nachträgliche Änderung einer Sitzung. Immer mit Grund und Vorher/Nachher in der → Audit-Spur.

## L

**Live-Ansicht** – die Seite **Würfel live**: zeigt die Lage, die Entprellung, die letzten Bewegungen und ihre Wirkung in Echtzeit.

**Loopback** – die Adresse `127.0.0.1` („dieser Rechner“). Agent-API und Dashboard sind **nur** darüber erreichbar.

## M

**Matter** – ein herstellerübergreifender Smarthome-Standard. OctaLedger spricht ihn **nicht direkt**, sondern über → Home Assistant.

**Migration** – nummerierte SQL-Datei, die das Datenbankschema auf den neuesten Stand bringt (vorher wird automatisch eine Kopie angelegt).

**Modus (Zeit / Steuerung)** – jeder Würfel steht im → Zeitmodus oder im → Steuerungsmodus. Umschaltbar pro Würfel.

**MQTT** – leichtgewichtiges Nachrichtenprotokoll des Smarthomes; Nachrichten gehen an einen „Broker“ (z. B. Mosquitto) unter einem „Thema“.

## N

**Musik-Modus** – (geplant, AP-48 bis AP-50) dritte Betriebsart je Würfel: jede Seite spielt einen eigenen Titel (Radio, Datei, Home Assistant/Cast, Spotify, YouTube Music); steht der Würfel in der **Halterung** (auf keiner Seite), hält die Musik ganz an. Es entstehen keine Zeiten.

**Neutral (0)** – der Würfel liegt auf keiner stabilen Seite (z. B. in der Hand). Im Zeitmodus beendet es die laufende Sitzung nur, wenn die Einstellung „Neutral = Pause“ gewählt ist; im Steuerungsmodus löst es nie eine Aktion aus.

## O

**Outbox (Warteschlange)** – Tabelle `integration_jobs`: Aktionen werden **zuerst gespeichert** (in derselben Transaktion wie das auslösende Ereignis) und erst dann gesendet. Verhindert Verlust und Doppelsendung.

## P

**Pairing** → Kopplung.

**Projekt** – optional, wofür eine Zeit gebucht wird.

**Sicherung vor dem Löschen** – vor jedem Löschen und Zurücksetzen schreibt OctaLedger automatisch eine vollständige Sicherung (`octaledger-pre-…json` im Ordner `backups`) und nennt ihren Namen; sie ist das „Rückgängig“.

**Prüfsumme (Checksumme)** – SHA-256-Wert über den Inhalt einer Sicherung; erkennt Beschädigung und Abschneiden.

## Q

**QoS (Quality of Service)** – bei MQTT: 0 = höchstens einmal, 1 = mit Bestätigung des Brokers.

## R

**Rohereignis** – jede einzelne Beobachtung des Würfels, unverändert gespeichert, bevor etwas daraus folgt. Der Beleg hinter jeder Sitzung und Aktion.

**Restore (Wiederherstellung)** – Ersetzen aller Daten durch eine Sicherung; erst vollständig geprüft, dann in einer Transaktion, mit automatischer Sicherung des alten Stands.

## S

**Seite** – eine der acht Flächen des Würfels (1–8).

**Selbstbeschreibung** – Angaben, mit denen ein → Adapter der Software mitteilt, welche Felder und Aktionen er hat; daraus entstehen Formulare und Prüfungen automatisch.

**Sitzung (Zeitabschnitt)** – ein Zeitraum mit Beginn und Ende für eine Tätigkeit. Läuft sie noch, hat sie kein Ende. Es gibt höchstens eine laufende Sitzung, und Sitzungen überlappen nie.

**SQLite** – die eingebettete Datenbank, in der alle Daten liegen (eine Datei, kein Server).

**Steuerungsmodus** – Betriebsart eines Würfels, in der jede Seite eine → Aktion auslöst statt Zeit zu erfassen. Es entstehen **keine** Sitzungen.

**Streamlit** – das Python-Gerüst, auf dem das Dashboard läuft.

## T

**Token** – zufälliges Geheimnis (256 Bit) in der Datei `api_token`, das jede Anfrage an die → API als `Authorization: Bearer …` mitbringen muss. Schützt davor, dass fremde Webseiten
im Browser Anfragen an den eigenen Rechner stellen.

**Tracker** – anderes Wort für Würfel/Gerät.

**TLS** – Verschlüsselung von Verbindungen (https, MQTT über Port 8883).

## U

**Unsicher (Qualität)** – Kennzeichen einer Sitzung, bei der ein Teil der Zeit nicht sicher ist (z. B. Verbindungsabbruch). Der Anwender bestätigt oder korrigiert sie.

**UTC** – die Weltzeit, in der alle Zeiten gespeichert werden; angezeigt wird in der eingestellten Zeitzone.

## V

**Verbindung** – im Steuerungsmodus die Anbindung an etwas Steuerbares (z. B. „Mein Home Assistant“). Hat eine Art (→ Adapter), Einstellungen und → Geheimnisse.

**Verfall** – eine Aktion wird nach **30 Sekunden** nicht mehr gesendet (Status *expired*): Ein Licht, das eine Minute zu spät angeht, wäre ein Fehler.

## W

**Webhook** – eine Web-Anfrage an eine Adresse; der Allzweck-Adapter für Geräte und Dienste mit einfacher Web-Schnittstelle.

**WAL** – „Write-Ahead Logging“, Betriebsart von SQLite, in der Lesen und Schreiben sich nicht blockieren.

## Z

**Zeitmodus** – Standard-Betriebsart eines Würfels: Seiten sind Tätigkeiten, Drehungen starten und beenden Sitzungen.

**Zustandsautomat** – die Regeln, nach denen die Verbindung zu einem Würfel ihre Zustände wechselt (`idle … ready … reconnect_wait … stopped`), siehe [ARCHITEKTUR.md](ARCHITEKTUR.md) §6.
