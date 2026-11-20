# BLE-Protokoll und Kompatibilitätsaufnahme

Bekannte Community-Referenz: https://github.com/unixfg/triangles

```text
Orientierungsdienst: c7e70010-c847-11e6-8175-8c89a55d403c
Characteristic:     c7e70012-c847-11e6-8175-8c89a55d403c
```

Referenzimplementierungen beschreiben ein Byte, 1–8 für Seiten, 0 neutral.
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
