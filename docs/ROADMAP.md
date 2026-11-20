# Roadmap und Umsetzungsstand

Jeder Meilenstein braucht Tests und eine ehrliche Statusangabe. „Software fertig“ heißt: umgesetzt und
automatisch getestet; „Hardware offen“ heißt: mit echten Trackern noch nicht geprüft.

| Meilenstein | Inhalt | Software | Hardware |
|---|---|---|---|
| **M0** Grundgerüst | Paket, Decoder, Zeitvalidierung, CLI, Statusseite, Tests, Doku | ✅ fertig | – |
| **M1** Hardwarediagnose | Scan/Connect/Discovery, Eigenschaften anzeigen, Rohwerte empfangen, beide Geräte separat kalibrieren | ✅ Scanner, Transport, Capability-Discovery, Kalibrierung, Diagnose-Seite, Hardware-Smoketests | ⏳ **offen**: auf echten Geräten ausführen und Kompatibilitätsmatrix füllen |
| **M2** Dauerhafter Agent | Supervisor, Reconnect, begrenzte Queues, Shutdown, Baseline, Entprellung, FakeTransport | ✅ fertig | ⏳ Langzeit-/Reichweitentests offen |
| **M3** Persistenz und Zeitlogik | Migrationen, Ereignisspeicher, aktiver Tracker, Start/Stop/Pause, Unsicherheit, Korrekturen, Absturz-/Wiederherstellungstests | ✅ fertig | – |
| **M4** API und Dashboard | Token-Authentifizierung, Geräteeinrichtung, Projekte/Aktivitäten, Journal, Filter, Diagramme; GUI nur über die API | ✅ fertig (8 Seiten) | – |
| **M5** Datenportabilität | CSV, versioniertes JSON, Restore, Datenschutz-/Diagnoseexport, reproduzierbare Abhängigkeiten | ✅ CSV, JSON, Restore, anonymisierter Diagnosebericht, `constraints-tested.txt` | – |
| Release | Lizenz, Versionierung, Verpackung | ⏳ **offen** (Lizenz nicht gewählt, kein Release-Prozess) | – |

## Später (bewusst nicht im Umfang)

Parallele Gerätezeitachsen (benötigt eine Migration, die den Überschneidungs-Trigger anpasst, und die
Berichte unterscheiden bereits Gerätezeit und persönliche Zeit), Autostart/Tray, optionale
Home-Assistant-/Hue-/MQTT-Adapter (F-20), Integrationsaufträge (`integration_jobs`), weitere Sprachen.
Android, Cloud und Matter erst nach stabilem Kern.

## Nächste sinnvolle Schritte (außerhalb dieses Entwicklungsstands)

1. **Hardwaretest** mit den eigenen USB-C-Trackern (Anleitung: INSTALLATION.md Abschnitt 5), Matrix in
   [TESTPLAN.md](TESTPLAN.md) füllen; Entprellzeit und Neutralwert-Verhalten festlegen.
2. **Lizenz** wählen, Namens-/Markenfreiheit prüfen, privaten Meldeweg in `SECURITY.md` ergänzen.
3. Optional: Windows-Autostart, Installer, Release-Prozess.
