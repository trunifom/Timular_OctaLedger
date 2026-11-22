# BLE-Protokoll und Kompatibilitätsaufnahme

Bekannte Community-Referenz: https://github.com/unixfg/triangles

```text
Orientierungsdienst: c7e70010-c847-11e6-8175-8c89a55d403c
Characteristic:     c7e70012-c847-11e6-8175-8c89a55d403c
```

Referenzimplementierungen beschreiben ein Byte, 1–8 für Seiten, 0 neutral.
Laut README von `adn77/timeular` bedeuten **0 und 10** beide „Würfel liegt in der Basis“.
OctaLedger behandelt beide als neutral (Tabelle `BASE_VALUES` in `domain/orientation.py`,
eine einzige Stelle zum Anpassen). Jeder andere Wert (z. B. 9 oder 255) bleibt ein
`invalid`-Ereignis, dessen Meldung den **Rohwert** nennt (`raw=0x09`), damit man ihn am
echten Würfel auswerten kann. **Nicht hardwarebestätigt:** ob der eigene Würfel 0 oder 10
meldet, ist zu prüfen (Ergebnis hier eintragen).

**Beobachtung am echten Würfel (Protokoll vom 2026-11-22, ein Würfel, Windows):** Der Wert **0** kam als „neutral“ an und hat im Musik-Modus die Musik angehalten; **10 wurde nicht beobachtet**. Zusätzlich sendet der Würfel beim Rollen zwischen zwei Seiten gelegentlich die Einzelwerte **0x09, 0x0B und 0x0D** (insgesamt 54-mal in einer Sitzung, immer zwischen zwei Seitenwechseln). Ihre Bedeutung ist **unbekannt** (vermutlich Zwischenlagen); sie sind harmlos. Seit AP „Log-Auswertung“ wird je Verbindung **nur das erste Vorkommen jedes solchen Wertes** als `invalid`-Ereignis gespeichert, alle weiteren werden gezählt (Zusammenfassung im Protokoll beim Ende der Verbindung, z. B. `0x0D x11`). Pakete mit mehr oder weniger als einem Byte werden weiterhin jedes Mal gespeichert. Die Bestätigung von 0 stammt aus dem Protokoll; ob der Würfel dabei wirklich in der Halterung lag, hat noch niemand ausdrücklich bestätigt.

**Verbinden:** Standardmäßig sucht der Agent den Würfel vor dem Verbinden kurz (bis 8 s,
`[agent] scan_before_connect`, `scan_timeout_seconds` in `settings.toml`), weil Windows ein
gerade nicht werbendes Gerät sonst oft mit „Device … was not found“ ablehnt. Wirbt der Würfel
nicht, erscheint die Meldung „einmal drehen oder Knopf drücken“, und der bekannte
Wiederholungs-Rhythmus greift.
Diese Angaben sind kein universeller Hardwarebeweis. Eigene USB-C-Tracker und
Firmware prüfen. Der enthaltene Decoder validiert nur dieses erwartete Format.

Kalibrierung: jede Fläche oben halten, technische Nummer beobachten, Alias
zuordnen. Namen/Servicefilter dürfen Generationen nicht unbemerkt ausschließen.

Prüfen: Dienste, Read/Notify/Indicate, erste Meldung, Neutralwert, Aufwecken,
Batteriedienst optional, andere App gleichzeitig, Reichweite und Wiederverbindung.
Keine unbekannten Schreiboperationen. Keine Zusage von Rohbeschleunigung, Motor-
steuerung, Firmwareupdate oder Offlinebewegungshistorie.

Ausgangswert kann dieselbe Meldung wie das Abonnement liefern: Duplikate tolerieren.
Für zwei Clients Adapterressourcen und tatsächliche Parallelität praktisch testen.

## Auslesen des Würfels (AP-56)

