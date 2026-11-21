"""Orientation contract tests without Bluetooth hardware."""

import pytest

from octaledger.domain.orientation import decode_orientation


@pytest.mark.parametrize("side", range(9))
def test_accepts_orientation(side: int) -> None:
    assert decode_orientation(bytes([side])) == side


def test_base_value_ten_is_neutral() -> None:
    assert decode_orientation(b"\x0a") == 0


@pytest.mark.parametrize("payload", [b"", b"\x01\x02", b"\x09", b"\x0b", b"\xff"])
def test_rejects_invalid_packets(payload: bytes) -> None:
    with pytest.raises(ValueError):
        decode_orientation(payload)


@pytest.mark.parametrize(("payload", "raw"), [(b"\x09", "0x09"), (b"\xff", "0xFF")])
def test_invalid_value_message_carries_the_raw_byte(payload: bytes, raw: str) -> None:
    with pytest.raises(ValueError, match=raw):
        decode_orientation(payload)


def test_wrong_length_message_carries_the_raw_hex() -> None:
    with pytest.raises(ValueError, match="raw=0x0102"):
        decode_orientation(b"\x01\x02")
