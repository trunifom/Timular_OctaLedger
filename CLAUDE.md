# CLAUDE.md – Arbeitsanweisungen für LLM-Agenten (OctaLedger)

Diese Datei ist die **verbindliche Projektanweisung** für jeden LLM-Agenten und jede
Chat-Session (Claude Code, Codex, Copilot usw.). `AGENTS.md` verweist hierher.
Lies zuerst diese Datei, danach `docs/FORTSCHRITT.md` (Stand der Arbeit) und
`docs/PFLICHTENHEFT.md` (Soll-Anforderungen).

## 1. Projekt in einem Satz

OctaLedger ist eine lokale (local-first) Zeiterfassung für Timeular-/ZEI-Würfel per
Bluetooth LE unter Windows: Agent (Bleak) → SQLite → lokale Token-API (FastAPI) →
Streamlit-Dashboard. Unabhängig von Timeular/EARLY.

## 2. Arbeitsweise (Pflicht)

1. **Teile einzeln, der Reihe nach.** Ein Feature/Modul pro Arbeitsschritt, nie mehrere
   unfertige Dinge gleichzeitig.
2. **Jeder Teil umfasst immer:** Implementierung, Unit-Tests, sauberes Errorhandling,
   Logging, englische Kommentare/Docstrings und Dokumentation (siehe Abschnitt 5).
3. **Qualitäts-Gate vor jedem Commit** (alle drei müssen grün sein):
   ```bat
   .venv\Scripts\python.exe -m pytest
   .venv\Scripts\python.exe -m ruff check .
   .venv\Scripts\python.exe -m mypy
   ```
4. **Jeder Teil wird einzeln committet** mit ausführlicher Message (Betreff im
   Conventional-Commits-Stil, Body: Was, Warum, Tests, Dokumentation, Grenzen).
5. **Fortschrittsprotokoll pflegen:** Nach jedem umgesetzten Feature `docs/FORTSCHRITT.md`
   aktualisieren (Datum, Uhrzeit, Commit-Hash). Da der Hash erst nach dem Commit bekannt
   ist, wird er im **nächsten** Commit nachgetragen (letzter Eintrag: eigener kleiner
   `docs:`-Commit).
6. **Git:** `git add` und `git commit` sind erlaubt. **Niemals `git push`** – der Nutzer
   pusht selbst. Keine Secrets, keine echten Zeitdaten, keine Datenbanken committen.
7. **Lizenz ist offen:** Vor einer Veröffentlichung den Nutzer an die fehlende LICENSE
   erinnern. Keine Lizenz erfinden.
8. **Ehrlichkeit:** Nichts als „getestet" oder „hardwarevalidiert" ausgeben, was nicht
   ausgeführt wurde. BLE-Hardware ist nicht verifiziert; das Protokoll stammt aus
   Community-Referenzen. Status in README/FORTSCHRITT immer wahrheitsgemäß halten.

## 3. Code-Richtlinien

- Python ≥ 3.12, src-Layout, `mypy --strict`, `ruff` (E, F, I, B, UP, BLE, T20, C4, PIE, SIM, S, RUF100;
  Ausnahmen stehen in `pyproject.toml`, jedes `noqa` braucht eine Begründung), Zeilenlänge 100.
- **Code, Bezeichner, Kommentare, Docstrings, Logmeldungen: Englisch.**
  Benutzerdokumentation und GUI-Texte: Deutsch.
- **Kommentare umfassend und detailliert:** jedes Modul mit Modul-Docstring (Zweck,
  Verantwortung, Grenzen), jede öffentliche Klasse/Funktion mit Docstring (Args, Returns,
  Raises), nicht offensichtliche Logik mit erklärenden Inline-Kommentaren (das *Warum*).
- Schichten strikt einhalten (siehe `docs/ARCHITEKTUR.md`): `domain` kennt weder BLE,
  HTTP, SQL noch Streamlit. Abhängigkeiten zeigen nur nach innen.
- Immutable Datenmodelle (`@dataclass(frozen=True, slots=True)`), Typannotationen überall,
  keine Wildcard-Imports, keine globalen veränderlichen Zustände, kein `print` in
  Bibliothekscode (nur Logging), keine nackten `except:`.
