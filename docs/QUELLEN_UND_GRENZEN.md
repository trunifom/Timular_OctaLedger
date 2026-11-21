# Quellen und Grenzen

## Grundlagen

- Bleak / Loop und Windows: https://bleak.readthedocs.io/en/latest/troubleshooting.html
- Streamlit Host/Client: https://docs.streamlit.io/develop/concepts/architecture/architecture
- Python src-Layout: https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
- Community-Protokollreferenz: https://github.com/unixfg/triangles
- WCAG 2.x Kontrast (Berechnung): https://www.w3.org/TR/WCAG21/#contrast-minimum
- Farbpalette (farbenblind-freundlich): Okabe & Ito

## Was geprüft wurde

- **Alle automatischen Tests** (900 bestanden, 2 Hardwaretests übersprungen), `ruff check`,
  `ruff format --check` und `mypy --strict` auf **Windows 11 (10.0.26300), Python 3.12.3**, mit den
  Versionen aus `constraints-tested.txt` (u. a. Bleak 3.1.0, Streamlit 1.67.0, FastAPI 0.165.0).
- Die komplette Kette Tracker-**Simulator** → Agent → Datenbank → API → Dashboard-Client sowie jede
  Dashboard-Seite mit `AppTest` gegen den echten API-Server.
- Im Repository liegen keine Datenbanken, Logs, Tokens oder `.env`-Dateien (außer der leeren
  `.env.example`).

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
