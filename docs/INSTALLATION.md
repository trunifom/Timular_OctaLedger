# Installation und Ausführung

Diese Anleitung führt von einem leeren Windows-Rechner bis zur laufenden Zeiterfassung. Bedienung:
[BENUTZERHANDBUCH.md](BENUTZERHANDBUCH.md).

> **Stand:** Die Software ist vollständig und getestet (Windows 11, Python 3.12). Das Verhalten mit
> **echten Trackern** wurde noch nicht geprüft – siehe Abschnitt 5 und [TESTPLAN.md](TESTPLAN.md).

## 1. Voraussetzungen

| Komponente | Anforderung |
|---|---|
| Betriebssystem | Windows 11 (erstes Testziel) |
| Python | 3.12 oder neuer (`py -3.12 --version`) |
| Bluetooth | Bluetooth-LE-Adapter mit funktionierendem Treiber, Bluetooth in Windows **eingeschaltet** |
| Browser | aktueller Browser (Dashboard) |
| Internet | nur für Installation und Updates; die Erfassung läuft offline |
| Tracker | Timeular-/ZEI-kompatibler Würfel, geladen; **nicht gleichzeitig mit der Hersteller-App verbunden** |

## 2. Installation

Im Projektordner in einer Eingabeaufforderung (`cmd`) oder PowerShell:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Reproduzierbar mit den zuletzt **getesteten** Versionen (empfohlen):

```bat
.venv\Scripts\python.exe -m pip install -e ".[dev]" -c constraints-tested.txt
```

Prüfen:

```bat
.venv\Scripts\python.exe -m octaledger --version
.venv\Scripts\python.exe -m octaledger paths
```

`paths` zeigt, wo Ihre Daten liegen (Abschnitt 4). Es wird noch nichts angelegt.

## 3. Starten

| Aktion | Befehl |
|---|---|
| Agent **und** Dashboard | `scripts\start_all.bat` |
| Nur der Agent (Hintergrunderfassung) | `scripts\start_agent.bat` bzw. `.venv\Scripts\python.exe -m octaledger agent` |
| Nur das Dashboard | `scripts\start_dashboard.bat` bzw. `... -m octaledger dashboard` → `http://127.0.0.1:8501` |
| Status prüfen | `.venv\Scripts\python.exe -m octaledger status` |
| Beenden | im Agent-Fenster **Strg+C** (der Tracker wird sauber getrennt) |

- **Der Agent erfasst, das Dashboard zeigt an.** Das Dashboard darf jederzeit geschlossen werden.
- Beim **ersten Start** legt der Agent Datenordner, Datenbank, Einstellungen und das API-Token an.
- Das Dashboard bindet nur an `127.0.0.1` und sendet **keine Telemetrie** (`.streamlit/config.toml`).
- Mit dem **aktiven Tracker** und mit **jedem Würfel im Steuerungsmodus** verbindet der Agent automatisch,
  sobald eine Bluetooth-Adresse gespeichert ist.
- Ports: die API des Agenten hört auf `127.0.0.1:8765`, das Dashboard auf `127.0.0.1:8501`. Beide sind **nur von diesem
  Rechner** erreichbar; es ist **keine Firewall-Freigabe** nötig (und keine sinnvoll).

## 4. Datenablage und Konfiguration

Nutzerdaten liegen **nicht** im Projektordner. Rangfolge für das Wurzelverzeichnis:

1. Befehlszeilenargument `--data-dir`,
2. Umgebungsvariable `OCTALEDGER_DATA_DIR`,
3. Benutzerprofil: unter Windows `%LOCALAPPDATA%\OctaLedger`.

```text
settings.toml   api_token   secrets.json   data\octaledger.sqlite3   logs\octaledger.log   backups\   exports\
```

