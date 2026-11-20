# GitHub-Titel, Beschreibung und Veröffentlichung

## Namensvorschlag

Anwendungsname: OctaLedger
Repository: octaledger
Titel: OctaLedger – Local Time Tracking for Timeular

Die Verfügbarkeit oder markenrechtliche Unbedenklichkeit wurde nicht geprüft.
Kein offizielles Timeular-/EARLY-Produkt.

## Beschreibung zum Kopieren

Local-first Python time tracker for Timeular/ZEI BLE cubes with a Streamlit dashboard, SQLite storage, session management, charts and exports. In development.

## Topics

python, time-tracking, timeular, bluetooth-low-energy, bleak, streamlit,
sqlite, windows, local-first

## Erst lokal testen

Siehe README. Vor erstem Commit Lizenz bewusst auswählen. Keine echte .env,
Datenbank, Logs oder Tokens committen. pyproject.toml enthält absichtlich keine
unbegründete Lizenzangabe oder erfundene Autorenidentität.

## Git-Befehle: nur lokale Repositoryvorbereitung

```bat
git init -b main
git add .
git status
git commit -m "chore: scaffold OctaLedger architecture and requirements"
```

Benutzername/Email bei Bedarf selbst konfigurieren. Leere Ordner werden von Git
nicht erfasst; .gitkeep dient nur der geplanten Ordnerstruktur.

## Danach auf GitHub

Über die GitHub-Oberfläche ein leeres Repository mit gewähltem Namen anlegen.
Bei bereits vorhandenem lokalen README nicht zusätzlich remote initialisieren.
Die von GitHub angezeigte echte Remote-URL übernehmen; hier wird kein Konto geraten.

```bat
git remote add origin ECHTE_REMOTE_URL
git push -u origin main
```

Alternativ GitHub CLI nach Anmeldung verwenden. Das Paket führt keine Git-, Push-
oder GitHub-Erstellungsbefehle automatisch aus. Public/Private bewusst entscheiden.
