"""Webhook adapter: send a web request to any address (the universal "other standards" adapter).

A *connection* is a base address (``http://host:port``) with optional authorisation; an *action*
is one request to a path on it (method, optional body). That covers IFTTT-style services,
Node-RED, ESPHome, your own scripts and every device with a simple HTTP interface.

Safety rules
------------
* Only ``http`` and ``https`` addresses; the path is appended to the base address, so an action
  can never address another host.
* **Redirects are never followed** (a redirect could point to another scheme or host); a
  redirect answer is reported as an error.
* Environment proxies are ignored (``trust_env = False``): a request to your own network must
  not silently travel through a proxy.
* The answer is **not read** beyond the status line, so a hostile or huge answer costs nothing.
* The authorisation value is a secret (stored separately, never logged, never in an answer).
* A failure is retried only when the request **certainly did not reach the target** (cannot
  connect, name not found). A timeout *after* sending is reported but not retried, because the
  action may already have happened.

Limits: no client certificates, no query-string templates, text values are limited to 500
characters (so a body is short; that is plenty for a switch command).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from requests import Response

from octaledger.core.errors import IntegrationError, ValidationError
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

METHODS: Final = ("GET", "POST", "PUT", "PATCH", "DELETE")
CONTENT_TYPES: Final = (("application/json", "JSON"), ("text/plain", "Text"))
_HEADER_NAME: Final = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")


SETUP_GUIDE: Final = """\
**Wofür:** Eine beliebige Web-Adresse aufrufen, zum Beispiel Node-RED, ESPHome, IFTTT-ähnliche Dienste,
eigene Skripte oder ein **Home-Assistant-Webhook**.

1. **Basisadresse** eintragen, z. B. `http://192.168.1.20:1880` (mit `http://` oder `https://`, ohne Pfad).
2. Nur wenn das Ziel einen Zugang verlangt: unter *Erweiterte Einstellungen* den Namen des Kopfes
   (meist `Authorization`) und den **Zugangswert** eintragen, z. B. `Bearer MEIN-TOKEN`.
3. **Verbindung testen** prüft nur, ob das Ziel antwortet. Was eine Anfrage bewirkt, sehen Sie erst mit
   **Ausprobieren**.
4. Den **Pfad** und die Methode wählen Sie später pro Würfelseite (z. B. `/licht/an`).

**Gut zu wissen**
- Bei einem **Home-Assistant-Webhook** lautet der Pfad `/api/webhook/<ID>`. Die ID ist das Geheimnis, behandeln
  Sie sie wie ein Passwort. Home Assistant antwortet fast immer mit „OK“, **auch bei falscher ID**: Der Test
  kann einen Fehler dort nicht erkennen.
