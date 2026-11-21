# Quellen und Grenzen

## Grundlagen

- Bleak / Loop und Windows: https://bleak.readthedocs.io/en/latest/troubleshooting.html
- Streamlit Host/Client: https://docs.streamlit.io/develop/concepts/architecture/architecture
- Python src-Layout: https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
- Community-Protokollreferenz: https://github.com/unixfg/triangles
- WCAG 2.x Kontrast (Berechnung): https://www.w3.org/TR/WCAG21/#contrast-minimum
- Farbpalette (farbenblind-freundlich): Okabe & Ito

## Was geprüft wurde

- **Alle automatischen Tests** (1381 Tests, davon 4 übersprungen: 2 Hardwaretests, 2 plattform- bzw. seitenbedingt), `ruff check`,
  `ruff format --check` und `mypy --strict` auf **Windows 11 (10.0.26300), Python 3.12.3**, mit den
  Versionen aus `constraints-tested.txt` (u. a. Bleak 3.1.0, Streamlit 1.67.0, FastAPI 0.165.0).
- Die komplette Kette Tracker-**Simulator** → Agent → Datenbank → API → Dashboard-Client sowie jede
  Dashboard-Seite mit `AppTest` gegen den echten API-Server.
- Im Repository liegen keine Datenbanken, Logs, Tokens oder `.env`-Dateien (außer der leeren
  `.env.example`).

- **Aussehen im Browser:** Für die Bilder in `docs/images/` und die Sichtprüfung wurden die Seiten mit Playwright (Chromium) gegen eine
  Vorschau mit Simulator und Beispieldaten aufgenommen. Das zeigt das Rendering in **einem** Browser bei 1280 Pixeln Breite, ersetzt aber keinen Test auf kleinen
  Bildschirmen oder in anderen Browsern.

## Optionale Zusatzpakete und Lizenzen

| Paket | Zweck | Lizenz | Hinweis |
|---|---|---|---|
| `pystray` | Tray-Symbol (Extra `tray`) | LGPL-3.0 (belegt) | nur optional und dynamisch geladen; seit 2023 wenig gepflegt (Wartungsrisiko); bei einer gebündelten Auslieferung LGPL-Hinweise beilegen |
| `pillow` | Symbolbild für das Tray | HPND (PIL-Lizenz) | kommt ohnehin mit Streamlit |
| `holidays` | gesetzliche Feiertage offline (Extra `holidays`) | MIT (belegt) | Regionen/Unterteilungen und halbe Feiertage je Betrieb prüfen; eigene Abwesenheiten überschreiben die Liste |
| `winotify` | Windows-Hinweise (Extra `toast`) | MIT (belegt) | ohne eigene AppUserModelID erscheint ggf. ein Interpreter-Name als Absender [U] |

## Pausenregeln (nur Orientierung)

Die Tabellen in `domain/break_rules.py` stammen aus **Sekundärquellen** (ch.ch, WEKA, SECO-Wegleitung zum Arbeitsgesetz Art. 15; EU-Richtlinie 2003/88/EG Art. 4 in EUR-Lex) mit Stand 2026-11. Der **Wortlaut der Primärquellen** (fedlex.admin.ch, SR 822.11 und SR 822.111) wurde **nicht** von einem Menschen gegengeprüft. Das Gesetz gilt nur für bestimmte Betriebe und Personen; bei flexiblen Arbeitszeitsystemen gelten Besonderheiten. OctaLedger gibt keine Rechtsberatung und zieht nie automatisch Pausen ab.

## Was **nicht** geprüft wurde (Grenzen)

- **Keine echte BLE-Hardware:** Weder Scan noch Verbindung, Benachrichtigungen, Reconnect, Reichweite,
  Aufwecken, Adapter-/Treiberverhalten noch zwei parallele Verbindungen wurden mit echten Timeular-/ZEI-
  Trackern ausprobiert. Die Bleak-Schicht ist nur mit Stubs getestet.
- **Protokoll nicht hardwarevalidiert:** UUIDs und das Ein-Byte-Format (1–8, 0 neutral) stammen aus
  Community-Referenzen; Kompatibilität ist pro Exemplar und Firmware zu prüfen. Die Neutralwert-Pausenregel
  ist deshalb als experimentell gekennzeichnet und standardmäßig aus.
- **Kein visueller Browsertest:** `AppTest` prüft Elemente und Logik, nicht das tatsächliche Aussehen
  (Layout, Farben im Rendering, Verhalten auf kleinen Bildschirmen). Ein manueller Blick durch alle
  Seiten im Browser ist nötig.
- **Keine Leistungs- oder Batteriezahlen:** Latenz, CPU, Speicher und Langzeitstabilität sind nicht
  gemessen und werden nicht behauptet.
- **Keine rechtliche Prüfung:** Betriebliche/arbeitsrechtliche Konformität der Zeiterfassung ist separat
  zu prüfen; OctaLedger macht dazu keine Zusage.
- **Offene Entscheidungen:** Lizenz, Namens-/Markenfreiheit (nicht geprüft), privater Sicherheits-
  Meldeweg, Verpackung/Installer, Windows-Autostart.
- **Nur Windows 11 / Python 3.12** wurde getestet; andere Systeme sind nicht Ziel dieses Stands.
- Streamlit meldet in der verwendeten Version Änderungen an einzelnen APIs; die bekannten (z. B.
  `use_container_width`) wurden angepasst, zukünftige Versionen können weitere erfordern
  (`constraints-tested.txt` hält den getesteten Stand fest).
- **Anbindungen für den Steuerungsmodus (Webhook, MQTT, Home Assistant, Hue):** Sie sind nur gegen **lokale
  Testziele** geprüft (ein echter lokaler HTTP-Server, Attrappen), **nicht** gegen echte Geräte, Hubs oder
  Broker. Wie sich Ihr Ziel tatsächlich verhält (Zeitlimits, Zertifikate, Fehlermeldungen, Firmware-Besonderheiten),
  zeigt erst der Versuch mit **„Verbindung testen“** und **„Jetzt ausprobieren“**.
- **Matter und Google Home:** OctaLedger spricht **kein Matter und kein Google Home direkt**. Beide erreichen Sie
  **über Home Assistant** (falls Sie Ihre Geräte dort eingebunden haben). Eine eigene Matter-Unterstützung ist nicht
  vorhanden und nicht zugesagt (Pflichtenheft §2).
- **Zugangsdaten der Verbindungen** liegen im Benutzerprofil in `secrets.json`, **unverschlüsselt** (wie das
  API-Token), und werden nie gesichert. Wer Ihr Benutzerprofil lesen kann, kann sie lesen.
- **Philips Hue: Zertifikat der Bridge.** Die Bridge nutzt ein Zertifikat einer eigenen Zertifizierungsstelle, das ein
  normaler Check nicht prüfen kann. OctaLedger merkt sich deshalb beim Koppeln den **SHA-256-Fingerabdruck** des
  Bridge-Zertifikats („Vertrauen beim ersten Mal“) und spricht später nur noch mit genau diesem Zertifikat. Das Vertrauen
  entsteht also einmal im Heimnetz beim Koppeln (wie das Drücken des echten Knopfes). Die Anheftung selbst wurde **nicht mit
  einem echten TLS-Handshake oder einer echten Bridge** getestet, nur an ihren Nahtstellen (Fingerabdruck, Konfiguration der
  Verbindung, Verweigerung ohne Fingerabdruck).