- Zeit: intern immer UTC mit Zeitzone (`datetime` timezone-aware); Anzeige in gewählter
  IANA-Zeitzone. Keine naiven Datetimes.
- SQL nur in `infrastructure/storage`, immer parametrisiert (nie String-Formatierung).
- Keine BLE-Schreiboperationen auf unbekannte Characteristics. Kein UI-Aufruf im
  BLE-Callback. Keine Endlosschleifen im Streamlit-Skript.

## 4. Errorhandling und Logging

- Eigene Ausnahmehierarchie in `octaledger.core.errors`; jede Ausnahme besitzt einen
  **stabilen Fehlercode** (z. B. `OL-STORAGE-001`) und eine benutzerverständliche Meldung.
- Fremdfehler (sqlite3, OSError, Bleak, JSON) an der Systemgrenze abfangen, in eigene
  Ausnahmen übersetzen (`raise ... from exc`), Ursache nie verschlucken.
- Logging ausschließlich über `logging.getLogger(__name__)`; Konfiguration zentral in
  `octaledger.core.logging`. Stufen: DEBUG (Programmschritte), INFO (Zustandswechsel),
  WARNING (tolerierte Abweichung), ERROR (Fehlschlag), CRITICAL (Prozess nicht nutzbar).
- Logs enthalten **nie** Tokens, Passwörter oder vollständige Geräteadressen
  (Redaktion zentral im Logging-Filter).

## 5. Dokumentationspflicht (immer mitliefern)

| Zielgruppe | Datei | Inhalt |
|---|---|---|
| Endanwender | `docs/BENUTZERHANDBUCH.md` | Bedienung, Begriffe, Abläufe, Fehlerhilfe |
| Entwickler | `docs/SOFTWAREDOKUMENTATION.md` + `docs/ARCHITEKTUR.md` | Module, Schnittstellen, Datenfluss, Entscheidungen |
| Schnittstelle | `docs/API.md` | jeder Endpunkt (ein Test erzwingt Vollständigkeit) |
| Daten | `docs/DATENMODELL.md` | Dateien, Tabellen, Regeln, Sicherungsformat |
| Erweiterung | `docs/ADAPTER_ENTWICKLUNG.md` | neue Art von Verbindung hinzufügen |
| Begriffe, Übersicht | `docs/GLOSSAR.md`, `docs/README.md` | Fachbegriffe, Wegweiser durch alle Dokumente |
| Planung | `docs/PFLICHTENHEFT.md` §12 + `docs/UMSETZUNGSPLAN.md` | geplante Erweiterungen F-21 bis F-63, Pakete AP-35 bis AP-50 der Reihe nach |
| Betrieb | `docs/INSTALLATION.md` | Installation, Start, Konfiguration, Backup, Fehlersuche |
| Prozess | `docs/FORTSCHRITT.md` | Erledigt/offen mit Datum, Uhrzeit, Commit |

Jedes neue Feature aktualisiert die betroffenen Dateien im selben Arbeitsschritt.

## 6. GUI-/UX-Richtlinien (Streamlit)

- Klar, logisch, übersichtlich: eine Seite pro Aufgabe, Navigation in der Seitenleiste,
  konsistente Begriffe, keine Überladung.
