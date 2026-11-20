# Benutzerhandbuch

Dieses Handbuch richtet sich an Anwender von OctaLedger. Es wächst mit den
Funktionen; was noch nicht umgesetzt ist, steht in [FORTSCHRITT.md](FORTSCHRITT.md).

## 1. Was ist OctaLedger?

OctaLedger erfasst Arbeitszeit lokal auf Ihrem Rechner mit einem kompatiblen
Timeular-/ZEI-Würfel. Sie drehen den Würfel auf die Seite einer Tätigkeit, OctaLedger
startet die Zeit und speichert sie in einer lokalen Datenbank. Es wird kein
Herstellerkonto und keine Cloud benötigt.

## 2. Wenn eine Fehlermeldung erscheint

Fehlermeldungen enthalten einen **Fehlercode** wie `OL-BLE-002`. Nennen Sie diesen Code,
wenn Sie Hilfe suchen. Die Bedeutung aller Codes steht in der Tabelle unten.

| Code | Bedeutung | Was Sie tun können |
|---|---|---|
| OL-CONFIG-001 | Einstellungen ungültig | Einstellungsdatei prüfen oder zurücksetzen |
| OL-VALID-001 | Eingabe ungültig | Angaben im Formular prüfen |
| OL-STATE-001 | Eintrag nicht gefunden | Liste neu laden |
| OL-STATE-002 | Konflikt mit bestehenden Daten | Überschneidungen oder Duplikate beheben |
| OL-STATE-003 | Aktion jetzt nicht möglich | Zuerst die vorherige Aktion abschließen |
| OL-STORAGE-001 | Datenbank nicht les-/schreibbar | Speicherplatz und Rechte prüfen |
| OL-STORAGE-002 | Datenbank-Update fehlgeschlagen | Ihre Daten sind unverändert; Support kontaktieren |
| OL-STORAGE-003 | Daten beschädigt | Backup wiederherstellen |
| OL-DATA-001 | Export fehlgeschlagen | Zielordner und Speicherplatz prüfen |
| OL-DATA-002 | Import fehlgeschlagen | Datei prüfen; es wurde nichts verändert |
| OL-BLE-001 | Unerwartete Tracker-Daten | Tracker neu verbinden |
| OL-BLE-002 | Bluetooth-Verbindung fehlgeschlagen | Bluetooth einschalten, näher an den Tracker gehen |
| OL-BLE-003 | Gerät nicht unterstützt | Anderes Gerät wählen |
| OL-API-001 | Anmeldung an Schnittstelle fehlgeschlagen | Agent und Dashboard mit demselben Token starten |
| OL-API-002 | Agent nicht erreichbar | Agent starten |
| OL-API-003 | Anfrage abgelehnt | Dashboard nur lokal im Browser öffnen |
