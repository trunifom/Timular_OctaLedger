# Roadmap und Umsetzungsstand

Jeder Meilenstein braucht Tests und eine ehrliche Statusangabe. „Software fertig“ heißt: umgesetzt und
automatisch getestet; „Hardware offen“ heißt: mit echten Trackern noch nicht geprüft.

| Meilenstein | Inhalt | Software | Hardware |
|---|---|---|---|
| **M0** Grundgerüst | Paket, Decoder, Zeitvalidierung, CLI, Statusseite, Tests, Doku | ✅ fertig | – |
| **M1** Hardwarediagnose | Scan/Connect/Discovery, Eigenschaften anzeigen, Rohwerte empfangen, beide Geräte separat kalibrieren | ✅ Scanner, Transport, Capability-Discovery, Kalibrierung, Diagnose-Seite, Hardware-Smoketests | ⏳ **offen**: auf echten Geräten ausführen und Kompatibilitätsmatrix füllen |
| **M2** Dauerhafter Agent | Supervisor, Reconnect, begrenzte Queues, Shutdown, Baseline, Entprellung, FakeTransport | ✅ fertig | ⏳ Langzeit-/Reichweitentests offen |
| **M3** Persistenz und Zeitlogik | Migrationen, Ereignisspeicher, aktiver Tracker, Start/Stop/Pause, Unsicherheit, Korrekturen, Absturz-/Wiederherstellungstests | ✅ fertig | – |
| **M4** API und Dashboard | Token-Authentifizierung, Geräteeinrichtung, Projekte/Aktivitäten, Journal, Filter, Diagramme; GUI nur über die API | ✅ fertig (inzwischen 11 Seiten) | – |
| **M5** Datenportabilität | CSV, versioniertes JSON, Restore, Datenschutz-/Diagnoseexport, reproduzierbare Abhängigkeiten | ✅ CSV, JSON, Restore, anonymisierter Diagnosebericht, `constraints-tested.txt` | – |
| **M6** Steuerungsmodus | Modus pro Würfel, Aktionen je Seite, Warteschlange, Adapter (Webhook, MQTT, Home Assistant, Hue), Oberfläche *Verbindungen* | ✅ fertig (AP-26 bis AP-31) | ⏳ **offen**: gegen echte Home-Assistant-/Hue-/MQTT-Installationen ausprobieren |
| **M7** Dokumentation | API-Referenz, Architektur, Datenmodell, Sicherheit, Glossar, Adapter-Anleitung, README mit Bildern, Handbuch in der App, Wächtertests | ✅ fertig | – |
| **M8** Erweiterungen A und B | Würfel-Eingang, Verbindungsverlust mit Frist, Rückfragen, Taste, Arbeitstag (Auto-Stopp, Leerlauf, Erinnerungen), Tray/Toast/Autostart, Soll-Zeit, Tags/Budgets, PDF/ICS, Hue, Aktionsketten, Medien, Rezepte | ⏳ **geplant** (AP-35 bis AP-47, Anforderungen F-21 bis F-50, Reihenfolge und Entwürfe in [UMSETZUNGSPLAN.md](UMSETZUNGSPLAN.md)) | ⏳ Taste, Hue, Medien brauchen echte Geräte |
| Release | Lizenz, Versionierung, Verpackung | ⏳ **offen** (Lizenz nicht gewählt, kein Release-Prozess) | – |

## Später (bewusst nicht im Umfang)

Parallele Gerätezeitachsen (benötigt eine Migration, die den Überschneidungs-Trigger anpasst, und die
Berichte unterscheiden bereits Gerätezeit und persönliche Zeit), Autostart/Tray, weitere Sprachen,
weitere Adapter (z. B. Obsidian, Telegram, Zigbee2MQTT – Anleitung: ADAPTER_ENTWICKLUNG.md), Rückmeldung vom Ziel
(Lampenzustand lesen), Verschlüsselung von `secrets.json` (Windows-Tresor). Android, Cloud und ein eigener Matter-Zugang erst nach stabilem Kern.

## Nächste sinnvolle Schritte (außerhalb dieses Entwicklungsstands)

1. **Hardwaretest** mit den eigenen USB-C-Trackern (Anleitung: INSTALLATION.md Abschnitt 5), Matrix in
   [TESTPLAN.md](TESTPLAN.md) füllen; Entprellzeit und Neutralwert-Verhalten festlegen.
2. **Anbindungen** mit echten Zielen ausprobieren (Home Assistant, Hue, MQTT) und die Ergebnisse in [QUELLEN_UND_GRENZEN.md](QUELLEN_UND_GRENZEN.md) festhalten.
3. **Lizenz** wählen, Namens-/Markenfreiheit prüfen, privaten Meldeweg in `SECURITY.md` ergänzen.
4. Optional: Windows-Autostart, Installer, Release-Prozess.
