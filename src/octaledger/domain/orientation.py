"""Validate the expected one-byte orientation protocol.

The community reference describes a single byte per notification: ``1..8`` identify the
eight faces and ``0`` means "no stable face" (neutral). This is *not* a proof for every
firmware generation; the decoder therefore only validates the documented shape and never
guesses what a value means for the business logic.
"""

from octaledger.core.errors import ProtocolError

#: Highest technical face number accepted by the decoder.
MAX_ORIENTATION_VALUE = 8


def decode_orientation(payload: bytes) -> int:
    """Return the face number ``0..8``; zero remains neutral without interpretation.

    Args:
        payload: Raw bytes of one characteristic notification.

    Returns:
        The validated technical face number.

    Raises:
        ProtocolError: If the payload is not exactly one byte or the value is
            outside ``0..8``. ``ProtocolError`` is also a ``ValueError``.
    """
    if len(payload) != 1:
        raise ProtocolError(
            "Orientation packet must contain exactly one byte",
            details={"length": len(payload)},
        )
    value = payload[0]
    if value > MAX_ORIENTATION_VALUE:
        raise ProtocolError("Unsupported orientation value", details={"value": value})
    return value
