"""Validate the expected one-byte orientation protocol."""


def decode_orientation(payload: bytes) -> int:
    """Return 0..8; zero remains neutral without business interpretation."""
    if len(payload) != 1:
        raise ValueError("Orientation packet must contain exactly one byte")
    value = payload[0]
    if value > 8:
        raise ValueError("Unsupported orientation value")
    return value
