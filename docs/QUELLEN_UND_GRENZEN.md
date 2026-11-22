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
| `fpdf2` | PDF-Bericht (Extra `pdf`) | **LGPL-3.0-only** (aus den Paket-Metadaten der installierten Version 2.9.0; die frühere Planung nannte fälschlich BSD-2) | nur optional und dynamisch geladen; Standardschriften (Latin-1): Anführungszeichen, Gedankenstriche und „€“ werden ersetzt, andere Zeichen erscheinen als „?“ |
| `icalendar` | Kalender-Import (Extra `ics`) | BSD-2-Clause | – |
| `recurring-ical-events` | Terminserien im Fenster (Extra `ics`) | **LGPL-3.0-or-later** | nur optional und dynamisch geladen |
| `zeroconf` | Bridge-Suche im Heimnetz per mDNS (Extra `discovery`) | LGPL-2.1-or-later (Paket-Metadaten der Version 0.154.0) | nur optional und dynamisch geladen; manche Router blockieren Multicast, dann die Adresse von Hand eintragen |
| `miniaudio` | lokaler Player (Extra `audio`) | MIT (Paket-Metadaten der Version 1.73) | MP3, FLAC, WAV, Vorbis; alles andere nur über das optionale **FFmpeg** (AAC/M4A, WMA, Opus, Video-Ton; FFmpeg ist ein eigenes Programm mit eigener Lizenz, OctaLedger bündelt es nicht und startet es nur als Kindprozess); Streams werden von OctaLedger selbst geöffnet und der Engine als Bytes übergeben; ein Wiedergabetest mit echter Hardware steht aus |
| `winotify` | Windows-Hinweise (Extra `toast`) | MIT (belegt) | ohne eigene AppUserModelID erscheint ggf. ein Interpreter-Name als Absender [U] |

## Pausenregeln (nur Orientierung)

Die Tabellen in `domain/break_rules.py` stammen aus **Sekundärquellen** (ch.ch, WEKA, SECO-Wegleitung zum Arbeitsgesetz Art. 15; EU-Richtlinie 2003/88/EG Art. 4 in EUR-Lex) mit Stand 2026-11. Der **Wortlaut der Primärquellen** (fedlex.admin.ch, SR 822.11 und SR 822.111) wurde **nicht** von einem Menschen gegengeprüft. Das Gesetz gilt nur für bestimmte Betriebe und Personen; bei flexiblen Arbeitszeitsystemen gelten Besonderheiten. OctaLedger gibt keine Rechtsberatung und zieht nie automatisch Pausen ab.

## Hue-Erweiterungen (AP-43): Stand der Prüfung

Die JSON-Formen für Helligkeit, Farbtemperatur (`color_temperature.mirek`), Übergang (`dynamics.duration`) und Szenen-Aufruf (`recall.action` `active`/`dynamic_palette`/`static`, `dimming`, `duration`) stammen aus Drittquellen; die offizielle Dokumentation liegt hinter einem Entwicklerlogin und wurde **nicht** gelesen. Getestet ist gegen eine lokale Attrappe der Bridge (gesendete Bodies, Umschalten liest zuerst den Zustand, Mindestabstand, HTTP 429). **An einer echten Bridge ist nichts davon geprüft.** Die Cloud-Suche (`discovery.meethue.com`) wurde ebenfalls nur mit einer Attrappe getestet.

## Medien (AP-45): Stand der Prüfung

Die Dienste von Home Assistant (`media_player.play_media`, `media_pause`, `media_stop`, `volume_set`) und ihre Felder stammen aus der öffentlichen Dokumentation bzw. Drittquellen und wurden nur gegen eine Attrappe getestet. Der lokale Player ist gegen eine Attrappen-Engine getestet (Reihenfolge, Ersetzen, Fehler, Warteschlange, Adress- und Ordnerregeln); **tatsächliche Wiedergabe** (MP3-Stream, lokale Datei, Lautstärke) ist nicht an echter Hardware geprüft. Nicht gebaut: der „externe Player“ (VLC/mpv als Unterprozess) als zweite Stufe.

## Spotify direkt (AP-49): Stand der Prüfung

