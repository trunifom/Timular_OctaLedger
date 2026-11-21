# Mitarbeit

Verbindlich für Menschen **und** LLM-Agenten sind die Regeln in [CLAUDE.md](CLAUDE.md); hier die Kurzfassung.

- Pythoncode, Bezeichner, Kommentare, Docstrings und Logmeldungen auf **Englisch**; Benutzerdokumentation
  und GUI-Texte auf **Deutsch**. Kommentare erklären das *Warum*; jedes Modul hat einen Modul-Docstring.
- Kleine, nachvollziehbare Änderungen **mit Tests, Fehlerbehandlung (stabile Fehlercodes), Logging und
  Dokumentation**; ein Arbeitspaket pro Commit mit ausführlicher Beschreibung; Fortschritt in
  `docs/FORTSCHRITT.md` nachtragen.
- Schichten einhalten (`domain` kennt kein BLE/HTTP/SQL/Streamlit; SQL nur im Storage-Paket; Dashboard nur
  über die API). BLE: **nur lesen und abonnieren**, nie schreiben.

## Qualitäts-Gate (alles muss bestehen)

```bat
scripts\run_tests.bat
rem entspricht:
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy
```

Die GUI-Tests brauchen einige Minuten (jeder `AppTest`-Lauf führt eine echte Seite aus). Hardwaretests
laufen nur mit `OCTALEDGER_HARDWARE_TESTS=1` und nie in der CI.

## Erweitern – kurze Anleitungen

- **Neuer Fehlercode:** Klasse in `core/errors.py` (Code eindeutig, Format `OL-XXX-NNN`), Tabelle in
  SOFTWAREDOKUMENTATION §2.2 und Benutzerhandbuch §18 ergänzen, HTTP-Status in `api/app.py` zuordnen.
- **Neue Migration:** `NNNN_name.sql` (lückenlos, kein BEGIN/COMMIT, angewendete Dateien **nie** ändern),
  Test, Doku §9; die Tests leiten die erwartete Version aus den Paketdateien ab.
- **Neuer Endpunkt:** Service-Methode + Test, Request-Modell (`extra="forbid"`), Route (nur `GET` für
  Lesendes), Client-Methode, Eintrag in [docs/API.md](docs/API.md) (**ein Test schlägt fehl, wenn er fehlt**) und in
  SOFTWAREDOKUMENTATION §19/§20.
- **Neue Dashboard-Seite:** Modul in `dashboard/views/` mit `render(client, tz)`, Eintrag in `PAGES`,
  `page_help` + `help=` an **jedem** Feld, Texte HTML-escapen, `AppTest`-Tests; Seite im Benutzerhandbuch beschreiben.
- **Neue Art von Verbindung (Adapter):** eine Datei in `infrastructure/integrations/` + eine Zeile in `registry.py`; Oberfläche,
  API und Datenbank bleiben unverändert. Anleitung mit Beispiel und Checkliste: [docs/ADAPTER_ENTWICKLUNG.md](docs/ADAPTER_ENTWICKLUNG.md).

## Dokumentation gehört zur Änderung

Eine Änderung ist erst fertig, wenn ihre Dokumentation stimmt – **im selben Commit**. Wegweiser: [docs/README.md](docs/README.md).

| Änderung | Mindestens aktualisieren |
|---|---|
| Verhalten, das Anwender sehen | Benutzerhandbuch (und ggf. Startseite/Seitenhilfe), Glossar bei neuen Begriffen |
| Endpunkt | `docs/API.md`, SOFTWAREDOKUMENTATION §19/§20 |
| Tabelle/Spalte | Migration, `docs/DATENMODELL.md`, Sicherungsformat falls betroffen |
| Baustein, Thread, Datenfluss | `docs/ARCHITEKTUR.md` |
| Sicherheitsrelevantes | `SECURITY.md` |
| neue Datei | `docs/ORDNERSTRUKTUR.md` (Liste erzeugen: `python scripts/update_ordnerstruktur.py`) |
| Arbeitspaket | `docs/FORTSCHRITT.md` (mit Commit-Hash im **nächsten** Commit), `CHANGELOG.md`, Testzahlen in `docs/TESTPLAN.md` |

Der Test `tests/unit/test_documentation.py` erzwingt das Mechanische: Docstring an **jedem** Modul, jeder Klasse und jeder Funktion; jeder Endpunkt in `docs/API.md`; jede
Datei in `docs/ORDNERSTRUKTUR.md`; keine toten Verweise zwischen den Markdown-Dateien. Beim Schreiben von Docstrings: Zweck und **Warum** zuerst, Grenzen ehrlich benennen, Fehler (`Raises:`) nennen.

## Daten und Geheimnisse

Keine echten Arbeitszeitdaten, Geräteadressen oder Geheimnisse als Testfixtures committen. Eine Änderung an
Zeitsemantik oder Datenformat benötigt Dokumentation und Migrationstest. Kein `git push` durch Agenten.
