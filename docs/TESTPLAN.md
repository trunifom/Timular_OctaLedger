# Testplan

Unit: Decoder 0–8, ungültige Länge/Werte, Zeitzonenvalidierung, später Zustandsautomat.
Integration: SQLite, Migration, API-Token, Export/Restore und doppelte Aufträge.
Hardware: ausdrücklich manuell aktivieren; niemals automatisch unbekannte Geräte verbinden.

Matrix dokumentieren: Modell, Firmware, OS, Adapter, Treiber, Python, Bleak, Appversion.

Testfälle: alle Flächen; schnelles/langsames Drehen; Duplikate; Neutralwert; konkurrierende
Hersteller-App; Reichweite; Schlafmodus; Adapter aus/an; Reconnect; zwei Tracker;
Dashboard schließen; Agentabsturz; Neustart; Uhrsprung; Sommerzeit; voller Datenträger;
Import beschädigt; API nicht erreichbar; Token falsch; Backup in frischer Umgebung.

Akzeptanzfälle stehen im Pflichtenheft. Aktuell sind nur Decoder-/Zeitunit-Tests
implementiert. Tests im FakeTransport verwenden ausdrücklich synthetische Fixtures,
keine als echt ausgegebenen Arbeitszeitdaten.
