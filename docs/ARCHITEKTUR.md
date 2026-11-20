# Architektur

```text
Tracker A / Tracker B
       | BLE
       v
Agent: Bleak + ein dauerhafter AsyncIO-Loop
       | pro Gerät eigener Zustand
       v
Protokoll -> Beobachtung -> Entprellung/Baseline -> Sitzungslogik
                                   |                  |
                                   v                  v
                              Ereignisspeicher    SQLite / Audit
                                   |
                         lokale authentifizierte API
                                   |
                              Streamlit-GUI
```

## Verantwortungen

- domain: reine Datenmodelle und Regeln ohne BLE, HTTP oder Streamlit.
- application: Anwendungsfälle und Orchestrierung.
- infrastructure/ble: Betriebssystem-/Bleakzugriff und Gerätefähigkeiten.
- infrastructure/storage: SQLite und Migrationen; kein SQL in GUI-Dateien.
- infrastructure/integrations: getrennte externe Ausgabeadapter.
- agent: Prozess, Supervisor, Lebenszyklus und Shutdown.
- api: HTTP-Verträge, Validierung, Authentifizierung und Abhängigkeiten.
- dashboard: Darstellung und API-Client; kein eigener BleakClient.

## Verbindungszustände

idle -> scanning -> connecting -> discovering -> subscribing -> baseline -> ready
ready -> disconnected -> reconnect_wait -> connecting

„Verbunden“ ist nicht gleich „gültige Orientierung vorhanden“. Bei Reconnect
Dienste und Abonnement neu aufbauen; alte Tasks/Listener beenden. Jeder Verbindungs-
zyklus bekommt eine Kennung. Späte Ergebnisse alter Zyklen ignorieren.

## Nebenläufigkeit

BLE-Callback validiert kurz und übergibt ein Ereignis. Keine langsamen HTTP-Aufrufe
oder Diagramme darin. Ein zentraler Writer speichert Daten. GUI liest Snapshots.
Manueller Stopp beendet auch Reconnect. Shutdown sichert Daten und trennt BLE.

## Gründe

Bleak benötigt zusammengehörige Operationen in einem laufenden Loop:
https://bleak.readthedocs.io/en/latest/troubleshooting.html

Streamlit-Interaktionen lösen Reruns aus und Hardware liegt beim Pythonhost:
https://docs.streamlit.io/develop/concepts/architecture/architecture

## Status

Dies ist die Zielarchitektur. Server, Supervisor und Repository sind noch Stubs.
