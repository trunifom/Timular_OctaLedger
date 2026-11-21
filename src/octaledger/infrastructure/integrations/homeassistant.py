"""Home Assistant adapter: call services and scenes through Home Assistant's REST interface.

Home Assistant is the **hub** for the smart-home standards OctaLedger does not speak itself:
whatever you have connected there - Matter devices, Google Home integrations, Zigbee, Hue,
KNX - a cube face can switch, by calling a service of Home Assistant.

A *connection* is the address of your Home Assistant (``http://homeassistant.local:8123``) and a
**long-lived access token** (created in your Home Assistant profile; stored as a secret). An
*action* is one of: turn on (optionally with a brightness), turn off, toggle, activate a scene,
run a script, or - for everything else - call any ``domain.service`` with optional JSON data.

Safety rules
------------
* ``domain`` and ``service`` are restricted to ``[a-z0-9_]`` and the entity id to the Home
  Assistant format ``domain.object_id``, so no value can reshape the request path.
* Redirects are never followed, environment proxies are ignored, the answer is read only for
  the device list and then with a size limit (see :mod:`httpio`).
* The token is a secret: stored separately, sent only as a Bearer header, never logged and
  never part of an answer or error message.
* Retried only when the request certainly did not arrive; an HTTP answer or a timeout after
  sending is final (a repeated "toggle" would flip the device twice).

Limits: REST only (no websocket), no webhook triggers, the list of devices is capped, text values
are limited to 500 characters. Verified against a local fake of the interface, not a real Home
Assistant (the real one may differ in versions and error texts).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Final

from octaledger.core.errors import IntegrationError, ValidationError
from octaledger.domain.music_source import MusicSource, SourceKind
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
    read_limited,
    send,
)
from octaledger.infrastructure.integrations.urlcheck import check_media_url

_ENTITY: Final = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_WORD: Final = re.compile(r"^[a-z0-9_]+$")

#: Kinds of entities offered when listing devices to choose from, with their German headings.
DISCOVER_DOMAINS: Final = {
    "light": "Lampen",
    "switch": "Schalter",
    "scene": "Szenen",
    "script": "Skripte",
    "input_boolean": "Hilfsschalter",
    "fan": "Ventilatoren",
    "cover": "Rollläden",
    "media_player": "Mediengeräte",
}
MAX_DISCOVERED_PER_DOMAIN: Final = 200

_SWITCHABLE: Final = ("light", "switch", "input_boolean", "fan", "cover", "media_player")

_MEDIA_PLAYER_FIELD: Final = FieldSpec(
    "entity_id",
    "Mediengerät (entity_id)",
    required=True,
    choices_from=("media_player",),
    placeholder="media_player.wohnzimmer",
    help="Der Lautsprecher oder das Display in Home Assistant („media_player.…“). „Entdecken“ "
    "listet Ihre Mediengeräte auf.",
)
_MEDIA_URL_FIELD: Final = FieldSpec(
    "media_url",
    "Stream-Adresse",
    required=True,
    placeholder="https://example.org/radio.mp3",
    help="Eine http(s)-Adresse eines Streams, „media-source://…“ oder (mit passender Integration "
    "in Home Assistant) „spotify:…“. Spielen Sie nur Inhalte ab, deren Nutzung Ihnen erlaubt ist.",
)
_MEDIA_TYPE_FIELD: Final = FieldSpec(
    "media_type",
    "Medientyp",
    advanced=True,
    default="music",
    placeholder="music",
    help="Der Inhaltstyp, den Home Assistant erwartet (meist „music“). Voreinstellung: music.",
)
_MEDIA_SCHEMES: Final = ("media-source://", "spotify:")

_ENTITY_FIELD: Final = FieldSpec(
    "entity_id",
    "Gerät (entity_id)",
    required=True,
    choices_from=_SWITCHABLE,
    placeholder="light.schreibtisch",
    help="Der Name des Geräts in Home Assistant, im Format „bereich.name“ (Einstellungen › Geräte "
    "& Dienste › Entitäten). „Entdecken“ listet Ihre Geräte auf.",
)


SETUP_GUIDE: Final = """\
**Wofür:** Der Hub für Lampen, Schalter, Szenen und Skripte – und der Weg zu **Matter**- und
**Google-Home**-Geräten: Was in Home Assistant eingebunden ist, kann der Würfel schalten.