Die Seite *Würfel-Datenblatt* **liest** jede Characteristic, die der verbundene Würfel mit dem Recht „read“ anbietet, und speichert den Rohwert (hex). **Es wird nie geschrieben**, und nicht lesbare Angaben (nur schreiben, nur Benachrichtigung) werden **nicht angefasst**. Der Firmware-Update-Dienst (`c7e70000`, Community-Angabe: „wechselt in den Lade-Modus“) wird **nie** gelesen oder beschrieben, auch wenn er etwas Lesbares anböte. Gedeutet werden nur Angaben, deren Bedeutung bekannt ist (Standard-Characteristics für Batterie, Geräteinformation, Sendeleistung; Lage und Taste des Würfels); der Beschleunigungssensor `c7e70011` erscheint nur mit seiner **Länge**, weil sich die Quellen über sein Format widersprechen (drei 16-Bit- oder drei 32-Bit-Werte). Eine **Aufzeichnung** liest ihn 5 bis 30 Sekunden lang alle 0,2 bis 2 Sekunden und speichert nur die Rohwerte. Welche Dienste Ihr Würfel wirklich anbietet, zeigt das Datenblatt; tragen Sie auffällige Befunde hier ein.

## Taste und Batterie (AP-37)

- **Taste:** Characteristic `c7e70021-c847-11e6-8175-8c89a55d403c` (Community-Referenz `codingforfun/zeipy`), ein Byte: `0` = kurzer, `1` = langer Druck. OctaLedger **abonniert** sie nur (kein Schreiben), wenn der Würfel sie mit Notify/Indicate anbietet. **Nicht hardwarebestätigt:** UUID, Wertebedeutung und der Zeitpunkt der Meldung sind am echten Würfel zu prüfen (Seite *Würfel live*, „Letzte Bewegungen“). Unbekannte Werte werden als `invalid` mit Rohwert protokolliert. Gleiche Drücke innerhalb von 500 ms zählen einmal.
- **Batterie:** wird beim Verbinden und danach alle 10 Minuten **gelesen**; unter der eingestellten Grenze (Voreinstellung 20 %) gibt es **einmal** eine Erinnerung.

## Erfahrungen aus der ersten Erprobung (nicht hardwarevalidiert)

Die folgenden Beobachtungen stammen aus einer ersten Inbetriebnahme mit einem echten Würfel und sind **keine** Zusicherung:

- Der Würfel muss im **Kopplungsmodus** sein (Knopf lange gedrückt halten, bis er blau blinkt), sonst findet ihn die Suche nicht.
- Er meldete sich in der Liste als „Timeular Tra…“ **ohne** den Orientierungsdienst in der Werbung; ohne Namenshinweis war er unter vielen unbenannten
  Geräten kaum zu erkennen. Die Suche markiert deshalb Treffer, deren Name nach einem Tracker aussieht (`looks_like_tracker`); der Dienst
  wird erst nach dem Verbinden geprüft.
- Ein Würfel hat meist nur eine aktive Verbindung: Hersteller-App, Handy und Windows-Einstellungen sollten getrennt sein.

## Umsetzungsstand

Implementiert in `src/octaledger/infrastructure/ble/` (`protocol`, `transport`, `client`, `scanner`,
`fake`); Details in [SOFTWAREDOKUMENTATION.md](SOFTWAREDOKUMENTATION.md) §13–14.

- `discover_capabilities` prüft, was ein Gerät **wirklich** anbietet (Orientierungs-Characteristic mit
  Notify/Indicate); fehlt sie, wird das Gerät mit der Liste der angebotenen Dienste abgelehnt.
- Es gibt **keine Schreiboperation** in der BLE-Schicht (per Konstruktion, getestet).
- Optional und nur lesend: Batterie (`180f/2a19`), Modell/Firmware (`180a/2a24`, `2a26`).
- Scan nur auf Anforderung; keine Filterung, die andere Generationen ausschließen würde.
- Der Anfangswert wird gelesen (falls lesbar) und darf die erste Benachrichtigung duplizieren.

**Hardwarestatus: nicht validiert.** Die Punkte der Liste „Prüfen“ oben sind am eigenen Gerät
abzuarbeiten (Anleitung: INSTALLATION.md Abschnitt 5, Ergebnis in die Matrix in TESTPLAN.md).
