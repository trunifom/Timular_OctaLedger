"""Demo adapter ("Testverbindung / Probelauf"): practise the whole control mode without any device.

Nothing leaves the computer: every action is acknowledged with a message that says what *would*
have been sent. The connection can also simulate failures, so retry behaviour, the job history
and the error messages of the interface can be tried safely before a real target is connected.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Final

from octaledger.core.errors import IntegrationConnectionError, IntegrationError
from octaledger.infrastructure.integrations.base import (
    ActionSpec,
    Adapter,
    AdapterSpec,
    FieldSpec,
)

logger = logging.getLogger(__name__)

SETUP_GUIDE: Final = """\
**Wofür:** Zum **Üben und Testen** ohne Lampe, Home Assistant oder Bridge. Nichts wird gesendet; jede Aktion wird
nur bestätigt („wäre gesendet worden“).

1. **Verbindung anlegen** (keine Angaben nötig).
2. Einer Würfelseite die Aktion **Nachricht (Probelauf)** zuordnen (Seite *Würfel verwalten*, Modus *Steuerung*).
3. Würfel drehen und unter **Smarthome & Verbindungen** den **Verlauf** ansehen.

Unter *Erweiterte Einstellungen* können Sie **Fehler simulieren** („nicht erreichbar“ prüft das automatische
Wiederholen, „Fehler“ zeigt die Fehlermeldung), um zu sehen, wie sich OctaLedger dann verhält.
"""  # noqa: E501


class DemoAdapter(Adapter):
    """Acknowledges everything; optionally simulates a failure."""

    spec = AdapterSpec(
        kind="demo",
        title="Testverbindung (Probelauf)",
        description=(
            "Zum Üben ohne Geräte: Aktionen werden nur bestätigt, nichts wird gesendet. Fehler "
            "lassen sich simulieren."
        ),
        setup_guide=SETUP_GUIDE,
        config_fields=(
            FieldSpec(
                "mode",
                "Verhalten",
                kind="choice",
                advanced=True,
                default="ok",
                choices=(
                    ("ok", "Immer erfolgreich"),
                    ("unreachable", "Ziel nicht erreichbar simulieren (wird wiederholt)"),
                    ("error", "Fehler simulieren (wird nicht wiederholt)"),
                ),
                help="Wie die Testverbindung antwortet. Voreinstellung: immer erfolgreich.",
            ),
        ),
        actions=(
            ActionSpec(
                "say",
                "Nachricht (Probelauf)",
                "Tut so, als würde diese Nachricht gesendet.",
                (
                    FieldSpec(
                        "text",
                        "Nachricht",
                        default="Hallo",
                        placeholder="Licht an",
                        help="Ein beliebiger Text für den Verlauf. Es wird nichts gesendet.",
                    ),
                ),
            ),
        ),
    )

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """The demo target is always "reachable" unless a failure is simulated."""
        self._maybe_fail(config)
        return "Testverbindung bereit (es wird nichts gesendet)."

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Acknowledge the action (or fail as configured)."""
        self._maybe_fail(config)
        text = str(params.get("text") or "Hallo")
        logger.info("Demo action executed")
        return f"Probelauf: „{text}“ wäre jetzt gesendet worden."

    @staticmethod
    def _maybe_fail(config: Mapping[str, Any]) -> None:
        mode = config.get("mode", "ok")
        if mode == "unreachable":
            raise IntegrationConnectionError(
                "Simulated: target unreachable",
                user_message="Simuliert: Das Ziel ist nicht erreichbar.",
            )
        if mode == "error":
            raise IntegrationError(
                "Simulated error", user_message="Simuliert: Das Ziel meldet einen Fehler."
            )
