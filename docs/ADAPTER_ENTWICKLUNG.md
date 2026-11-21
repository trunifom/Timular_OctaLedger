# OctaLedger – Anleitung: einen neuen Adapter schreiben

Ein **Adapter** bringt OctaLedger bei, mit einer weiteren Art von Gegenstelle zu sprechen (Licht, Steckdose, Messenger, Webdienst …). Die
mitgelieferten Adapter sind **Webhook**, **MQTT**, **Home Assistant** und **Philips Hue**. Ein neuer Adapter ist **eine Datei plus eine Zeile** –
Oberfläche, Schnittstelle und Datenbank müssen **nicht** geändert werden, weil sich jeder Adapter selbst beschreibt.

Diese Anleitung richtet sich an Entwickler. Voraussetzung: Sie haben die [Architektur](ARCHITEKTUR.md) (Abschnitt 5, Steuerungsmodus) gelesen.
Anwender, die nur etwas anbinden wollen, brauchen in den meisten Fällen **keinen** neuen Adapter: Der **Webhook-Adapter** erreicht jedes Gerät mit
einfacher Web-Schnittstelle, und **Home Assistant** erreicht tausende Geräte (auch Matter und Google Home).

**Inhalt**

1. [Wie ein Adapter ins Ganze passt](#1-wie-ein-adapter-ins-ganze-passt)
2. [Der Vertrag](#2-der-vertrag)
3. [Die Selbstbeschreibung (`AdapterSpec`)](#3-die-selbstbeschreibung-adapterspec)
4. [Die zwei Fehlerarten – und warum sie so wichtig sind](#4-die-zwei-fehlerarten--und-warum-sie-so-wichtig-sind)
5. [Sicherheitsregeln](#5-sicherheitsregeln)
6. [Schritt für Schritt: ein Beispiel](#6-schritt-für-schritt-ein-beispiel)
7. [Tests](#7-tests)
8. [Checkliste](#8-checkliste)
9. [Die mitgelieferten Adapter im Überblick](#9-die-mitgelieferten-adapter-im-überblick)

---

## 1. Wie ein Adapter ins Ganze passt

```text
Würfel -> Tracking-Service -> Auftrag in der Warteschlange (Outbox)
                                       |
              Dispatcher-Thread -> IntegrationService.process_due()
                                       |   holt Einstellungen (Datenbank) und Geheimnisse (SecretStore)
                                       v
                              Adapter.execute(config, secrets, params, timeout=…)
```

Der Adapter kennt weder Datenbank noch Warteschlange, weder Würfel noch Oberfläche. Er bekommt **Einstellungen**, **Geheimnisse** und die **Parameter der Aktion**
und tut eine Sache. Wiederholungen, Verfall, Verlauf, Zeitlimit und Protokoll erledigt der `IntegrationService`.

Weil der Adapter sich selbst beschreibt, gilt:

* die Seite **Verbindungen** erzeugt das Formular für Einstellungen und Aktionen **automatisch** aus `AdapterSpec` (`dashboard/forms.py`),
* `GET /adapters` liefert dieselbe Beschreibung an jeden Client ([API.md](API.md) §7),
* der Dienst prüft Eingaben mit **derselben** Beschreibung – Oberfläche und Prüfung können nicht auseinanderlaufen.

## 2. Der Vertrag

Basisklasse `Adapter` in `src/octaledger/infrastructure/integrations/base.py`:

| Element | Pflicht? | Aufgabe |
|---|---|---|
| `spec: AdapterSpec` | ja | Selbstbeschreibung (Klassenattribut) |
| `check(config, secrets, *, timeout) -> str` | ja | Verbindung **ohne Nebenwirkung** testen; kurze deutsche Meldung zurückgeben |
| `execute(config, secrets, params, *, timeout) -> str` | ja | Eine Aktion ausführen; kurze deutsche Meldung zurückgeben |
| `validate_config(values)` | nein | Einstellungen prüfen; die Basisklasse prüft Typen/Pflichtfelder, überschreiben Sie nur für **zusätzliche** Regeln (z. B. Adresse) |
| `validate_action(params)` | nein | Parameter einer Aktion prüfen (die Basisklasse prüft Aktion und Felder) |
| `pair(config, *, timeout) -> PairResult` | nur wenn `can_pair` | einmalige Kopplung; liefert Geheimnisse und Einstellungen zum Speichern |
| `spec.presets` (`Preset`) | optional | Vorlagen für eine Aktion (`id`, `label`, `action`, `description`, `params`, `verified`): Die Oberfläche zeigt sie als Auswahl und füllt nur das Formular. Das Feld `verified` bleibt `False`, bis die Vorlage an einem echten Ziel geprüft wurde |
| `FieldSpec(placeholders=True)` | optional | erlaubt in diesem Textfeld die Platzhalter `{device}`, `{face}`, `{label}`, `{time}`; sie werden beim Senden ersetzt (JSON-Vorlagen maskiert), unbekannte Namen werden beim Speichern abgelehnt (`domain/placeholders.py`) |
| `find_targets(*, online=False, timeout) -> list` | nur wenn `can_find` | das Ziel im Netz suchen: `[{"id", "address", "name"}]`; `online` erlaubt einen Internetdienst und darf **nie** ohne ausdrücklichen Klick des Anwenders benutzt werden |
| `discover(config, secrets, *, timeout) -> dict` | nur wenn `can_discover` | Auswahllisten, z. B. `{"lights": [{"id": "1", "name": "Schreibtisch"}]}` |

Rückgabe von `check`/`execute`: ein **kurzer deutscher Satz**, der im Verlauf und in der Oberfläche erscheint („Anfrage gesendet (HTTP 200).“). Er darf
**keine Geheimnisse** enthalten.

`timeout` ist die Zeit in Sekunden, die ein einzelner Aufruf höchstens dauern darf. **Halten Sie ihn ein** – jede Netzwerkoperation braucht ein Zeitlimit.

## 3. Die Selbstbeschreibung (`AdapterSpec`)

```python
AdapterSpec(
    kind="shelly",  # technischer Name, eindeutig, 1-40 Zeichen; steht in der Datenbank
    title="Shelly (Relais)",  # Anzeigename (Deutsch)
    description="…",  # ein bis zwei Sätze für Anwender (Deutsch)
    config_fields=(FieldSpec(...),),  # Einstellungen der VERBINDUNG
    actions=(ActionSpec(...),),  # was die Verbindung tun kann
    can_pair=False,
    pair_help="",  # braucht es eine einmalige Kopplung?
    can_discover=False,  # kann sie Geräte/Szenen zur Auswahl auflisten?
    can_find=False,  # kann sie das Ziel im Netz suchen (Knöpfe „Im Heimnetz suchen“ / „Im Internet nachschlagen“)?
    find_help="",  # erklärt, was die Suche sendet
)
```

**`FieldSpec`** – ein Eingabefeld:

| Angabe | Bedeutung |
|---|---|
| `name` | Schlüssel in Einstellungen/Parametern |
| `label` | deutsche Beschriftung |
| `kind` | `text`, `password` (**Geheimnis**), `int`, `bool`, `choice` |
| `required` | leere Eingabe wird abgelehnt |
| `help` | deutscher Hilfetext (erscheint als Tooltip – **an jedem Feld Pflicht**) |
| `default`, `placeholder` | Vorbelegung, Beispieltext |
| `choices` | Paare `(Wert, Beschriftung)` für `choice` |
| `minimum`, `maximum` | Grenzen für `int` |
| `choices_from` | Namen von `discover`-Kategorien; die Oberfläche bietet dann eine Auswahlliste statt Freitext |

Texte sind auf 500 Zeichen und **eine Zeile** begrenzt (Zeilenumbrüche werden abgelehnt) – das ist mehr als genug für einen Schaltbefehl.

**`ActionSpec`** – eine Aktion: `id`, `label`, `description`, `fields` und **`idempotent`**: Bewirkt zweimaliges Ausführen dasselbe wie einmaliges?
„Einschalten“ ist idempotent, „Umschalten“ nicht. Die Oberfläche **warnt** vor nicht idempotenten Aktionen; ordnen Sie das ehrlich ein.

**Geheimnisse:** Felder der Art `password` landen **nie** in der Datenbank, in Sicherungen, API-Antworten oder Protokollen, sondern im `SecretStore`.
Im Adapter kommen sie getrennt als `secrets` an.

## 4. Die zwei Fehlerarten – und warum sie so wichtig sind

Aus der Fehlerklasse folgt, **ob die Warteschlange es nochmals versucht**:

| Fehler | Wann auslösen | Folge |
|---|---|---|
| `IntegrationConnectionError` | Die Anfrage ist **sicher nicht angekommen**: nicht verbunden, Name nicht aufgelöst, Zeitüberschreitung **beim Verbinden** | bis zu 3 Versuche (Pausen 1 s, 3 s), solange die Aktion nicht verfallen ist |
| `IntegrationError` | alles andere: Zugang abgelehnt, Fehlerantwort, Verbindung mitten in der Anfrage abgebrochen, Zeitüberschreitung **nach** dem Senden | Auftrag `failed`, **keine** Wiederholung |
| `ValidationError` | nur in `validate_*`: Eingabe falsch | wird dem Anwender mit deutschem Text gezeigt |

**Im Zweifel `IntegrationError`.** Eine doppelt gesendete Aktion („Umschalten“!) ist schlimmer als eine, die der Anwender im Verlauf als gescheitert sieht. Die
gemeinsame Hilfsfunktion `httpio.send` nimmt Ihnen diese Einordnung für HTTP ab.

Alle drei Klassen haben einen deutschen `user_message` (für Anwender) und eine englische technische Meldung (fürs Protokoll). Schreiben Sie die deutsche Meldung so, dass
ein Laie weiß, **was er tun kann** („Bitte Zugangskopf und -wert prüfen.“).

## 5. Sicherheitsregeln

Diese Regeln gelten für **jeden** Adapter und werden bei einer Durchsicht geprüft:

1. **Zeitlimit überall.** Nie ohne `timeout`; nie unbegrenzt auf eine Antwort warten.
2. **Keine Geheimnisse sichtbar:** weder in Meldungen noch im Protokoll noch in Ausnahmetexten. Das Protokoll schwärzt registrierte Geheimnisse, aber verlassen Sie sich nicht darauf.
3. **Keine Weiterleitungen**, keine **Umgebungs-Proxys** (`httpio.new_session()` ist so eingestellt). Eine Weiterleitung könnte auf einen anderen Rechner zeigen.
4. **Ziel einschränken:** Adressen mit `httpio.check_base_url` prüfen (nur `http`/`https`, ohne Benutzername, Abfrage-Teil und Fragment). Der Pfad einer Aktion wird an die
   **Basisadresse angehängt** – eine Aktion kann nie einen anderen Rechner ansprechen.
5. **Antworten begrenzen:** Antwortkörper nur lesen, wenn nötig, und dann mit Größengrenze (`httpio.read_limited`).
6. **Keine Befehle, keine Dateipfade** aus Eingaben ausführen oder öffnen.
7. **Einzige Wirkung ist die beschriebene.** `check` darf nichts schalten.
8. **Zertifikate prüfen** (`verify_tls=True` als Standard); ein Abschalten muss ausdrücklich, mit Hilfetext, möglich sein.

## 6. Schritt für Schritt: ein Beispiel

Wir bauen einen Adapter für ein **Relais mit einfacher Web-Schnittstelle** (angelehnt an Geräte, die `GET /relay/0?turn=on` verstehen). Er hat eine
Einstellung (Adresse) und eine Aktion (Relais schalten).

**Schritt 1 – Datei** `src/octaledger/infrastructure/integrations/relay.py`:

```python
"""Relay adapter: switch a relay that offers a plain HTTP interface (``GET /relay/0?turn=on``).

Safety rules: see ``base.py`` (no redirects, no proxies, short timeout, the answer is not read).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from octaledger.core.errors import IntegrationError
from octaledger.infrastructure.integrations.base import (
    ActionSpec,
    Adapter,
    AdapterSpec,
    FieldSpec,
)
from octaledger.infrastructure.integrations.httpio import (
    SessionFactory,
    check_base_url,
    new_session,
    send,
)


class RelayAdapter(Adapter):
    """Switches a relay over HTTP."""

    spec = AdapterSpec(
        kind="relay",
        title="Relais (Web-Schnittstelle)",
        description="Schaltet ein Relais, das über eine einfache Web-Adresse bedient wird.",
        config_fields=(
            FieldSpec(
                "base_url",
                "Adresse des Relais",
                required=True,
                placeholder="http://192.168.1.50",
                help="Adresse des Geräts im Heimnetz, mit http://.",
            ),
        ),
        actions=(
            ActionSpec(
                "switch",
                "Relais schalten",
                "Schaltet das Relais ein oder aus.",
                (
                    FieldSpec(
                        "state",
                        "Zustand",
                        kind="choice",
                        default="on",
                        choices=(("on", "Ein"), ("off", "Aus")),
                        help="„Ein“ oder „Aus“ – das Ergebnis ist bei jedem Senden dasselbe.",
                    ),
                ),
                idempotent=True,  # setting a state twice is harmless (toggling would not be)
            ),
        ),
    )

    def __init__(self, session_factory: SessionFactory = new_session) -> None:
        """Create the adapter (``session_factory`` is replaceable for tests)."""
        self._session_factory = session_factory

    def validate_config(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Check the settings: a plain http(s) base address."""
        config = super().validate_config(values)
        config["base_url"] = check_base_url(config["base_url"])
        return config

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """Ask the device for its status without switching anything."""
        status = self._request(config, "/status", timeout)
        return f"Das Relais ist erreichbar (HTTP {status})."

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Switch the relay; only a 2xx answer counts as success."""
        state = params["state"]  # already validated against the choices
        status = self._request(config, f"/relay/0?turn={state}", timeout)
        return f"Relais geschaltet (HTTP {status})."

    def _request(self, config: Mapping[str, Any], path: str, timeout: float) -> int:
        """One GET request; connection problems are classified by ``httpio.send``."""
        response = send(
            self._session_factory,
            "GET",
            str(config["base_url"]).rstrip("/") + path,
            headers={"User-Agent": "OctaLedger"},
            data=None,
            timeout=timeout,
            verify=True,
        )
        status = response.status_code
        response.close()  # the body is never read
        if not 200 <= status < 300:
            raise IntegrationError(
                f"HTTP {status}",
                user_message=f"Das Relais hat die Anfrage abgelehnt (HTTP {status}).",
            )
        return status
```

**Schritt 2 – eintragen** in `src/octaledger/infrastructure/integrations/registry.py`:

```python
from octaledger.infrastructure.integrations.relay import RelayAdapter
...
    adapters: list[Adapter] = [
        WebhookAdapter(),
        MqttAdapter(),
        HomeAssistantAdapter(),
        HueAdapter(),
        RelayAdapter(),          # <- neu
    ]
```

**Schritt 3 – ausprobieren.** Agent und Dashboard starten; auf der Seite **Verbindungen** erscheint „Relais (Web-Schnittstelle)“ in der Auswahl, mit dem
Formular aus Ihrer Beschreibung. Eine Änderung an `api/`, `dashboard/` oder der Datenbank war **nicht** nötig.

**Schritt 4 – Tests und Dokumentation** (Abschnitte 7 und 8).

### Kopplung und Entdeckung (optional)

* **Kopplung** (`can_pair=True`, `pair_help="…"`): `pair()` führt einen einmaligen Schritt aus (bei Hue: die Bridge-Taste wurde gedrückt, jetzt Schlüssel anfordern) und
  gibt ein `PairResult(secrets={…}, config={…}, message="…")` zurück. Der Dienst legt die Geheimnisse im `SecretStore` ab und ergänzt die Einstellungen.
* **Entdeckung** (`can_discover=True`): `discover()` gibt Kategorien mit Einträgen zurück: `{"lights": [{"id": "…", "name": "…"}]}`. Tragen Sie die Kategorie
  im Feld einer Aktion als `choices_from=("lights",)` ein, und die Oberfläche zeigt dort eine **Auswahlliste** statt eines Textfelds.

## 7. Tests

Orientieren Sie sich an `tests/unit/test_adapter_webhook.py`: Es läuft gegen einen **echten lokalen HTTP-Server** (`http.server` in einem Thread), nicht gegen
Attrappen des Netzwerks. Mindestens zu prüfen:

| Fall | Erwartung |
|---|---|
| Selbstbeschreibung | `kind` eindeutig; jedes Feld hat `help` und deutsches `label`; Geheimnisse sind `password` |
| `validate_config`/`validate_action` | gültige Eingaben werden bereinigt; unbekannte Felder, fehlende Pflichtfelder, falsche Typen ergeben `ValidationError` mit deutschem Text |
| `check` | Erfolg meldet einen deutschen Satz; **schaltet nichts** (Server prüfen: nur der Statusaufruf kam an) |
| `execute` | gesendete Anfrage prüfen (Methode, Pfad, Kopfzeilen, Inhalt); 2xx = Erfolg |
| Fehlerklassifizierung | nicht erreichbar → `IntegrationConnectionError`; Fehlerantwort/Zugang abgelehnt → `IntegrationError`; Weiterleitung wird **nicht** befolgt |
| Zeitlimit | langsamer Server → Fehler innerhalb des Limits, kein Hängen |
| Geheimnisse | tauchen weder in Meldungen noch in `str(Fehler)` noch im Protokoll auf |
| Ganze Kette | über `IntegrationService.process_due` mit `adapters={...}`: Auftrag wird `done`/`failed`; Wiederholung nur bei `IntegrationConnectionError` |

Ein neuer Adapter bringt automatisch von den **Wächtertests** profitierende Prüfungen mit (Docstrings überall, Datei in `ORDNERSTRUKTUR.md`).

## 8. Checkliste

- [ ] Modul-Docstring (englisch) mit Zweck, Sicherheitsregeln und Grenzen; jede Funktion/Klasse mit Docstring
- [ ] `kind` eindeutig, `title`/`description`/`label`/`help` auf **Deutsch**, **an jedem Feld** ein `help`
- [ ] Geheimnisse nur als `password`-Felder; nirgends ausgegeben
- [ ] Zeitlimit überall; keine Weiterleitungen, keine Umgebungs-Proxys
- [ ] Fehlerklassen richtig gewählt (im Zweifel `IntegrationError`); deutsche `user_message` mit Handlungshinweis
- [ ] `idempotent` ehrlich gesetzt
- [ ] Eintrag in `registry.py`
- [ ] Tests (Abschnitt 7), `ruff check`, `ruff format --check`, `mypy`, `pytest` grün
- [ ] Benutzerhandbuch: Kapitel „Anbindungen“ um den Adapter ergänzen (Voraussetzung, Felder, Beispiel, typische Fehler)
- [ ] Tabelle in Abschnitt 9 dieser Datei, `docs/ARCHITEKTUR.md` §5, README-Tabelle ergänzen
- [ ] `docs/FORTSCHRITT.md` und `CHANGELOG.md`

## 9. Die mitgelieferten Adapter im Überblick

| `kind` | Aktionen (`id`) | Kopplung | Entdeckung | Besonderheiten |
|---|---|---|---|---|
| `webhook` | `request` (Pfad, Methode, Inhaltstyp, Inhalt) | – | – | nicht idempotent (kann beliebige Wirkung haben); Zugangskopf als Geheimnis; keine Weiterleitungen; Antwort wird nicht gelesen |
| `mqtt` | `publish` (Thema, Inhalt, QoS 0/1, retain) | – | – | eigener MQTT-3.1.1-Sender (Standardbibliothek); TLS mit Zertifikatsprüfung; keine Platzhalter und kein `$`-Thema |
| `homeassistant` | `turn_on` (optional Helligkeit), `turn_off`, `toggle`, `scene`, `script`, `service` | – | Geräte, Szenen, Skripte | REST-Schnittstelle mit Langzeit-Zugriffstoken; **der Weg zu Matter und Google Home** |
| `hue` | `light`, `room`, `scene` | Bridge-Taste | Lampen, Räume, Szenen | CLIP v2 über HTTPS; **Zertifikat der Bridge wird beim ersten Mal angeheftet** (SHA-256) |

Die genauen Felder jeder Verbindung liefert `GET /adapters` – oder der Quelltext der jeweiligen Datei.
