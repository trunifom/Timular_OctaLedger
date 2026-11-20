"""Manual hardware smoke tests - skipped unless explicitly enabled.

These tests talk to REAL Bluetooth hardware. They never run automatically (CI, plain
``pytest``). To run them deliberately on a machine with a tracker nearby::

    set OCTALEDGER_HARDWARE_TESTS=1
    set OCTALEDGER_HARDWARE_ADDRESS=<address shown by the scan test>   (for the connect test)
    .venv\\Scripts\\python.exe -m pytest tests/hardware -s

The tests only scan, read and subscribe; they never write to a device and never connect to
a device you did not name explicitly. Record results in the compatibility matrix of
``docs/TESTPLAN.md`` (model, firmware, OS, adapter, driver, Python, Bleak, app version).
"""

import asyncio
import os

import pytest

from octaledger.infrastructure.ble.client import BleakTransport
from octaledger.infrastructure.ble.protocol import (
    ORIENTATION_CHARACTERISTIC_UUID,
    discover_capabilities,
)
from octaledger.infrastructure.ble.scanner import scan

pytestmark = pytest.mark.skipif(
    os.environ.get("OCTALEDGER_HARDWARE_TESTS") != "1",
    reason="hardware tests are opt-in: set OCTALEDGER_HARDWARE_TESTS=1",
)


def test_scan_lists_nearby_devices() -> None:
    results = asyncio.run(scan(8.0))
    for result in results:
        print(f"{result.address}  candidate={result.is_candidate}  {result.label}")
    assert isinstance(results, list)


@pytest.mark.skipif(
    not os.environ.get("OCTALEDGER_HARDWARE_ADDRESS"),
    reason="set OCTALEDGER_HARDWARE_ADDRESS to the tracker address",
)
def test_connect_discover_and_receive_one_orientation() -> None:
    async def scenario() -> None:
        transport = BleakTransport(os.environ["OCTALEDGER_HARDWARE_ADDRESS"])
        await transport.connect()
        try:
            capabilities = discover_capabilities(await transport.discover())
            print("capabilities:", capabilities)
            if capabilities.can_read_orientation:
                print(
                    "initial orientation byte:",
                    await transport.read(ORIENTATION_CHARACTERISTIC_UUID),
                )
        finally:
            await transport.disconnect()

    asyncio.run(scenario())
