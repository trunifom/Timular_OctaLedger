# OctaLedger – Rezeptbuch: Node-RED und andere Open-Source-Ziele

Dieses Rezeptbuch zeigt, wie Sie den Würfel mit **Node-RED, Zigbee2MQTT, WLED, Shelly, openHAB** und **Home Assistant** verbinden, ohne dass OctaLedger
dafür einen eigenen Adapter braucht: Alles läuft über die beiden allgemeinen Verbindungsarten **Webhook** (Web-Anfrage) und **MQTT**.
In der Oberfläche wählen Sie bei der Würfelseite die **Vorlage** (Auswahl „Vorlage (optional)“), klicken *Vorlage übernehmen* und passen danach an, was
bei Ihnen anders heißt.

> **Ehrlich zum Stand:** Kein Rezept wurde bisher an einem **echten Ziel** geprüft (Stand 2026-11-22). Die Vorlagen sind getestet (sie sind gültig, die Platzhalter
> werden richtig ersetzt), aber ob **Ihr** Gerät genau so reagiert, zeigt erst ein Versuch. Nutzen Sie dafür *Jetzt ausprobieren*. Wenn ein Rezept bei Ihnen
> funktioniert (oder nicht), tragen Sie es hier mit Datum ein.

Inhalt: [Platzhalter](#1-platzhalter-in-nachrichten) · [Node-RED](#2-node-red) · [Zigbee2MQTT](#3-zigbee2mqtt) · [Tasmota](#4-tasmota) · [WLED](#5-wled) ·
[Shelly](#6-shelly-generation-2) · [openHAB](#7-openhab) · [Home-Assistant-Webhook](#8-home-assistant-webhook)

## 1. Platzhalter in Nachrichten

Im **Inhalt** einer Webhook-Anfrage und einer MQTT-Nachricht dürfen vier Platzhalter stehen. OctaLedger ersetzt sie **beim Senden**:

| Platzhalter | wird ersetzt durch |
|---|---|
| `{device}` | Name des Würfels |
| `{face}` | Seite 1 bis 8 (Zahl) |
| `{label}` | Name der Seite |
| `{time}` | Zeitpunkt der Drehung in UTC, z. B. `2026-01-05T08:00:03Z` |

Beispiel: `{"device":"{device}","face":{face},"label":"{label}","time":"{time}"}`.

**Regeln und Sicherheit**
- Es sind **nur diese vier Namen** erlaubt; ein anderer Name wird beim Speichern abgelehnt. Es gibt **keine Ausdrücke**: `{face+1}` bleibt Text.
- Ist der Inhalt eine **JSON-Vorlage** (er ist gültiges JSON, sobald die Platzhalter Werte haben), werden eingesetzte Texte **maskiert**: Ein Seitenname wie `Lampe"} {"x":1` kann die Struktur der Nachricht nicht verändern. Platzhalter gehören **nur in Zahlen und in Anführungszeichen**; der Inhalt `{"a":{label}}` (Platzhalter für Text außerhalb von Anführungszeichen) ist kein gültiges JSON und wird abgelehnt.
- Bei einfachem Text (z. B. `ON`) wird roh eingesetzt.
- In **Kopfzeilen** (Zugangswert) und im **Pfad** gibt es keine Platzhalter.

## 2. Node-RED

**Voraussetzung:** Node-RED läuft im Heimnetz (Standard-Port 1880).

**Schritte in Node-RED:** Knoten **http in** (Methode POST, URL `/octaledger`) und **http response** anlegen und verbinden; dazwischen z. B. ein **debug**-Knoten. Wenn Sie
Unterschiede je Seite brauchen, lesen Sie im Flow `msg.payload.face`.

**Schritte in OctaLedger**
1. *Smarthome & Verbindungen* → Art **Webhook**, Basisadresse `http://<IP>:1880` (ohne Pfad).
2. Würfelseite → Verbindung wählen, Aktion *Anfrage senden*, Vorlage **Node-RED (HTTP-In, JSON)** übernehmen.
3. *Jetzt ausprobieren*: Im Debug-Fenster von Node-RED erscheint die Nachricht.

**MQTT statt HTTP:** Verbindung **MQTT**, Vorlage **Node-RED (MQTT in)** (Thema `octaledger/seite`), in Node-RED ein Knoten **mqtt in** auf dasselbe Thema.

**Absichern:** Der Knoten „http in“ ist standardmäßig **ungeschützt**. Möglichkeiten (laut Node-RED-Dokumentation): `httpNodeAuth` (Basic-Auth, ein Benutzer) in der `settings.js`,
eine eigene Prüfung im Flow (z. B. ein Kopf mit einem Geheimnis) oder ein Reverse-Proxy. Tragen Sie in OctaLedger unter *Erweiterte Einstellungen* den Zugangskopf und den **Zugangswert**
ein (z. B. `Authorization` und `Basic <Base64 aus benutzer:passwort>`).

**Typische Fehler:** *Zeitüberschreitung*: falsche IP oder Port, oder Node-RED läuft auf einem anderen Gerät/Netz. *404*: der Pfad im „http in“-Knoten weicht ab.
*Nichts passiert*: Der Flow wurde nicht bereitgestellt („Deploy“).

*Geprüft am echten Ziel:* noch nicht.

## 3. Zigbee2MQTT

**Voraussetzung:** Zigbee2MQTT läuft und ist mit einem MQTT-Broker verbunden (z. B. Mosquitto).

**Schritte in OctaLedger**
1. Verbindung **MQTT** (Adresse des Brokers, Port 1883, ggf. Benutzer und Passwort).
2. Würfelseite → Aktion *Nachricht veröffentlichen* → Vorlage **Zigbee2MQTT: Lampe einschalten** (oder ausschalten).
3. Im Thema `zigbee2mqtt/lampe/set` ersetzen Sie `lampe` durch den **Gerätenamen aus Zigbee2MQTT** (Frontend → Gerät → „Friendly name“).
4. *Jetzt ausprobieren*.

Der Inhalt `{"state":"ON"}` bzw. `{"state":"OFF"}` ist laut Zigbee2MQTT-Dokumentation das Format zum Schalten. Besser als `TOGGLE` (das bei jedem Senden wechselt).

**Typische Fehler:** Das Thema stimmt nicht mit dem „Friendly name“ überein (Groß-/Kleinschreibung zählt). Broker und Zigbee2MQTT nutzen unterschiedliche Basisthemen
(`zigbee2mqtt` ist nur der Standard).

*Geprüft am echten Ziel:* noch nicht.

## 4. Tasmota

**Voraussetzung:** Ein Tasmota-Gerät mit MQTT-Verbindung zu Ihrem Broker.

1. Verbindung **MQTT** wie oben.
2. Vorlage **Tasmota: Schalter einschalten** (oder ausschalten): Thema `cmnd/steckdose/POWER`, Inhalt `ON`.
3. Ersetzen Sie `steckdose` durch das **Topic** Ihres Geräts (Tasmota → Konfiguration → MQTT).

*Geprüft am echten Ziel:* noch nicht.

## 5. WLED

**Voraussetzung:** Eine WLED-Leuchte im Heimnetz.

1. Verbindung **Webhook**, Basisadresse `http://<IP der WLED>` (ohne Pfad).
2. Vorlage **WLED einschalten** / **WLED ausschalten** (`POST /json/state` mit `{"on":true}` bzw. `{"on":false}`).

*Geprüft am echten Ziel:* noch nicht.

## 6. Shelly (Generation 2)

**Voraussetzung:** Ein Shelly der 2. Generation (z. B. Plus-Serie) im Heimnetz, ohne Zugangsschutz oder mit eingetragenem Zugang.

1. Verbindung **Webhook**, Basisadresse `http://<IP des Shelly>`.
2. Vorlage **Shelly (Gen2) einschalten** / **ausschalten** (`GET /rpc/Switch.Set?id=0&on=true`). `id=0` ist der erste Kanal.

Geräte der 1. Generation nutzen eine andere Schnittstelle (`/relay/0?turn=on`); tragen Sie diese von Hand als Pfad ein.

*Geprüft am echten Ziel:* noch nicht.

## 7. openHAB

**Voraussetzung:** openHAB mit REST-API; ein Item, das „ON“ versteht.

1. Verbindung **Webhook**, Basisadresse `http://<IP>:8080`; bei aktivem Zugangsschutz Kopf und Wert eintragen.
2. Vorlage **openHAB: Item auf ON setzen** (`POST /rest/items/MeinItem`, Text `ON`). Ersetzen Sie `MeinItem` durch den Namen Ihres Items.

*Geprüft am echten Ziel:* noch nicht.

## 8. Home-Assistant-Webhook

Eine Automation in Home Assistant mit dem Auslöser **Webhook** kann alles tun, was Home Assistant kann (auch Matter- und Google-Home-Geräte).

1. In Home Assistant: Automation → Auslöser *Webhook* → Sie erhalten eine **ID** (sie ist das Geheimnis wie ein Passwort).
2. In OctaLedger: Verbindung **Webhook** mit der Adresse von Home Assistant (`http://<IP>:8123`), Vorlage **Home-Assistant-Webhook** (`POST /api/webhook/ID`).
3. Ersetzen Sie `ID` durch Ihre Webhook-ID. Die Seite (`{face}`) kommt als JSON in der Automation an.

**Hinweis:** Home Assistant antwortet auf einen Webhook fast immer mit „OK“, **auch bei falscher ID**; der Test erkennt einen Fehler dort nicht.
Für Lampen und Szenen ist die Verbindung **Home Assistant** (mit Zugriffstoken) meist die bessere Wahl.

*Geprüft am echten Ziel:* noch nicht.