Die Endpunkte (`/authorize` und `/api/token` mit PKCE, `/v1/me/player/play|pause|volume`), die Berechtigungen (`user-modify-playback-state`, `user-read-playback-state`) und die Fehlerbedeutungen (403 = Premium nötig, 404 = kein aktives Gerät, 429 = langsamer) stammen aus der öffentlichen Spotify-Dokumentation und wurden nur gegen eine lokale Attrappe getestet; die PKCE-Prüfsumme gegen das Beispiel aus RFC 7636. **Nicht geprüft:** Anmeldung und Wiedergabe mit einem echten Premium-Konto und einer echten App-Registrierung, das Verhalten bei einem vom Spotify rotierten Refresh-Token (OctaLedger behält den gespeicherten; bei „Zugang abgelehnt“ erneut koppeln) und künftige Änderungen der Spotify-Regeln für Entwickler-Apps. Die dauerhafte Berechtigung liegt wie alle Geheimnisse **unverschlüsselt** in `secrets.json` im Benutzerprofil (Zugriff nur für Ihr Windows-Konto). Beachten Sie die Spotify-Entwicklerbedingungen.

## Player in der App (AP-50): Stand der Prüfung

Geprüft (automatisch): der Zustand des Adapters, die Form der YouTube-Kennungen (nur `[A-Za-z0-9_-]`, 11 bzw. 10–60 Zeichen), dass ein falscher Wert nie in die Seite gelangt, dass derselbe Zustand denselben Seitentext ergibt (der Browser behält den laufenden Player) und dass vor der Zustimmung nichts Externes geladen wird. **Nicht geprüft:** Verhalten der IFrame-Player-API (`YT.Player`, `setVolume`, `playVideo`, Fehlercodes 101/150), Autoplay-Regeln der Browser, ob Streamlit das Neuzeichnen ohne Unterbrechung der Wiedergabe erlaubt, und welche Videos einbettbar sind. Harte Grenze: **nur bei geöffneter Seite**. Datenschutz und Sicherheit: Der Player ist ein **eingebetteter Rahmen von `youtube-nocookie.com`** (fremde Herkunft); **es läuft kein fremdes Skript im Dashboard** (Lautstärke und Start gehen per `postMessage` an den Rahmen, das einzige Skript der Seite ist unser eigenes und enthält nur geprüfte Werte). Ob der Rahmen diese Befehle in Ihrem Browser annimmt (`enablejsapi=1`), ist **nicht geprüft**; ohne sie startet das Video trotzdem (Autoplay), nur die Lautstärke bliebe die des Videos.

## Bluetooth-Schnittstelle des Würfels (Recherche vom 2026-11-22)

Es wurde **keine offizielle Bluetooth-Dokumentation** des Herstellers gefunden; die Tabelle der Dienste und Characteristics steht in `docs/UMSETZUNGSPLAN.md` §20.2 und stammt aus Community-Quellen (`codingforfun/zeipy`, `maslovw/timeular-local`, `adn77/timeular`, `zntrio/timeular`, Blog von LeMaRiva), die sich teilweise **widersprechen** (Format des Beschleunigungssensors, Werte der Halterung, Dienst `c7e70030`). Einstellbare Werte (LED, Empfindlichkeit, Energiemodus) sind **nicht belegt**; ein Schreibzugriff auf unbekannte Characteristics findet nicht statt.

## Würfel auslesen (AP-56): Stand der Prüfung

Geprüft (mit einem Ersatz-Würfel im Speicher): dass nur lesbare Angaben gelesen werden, dass der Firmware-Update-Dienst und nicht lesbare Angaben nie angefasst werden, dass es auf der Verbindung **keine Schreibfunktion** gibt, die Deutung bekannter Werte, die Länge des Beschleunigungssensors, die Grenzen der Aufzeichnung (5–30 s, 0,2–2 s), Speichern, Löschen, Begrenzung auf 20 und die Sicherung. **Nicht geprüft:** das Auslesen an einem **echten Würfel** (welche Dienste er wirklich anbietet, ob das Lesen jeder Angabe gelingt), das tatsächliche Format der Beschleunigungs-Rohdaten und ob der Sensor überhaupt Bewegungsdaten liefert. Einstellbare Werte (LED, Empfindlichkeit, Energiemodus) sind **nicht umgesetzt**, weil keine Primärquelle vorliegt.

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
