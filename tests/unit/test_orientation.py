"""Orientation contract tests without Bluetooth hardware."""

import pytest

from octaledger.domain.orientation import decode_orientation


@pytest.mark.parametrize("side", range(9))
def test_accepts_orientation(side: int) -> None:
    assert decode_orientation(bytes([side])) == side


@pytest.mark.parametrize("payload", [b"", b"\x01\x02", b"\x09", b"\xff"])
def test_rejects_invalid_packets(payload: bytes) -> None:
    with pytest.raises(ValueError):
        decode_orientation(payload)
