"""The adapters shipped with OctaLedger.

``default_adapters()`` builds the mapping ``kind -> adapter`` that the agent hands to the
integration service. Adding an adapter means writing the module and listing it here; nothing
else (storage, API, dashboard) needs to change, because adapters describe themselves.
"""

from __future__ import annotations

from octaledger.infrastructure.integrations.base import Adapter
from octaledger.infrastructure.integrations.browser import BrowserAdapter
from octaledger.infrastructure.integrations.demo import DemoAdapter
from octaledger.infrastructure.integrations.homeassistant import HomeAssistantAdapter
from octaledger.infrastructure.integrations.hue import HueAdapter
from octaledger.infrastructure.integrations.mqtt import MqttAdapter
from octaledger.infrastructure.integrations.player import PlayerAdapter
from octaledger.infrastructure.integrations.spotify import SpotifyAdapter
from octaledger.infrastructure.integrations.webhook import WebhookAdapter


def default_adapters() -> dict[str, Adapter]:
    """Return one instance of every shipped adapter, keyed by its ``spec.kind``."""
    adapters: list[Adapter] = [
        WebhookAdapter(),
        MqttAdapter(),
        HomeAssistantAdapter(),
        HueAdapter(),
        PlayerAdapter(),
        SpotifyAdapter(),
        BrowserAdapter(),
        DemoAdapter(),
    ]
    return {adapter.spec.kind: adapter for adapter in adapters}