| Datei/Ordner | Inhalt |
|---|---|
| `settings.toml` | Einstellungen (Vorlage: `config\settings.example.toml`); fehlt sie, gelten Standardwerte |
| `api_token` | geheimes API-Token (256 Bit), vom Agenten erzeugt |
| `secrets.json` | Zugangsdaten Ihrer Verbindungen im Steuerungsmodus (Passwörter, Tokens). **Nicht verschlüsselt**, nur im Benutzerprofil, **nie** in Sicherungen, Exporten, Diagnosebericht oder Protokoll. Beschädigt? Datei löschen und die Zugangsdaten neu eingeben |
| `data\` | SQLite-Datenbank (zusätzliche `*-wal`/`*-shm`-Dateien sind normal, nicht einzeln löschen) |
| `logs\` | rotierende Logdatei (1 MB × 5), Geheimnisse sind maskiert |
| `backups\` | JSON-Sicherungen und automatische Kopien vor Migration/Restore |
| `exports\` | CSV-Exporte |

Überschreibungen per Umgebungsvariable:

| Variable | Wirkung |
|---|---|
| `OCTALEDGER_DATA_DIR` | Datenverzeichnis |
| `OCTALEDGER_HOST` | API-Adresse (nur `127.0.0.1`, `::1`, `localhost`) |
| `OCTALEDGER_PORT` | API-Port (1024–65535, Standard 8765) |
| `OCTALEDGER_API_TOKEN` | Token statt Token-Datei (mindestens 32 Zeichen); für Agent **und** Dashboard setzen |

Beispiel (PowerShell): `$env:OCTALEDGER_DATA_DIR = "D:\OctaLedgerDaten"`

**Token erneuern:** Agent beenden, Datei `api_token` löschen, Agent und Dashboard neu starten. Das Token
gehört nie ins Repository, in Screenshots oder Tickets (Logs maskieren es automatisch).

## 5. Bluetooth und Hardwaretest

0. Ein Würfel, der sich nicht finden lässt, ist meist nicht im **Kopplungsmodus**: Den Knopf am Würfel **lange gedrückt halten**, bis
   er **blau blinkt**, dann sofort suchen. Er darf nicht gleichzeitig mit dem Handy, der Hersteller-App oder den Windows-Bluetooth-
   Einstellungen verbunden sein. Der Würfel meldet sich in der Liste oft als „Timeular Tra…“ (die Startseite markiert solche Treffer).
1. Würfel laden und einmal drehen (weckt ihn). Hersteller-App schließen.
2. `.venv\Scripts\python.exe -m octaledger scan` listet Geräte in der Nähe (verbindet nichts).
3. Im Dashboard (Bereich **Geräte**): registrieren, suchen, Adresse speichern, **Verbinden**,
   Seiten zuordnen.
4. **Hardwaretests bewusst starten** (nur Suchen/Lesen/Abonnieren, kein Schreiben):

   ```bat
   set OCTALEDGER_HARDWARE_TESTS=1
   .venv\Scripts\python.exe -m pytest tests\hardware -s
   rem Adresse aus der Ausgabe übernehmen und den Verbindungstest starten:
   set OCTALEDGER_HARDWARE_ADDRESS=<Adresse>
   .venv\Scripts\python.exe -m pytest tests\hardware -s
   ```
5. Ergebnisse (Modell, Firmware, Windows, Adapter, Treiber, Python, Bleak, App-Version) in die
   Kompatibilitätsmatrix von [TESTPLAN.md](TESTPLAN.md) eintragen. **Erst danach** gelten die
   Abnahmekriterien mit Hardwarebezug (A-01, A-05) als geprüft.

## 5a. Netzwerk für den Steuerungsmodus

Der Steuerungsmodus sendet **von diesem Rechner aus** an Ihre Geräte; es gehen keine Verbindungen von außen herein.

| Anbindung | Ziel und Port (üblich) | Voraussetzung |
|---|---|---|
| Home Assistant | `http://<adresse>:8123` | Ein „langlebiges Zugriffstoken“ (Home Assistant → Profil, ganz unten) |
| Philips Hue | die Bridge im Heimnetz (HTTPS, Port 443) | Zugriff auf das Heimnetz; Koppeln durch Drücken des Knopfs an der Bridge |
| MQTT | `<broker>:1883` (ohne TLS) oder `:8883` (TLS) | Broker erreichbar; ggf. Benutzername/Passwort |
| Webhook | beliebige `http(s)`-Adresse | Ziel erreichbar |

* Der Rechner muss im **selben Netz** wie das Ziel sein (ein VPN oder ein Gastnetz kann es trennen).
* Ein **Proxy** der Umgebung wird **ignoriert**: Anfragen ins eigene Netz gehen bewusst direkt.
* Weiterleitungen (HTTP 301/302) werden **nicht befolgt**; tragen Sie die endgültige Adresse ein.
* Beim Einrichten helfen *Verbindung testen* und *Jetzt ausprobieren* (Seite **Verbindungen**). Sie prüfen Erreichbarkeit, Zugang und Wirkung.
* Die Zugangsdaten liegen in `secrets.json` (siehe Abschnitt 4), nicht in der Sicherung.

## 6. Sicherung und Wiederherstellung

```bat
.venv\Scripts\python.exe -m octaledger backup                         rem in den Ordner backups
.venv\Scripts\python.exe -m octaledger backup --output D:\Sicherung\octaledger.json
.venv\Scripts\python.exe -m octaledger restore D:\Sicherung\octaledger.json          rem nur Vorschau
.venv\Scripts\python.exe -m octaledger restore D:\Sicherung\octaledger.json --yes    rem ersetzt alles
```

