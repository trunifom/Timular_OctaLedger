# OctaLedger – Dokumentationsübersicht

Diese Seite hilft Ihnen, **das richtige Dokument zu finden**. Die Dokumentation ist nach Zielgruppen geordnet; alle Dateien sind
Markdown und liegen in diesem Ordner. Das **Benutzerhandbuch** und die **Installationsanleitung** lesen Sie auch direkt im Programm auf der **Startseite**.

## Ich will …

| … | Dann lesen Sie |
|---|---|
| OctaLedger **installieren und starten** | [INSTALLATION.md](INSTALLATION.md) – danach der Schnellstart im [Benutzerhandbuch](BENUTZERHANDBUCH.md#3-schnellstart-in-10-minuten) |
| verstehen, **was der Würfel kann** und wie ich ihn bediene | [BENUTZERHANDBUCH.md](BENUTZERHANDBUCH.md) |
| mit dem Würfel **Licht oder Smarthome steuern** | [Benutzerhandbuch, Kapitel 20](BENUTZERHANDBUCH.md#20-dinge-steuern-der-steuerungsmodus) |
| einen **Fachbegriff** nachschlagen | [GLOSSAR.md](GLOSSAR.md) |
| **wissen, wie OctaLedger gebaut ist** | [ARCHITEKTUR.md](ARCHITEKTUR.md) |
| die **Datenbank und Dateien** verstehen | [DATENMODELL.md](DATENMODELL.md) |
| die **Schnittstelle (REST-API)** nutzen | [API.md](API.md) |
| **Node-RED, Zigbee2MQTT, WLED, Shelly, openHAB** anbinden (Vorlagen und Rezepte) | [REZEPTE.md](REZEPTE.md) |
| einen **neuen Adapter** (Anbindung) schreiben | [ADAPTER_ENTWICKLUNG.md](ADAPTER_ENTWICKLUNG.md) |
| im Code **etwas ändern oder ergänzen** | [CONTRIBUTING.md](../CONTRIBUTING.md), [SOFTWAREDOKUMENTATION.md](SOFTWAREDOKUMENTATION.md), [ORDNERSTRUKTUR.md](ORDNERSTRUKTUR.md) |
| wissen, **wie das Bluetooth-Protokoll** funktioniert | [BLE_PROTOCOL.md](BLE_PROTOCOL.md) |
| die **Sicherheit** beurteilen | [SECURITY.md](../SECURITY.md) |
| wissen, **was geprüft ist und was nicht** | [TESTPLAN.md](TESTPLAN.md), [QUELLEN_UND_GRENZEN.md](QUELLEN_UND_GRENZEN.md) |
| den **Projektstand und die Planung** sehen | [FORTSCHRITT.md](FORTSCHRITT.md), [ROADMAP.md](ROADMAP.md), [CHANGELOG.md](../CHANGELOG.md), [PFLICHTENHEFT.md](PFLICHTENHEFT.md) |
| wissen, **was als Nächstes gebaut wird** und **wie** (Reihenfolge, Entwürfe, Risiken) | [UMSETZUNGSPLAN.md](UMSETZUNGSPLAN.md), Anforderungen F-21 bis F-63 im [Pflichtenheft](PFLICHTENHEFT.md#12-erweiterungen-funktion-a-steuern-und-funktion-b-zeit-erfassen-geplant) |
| wissen, **wie die Oberfläche gestaltet wurde** | [GUI_KONZEPT.md](GUI_KONZEPT.md) |
| das Projekt **auf GitHub** bereitstellen | [GITHUB.md](GITHUB.md) |

## Alle Dokumente nach Zielgruppe

### Anwender

| Dokument | Inhalt |
|---|---|
| [BENUTZERHANDBUCH.md](BENUTZERHANDBUCH.md) | Bedienung Schritt für Schritt, alle Seiten des Dashboards, Zeiterfassung, Steuerungsmodus, Korrekturen, Sicherung, Fehlermeldungen, häufige Fragen |
| [INSTALLATION.md](INSTALLATION.md) | Voraussetzungen, Installation, Start, Bluetooth-Hinweise, Fehlerbehebung |
| [GLOSSAR.md](GLOSSAR.md) | alle Fachbegriffe |
| [REZEPTE.md](REZEPTE.md) | Rezeptbuch: Node-RED, Zigbee2MQTT, Tasmota, WLED, Shelly, openHAB, Home-Assistant-Webhook, Platzhalter in Nachrichten |

### Entwickler

| Dokument | Inhalt |
|---|---|
| [ARCHITEKTUR.md](ARCHITEKTUR.md) | Bausteine, Schichten, Prozesse und Threads, Datenflüsse (Zeit und Steuerung), Entwurfsentscheidungen, Erweiterungspunkte |
| [SOFTWAREDOKUMENTATION.md](SOFTWAREDOKUMENTATION.md) | Modul für Modul: Aufgaben, Fehlercodes, Einstellungen, Schnittstellen, Tests – das ausführliche Nachschlagewerk |
| [API.md](API.md) | jeder Endpunkt der lokalen REST-API mit Anfrage, Antwort, Fehlern und Beispielen |
| [DATENMODELL.md](DATENMODELL.md) | Dateien, Tabellen (Migrationen 0001–0003), Regeln der Datenbank, Zeitkodierung, Sicherungsformat |
| [ADAPTER_ENTWICKLUNG.md](ADAPTER_ENTWICKLUNG.md) | Anleitung mit Beispiel: eine neue Art von Verbindung hinzufügen |
| [BLE_PROTOCOL.md](BLE_PROTOCOL.md) | was vom Würfel gelesen wird (Community-Referenz, nicht hardwarevalidiert) |
| [ORDNERSTRUKTUR.md](ORDNERSTRUKTUR.md) | jede Datei des Projekts mit Verantwortung der Ordner |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Regeln und Rezepte: Fehlercode, Migration, Endpunkt, Seite, Adapter |
| [../CLAUDE.md](../CLAUDE.md), [../AGENTS.md](../AGENTS.md) | verbindliche Regeln für Menschen und LLM-Agenten |

### Planung, Qualität, Grenzen

| Dokument | Inhalt |
|---|---|
| [PFLICHTENHEFT.md](PFLICHTENHEFT.md) | Anforderungen (F-xx) und Abnahmekriterien, geplante Erweiterungen F-21 bis F-63 (Abschnitt 12) |
| [UMSETZUNGSPLAN.md](UMSETZUNGSPLAN.md) | die Arbeitspakete AP-35 bis AP-50 der Reihe nach: Warum, Was, Wo, Wie, Tests, Doku, Risiken, Abnahme |
| [TESTPLAN.md](TESTPLAN.md) | Teststrategie, Zahlen, Abnahmetabelle, Hardwaretest-Matrix |
| [QUELLEN_UND_GRENZEN.md](QUELLEN_UND_GRENZEN.md) | Quellen, Annahmen, was nicht geprüft ist |
| [ROADMAP.md](ROADMAP.md) | Pakete und Reihenfolge |
| [FORTSCHRITT.md](FORTSCHRITT.md) | erledigte Arbeitspakete mit Commit |
| [../CHANGELOG.md](../CHANGELOG.md) | Änderungen je Version |
| [../SECURITY.md](../SECURITY.md) | Bedrohungen, Maßnahmen, Grenzen, Meldeweg |
| [GUI_KONZEPT.md](GUI_KONZEPT.md) | Recherche und Design-System der Oberfläche |
| [GITHUB.md](GITHUB.md) | Veröffentlichung, Lizenz, Repository-Einstellungen |

## Dokumentation im Code

Neben diesen Dateien ist der **Quelltext selbst dokumentiert**: Jedes Modul beginnt mit einem Docstring (Aufgabe, Regeln, Grenzen), jede Klasse und Funktion hat einen,
und Kommentare erklären das **Warum**, nicht das Was. Ein Test (`tests/unit/test_documentation.py`) stellt sicher, dass das so bleibt: Er prüft, dass **alles** Docstrings hat, dass **jeder
Endpunkt** in [API.md](API.md) steht, dass **jede Datei** in [ORDNERSTRUKTUR.md](ORDNERSTRUKTUR.md) aufgeführt ist und dass **keine Verweise** zwischen den Dokumenten ins Leere führen.

## Dokumentation in der Oberfläche

* **Startseite:** was OctaLedger und der Würfel sind, geführte Einrichtung, die Handbücher zum Durchsuchen und Nachlesen.
* **Jede Seite** beginnt mit „So funktioniert diese Seite“, und **jedes Eingabefeld** hat einen Hilfetext (Fragezeichen).
* **Fehlermeldungen** sind deutsch, nennen die Ursache und was zu tun ist, und tragen einen Code (`OL-…`), der im Benutzerhandbuch (Kapitel 18) erklärt wird.

## Konventionen

* **Sprache:** Benutzerdokumentation und Oberfläche auf **Deutsch**; Code, Kommentare, Docstrings und Protokollmeldungen auf **Englisch**.
* **Ehrlichkeit:** Was nicht mit echter Hardware oder echten Zielsystemen geprüft ist, steht ausdrücklich dabei.
* **Pflege:** Jede Änderung am Verhalten aktualisiert die zugehörige Dokumentation im selben Commit.
