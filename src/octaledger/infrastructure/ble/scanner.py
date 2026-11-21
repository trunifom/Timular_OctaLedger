"""Explicit, user-driven BLE discovery.

Responsibility
--------------
Scan for nearby Bluetooth LE devices **only when the user asks for it** and report what was
found. The scanner never connects to anything by itself (``docs/TESTPLAN.md``: "never connect
unknown devices automatically").

Design notes
------------
* Devices that advertise the orientation service are flagged as *candidates* and listed
  first, but **no device is filtered out**: names and service filters must not silently
  exclude other hardware generations (``docs/BLE_PROTOCOL.md``).
* A scan can fail for ordinary reasons (Bluetooth switched off, no adapter, permissions);
  these are translated into :class:`BleConnectionError` with a helpful German message.
* The Bleak scanner class is injectable so the logic is testable without a radio.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final

from bleak import BleakScanner
from bleak.exc import BleakError

from octaledger.core.errors import BleConnectionError, ValidationError
from octaledger.infrastructure.ble.protocol import ORIENTATION_SERVICE_UUID, normalize_uuid

logger = logging.getLogger(__name__)

#: Accepted scan duration range in seconds.
MIN_SCAN_SECONDS: Final = 1.0
MAX_SCAN_SECONDS: Final = 30.0
DEFAULT_SCAN_SECONDS: Final = 5.0

#: ``discover(timeout, return_adv=True)`` style callable (injectable for tests).
DiscoverFn = Callable[..., Awaitable[dict[str, tuple[Any, Any]]]]


@dataclass(frozen=True, slots=True)
class ScanResult:
    """One device seen during a scan.

    Attributes:
        address: Platform address/identifier needed to connect (a hint, not an identity).
        name: Advertised local name, if any.
        rssi: Signal strength in dBm (closer to 0 is stronger), if known.
        service_uuids: Advertised service UUIDs (lower case).
        is_candidate: ``True`` if it advertises the orientation service.

    A device can also be recognised by its *name* (:attr:`looks_like_tracker`): some trackers
    only announce their services after a connection is made, so the orientation service is not
    in the advertisement even though the device is the cube.
    """

    address: str
    name: str | None
    rssi: int | None
    service_uuids: tuple[str, ...]
    is_candidate: bool

    @property
    def looks_like_tracker(self) -> bool:
        """``True`` if the advertised name suggests a Timeular/ZEI tracker (a hint only)."""
        name = (self.name or "").casefold()
        return self.is_candidate or "timeular" in name or name.startswith("zei")

    @property
    def label(self) -> str:
        """Short human-readable label for lists ("name (-60 dBm)")."""
        name = self.name or "Unbenanntes Gerät"
        return f"{name} ({self.rssi} dBm)" if self.rssi is not None else name


def _result(address: str, device: Any, advertisement: Any) -> ScanResult:
    """Convert Bleak objects into a :class:`ScanResult` (tolerant of missing fields)."""
    uuids = tuple(
        sorted(normalize_uuid(u) for u in (getattr(advertisement, "service_uuids", None) or []))
    )
    name = getattr(advertisement, "local_name", None) or getattr(device, "name", None)
    rssi = getattr(advertisement, "rssi", None)
    return ScanResult(
        address=str(address),
        name=str(name) if name else None,
        rssi=int(rssi) if isinstance(rssi, int) else None,
        service_uuids=uuids,
        is_candidate=normalize_uuid(ORIENTATION_SERVICE_UUID) in uuids,
    )


def sort_results(results: list[ScanResult]) -> list[ScanResult]:
    """Probable trackers first, then by signal strength (strongest first), then by name.

    Nothing is removed: a name or service filter must never hide another hardware generation.
    """
    return sorted(
        results,
        key=lambda r: (
            not r.is_candidate,
            not r.looks_like_tracker,
            -(r.rssi if r.rssi is not None else -999),
            r.name or "",
        ),
    )


async def scan(
    timeout: float = DEFAULT_SCAN_SECONDS, *, discover: DiscoverFn | None = None
) -> list[ScanResult]:
    """Scan for BLE devices for ``timeout`` seconds.

    Args:
        timeout: Scan duration (1..30 s).
        discover: Replacement for ``BleakScanner.discover`` (tests).

    Returns:
        All devices seen, candidates first. May be empty.

    Raises:
        ValidationError: If ``timeout`` is out of range.
        BleConnectionError: If the scan could not run (Bluetooth off, no adapter ...).
    """
    if not MIN_SCAN_SECONDS <= timeout <= MAX_SCAN_SECONDS:
        raise ValidationError(
            f"Scan timeout must be {MIN_SCAN_SECONDS}..{MAX_SCAN_SECONDS} s",
            user_message=f"Die Suchdauer muss zwischen {MIN_SCAN_SECONDS:g} und "
            f"{MAX_SCAN_SECONDS:g} Sekunden liegen.",
            details={"timeout": timeout},
        )
    discover_fn: DiscoverFn = discover or BleakScanner.discover
    logger.info("BLE scan started (%.1f s)", timeout)
    try:
        found = await discover_fn(timeout=timeout, return_adv=True)
    except (BleakError, OSError, TimeoutError) as exc:
        raise BleConnectionError(
            f"BLE scan failed: {exc}",
            user_message=(
                "Die Bluetooth-Suche ist fehlgeschlagen. Ist Bluetooth eingeschaltet und "
                "ein Bluetooth-LE-Adapter vorhanden?"
            ),
        ) from exc
    results = sort_results([_result(address, dev, adv) for address, (dev, adv) in found.items()])
    logger.info(
        "BLE scan finished: %d device(s), %d candidate(s)",
        len(results),
        sum(r.is_candidate for r in results),
    )
    return results
