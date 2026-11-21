"""A scriptable integration adapter shared by the tests (no network, no real target)."""

from collections.abc import Mapping
from typing import Any

from octaledger.core.errors import IntegrationError
from octaledger.infrastructure.integrations.base import (
    ActionSpec,
    Adapter,
    AdapterSpec,
    FieldSpec,
    PairResult,
)


class FakeAdapter(Adapter):
    """Records every call and raises whatever the test queued in ``script``.

    The only valid password is ``"richtig"``, so credential handling can be observed.
    """

    spec = AdapterSpec(
        kind="fake",
        title="Testverbindung",
        description="Nur für Tests",
        config_fields=(
            FieldSpec("host", "Adresse", required=True),
            FieldSpec("port", "Port", kind="int", minimum=1, maximum=65535, default=80),
            FieldSpec("password", "Passwort", kind="password", required=True),
        ),
        actions=(
            ActionSpec(
                "ping",
                "Anpingen",
                "Sendet ein Signal",
                (FieldSpec("target", "Ziel", required=True, choices_from=("lights",)),),
            ),
            ActionSpec("toggle", "Umschalten", "Schaltet um", idempotent=False),
        ),
        can_pair=True,
        can_discover=True,
    )

    def __init__(self) -> None:
        self.calls: list[tuple[Mapping[str, Any], Mapping[str, str], Mapping[str, Any]]] = []
        self.script: list[BaseException | None] = []

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        if secrets.get("password") != "richtig":
            raise IntegrationError("bad credentials", user_message="Zugangsdaten abgelehnt.")
        return f"Verbunden mit {config['host']}."

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        self.calls.append((dict(config), dict(secrets), dict(params)))
        outcome = self.script.pop(0) if self.script else None
        if outcome is not None:
            raise outcome
        return "gesendet"

    def pair(self, config: Mapping[str, Any], *, timeout: float) -> PairResult:
        return PairResult(
            secrets={"password": "gekoppelt"},
            config={"host": "bridge.local"},
            message="Gekoppelt!",
        )

    def discover(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> dict[str, list[dict[str, str]]]:
        return {"lights": [{"id": "1", "name": "Schreibtisch"}]}