- Weiterleitungen werden nicht befolgt: tragen Sie die endgültige Adresse ein.
"""  # noqa: E501


class WebhookAdapter(Adapter):
    """Sends HTTP requests (see the module docstring for the safety rules)."""

    spec = AdapterSpec(
        kind="webhook",
        title="Webhook (Web-Anfrage)",
        description=(
            "Schickt eine Web-Anfrage an eine beliebige Adresse, zum Beispiel an Node-RED, "
            "ESPHome, IFTTT oder ein eigenes Skript. Die Notlösung für jedes Gerät mit einfacher "
            "Web-Schnittstelle."
        ),
        setup_guide=SETUP_GUIDE,
        config_fields=(
            FieldSpec(
                "base_url",
                "Basisadresse",
                required=True,
                placeholder="http://192.168.1.20:1880",
                help="Adresse des Ziels mit http:// oder https://. Der Pfad der Aktion wird "
                "angehängt.",
            ),
            FieldSpec(
                "auth_header",
                "Name des Zugangs-Kopfes",
                advanced=True,
                default="Authorization",
                help="Nur nötig, wenn das Ziel einen Zugang verlangt (meist „Authorization“).",
            ),
            FieldSpec(
                "auth_value",
                "Zugangswert",
                kind="password",
                help="Zum Beispiel „Bearer MEIN-TOKEN“. Leer lassen, wenn das Ziel keinen Zugang "
                "verlangt.",
            ),
            FieldSpec(
                "verify_tls",
                "Zertifikat prüfen (https)",
                advanced=True,
                kind="bool",
                default=True,
                help="Bei https das Zertifikat des Ziels prüfen. Nur ausschalten, wenn das Ziel "
                "ein selbst erzeugtes Zertifikat nutzt.",
            ),
        ),
        actions=(
            ActionSpec(
                "request",
                "Anfrage senden",
                "Schickt eine Anfrage an einen Pfad des Ziels.",
                (
                    FieldSpec(
                        "path",
                        "Pfad",
                        default="/",
                        required=True,
                        placeholder="/licht/an",
                        help="Beginnt mit „/“ und wird an die Basisadresse angehängt.",
                    ),
                    FieldSpec(
                        "method",
                        "Methode",
                        kind="choice",
                        default="POST",
                        choices=tuple((m, m) for m in METHODS),
                        help="Die Web-Methode. Zum Auslösen genügt meistens POST.",
                    ),
                    FieldSpec(
                        "content_type",
                        "Inhaltstyp",
                        advanced=True,
                        kind="choice",
                        default="application/json",
                        choices=CONTENT_TYPES,
                        help="Art des Inhalts (nur relevant, wenn ein Inhalt gesendet wird).",
                    ),
                    FieldSpec(
                        "body",
                        "Inhalt (optional)",
                        placeholder='{"an": true}',
                        help="Wird mitgesendet, wenn die Methode es erlaubt. Bei JSON muss er "
                        "gültiges JSON sein.",
                    ),
                ),
                idempotent=False,
            ),
        ),
    )

    def __init__(self, session_factory: SessionFactory = new_session) -> None:
        """Create the adapter (``session_factory`` is replaceable for tests)."""
        self._session_factory = session_factory

    # ------------------------------------------------------------------ validation

    def validate_config(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Check the settings: a plain http(s) base address and a valid header name."""
        config = super().validate_config(values)
        config["base_url"] = check_base_url(config["base_url"])
        header = config.get("auth_header")
        if header and not set(header) <= _HEADER_NAME:
            raise ValidationError(
                f"Invalid header name {header!r}",
                user_message="„Name des Zugangs-Kopfes“ darf nur Buchstaben, Ziffern und „-“ "
                "enthalten.",
                details={"field": "auth_header"},
            )
        return config

    def validate_action(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Check the request: a path starting with ``/`` and, for JSON, a parsable body."""
        cleaned = super().validate_action(params)
        path = str(cleaned.get("path", "/"))
        if not path.startswith("/") or path.startswith("//"):
            raise ValidationError(
                f"Invalid path {path!r}",
                user_message="Der Pfad muss mit „/“ beginnen.",
                details={"field": "path"},
            )
        cleaned["path"] = path
        cleaned.setdefault("method", "POST")
        cleaned.setdefault("content_type", "application/json")
        body = cleaned.get("body")
        if body and cleaned["content_type"] == "application/json":
            try:
                json.loads(body)
            except ValueError:
                raise ValidationError(
                    "Body is not valid JSON",
                    user_message="Der Inhalt ist kein gültiges JSON.",
                    details={"field": "body"},
                ) from None
        if body and cleaned["method"] == "GET":
            raise ValidationError(
                "GET with a body",
                user_message="Mit der Methode GET kann kein Inhalt gesendet werden.",
                details={"field": "body"},
            )
        return cleaned

    # ----------------------------------------------------------------- operations

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """Ask the base address once (GET); any answer below 500 proves the target is there."""
        response = self._send(config, secrets, "GET", "/", None, "text/plain", timeout)
        status = response.status_code
        response.close()
        if status in (401, 403):
            raise IntegrationError(
                f"HTTP {status}",
                user_message=f"Das Ziel ist erreichbar, lehnt den Zugang aber ab (HTTP {status}). "
                "Bitte Zugangskopf und -wert prüfen.",
            )
        if status >= 500:
            raise IntegrationError(
                f"HTTP {status}",
                user_message=f"Das Ziel ist erreichbar, meldet aber einen Fehler (HTTP {status}).",
            )
        return f"Das Ziel ist erreichbar (HTTP {status})."

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Send the request of an action; 2xx is success, everything else is an error."""
        response = self._send(
            config,
            secrets,
            str(params.get("method", "POST")),
            str(params.get("path", "/")),
            params.get("body") or None,
            str(params.get("content_type", "application/json")),
            timeout,
        )
        status = response.status_code
        response.close()
        if 200 <= status < 300:
            return f"Anfrage gesendet (HTTP {status})."
        if 300 <= status < 400:
            raise IntegrationError(
                f"HTTP {status} redirect not followed",
                user_message=f"Das Ziel leitet weiter (HTTP {status}). Weiterleitungen werden aus "
                "Sicherheitsgründen nicht befolgt; tragen Sie die endgültige Adresse ein.",
            )
        if status in (401, 403):
            raise IntegrationError(
                f"HTTP {status}",
                user_message=f"Das Ziel lehnt den Zugang ab (HTTP {status}). Bitte Zugangskopf "
                "und -wert prüfen.",
            )
        raise IntegrationError(
            f"HTTP {status}", user_message=f"Das Ziel hat die Anfrage abgelehnt (HTTP {status})."
        )

    # -------------------------------------------------------------------- internals

    def _send(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        method: str,
        path: str,
        body: str | None,
        content_type: str,
        timeout: float,
    ) -> Response:
        """Send one request; failures are classified by :func:`httpio.send`."""
        url = str(config["base_url"]).rstrip("/") + path
        headers = {"User-Agent": "OctaLedger"}
        value = secrets.get("auth_value")
        if value:
            headers[str(config.get("auth_header") or "Authorization")] = value
        if body is not None:
            headers["Content-Type"] = content_type
        return send(
            self._session_factory,
            method,
            url,
            headers=headers,
            data=None if body is None else body.encode("utf-8"),
            timeout=timeout,
            verify=bool(config.get("verify_tls", True)),
        )
