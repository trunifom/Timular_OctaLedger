"""UUIDs, capability discovery and payload decoding for the tracker's GATT profile.

Responsibility
--------------
Everything that knows *what the bytes mean*, independent of the Bluetooth stack:

* the community-documented UUIDs (see ``docs/BLE_PROTOCOL.md``; **not** a universal proof
  for every firmware generation, hence capability discovery instead of blind assumptions),
* :func:`discover_capabilities`, which inspects the GATT services a device really offers and
  decides whether it can be used (orientation characteristic with notify/indicate),
* strict decoders for the orientation byte, the optional battery level and the optional
  model/firmware strings.

Safety rule: OctaLedger only ever **reads and subscribes**. There is deliberately no write
operation anywhere in the BLE layer (no motor/LED/firmware commands, Pflichtenheft section 2).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from octaledger.core.errors import ProtocolError, UnsupportedDeviceError
from octaledger.domain.models import ButtonPress
from octaledger.domain.orientation import decode_orientation

#: Community-documented orientation service and characteristic (one byte, 0..8).
ORIENTATION_SERVICE_UUID: Final = "c7e70010-c847-11e6-8175-8c89a55d403c"
ORIENTATION_CHARACTERISTIC_UUID: Final = "c7e70012-c847-11e6-8175-8c89a55d403c"

#: The cube's button (community reference, **not hardware-confirmed**): one byte,
#: 0 = short press, 1 = long press.
BUTTON_CHARACTERISTIC_UUID: Final = "c7e70021-c847-11e6-8175-8c89a55d403c"

#: Standard Bluetooth SIG services/characteristics (optional extras, read-only).
BATTERY_SERVICE_UUID: Final = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID: Final = "00002a19-0000-1000-8000-00805f9b34fb"
DEVICE_INFO_SERVICE_UUID: Final = "0000180a-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_UUID: Final = "00002a24-0000-1000-8000-00805f9b34fb"
FIRMWARE_REVISION_UUID: Final = "00002a26-0000-1000-8000-00805f9b34fb"

#: Upper bound for informational strings read from the device.
MAX_TEXT_LENGTH: Final = 100


def normalize_uuid(value: str) -> str:
    """Return a UUID in lower case for reliable comparison."""
    return value.strip().lower()


@dataclass(frozen=True, slots=True)
class GattCharacteristic:
    """A characteristic as reported by the Bluetooth stack (transport neutral)."""

    uuid: str
    #: Lower-case property names such as ``read``, ``notify``, ``indicate``, ``write``.
    properties: frozenset[str]


@dataclass(frozen=True, slots=True)
class GattService:
    """A GATT service with its characteristics (transport neutral)."""

    uuid: str
    characteristics: tuple[GattCharacteristic, ...]


@dataclass(frozen=True, slots=True)
class DeviceCapabilities:
    """What a connected device can do, derived from its real GATT layout.

    Attributes:
        orientation_mode: ``"notify"`` or ``"indicate"`` (notify preferred).
        can_read_orientation: Whether the initial value can be read before subscribing.
        has_battery / has_model / has_firmware: Optional read-only information.
        has_button: Whether the button characteristic can be subscribed to (notify/indicate).
        service_uuids: Every service the device offered (for the compatibility report).
    """

    orientation_mode: str
    can_read_orientation: bool
    has_battery: bool
    has_model: bool
    has_firmware: bool
    service_uuids: tuple[str, ...]
    has_button: bool = False


def _find(
    services: Iterable[GattService], service_uuid: str, char_uuid: str
) -> GattCharacteristic | None:
    """Return the characteristic ``char_uuid`` inside service ``service_uuid`` if present."""
    wanted_service, wanted_char = normalize_uuid(service_uuid), normalize_uuid(char_uuid)
    for service in services:
        if normalize_uuid(service.uuid) != wanted_service:
            continue
        for characteristic in service.characteristics:
            if normalize_uuid(characteristic.uuid) == wanted_char:
                return characteristic
    return None


def discover_capabilities(services: Iterable[GattService]) -> DeviceCapabilities:
    """Decide from the offered GATT services whether and how the device can be used.

    Args:
        services: Services reported by the Bluetooth stack.

    Returns:
        The capabilities of the device.

    Raises:
        UnsupportedDeviceError: If the orientation characteristic is missing or offers
            neither notify nor indicate. The error lists the offered service UUIDs so that
            a compatibility report can be written (``details['services']``).
    """
    services = list(services)
    offered = tuple(sorted(normalize_uuid(s.uuid) for s in services))
    orientation = _find(services, ORIENTATION_SERVICE_UUID, ORIENTATION_CHARACTERISTIC_UUID)
    if orientation is None:
        raise UnsupportedDeviceError(
            "Orientation characteristic not found",
            user_message=(
                "Dieses Gerät bietet den erwarteten Orientierungsdienst nicht an. "
                "Es ist vermutlich kein kompatibler Tracker oder eine andere Firmware."
            ),
            details={"services": list(offered)},
        )
    properties = {p.lower() for p in orientation.properties}
    if "notify" in properties:
        mode = "notify"
    elif "indicate" in properties:
        mode = "indicate"
    else:
        raise UnsupportedDeviceError(
            "Orientation characteristic offers neither notify nor indicate",
            details={"properties": sorted(properties), "services": list(offered)},
        )
    return DeviceCapabilities(
        orientation_mode=mode,
        can_read_orientation="read" in properties,
        has_battery=_has_read(services, BATTERY_SERVICE_UUID, BATTERY_LEVEL_UUID),
        has_model=_has_read(services, DEVICE_INFO_SERVICE_UUID, MODEL_NUMBER_UUID),
        has_firmware=_has_read(services, DEVICE_INFO_SERVICE_UUID, FIRMWARE_REVISION_UUID),
        service_uuids=offered,
        has_button=_has_button(services),
    )


def _has_button(services: list[GattService]) -> bool:
    """Whether any service offers the button characteristic with notify or indicate."""
    wanted = normalize_uuid(BUTTON_CHARACTERISTIC_UUID)
    return any(
        normalize_uuid(c.uuid) == wanted
        and {p.lower() for p in c.properties} & {"notify", "indicate"}
        for s in services
        for c in s.characteristics
    )


def _has_read(services: list[GattService], service_uuid: str, char_uuid: str) -> bool:
    """Whether an optional characteristic exists and is readable."""
    characteristic = _find(services, service_uuid, char_uuid)
    return characteristic is not None and "read" in {p.lower() for p in characteristic.properties}


# ------------------------------------------------------------------------------ decoders


def decode_orientation_payload(payload: bytes) -> int:
    """Decode one orientation notification (``0..8``).

    Raises:
        ProtocolError: If the payload is not exactly one byte in range.
    """
    return decode_orientation(payload)


def decode_battery_level(payload: bytes) -> int:
    """Decode the standard battery level (one byte, percent ``0..100``).

    Raises:
        ProtocolError: If the payload is malformed.
    """
    if len(payload) != 1 or payload[0] > 100:
        raise ProtocolError(
            "Battery level must be one byte 0..100", details={"length": len(payload)}
        )
    return payload[0]


def decode_button_payload(payload: bytes) -> ButtonPress:
    """Decode one button notification: ``0`` is a short, ``1`` a long press.

    Raises:
        ProtocolError: For anything else; the message carries the raw bytes in hex.
    """
    if len(payload) != 1 or payload[0] not in (0, 1):
        raise ProtocolError(
            f"Unsupported button packet (raw=0x{payload.hex() or '-'})",
            details={"length": len(payload)},
        )
    return ButtonPress.SHORT if payload[0] == 0 else ButtonPress.LONG


def decode_text(payload: bytes) -> str:
    """Decode an informational string (model, firmware) strictly as UTF-8.

    Trailing NUL padding and surrounding whitespace are removed.

    Raises:
        ProtocolError: If the bytes are not valid UTF-8, empty or longer than
            :data:`MAX_TEXT_LENGTH`.
    """
    try:
        text = payload.decode("utf-8").rstrip("\x00").strip()
    except UnicodeDecodeError as exc:
        raise ProtocolError("Device text is not valid UTF-8") from exc
    if not text or len(text) > MAX_TEXT_LENGTH or not text.isprintable():
        raise ProtocolError(
            "Device text is empty, too long or contains control characters",
            details={"length": len(text)},
        )
    return text