- `backup` funktioniert auch bei laufendem Agent (konsistenter Schnappschuss).
- `restore` prüft die Datei **vollständig, ohne etwas zu ändern**, legt vor dem Ersetzen automatisch eine
  Kopie des aktuellen Stands an (`backups\octaledger-pre-restore-…`) und **verweigert**, solange der
  Agent läuft. Bei jedem Fehler bleibt alles unverändert.
- Dasselbe geht komfortabel im Dashboard (Bereich **Daten**). Eine Sicherung ist erst belastbar, wenn
  ein Restore einmal erfolgreich getestet wurde.
- Datenbank-Updates: Beim Start migriert OctaLedger die Datenbank selbstständig; vorher entsteht eine
  geprüfte Kopie in `backups\`. Eine Datenbank einer **neueren** Programmversion wird nie verändert.

## 7. Updates und Deinstallation

- **Update:** Projektordner aktualisieren, dann `pip install -e ".[dev]"` erneut ausführen; Agent neu
  starten (Datenbank wird mit Sicherung migriert).
- **Deinstallation:** `.venv` und Projektordner löschen. **Ihre Daten bleiben** im Datenordner (Abschnitt
  4) erhalten, bis Sie ihn selbst löschen.

## 8. Entwicklung und Qualitätsprüfung

```bat
scripts\run_tests.bat
```

führt aus: `pytest`, `ruff check .`, `ruff format --check .` und `mypy` (strict). Alle vier müssen
bestehen (dasselbe läuft in der CI, `.github\workflows\ci.yml`). Die GUI-Tests brauchen wenige Minuten,
weil jeder `AppTest`-Lauf eine echte Seite ausführt. Hardwaretests laufen **nie** automatisch.
Richtlinien: [CLAUDE.md](../CLAUDE.md), [CONTRIBUTING.md](../CONTRIBUTING.md).

## 9. Fehlersuche

| Symptom | Ursache / Abhilfe |
|---|---|
| Dashboard: „Der OctaLedger-Agent ist nicht erreichbar“ (`OL-API-002`) | Agent starten (`scripts\start_agent.bat`), dann „Neu laden“ |
| Dashboard: „Es gibt noch kein API-Token“ (`OL-CONFIG-001`) | Agent einmal starten – er erzeugt das Token |
| Agent: „Der Port 8765 ist bereits belegt“ | Agent läuft schon, oder anderer Port nötig (`settings.toml`/`OCTALEDGER_PORT`) |
| Anmeldung fehlgeschlagen (`OL-API-001`) | Agent und Dashboard nutzen unterschiedliche Tokens/Datenordner (`OCTALEDGER_DATA_DIR`, `OCTALEDGER_API_TOKEN` angleichen) |
| „Bluetooth-Suche fehlgeschlagen“ (`OL-BLE-002`) | Bluetooth einschalten, Adapter/Treiber prüfen |
| Suche findet den Würfel nicht | Würfel drehen (wecken), näher heran, Hersteller-App schließen |
| „Gerät wird nicht unterstützt“ (`OL-BLE-003`) | Das Gerät bietet den erwarteten Dienst nicht an; Dienstliste im Technikdetail für den Kompatibilitätsbericht verwenden |
| Einstellungen werden abgelehnt (`OL-CONFIG-001`) | Meldung nennt Abschnitt, Schlüssel und erlaubte Werte; `settings.toml` korrigieren oder löschen |
| Datenbank „von einer neueren Version“ (`OL-STORAGE-002`) | OctaLedger aktualisieren; die Datei wurde nicht verändert |
| Datenbank beschädigt (`OL-STORAGE-003`) | Dashboard → Diagnose → „Datenbank prüfen“; Sicherung wiederherstellen |
| `Zugriff verweigert` bei Cache-Ordnern in Tests | `-p no:cacheprovider` ist in `pyproject.toml` gesetzt |
| `ModuleNotFoundError: octaledger` | `pip install -e ".[dev]"` im aktiven venv |
| Verbindung: „Das Ziel ist nicht erreichbar“ (`OL-INTEG-002`) | Adresse/Port prüfen, Gerät eingeschaltet, gleiches Netz (Abschnitt 5a) |
| Verbindung: Zugang abgelehnt (`OL-INTEG-001`) | Token/Passwort in der Verbindung neu eintragen (Feld leer lassen = alten Wert behalten) |
| Licht reagiert nicht, Verlauf zeigt „erledigt“ | Die Aktion wurde angenommen: Gerät/Szene in der Aktion prüfen (*Geräte auflisten* verwenden) |
| Aktion „abgelaufen“ | Das Ziel war länger als 30 Sekunden nicht erreichbar; erneut drehen |
| Ausgabe enthält `[OL-…-nnn]` | stabiler Fehlercode, Bedeutung in [SOFTWAREDOKUMENTATION.md](SOFTWAREDOKUMENTATION.md) §2.2 |
