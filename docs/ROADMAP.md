# Roadmap

## M0 – Vorliegendes Grundgerüst
Paket, Decoder, Zeitvalidierung, CLI, Statusseite, Tests und Dokumentation.

## M1 – Hardwarediagnose
Scan/Connect/Discovery, Eigenschaften anzeigen, Rohwerte empfangen, beide Geräte
separat kalibrieren. Keine automatische produktive Zeitmessung versprechen.

## M2 – Dauerhafter Agent
Supervisor, Reconnect, begrenzte Queues, Shutdown, Baseline, Entprellung, FakeTransport
für deterministische Tests. Ein Loop, ein eindeutiger Besitzer pro Gerät.

## M3 – Persistenz und Zeitlogik
Migrationen, Ereignisspeicher, ausgewählter aktiver Tracker, Start/Stop/Pause,
Unsicherheit, Korrekturen. Absturz- und Wiederherstellungstests.

## M4 – API und Dashboard
Lokale Tokenauthentifizierung, Geräteeinrichtung, Projekte/Aktivitäten, Journal,
Filter, Diagramme. GUI arbeitet ausschließlich über die API.

## M5 – Datenportabilität
CSV, versioniertes JSON, Restore, Datenschutz-/Diagnoseexport, Release und
reproduzierbare Abhängigkeiten.

## Später
Parallele Gerätezeitachsen, Autostart/Tray, optionale HA-/Hue-/MQTT-Adapter.
Android, Cloud und Matter erst nach stabilem Kern.

Jeder Meilenstein braucht Tests und ehrliche README-Statusänderung.
