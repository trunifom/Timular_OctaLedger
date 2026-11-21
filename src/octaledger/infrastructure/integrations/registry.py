"""The adapters shipped with OctaLedger.

``default_adapters()`` builds the mapping ``kind -> adapter`` that the agent hands to the
integration service. Adding an adapter means writing the module and listing it here; nothing
else (storage, API, dashboard) needs to change, because adapters describe themselves.
"""

from __future__ import annotations

from octaledger.infrastructure.integrations.base import Adapter


def default_adapters() -> dict[str, Adapter]:
    """Return one instance of every shipped adapter, keyed by its ``spec.kind``."""
    adapters: list[Adapter] = []
    return {adapter.spec.kind: adapter for adapter in adapters}
