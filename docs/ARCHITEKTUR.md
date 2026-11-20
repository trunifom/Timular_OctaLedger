# Architektur

```text
Tracker A / Tracker B
       | BLE (nur lesen und abonnieren)
       v
Agent: Bleak + ein dauerhafter AsyncIO-Loop (eigener Thread)
       | pro Gerät: DeviceWorker mit eigenem Zustandsautomaten
       v
Protokoll -> Beobachtung -> Entprellung/Baseline -> Tracking-Service (Sitzungslogik)
                                   |                         |
                                   v                         v
                            Ereignisspeicher          SQLite / Auditspur
                                   \                         /
                                    lokale authentifizierte API (FastAPI, nur Loopback)
                                                 |
                                         Streamlit-Dashboard
```

**Status: umgesetzt.** Alle Teile existieren und sind automatisch getestet (siehe
[TESTPLAN.md](TESTPLAN.md)); die Anbindung an echte Tracker ist nur simuliert getestet.

## Verantwortungen und Module

| Schicht | Paket | Verantwortung |
|---|---|---|
| domain | `octaledger.domain` | reine Modelle und Regeln ohne BLE, HTTP, SQL oder Streamlit: `models`, `orientation`, `state_machine` (Entprellung, Baseline, Verbindungszustände, Backoff), `time_rules` (UTC, Tagesgrenzen, Überschneidungen) |
| application | `octaledger.application` | Anwendungsfälle: `tracking_service`, `device_service`, `catalog_service`, `reporting_service`, `export_service` |
| infrastructure/ble | `octaledger.infrastructure.ble` | `protocol` (UUIDs, Capability-Discovery, Decoder), `transport` (Schnittstelle **ohne** Schreibzugriff), `fake` (Simulator), `client` (Bleak), `scanner` |
| infrastructure/storage | `octaledger.infrastructure.storage` | SQLite, Migrationen, Repositories; **kein SQL außerhalb** |
| infrastructure/integrations | `octaledger.infrastructure.integrations` | Platz für spätere Ausgabeadapter (F-20), noch leer |
| agent | `octaledger.agent` | Prozess: `main` (Laufzeit, Threads, Start/Shutdown), `supervisor` (Worker, Reconnect, Puffer) |
| api | `octaledger.api` | HTTP-Verträge, Validierung, Authentifizierung, Host-/Origin-Schutz |
| dashboard | `octaledger.dashboard` (+ `dashboard_client`) | Darstellung und API-Client; **kein eigener BleakClient, kein SQL** |
| core | `octaledger.core` | Fehlercodes, Logging, atomarer Dateizugriff, Einstellungen/Pfade |

Abhängigkeiten zeigen nach innen: `domain` ← `application` ← `infrastructure`/`api`/`agent`; `core` darf
von allen genutzt werden und importiert selbst keine Schicht.

## Verbindungszustände

`idle -> scanning -> connecting -> discovering -> subscribing -> baseline -> ready`;
`ready -> disconnected -> reconnect_wait -> connecting`; jeder Zustand `-> stopped` (bewusster Stopp,
verhindert Reconnect).

„Verbunden“ ist nicht gleich „gültige Orientierung vorhanden“: nur `ready` (Baseline gelesen) zählt. Bei
Reconnect werden Dienste und Abonnement neu aufgebaut; **jeder Verbindungszyklus bekommt eine neue
Kennung und einen neuen Transport**, späte Ergebnisse alter Zyklen werden ignoriert. Implementiert in
`domain/state_machine.py` und `agent/supervisor.py`.

## Nebenläufigkeit

- **Ein** Loop besitzt alle BLE-Clients (Bleak-Anforderung); jeder `DeviceWorker` ist der einzige
  Besitzer „seines“ Geräts.
- Der BLE-Callback validiert kurz, schreibt in einen **begrenzten** Puffer (Überlauf: ältester Wert
  fällt, wird gezählt) und weckt den Worker **thread-sicher**. Keine langsamen Aufrufe, keine GUI.
- Datenbankarbeit läuft in `asyncio.to_thread`, strikt in Reihenfolge je Gerät; der Agent ist der
  einzige reguläre Schreiber; die GUI liest/schreibt nur über die API.
- Manueller Stopp beendet auch Reconnect. Shutdown: API → Tracker (Verbindung trennen, abschließende
  Ereignisse) → Loop → Threads.
- Die API erreicht die BLE-Seite nur über `AgentControl` (`run_coroutine_threadsafe`).
- Streamlit führt das Skript bei jeder Interaktion neu aus; es enthält keine Endlosschleifen und keine
  BLE-Arbeit. Zustand liegt in `st.session_state`; Schließen/Neuladen beendet die Erfassung nicht.

## Sicherheit (Kurzfassung)

Loopback-API, Bearer-Token (nie in URLs), Host-/Origin-Prüfung gegen CSRF/DNS-Rebinding, Token und
Adressen im Log maskiert, kein Zustandswechsel über GET, strikte Request-Modelle, atomare Dateien,
validierter Restore, **keine BLE-Schreiboperationen**. Details: [SOFTWAREDOKUMENTATION.md](SOFTWAREDOKUMENTATION.md)
§18–19 und [SECURITY.md](../SECURITY.md).

## Gründe

Bleak benötigt zusammengehörige Operationen in einem laufenden Loop:
https://bleak.readthedocs.io/en/latest/troubleshooting.html

Streamlit-Interaktionen lösen Reruns aus und Hardware liegt beim Pythonhost:
https://docs.streamlit.io/develop/concepts/architecture/architecture
