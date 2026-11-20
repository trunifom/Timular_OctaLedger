# Sicherheit

OctaLedger ist ein lokales Programm. Umgesetzte Schutzmaßnahmen (Details: docs/SOFTWAREDOKUMENTATION.md
§17–20):

- Lokale API **nur auf Loopback** (`127.0.0.1`, `::1`, `localhost`; andere Adressen werden abgelehnt);
  alle geschützten Routen verlangen ein **Bearer-Token** (256 Bit, Vergleich in konstanter Zeit, nie in
  URLs); **Host-** und **Origin-Prüfung** gegen CSRF/DNS-Rebinding; kein Zustandswechsel über GET;
  strikte Eingabemodelle; Interna und Stacktraces werden nie ausgeliefert.
- Das Dashboard sendet das Token **nur an Loopback-Adressen** und läuft ohne Telemetrie.
- Tokens, Passwörter und Teile von Bluetooth-Adressen werden vor dem Schreiben in Logs **maskiert**.
- **Keine BLE-Schreibzugriffe** (nur lesen und abonnieren); keine Shell-/Pfadausführung aus Importdateien;
  Dateinamen für Exporte werden streng geprüft.
- Dateien werden atomar geschrieben; Backups tragen eine Prüfsumme; der Restore validiert vollständig und
  läuft in einer Transaktion mit vorheriger Sicherung. CSV-Zellen sind gegen Formel-Injection geschützt.

Nicht umgesetzt: Netzwerkfreigabe (bewusst nur Loopback), Ratenbegrenzung für Fehlversuche (bei 256 Bit
Zufall aussichtslos), Verschlüsselung der Datenbank im Ruhezustand (Schutz durch Benutzerprofil/Windows).

Keine Tokens oder privaten Zeitdaten in öffentliche Issues schreiben.
**Offen:** Ein Projektbetreiber muss vor Veröffentlichung einen privaten Meldeweg für Sicherheitsprobleme
ergänzen (z. B. GitHub „Security Advisories“ oder eine E-Mail-Adresse) – er ist hier bewusst nicht erfunden.