- **Jedes** Eingabe-/Ausgabefeld, jede Funktion und jeder Bereich hat einen Hilfetext
  (`help=`-Parameter, Info-Expander oder „ℹ️"-Popover) in verständlichem Deutsch.
- **Pflicht-Bedienelemente:** Hell-/Dunkel-Umschalter und Schriftgrößen-Umschalter
  (zwei Stufen: normal/groß). Einstellungen bleiben in der Session erhalten.
- Fehler dem Nutzer verständlich zeigen (inkl. Fehlercode), nie Stacktraces.
- Leere Zustände erklären, was zu tun ist. Keine erfundenen Daten anzeigen.

## 7. Daten: Speichern, Laden, Import, Export

- Nutzerdaten im Benutzerprofil (platformdirs), nie im Repository.
- Schreibvorgänge transaktional; Dateiexporte atomar (temporäre Datei + `os.replace`).
- Jedes Dateiformat ist versioniert (`schema_version`) und wird beim Laden validiert.
- Import/Restore: erst vollständig validieren, dann in **einer** Transaktion anwenden;
  vor Restore automatisches Backup. Keine Pfade/Befehle aus Importdateien ausführen.
- CSV: UTF-8 mit BOM (Excel), Formel-Injection neutralisieren (`=`, `+`, `-`, `@`).

## 8. Stand der Architektur und des Projekts (Kurzfassung)

Schichten: `domain` → `application` → `infrastructure` / `api` / `agent`; `dashboard` spricht nur über
`dashboard_client` mit der API. Der Agent ist der einzige reguläre DB-Schreiber. **Ein** AsyncIO-Loop
(eigener Thread) besitzt alle BLE-Clients. Details: `docs/ARCHITEKTUR.md`.

**Arbeitsstand (siehe `docs/FORTSCHRITT.md`):** Alle Arbeitspakete AP-00 bis AP-32c sind umgesetzt (AP-22 bis AP-25: Live-Daten, Seite „Würfel live“, Assistent „Seiten zuordnen“, Startseite mit geführter Einrichtung und Handbuch; AP-26 bis AP-31: Steuerungsmodus mit Adapter-Baukasten, Warteschlange, Webhook, MQTT, Home Assistant, Hue und Oberfläche, siehe `docs/SOFTWAREDOKUMENTATION.md` §31; AP-32: umfassende Dokumentation und Wächtertests, §32). **Offen
und nicht von Agenten lösbar:** Hardwaretest mit echten Trackern (Anleitung: `docs/INSTALLATION.md` §5,
Matrix in `docs/TESTPLAN.md`), Lizenzwahl (**den Nutzer daran erinnern, bevor veröffentlicht wird**),
Namens-/Markenprüfung, privater Sicherheits-Meldeweg, F-20 (Integrationen, „Kann“).

**Gelernte Regeln für weitere Arbeit:**

- Qualitäts-Gate ist `scripts\run_tests.bat` (pytest, ruff check, **ruff format --check**, mypy strict);
  die GUI-Tests dauern einige Minuten. Nach `ruff format` erneut prüfen.
- BLE-/Bleak-Callbacks dürfen **nicht** annehmen, auf dem Loop-Thread zu laufen: Events nur über
  `DeviceWorker._set` (thread-sicher) setzen.
- GUI-Konzept und Design-System: `docs/GUI_KONZEPT.md`. Seiten werden als `PageDef` in `dashboard/views/__init__.py`
  registriert (Gruppe, Icon, Tooltip); das Menü besteht aus Buttons `nav_<slug>`; **Seitentitel = Menütext**;
  Begriff „Eintrag“ statt „Sitzung"; Schrift/Farben nur über `dashboard/theme.py`, keine externen CDNs.
- Streamlit: `width="stretch"` statt `use_container_width`; Benutzertexte in `unsafe_allow_html`-Blöcken
  mit `html.escape`; Widget-`key=` eindeutig vergeben (Tests nutzen sie); `help=` an jedem Feld.
- Seitenfehler im Dashboard fängt `main.run` (Meldung mit Code, Traceback nur im Log); nicht abgefangene
  Ausnahmen aller Threads landen über `install_exception_hooks` im Log.
- Fehler an Systemgrenzen in `OctaLedgerError`-Unterklassen übersetzen; neue Fehlerklasse = neuer stabiler
  Code + Doku + HTTP-Status in `api/app.py`.
- Tests neuer Seiten: Fixture `api_server` aus `tests/conftest.py` + `AppTest`; Beispieldaten nicht in der
  Zukunft anlegen (siehe `tests/gui/test_gui_journal_statistics.py`).
- Dokumentation immer im selben Arbeitsschritt aktualisieren; ehrlich bleiben (nichts als hardwaregeprüft
  ausgeben, was nur simuliert ist).
- Niemals `git push`; die Hash-Nachtragsregel für `docs/FORTSCHRITT.md` beachten.
