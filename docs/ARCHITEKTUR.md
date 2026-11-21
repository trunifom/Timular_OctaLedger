# OctaLedger – Architektur

Dieses Dokument erklärt, **wie OctaLedger aufgebaut ist und warum**: welche Bausteine es gibt, wie Daten fließen, welche Prozesse und
Threads laufen, wie die Zeiterfassung und der Steuerungsmodus zusammenspielen und wo man erweitern kann. Wer nur das Programm benutzen
will, liest das [Benutzerhandbuch](BENUTZERHANDBUCH.md). Einzelheiten zu jeder Datei stehen im Quelltext (Modul-Docstrings) und in der
[Softwaredokumentation](SOFTWAREDOKUMENTATION.md); die Schnittstelle beschreibt die [API-Referenz](API.md).

**Inhalt**

1. [Überblick in einem Bild](#1-überblick-in-einem-bild)
2. [Schichten und Verantwortungen](#2-schichten-und-verantwortungen)
3. [Prozesse und Threads](#3-prozesse-und-threads)
4. [Datenfluss Zeiterfassung](#4-datenfluss-zeiterfassung)
5. [Datenfluss Steuerungsmodus](#5-datenfluss-steuerungsmodus)
6. [Verbindungszustände eines Würfels](#6-verbindungszustände-eines-würfels)
7. [Speicherung und Dateien](#7-speicherung-und-dateien)
8. [Das Dashboard](#8-das-dashboard)
9. [Fehlerbehandlung und Protokollierung](#9-fehlerbehandlung-und-protokollierung)
10. [Sicherheitsarchitektur](#10-sicherheitsarchitektur)
11. [Erweiterungspunkte](#11-erweiterungspunkte)
12. [Entwurfsentscheidungen und ihre Gründe](#12-entwurfsentscheidungen-und-ihre-gründe)
13. [Bekannte Grenzen](#13-bekannte-grenzen)

---

## 1. Überblick in einem Bild

```text
  Würfel A / Würfel B  (Timeular/ZEI, Bluetooth Low Energy)
        |  nur lesen und abonnieren – OctaLedger schreibt nie in den Würfel
        v
 +------------------------------------------------------------------------------+
 |  AGENT (ein Python-Prozess, läuft im Hintergrund)                            |
 |                                                                              |
 |  BLE-Thread: ein asyncio-Loop                  API-Thread       Dispatcher    |
 |   DeviceWorker je Würfel                       (uvicorn)        -Thread       |
 |    Protokoll -> Beobachtung -> Entprellung        |                |          |
 |                       |                           |                |          |
 |                       v                           v                v          |
 |        Tracking-Service  <------ Anwendungsdienste ------>  Integrationsdienst|
 |        (Zeit ODER Steuerung)                                   |  Adapter     |
 |                       |                                        |  (Webhook,   |
 |                       v                                        |  MQTT, HA,   |
 |              SQLite (ein Schreiber)  <-- Warteschlange ("Outbox")  Hue)       |
 +------------------------------------------------------------------------------+
        ^  HTTP, nur 127.0.0.1, Token                                |
        |                                                            v
 +--------------------+                                  Licht, Smarthome, Broker, Webdienst
 | DASHBOARD          |
 | (Streamlit, Browser|
 |  auf 127.0.0.1)    |
 +--------------------+
```

Drei Leitgedanken prägen alles:

* **Der Agent erfasst, das Dashboard zeigt.** Schließt man den Browser, läuft die Erfassung (und der Steuerungsmodus) weiter.
* **Eine Wahrheit:** alle Daten liegen in **einer** SQLite-Datenbank, geschrieben von **einem** Schreiber (dem Agenten). Das Dashboard
  bekommt nie Zugriff auf die Datei, sondern fragt die lokale API.
* **Zuerst die Sicherheit der Daten:** Eine Beobachtung wird gespeichert, **bevor** etwas daraus folgt; eine Aktion wird **in derselben Transaktion**
  vorgemerkt wie das Ereignis, das sie auslöst.

## 2. Schichten und Verantwortungen

Abhängigkeiten zeigen **nur nach innen**: `domain` ← `application` ← `infrastructure` / `api` / `agent`. Das Paket `core` (Fehler, Logging,
Dateizugriff, Einstellungen, Geheimnisspeicher) darf von allen genutzt werden und importiert selbst keine Schicht. Das Dashboard
darf nur den `dashboard_client` verwenden.

| Schicht | Paket | Verantwortung |
|---|---|---|
| **domain** | `octaledger.domain` | reine Modelle und Regeln, ohne BLE, HTTP, SQL oder Streamlit: `models` (Gerät, Sitzung, Aktion, Auftrag …), `orientation` (Rohwert ↔ Seite), `state_machine` (Entprellung, Baseline, Verbindungszustände, Wiederverbindungs-Wartezeiten), `time_rules` (UTC, Tagesgrenzen, Überschneidungen) |
| **application** | `octaledger.application` | Anwendungsfälle, jeder in genau einem Dienst: `tracking_service` (Sitzungslogik **und** Weiche Zeit/Steuerung), `device_service` (Geräte, Seitenbelegung, Modus), `catalog_service` (Aktivitäten, Projekte), `reporting_service` (Berichte), `export_service` (CSV, Sicherung, Wiederherstellung), `integration_service` (Verbindungen, Aktionen, Versand), `outbox` (Regeln der Warteschlange) |
| **infrastructure/ble** | `octaledger.infrastructure.ble` | `protocol` (UUIDs, Fähigkeitenerkennung, Decoder), `transport` (Schnittstelle **ohne** Schreibzugriff), `fake` (Simulator für Tests und Vorschau), `client` (Bleak), `scanner` |
| **infrastructure/storage** | `octaledger.infrastructure.storage` | SQLite-Zugriff, nummerierte Migrationen, Repositories; **kein SQL außerhalb dieses Pakets** |
| **infrastructure/integrations** | `octaledger.infrastructure.integrations` | Adapter des Steuerungsmodus: `base` (Vertrag: `Adapter`, `AdapterSpec`, `FieldSpec`, `ActionSpec`), `registry`, `httpio` (gemeinsame, sichere HTTP-Logik), `webhook`, `mqtt`, `homeassistant`, `hue` |
| **agent** | `octaledger.agent` | der Prozess: `main` (`AgentRuntime`: Start, Threads, Herunterfahren, Autostart), `supervisor` (Worker, Wiederverbindung, Puffer), `dispatcher` (Versand-Thread) |
| **api** | `octaledger.api` | HTTP-Verträge (`schemas`), Routen, Authentifizierung und Host-/Origin-Schutz (`security`), Anwendungskontext |
| **dashboard** | `octaledger.dashboard` + `octaledger.dashboard_client` | Darstellung (Seiten, Formulare, SVG-Würfel, Handbuch-Leser) und der API-Client; **kein BleakClient, kein SQL** |
| **core** | `octaledger.core` | Fehlerklassen mit stabilen Codes, Protokollierung mit Schwärzung, atomarer Dateizugriff, Einstellungen/Pfade, `SecretStore` |

**Warum so streng?** Jede Regel lässt sich ohne Bluetooth, Netzwerk und Browser testen (die Tests der Domäne laufen in Millisekunden), und ein
Wechsel an einem Rand (zum Beispiel ein anderes Dashboard) berührt die Mitte nicht.

## 3. Prozesse und Threads

OctaLedger besteht aus **zwei Betriebssystem-Prozessen** (Befehle `octaledger agent` und `octaledger dashboard`, gemeinsam gestartet mit
`scripts\start_all.bat`):

| Prozess | Inhalt |
|---|---|
| **Agent** | Hauptthread (wartet auf Beenden), **BLE-Thread** mit dem asyncio-Loop, **API-Thread** (uvicorn), **Dispatcher-Thread** (Versand der Aktionen) |
| **Dashboard** | Streamlit-Server (Skript läuft bei jeder Interaktion neu); spricht nur über HTTP mit dem Agenten |

Regeln der Nebenläufigkeit:

* **Ein Loop besitzt alle BLE-Clients** (eine Anforderung von Bleak). Jeder `DeviceWorker` ist der einzige Besitzer „seines“ Würfels.
* Der **BLE-Callback** prüft kurz, schreibt in einen **begrenzten Puffer** (bei Überlauf fällt der älteste Wert weg und wird gezählt) und weckt den Worker
  thread-sicher. Im Callback gibt es nie langsame Aufrufe.
* **Datenbankarbeit** läuft in `asyncio.to_thread`, strikt in Reihenfolge je Gerät. Der Agent ist der **einzige reguläre Schreiber**.
* Die **API** erreicht die BLE-Seite ausschließlich über `AgentControl` (`run_coroutine_threadsafe`) – nie direkt.
* Der **Dispatcher** ist ein eigener Daemon-Thread: Netzwerkanfragen dürfen den BLE-Loop nie aufhalten, und das Dashboard ist nicht beteiligt.
  Er arbeitet Aufträge **nacheinander in Erzeugungsreihenfolge** ab („an“ dann „aus“ bleibt „an“, dann „aus“), überlebt jeden Fehler und wartet
  über ein `threading.Event`, damit das Herunterfahren nicht auf ein Intervall wartet.
* **Herunterfahren** in dieser Reihenfolge: API → Tracker (Verbindung trennen, abschließende Ereignisse) → Loop → Dispatcher → Threads.
* **Autostart:** Nach dem Start verbindet der Agent den aktiven Tracker **und jeden Tracker im Steuerungsmodus** (sofern eine Adresse
  gespeichert ist). Ein Fehler bei einem Würfel stoppt weder die anderen noch den Agenten.

## 4. Datenfluss Zeiterfassung

```text
Würfel dreht sich
  1. BLE-Benachrichtigung (ein Byte: Seite 0–8)                          [BLE-Thread]
  2. Protokoll-Decoder: Rohwert prüfen; ungültig -> Diagnose, nie eine Sitzung
  3. Puffer -> DeviceWorker -> Entprellung (Seite muss kurz stabil bleiben)
  4. Rohereignis (raw_event) wird GESPEICHERT                           [DB-Transaktion]
  5. Tracking-Service, Weiche: Modus des Würfels = Zeit
       a. ist der Würfel der aktive Tracker? (nur dieser beeinflusst die Zeit)
       b. Seite -> Aktivität/Projekt (Seitenbelegung)
       c. laufende Sitzung beenden, neue starten (gleiche Transaktion)
  6. Dashboard fragt per API: Übersicht, Journal, Berichte
```

Wichtige Regeln dabei:

* **Baseline:** Beim (Wieder-)Verbinden wird die aktuelle Lage nur gelesen – sie startet **keine** Sitzung.
* **Unsichere Sitzungen:** Reißt die Verbindung ab, wird die Sitzung nicht geraten, sondern als *unsicher* markiert; der Anwender bestätigt oder korrigiert sie.
* **Eine laufende Sitzung zur Zeit** und **keine überlappenden Sitzungen** – beides erzwingt die Datenbank selbst (Index und Trigger), nicht nur der Code.
* **Zeit ist UTC;** erst die Anzeige rechnet in die gewählte Zeitzone (Sommerzeit inklusive).
* **Korrekturen** ändern nie still: Vorher/Nachher, Grund und Zeitpunkt landen in `corrections`.

## 5. Datenfluss Steuerungsmodus

Jeder Würfel steht in genau einem **Modus**: `time` (Standard) oder `control`. Die Weiche sitzt im `tracking_service`:

```text
Würfel dreht sich  (Schritte 1–4 wie oben: Entprellung, Rohereignis speichern)
  5. Weiche: Modus des Würfels = Steuerung
       -> KEINE Sitzung, keine Berührung der Zeiterfassung
       a. Baseline/Trennung/Neutral/ungültig: nichts tun
       b. Seitenwechsel: Aktion dieser Seite suchen (face_actions)
       c. Auftrag (integration_jobs) in DERSELBEN Transaktion wie das Rohereignis anlegen
          Schlüssel für Doppelsicherheit = ID des Rohereignisses (UNIQUE)
  6. Dispatcher-Thread (alle 0,25 s): fällige Aufträge holen, nacheinander senden
       - abgelaufen (älter als 30 s)?   -> expired, nicht mehr senden
       - Adapter.execute(...)           -> done
       - IntegrationConnectionError      -> "kam sicher nicht an": bis zu 3 Versuche mit 1 s / 3 s Pause
       - IntegrationError                -> failed, KEINE Wiederholung (Aktion könnte schon passiert sein)
  7. Verlauf im Dashboard (Seite „Verbindungen“) und in der Live-Ansicht
```

Die Zusicherungen der Warteschlange (`application/outbox.py`):

| Eigenschaft | Umsetzung |
|---|---|
| **zuverlässig** | Auftrag und Rohereignis in **einer** Transaktion – nichts geht zwischen „gesehen“ und „vorgemerkt“ verloren |
| **nicht doppelt** | eindeutiger Schlüssel (ID des Rohereignisses); auch ein erneutes Verarbeiten erzeugt keinen zweiten Auftrag |
| **nicht zu spät** | Lebensdauer 30 s – ein Licht, das eine Minute später angeht, wäre ein Fehler |
| **begrenzt** | höchstens 50 wartende Aufträge je Verbindung; weitere werden mit klarem Grund als *expired* abgelegt |
| **vorsichtig wiederholt** | nur bei Fehlern, die **sicher** keine Wirkung hatten; maximal 3 Versuche |
| **nachvollziehbar** | der Verlauf nennt je Auftrag Status, Versuche und Fehlertext (ohne Geheimnisse); Erledigtes wird 7 Tage aufbewahrt |

**Adapter** sind austauschbar. Jeder beschreibt sich selbst (`AdapterSpec`: Felder, Aktionen, ob Kopplung/Entdeckung möglich ist); die
Oberfläche erzeugt daraus ihre Formulare, und der `IntegrationService` prüft Eingaben anhand derselben Beschreibung. Ein neuer
Adapter braucht deshalb weder neue Oberfläche noch neue API (siehe [Adapter-Entwicklung](ADAPTER_ENTWICKLUNG.md)).

| Adapter | Art | Besonderheiten |
|---|---|---|
| Webhook | HTTP-Anfrage an eine beliebige Adresse | keine Weiterleitungen, keine Proxys, Antwort wird nicht ausgewertet |
| MQTT | Nachricht an einen Broker veröffentlichen | eigener MQTT-3.1.1-Sender (nur Standardbibliothek), QoS 0/1, TLS, hartes Zeitlimit |
| Home Assistant | Dienste, Szenen, Skripte, Schalter | der Weg zu **Matter** und **Google Home** (beide hängen am Home Assistant); Entdeckung der Geräte |
| Philips Hue | Lampe, Raum, Szene über die Bridge | Kopplung per Bridge-Taste, **Zertifikat-Anheftung** beim ersten Mal (SHA-256), Entdeckung |

## 6. Verbindungszustände eines Würfels

```text
idle -> scanning -> connecting -> discovering -> subscribing -> baseline -> ready
ready -> disconnected -> reconnect_wait -> connecting          (automatische Wiederverbindung)
jeder Zustand -> stopped                                      (bewusster Stopp, kein Wiederverbinden)
```

* „Verbunden“ ist **nicht** „gültige Lage bekannt“: Nur `ready` (Baseline gelesen) zählt.
* **Jeder Verbindungszyklus** erhält eine neue Kennung und einen neuen Transport; späte Ergebnisse alter Zyklen werden ignoriert.
* Wartezeiten der Wiederverbindung wachsen (Backoff mit Obergrenze); ein bewusster Stopp beendet auch sie.
* Umgesetzt in `domain/state_machine.py` (reine Regeln) und `agent/supervisor.py` (Ausführung).

## 7. Speicherung und Dateien

Alle Nutzerdaten liegen im **Benutzerprofil**, nie im Projektordner (Ort anzeigen: `octaledger paths`; änderbar mit `--data-dir` oder
`OCTALEDGER_DATA_DIR`).

| Datei/Ordner | Inhalt | Besonderheit |
|---|---|---|
| `data/octaledger.sqlite3` | SQLite-Datenbank (Geräte, Katalog, Rohereignisse, Sitzungen, Korrekturen, Verbindungen, Aktionen, Aufträge, Zustand) | WAL-Modus; Migrationen `0001`–`0003` |
| `api_token` | Anmelde-Token der lokalen API | zufällig, 256 Bit, einmal erzeugt |
| `secrets.json` | Zugangsdaten der Verbindungen | **nicht in der Datenbank, nicht in Sicherungen, nie in API-Antworten oder Protokollen**; nicht verschlüsselt |
| `settings.toml` | Einstellungen | atomar geschrieben, streng geprüft |
| `logs/` | Protokolle (rotierend, Zugangsdaten geschwärzt) | |
| `backups/`, `exports/` | JSON-Sicherungen, CSV-Exporte | feste Ordner, Dateinamen vom Programm erzeugt |

Das Schema steht in [DATENMODELL.md](DATENMODELL.md). Datenbankregeln, die die **Konsistenz** sichern (eindeutige Namen, höchstens eine laufende Sitzung,
keine Überlappung, Wertebereiche), stehen in der Datenbank selbst – ein Fehler im Code kann sie nicht umgehen.

## 8. Das Dashboard

* **Streamlit** führt das Skript bei jeder Interaktion neu aus. Es gibt keine Endlosschleifen und keine BLE-Arbeit; Zustand liegt in
  `st.session_state`. Live-Teile (Würfel live, Verlauf) aktualisieren sich über `st.fragment(run_every=…)`, ohne die ganze Seite neu zu laden.
* **Navigation** (vier Gruppen): *Start* – Startseite; *Alltag* – Übersicht, Würfel live, Zeitjournal, Statistik; *Einrichten* – Geräte, Seiten zuordnen, Verbindungen, Verwaltung; *System* – Daten, Einstellungen, Diagnose.
* **Formulare der Verbindungen** entstehen **generisch** aus der Selbstbeschreibung der Adapter (`dashboard/forms.py`).
* Der **SVG-Würfel** (`dashboard/cube.py`) zeigt die Lage; Bewegungen erkennt man auch ohne Hardware (Simulator, Vorschau).
* **Handbuch in der App:** `docs_reader.py` liest die Markdown-Dateien aus `docs/`, teilt sie an `## `-Überschriften in Kapitel und bietet Suche –
  die Dokumentation hat eine einzige Quelle (auch lesbar auf GitHub).
* Der Dashboard-Server hängt nur an `127.0.0.1`, ohne Telemetrie; das Token sendet er **nur an Loopback-Adressen**.

## 9. Fehlerbehandlung und Protokollierung

* Jede absichtliche Störung ist eine Unterklasse von `OctaLedgerError` mit **stabilem Code** (`OL-…`), deutscher Meldung für Anwender und
  englischer technischer Meldung. Die API übersetzt sie in HTTP-Status (siehe [API.md](API.md) §3); der Client macht aus dem Fehlerrumpf wieder die passende
  Klasse – die Oberfläche zeigt `message`, nie einen Stacktrace.
* **Unerwartete** Fehler werden mit Stacktrace protokolliert, nach außen aber nur als allgemeiner 500er gemeldet.
* **Protokolle** schwärzen Token, Passwörter und Bluetooth-Adressen, bevor sie geschrieben werden (`register_secret`); jeder gespeicherte
  Geheimniswert wird beim Speichern/Laden dort angemeldet.
* Der **Agent überlebt** einzelne Fehler: ein fehlgeschlagener Würfel, ein fehlschlagender Adapter, ein kaputter Auftrag beenden weder den Agenten noch die anderen Würfel.

## 10. Sicherheitsarchitektur

Kurz: Der Agent lauscht **nur auf `127.0.0.1`**; jede Anfrage braucht ein **Bearer-Token** (konstante Zeit, nie in Adressen), und **Host- und
Origin-Kopfzeile** werden geprüft (CSRF/DNS-Rebinding). Es gibt **keine BLE-Schreibzugriffe**. Zugangsdaten der Verbindungen liegen getrennt
(`secrets.json`), erscheinen nie in Sicherungen, Antworten oder Protokollen. Adapter folgen keinen Weiterleitungen, ignorieren Umgebungs-Proxys und
begrenzen Zeit und Antwortgröße; Hue prüft das Zertifikat der Bridge per Anheftung. Sicherungen tragen eine Prüfsumme und werden vor dem Einspielen vollständig validiert.
Ausführlich: [SECURITY.md](../SECURITY.md).

## 11. Erweiterungspunkte

| Ziel | Wo | Anleitung |
|---|---|---|
| neue **Art von Verbindung** (z. B. Telegram, Zigbee2MQTT) | Adapter in `infrastructure/integrations/` + Eintrag in `registry.py` | [ADAPTER_ENTWICKLUNG.md](ADAPTER_ENTWICKLUNG.md) |
| neuer **Endpunkt** | `api/routes.py` + `api/schemas.py` + Methode im `dashboard_client` + Eintrag in `docs/API.md` | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| neue **Fehlerart** | Unterklasse in `core/errors.py` (+ Statuszuordnung in `api/app.py`) | CONTRIBUTING |
| neue **Datenbankspalte/-tabelle** | nummerierte Migration `NNNN_name.sql` (lückenlos, eine Transaktion) | CONTRIBUTING |
| neue **Dashboard-Seite** | Datei in `dashboard/views/`, Eintrag in der Navigation, `page_help` | CONTRIBUTING |
| anderer **Würfel/Transport** | neuer `Transport` hinter der Schnittstelle in `infrastructure/ble/` | [BLE_PROTOCOL.md](BLE_PROTOCOL.md) |

## 12. Entwurfsentscheidungen und ihre Gründe

| Entscheidung | Grund |
|---|---|
| Agent und Dashboard als **getrennte Prozesse** | Streamlit führt Skripte bei jeder Interaktion neu aus und ist für dauerhafte Hardwarearbeit ungeeignet; Browser schließen darf die Erfassung nicht stoppen |
| **Ein** asyncio-Loop für alle BLE-Clients | Bleak verlangt zusammengehörige Operationen in einem laufenden Loop ([Bleak: Troubleshooting](https://bleak.readthedocs.io/en/latest/troubleshooting.html)) |
| **SQLite** mit einem Schreiber | lokal, ohne Server, transaktional; ein Schreiber vermeidet Sperrkonflikte |
| Dashboard **ohne** Datenbankzugriff | eine Schnittstelle, eine Sicherheitsgrenze, testbar |
| **Outbox** statt „sofort senden“ | Ein Absturz oder Netzwerkfehler darf weder ein Ereignis verlieren noch eine Aktion doppelt auslösen |
| Wiederholung **nur bei sicherem Nichtankommen** | Eine doppelt gesendete Aktion (Umschalten!) ist schlimmer als eine verlorene, die der Anwender sieht |
| Aktionen **verfallen** nach 30 s | Verspätete Reaktionen wirken wie Fehler |
| **Home Assistant** als Hub für Matter und Google Home | Matter/Google-Home-Geräte werden dort gesammelt; eine sorgfältige Anbindung ersetzt viele halbe |
| **Geheimnisse getrennt** | Sicherung und Datenbank dürfen geteilt werden können, ohne Zugänge preiszugeben |
| **Selbstbeschreibung der Adapter** | neue Verbindungsarten ohne Änderung an Oberfläche und API |
| **Keine BLE-Schreibzugriffe** | der Würfel gehört dem Anwender; OctaLedger liest nur |
| Dokumentation als **Markdown in `docs/`**, in der App gelesen | eine Quelle für GitHub und Programm |

Quellen zu Bleak und Streamlit: <https://bleak.readthedocs.io/en/latest/troubleshooting.html>,
<https://docs.streamlit.io/develop/concepts/architecture/architecture>.

## 13. Bekannte Grenzen

* Die Anbindung an **echte Würfel** wurde bisher nur mit Simulator und Testdoppeln geprüft; ein Test mit Hardware steht aus (siehe [TESTPLAN.md](TESTPLAN.md), [QUELLEN_UND_GRENZEN.md](QUELLEN_UND_GRENZEN.md)).
* **Hue** über eine echte Bridge und der echte TLS-Handshake mit Zertifikat-Anheftung sind nicht getestet.
* Es gibt **eine** lokale Installation für **einen** Anwender; keine Synchronisation, kein Mehrbenutzerbetrieb.
* `secrets.json` ist nicht verschlüsselt (Schutz durch das Benutzerprofil von Windows).
* Aktionen sind **Einbahn**: Der Würfel schaltet, liest aber den Zustand der Lampe nicht zurück (z. B. nach manuellem Umschalten).