1. **Adresse** von Home Assistant eintragen, z. B. `http://homeassistant.local:8123` (mit Port).
2. **Zugriffstoken** erstellen: In Home Assistant unten links auf Ihren **Benutzernamen** klicken (Profil) →
   Tab **Sicherheit** → ganz unten **Langlebige Zugriffstoken** → **Token erstellen** → Namen „OctaLedger“
   vergeben → Token kopieren (es wird **nur einmal** angezeigt) und hier einfügen.
3. **Verbindung testen.**
4. Mit **Geräte der Verbindung auflisten** wählen Sie Lampen, Szenen und Skripte **nach Namen** aus.

**Wo finde ich die Adresse?** Home Assistant läuft meist auf einem Mini-PC/Raspberry Pi (Home Assistant OS). Öffnen Sie
Home Assistant im Browser: **genau die Adresse, die dort oben in der Adresszeile steht**, ist die richtige (z. B.
`http://192.168.1.20:8123`). Der Standard-Port ist **8123**. Der Name `homeassistant.local` funktioniert unter Windows nicht
immer – nehmen Sie dann die **IP-Adresse** (Router-Geräteliste). Mit Nabu Casa gilt die `https://….ui.nabu.casa`-Adresse.

**Noch kein Home Assistant?** Dann brauchen Sie es nicht: Für Philips Hue gibt es die direkte Verbindung **Philips Hue**,
für einfache Dinge einen **Webhook** und zum Üben die **Testverbindung (Probelauf)**.

**Wenn es nicht klappt**
- *„nicht erreichbar“:* Adresse und Port prüfen (im Browser öffnen), PC und Home Assistant im selben Netz?
- *„Token abgelehnt“ (401):* Token neu erstellen und **vollständig** einfügen (kein Leerzeichen am Ende).
- Matter-/Google-Geräte erscheinen erst in der Liste, wenn sie **in Home Assistant** eingebunden sind.

