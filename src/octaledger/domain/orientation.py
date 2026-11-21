"""Validate the expected one-byte orientation protocol.

The community reference describes a single byte per notification: ``1..8`` identify the
eight faces and ``0`` means "no stable face" (neutral). This is *not* a proof for every
firmware generation; the decoder therefore only validates the documented shape and never
guesses what a value means for the business logic.
"""

from octaledger.core.errors import ProtocolError

#: Highest technical face number accepted by the decoder.
MAX_ORIENTATION_VALUE = 8
#: Raw values meaning "tracker rests in its base/charging holder" (community reference:
#: ``0`` and ``10``). Both are normalised to ``0`` (neutral). Kept as one table so it can
#: be adjusted in a single place once real hardware has been observed (BLE_PROTOCOL.md).
BASE_VALUES = frozenset({0, 10})


def decode_orientation(payload: bytes) -> int:
    """Return the face number ``0..8``; base values (``0``, ``10``) become ``0`` (neutral).

    Args:
        payload: Raw bytes of one characteristic notification.

    Returns:
        The validated technical face number.

    Raises:
        ProtocolError: If the payload is not exactly one byte or the value is
            neither a face ``1..8`` nor a base value. ``ProtocolError`` is also a
            ``ValueError``; its message carries the raw bytes in hex for diagnosis.
    """
    if len(payload) != 1:
        raise ProtocolError(
            f"Orientation packet must contain exactly one byte (len={len(payload)} "
            f"raw=0x{payload.hex() or '-'})",
            details={"length": len(payload), "raw": payload.hex()},
        )
    value = payload[0]
    if value in BASE_VALUES:
        return 0
    if value > MAX_ORIENTATION_VALUE:
        raise ProtocolError(
            f"Unsupported orientation value (raw=0x{value:02X})", details={"value": value}
        )
    return value