**Tipps**
- Legen Sie ein **eigenes Token nur für OctaLedger** an: Sie können es jederzeit löschen, ohne etwas anderes zu stören.
- Matter oder Google Home einbinden? Das geschieht **in Home Assistant**; danach erscheinen die Geräte hier in der Liste.
"""  # noqa: E501


class HomeAssistantAdapter(Adapter):
    """Calls services of a Home Assistant (see the module docstring)."""

    spec = AdapterSpec(
        kind="homeassistant",
        title="Home Assistant",
        description=(
            "Schaltet Geräte, Szenen und Skripte über Ihren Home Assistant. Der Weg zu Matter-"
            "Geräten und Google Home, sofern Sie diese dort eingebunden haben."
        ),
        setup_guide=SETUP_GUIDE,
        config_fields=(
            FieldSpec(
                "base_url",
                "Adresse von Home Assistant",
                required=True,
                placeholder="http://homeassistant.local:8123",
                help="Die Adresse Ihres Home Assistant mit http:// oder https:// und Port.",
            ),
            FieldSpec(
                "token",
                "Zugriffstoken",
                kind="password",
                required=True,
                help="Ein „langlebiges Zugriffstoken“: in Home Assistant unten im Benutzerprofil "
                "erstellen. Wird getrennt gespeichert und nie in Sicherungen oder Anzeigen "
                "gezeigt.",
            ),
            FieldSpec(
                "verify_tls",
                "Zertifikat prüfen (https)",
                advanced=True,
                kind="bool",
                default=True,
                help="Bei https das Zertifikat prüfen. Nur ausschalten, wenn Home Assistant ein "
                "selbst erzeugtes Zertifikat nutzt.",
            ),
        ),
        actions=(
            ActionSpec(
                "turn_on",
                "Einschalten",
                "Schaltet ein Gerät ein, bei Lampen auf Wunsch mit Helligkeit.",
                (
                    _ENTITY_FIELD,
                    FieldSpec(
                        "brightness",
                        "Helligkeit in % (nur Lampen)",
                        kind="int",
                        minimum=1,
                        maximum=100,
                        help="Nur für Lampen („light.…“). Leer lassen für die letzte Helligkeit.",
                    ),
                ),
            ),
            ActionSpec(
                "turn_off",
                "Ausschalten",
                "Schaltet ein Gerät aus.",
                (_ENTITY_FIELD,),
            ),
            ActionSpec(
                "toggle",
                "Umschalten",
                "Schaltet um: an wird aus, aus wird an. Bei jedem Senden erneut.",
                (_ENTITY_FIELD,),
                idempotent=False,
            ),
            ActionSpec(
                "scene",
                "Szene aktivieren",
                "Aktiviert eine Szene.",
                (
                    FieldSpec(
                        "entity_id",
                        "Szene (entity_id)",
                        required=True,
                        choices_from=("scene",),
                        placeholder="scene.abend",
                        help="Der Name der Szene, beginnt mit „scene.“.",
                    ),
                ),
            ),
            ActionSpec(
                "script",
                "Skript ausführen",
                "Führt ein Skript von Home Assistant aus.",
                (
                    FieldSpec(
                        "entity_id",
                        "Skript (entity_id)",
                        required=True,
                        choices_from=("script",),
                        placeholder="script.feierabend",
                        help="Der Name des Skripts, beginnt mit „script.“.",
                    ),
                ),
                idempotent=False,
            ),
            ActionSpec(
                "media_play",
                "Musik abspielen",
                "Spielt eine Stream-Adresse (z. B. Internetradio) auf einem Lautsprecher oder "
                "Display ab, das Home Assistant kennt (Sonos, Cast, AirPlay ...).",
                (_MEDIA_PLAYER_FIELD, _MEDIA_URL_FIELD, _MEDIA_TYPE_FIELD),
                idempotent=False,
                capability="music",
            ),
            ActionSpec(
                "media_pause",
                "Wiedergabe pausieren",
                "Hält die Wiedergabe eines Mediengeräts an (Fortsetzen ist möglich).",
                (_MEDIA_PLAYER_FIELD,),
                capability="music",
            ),
            ActionSpec(
                "media_stop",
                "Wiedergabe beenden",
                "Beendet die Wiedergabe eines Mediengeräts ganz.",
                (_MEDIA_PLAYER_FIELD,),
                capability="music",
            ),
            ActionSpec(
                "media_volume",
                "Lautstärke setzen",
                "Stellt die Lautstärke eines Mediengeräts ein.",
                (
                    _MEDIA_PLAYER_FIELD,
                    FieldSpec(
                        "volume",
                        "Lautstärke in %",
                        kind="int",
                        required=True,
                        minimum=0,
                        maximum=100,
                        help="0 = stumm, 100 = voll. Es ändert nur dieses Gerät.",
                    ),
                ),
                capability="music",
            ),
            ActionSpec(
                "service",
                "Beliebigen Dienst aufrufen",
                "Für alles andere: ruft einen Dienst „bereich.dienst“ mit optionalen Daten auf.",
                (
                    FieldSpec(
                        "domain",
                        "Bereich",
                        required=True,
                        placeholder="light",
                        help="Der Bereich des Dienstes, z. B. „light“ oder „climate“.",
                    ),
                    FieldSpec(
                        "service",
                        "Dienst",
                        required=True,
                        placeholder="turn_on",
                        help="Der Name des Dienstes, z. B. „turn_on“ oder „set_temperature“.",
                    ),
                    FieldSpec(
                        "entity_id",
                        "Gerät (optional)",
                        placeholder="light.schreibtisch",
                        help="Auf welches Gerät sich der Dienst bezieht (wenn er eines braucht).",
                    ),
                    FieldSpec(
                        "data",
                        "Weitere Daten als JSON (optional)",
                        placeholder='{"brightness_pct": 40}',
                        help="Zusätzliche Angaben für den Dienst als JSON-Objekt.",
                    ),
                ),
                idempotent=False,
            ),
        ),
        can_discover=True,
    )

    def __init__(self, session_factory: SessionFactory = new_session) -> None:
        """Create the adapter (``session_factory`` is replaceable for tests)."""
        self._session_factory = session_factory

    # ------------------------------------------------------------------ validation

    def validate_config(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Check the settings: a plain http(s) address (the token is a separate secret)."""
        config = super().validate_config(values)
        config["base_url"] = check_base_url(config["base_url"])
        return config

    def validate_action(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Check the entity id, the service name and the extra JSON data."""
        cleaned = super().validate_action(params)
        action = cleaned["action"]
        entity = cleaned.get("entity_id")
        if entity is not None and not _ENTITY.match(entity):
            raise ValidationError(
                f"Invalid entity id {entity!r}",
                user_message="„Gerät“ muss im Format „bereich.name“ stehen, z. B. "
                "light.schreibtisch.",
                details={"field": "entity_id"},
            )
        if action.startswith("media_"):
            _check_media(cleaned)
        if action in ("scene", "script") and not str(entity).startswith(f"{action}."):
            raise ValidationError(
                f"Entity is not a {action}",
                user_message=f"Der Name muss mit „{action}.“ beginnen.",
                details={"field": "entity_id"},
            )
        if (
            action == "turn_on"
            and cleaned.get("brightness")
            and not str(entity).startswith("light.")
        ):
            raise ValidationError(
                "Brightness for a non-light",
                user_message="Eine Helligkeit gibt es nur für Lampen („light.…“).",
                details={"field": "brightness"},
            )
        if action == "service":
            for name in ("domain", "service"):
                if not _WORD.match(str(cleaned[name])):
                    raise ValidationError(
                        f"Invalid {name} {cleaned[name]!r}",
                        user_message="Bereich und Dienst dürfen nur Kleinbuchstaben, Ziffern und "
                        "„_“ enthalten.",
                        details={"field": name},
                    )
            if cleaned.get("data"):
                _data_object(cleaned["data"])
        return cleaned

    # ----------------------------------------------------------------------- music

    def music_play_params(
        self, source: MusicSource, volume: int, options: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        """Volume first, then the title, on the media player the user chose."""
        entity = options.get("entity_id", "")
        if not entity.startswith("media_player."):
            raise ValidationError(
                "No media player chosen",
                user_message="Bitte wählen Sie das Mediengerät (Lautsprecher oder Display).",
            )
        if source.kind is SourceKind.SPOTIFY:
            media = f"spotify:{source.ref}"
        elif source.kind is SourceKind.YOUTUBE:
            media = source.youtube_url  # played via Cast if Home Assistant supports it [U]
        else:
            media = source.ref
        return [
            {"action": "media_volume", "entity_id": entity, "volume": volume},
            {"action": "media_play", "entity_id": entity, "media_url": media},
        ]

    def music_stop_params(
        self, play_params: Mapping[str, Any], pause: bool = False
    ) -> dict[str, Any] | None:
        """Stop (or pause) the media player that the play action used."""
        entity = play_params.get("entity_id")
        if not entity:
            return None
        return {"action": "media_pause" if pause else "media_stop", "entity_id": entity}

    # ----------------------------------------------------------------- operations

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """Ask the API root; it answers only to a valid token."""
        response = self._call(config, secrets, "GET", "/api/", None, timeout)
        status = response.status_code
        response.close()
        self._raise_for_status(status, checking=True)
        return "Home Assistant ist erreichbar und das Zugriffstoken wird akzeptiert."

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Call the service that belongs to the action."""
        domain, service, data = _service_call(params)
        path = f"/api/services/{domain}/{service}"
        response = self._call(config, secrets, "POST", path, data, timeout)
        status = response.status_code
        response.close()
        self._raise_for_status(status, checking=False)
        return f"Dienst {domain}.{service} aufgerufen."

    def discover(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> dict[str, list[dict[str, str]]]:
        """List lights, switches, scenes ... (``{"light": [{"id", "name"}]}``)."""
        response = self._call(config, secrets, "GET", "/api/states", None, timeout)
        status = response.status_code
        if status != 200:
            response.close()
            self._raise_for_status(status, checking=True)
        body = read_limited(response)
        try:
            states = json.loads(body)
        except ValueError as exc:
            raise IntegrationError(
                "Home Assistant sent no valid JSON",
                user_message="Home Assistant hat keine lesbare Geräteliste geliefert.",
            ) from exc
        found: dict[str, list[dict[str, str]]] = {domain: [] for domain in DISCOVER_DOMAINS}
        for state in states if isinstance(states, list) else []:
            entity = state.get("entity_id") if isinstance(state, dict) else None
            if not isinstance(entity, str) or "." not in entity:
                continue
            domain = entity.split(".", 1)[0]
            if domain in found and len(found[domain]) < MAX_DISCOVERED_PER_DOMAIN:
                attributes = state.get("attributes")
                name = attributes.get("friendly_name") if isinstance(attributes, dict) else None
                found[domain].append({"id": entity, "name": str(name or entity)[:100]})
        return {
            domain: sorted(items, key=lambda i: i["name"].casefold())
            for domain, items in found.items()
            if items
        }

    # -------------------------------------------------------------------- internals

    def _call(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        method: str,
        path: str,
        body: dict[str, Any] | None,
        timeout: float,
    ) -> Any:
        token = secrets.get("token")
        if not token:
            raise IntegrationError(
                "No access token stored",
                user_message="Es ist kein Zugriffstoken gespeichert. Bitte in der "
                "Verbindung eintragen.",
            )
        headers = {"Authorization": f"Bearer {token}", "User-Agent": "OctaLedger"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        return send(
            self._session_factory,
            method,
            str(config["base_url"]).rstrip("/") + path,
            headers=headers,
            data=data,
            timeout=timeout,
            verify=bool(config.get("verify_tls", True)),
        )

    @staticmethod
    def _raise_for_status(status: int, *, checking: bool) -> None:
        if 200 <= status < 300:
            return
        if status in (401, 403):
            raise IntegrationError(
                f"HTTP {status}",
                user_message="Home Assistant lehnt das Zugriffstoken ab. Bitte ein neues "
                "langlebiges Zugriffstoken erstellen und eintragen.",
            )
        if status == 404 and not checking:
            raise IntegrationError(
                "HTTP 404",
                user_message="Home Assistant kennt diesen Dienst nicht. Bitte „Bereich“ und "
                "„Dienst“ prüfen.",
            )
        if 300 <= status < 400:
            raise IntegrationError(
                f"HTTP {status} redirect not followed",
                user_message=f"Das Ziel leitet weiter (HTTP {status}). Weiterleitungen werden aus "
                "Sicherheitsgründen nicht befolgt; tragen Sie die endgültige Adresse ein.",
            )
        raise IntegrationError(
            f"HTTP {status}",
            user_message=f"Home Assistant hat die Anfrage abgelehnt (HTTP {status}).",
        )


def _data_object(text: str) -> dict[str, Any]:
    """Parse the extra JSON data; it must be an object."""
    try:
        data = json.loads(text)
    except ValueError:
        raise ValidationError(
            "Extra data is not valid JSON",
            user_message="Die weiteren Daten sind kein gültiges JSON.",
            details={"field": "data"},
        ) from None
    if not isinstance(data, dict):
        raise ValidationError(
            "Extra data is not an object",
            user_message='Die weiteren Daten müssen ein JSON-Objekt sein, z. B. {"a": 1}.',
            details={"field": "data"},
        )
    return data


def _check_media(cleaned: dict[str, Any]) -> None:
    """Validate the media device and (for playing) the stream address."""
    if not str(cleaned.get("entity_id", "")).startswith("media_player."):
        raise ValidationError(
            "Not a media player",
            user_message="Das Gerät muss mit „media_player.“ beginnen.",
            details={"field": "entity_id"},
        )
    url = cleaned.get("media_url")
    if url is None:
        return
    url = str(url).strip()
    if url.startswith(_MEDIA_SCHEMES):
        if len(url) > 500 or any(c.isspace() or ord(c) < 32 for c in url):
            raise ValidationError(
                "Invalid media identifier",
                user_message="Die Medienangabe enthält Leerzeichen oder ist zu lang.",
                details={"field": "media_url"},
            )
        cleaned["media_url"] = url
        return
    # A web address: the speaker fetches it, possibly from the home network, so private addresses
    # are fine here; loopback, link-local and metadata addresses never are.
    cleaned["media_url"] = check_media_url(url, allow_lan=True)


def _service_call(params: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Translate an action into ``(domain, service, request body)``."""
    action = str(params["action"])
    entity = params.get("entity_id")
    if action == "turn_on":
        if params.get("brightness"):
            return "light", "turn_on", {"entity_id": entity, "brightness_pct": params["brightness"]}
        return "homeassistant", "turn_on", {"entity_id": entity}
    if action == "turn_off":
        return "homeassistant", "turn_off", {"entity_id": entity}
    if action == "toggle":
        return "homeassistant", "toggle", {"entity_id": entity}
    if action in ("scene", "script"):
        return action, "turn_on", {"entity_id": entity}
    if action == "media_play":
        return (
            "media_player",
            "play_media",
            {
                "entity_id": entity,
                "media_content_id": params["media_url"],
                "media_content_type": params.get("media_type") or "music",
            },
        )
    if action in ("media_pause", "media_stop"):
        return "media_player", action, {"entity_id": entity}
    if action == "media_volume":
        return (
            "media_player",
            "volume_set",
            {
                "entity_id": entity,
                "volume_level": int(params["volume"]) / 100,
            },
        )
    body = _data_object(params["data"]) if params.get("data") else {}
    if entity:
        body["entity_id"] = entity
    return str(params["domain"]), str(params["service"]), body
