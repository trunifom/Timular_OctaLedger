"""The data sheet of a cube: what a read-out returns and how known values are worded (pure).

A **read-out** lists every characteristic the cube offers and reads those that can be read - read
only, never a write. The result is a list of :class:`Reading`, stored as a snapshot and shown as
the "Datenblatt".

Honesty rule: a value is **interpreted only when its meaning is known** - the standard Bluetooth
characteristics (battery, device information, transmit power) and the cube's orientation and
button values from the community sources. Everything else is shown as the **raw bytes in hex**
with its length and **no invented meaning**. For the accelerometer characteristic only the length
is stated, because the sources disagree about its format.

Characteristics that are not readable (write-only, notify-only) are listed with their properties
and are **not touched**. The DFU service of the cube (firmware update mode) is never read or
written, even if it should offer something readable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

#: ``0000xxxx-0000-1000-8000-00805f9b34fb``: how standard 16-bit UUIDs look in full.
_BASE_SUFFIX: Final = "-0000-1000-8000-00805f9b34fb"
_VENDOR_SUFFIX: Final = "-c847-11e6-8175-8c89a55d403c"

#: Service of the firmware-update mode of the cube (community source). Never touched.
DFU_SERVICE: Final = "c7e70000-c847-11e6-8175-8c89a55d403c"
ACCELEROMETER: Final = "c7e70011-c847-11e6-8175-8c89a55d403c"

#: Most readings kept per snapshot (a sanity limit, the cube has about twenty characteristics).
MAX_READINGS: Final = 200
#: Snapshots kept per cube.
KEEP_SNAPSHOTS: Final = 20

#: ``short uuid -> (German name, how the value is shown)``; kinds: text, percent, dbm, orientation,
#: button, length.
KNOWN: Final[dict[str, tuple[str, str]]] = {
    "2a00": ("Gerätename", "text"),
    "2a07": ("Sendeleistung", "dbm"),
    "2a19": ("Batterie", "percent"),
    "2a23": ("System-ID", "hex"),
    "2a24": ("Modell", "text"),
    "2a25": ("Seriennummer", "text"),
    "2a26": ("Firmware-Version", "text"),
    "2a27": ("Hardware-Version", "text"),
    "2a28": ("Software-Version", "text"),
    "2a29": ("Hersteller", "text"),
    "2a50": ("PnP-ID", "hex"),
    "c7e70012": ("Lage (aktive Seite)", "orientation"),
    "c7e70011": ("Beschleunigungssensor (Format unbestätigt)", "length"),
    "c7e70021": ("Taste", "button"),
}
#: Names of well known services (shown as the service heading).
SERVICES: Final[dict[str, str]] = {
    "1800": "Generic Access",
    "1801": "Generic Attribute",
    "1804": "Tx Power",
    "180a": "Geräteinformation",
    "180f": "Batterie",
    "c7e70010": "Lage (Community)",
    "c7e70020": "Taste und Leuchte (Community)",
    "c7e70030": "Kalibrierung? (nur eine Quelle)",
    "c7e70040": "Unbekannt (Community)",
    "c7e70000": "Firmware-Update (nie angefasst)",
}


@dataclass(frozen=True, slots=True)
class Reading:
    """One characteristic of the cube and, if it could be read, its value.

    Attributes:
        service: Full UUID of the service.
        uuid: Full UUID of the characteristic.
        properties: Lower-case property names (``read``, ``write``, ``notify`` ...).
        raw_hex: The value as hex text, or ``None`` if it was not read.
        error: Why a readable characteristic could not be read (German), or ``None``.
    """

    service: str
    uuid: str
    properties: tuple[str, ...]
    raw_hex: str | None = None
    error: str | None = None

    @property
    def length(self) -> int | None:
        """Number of bytes read (``None`` if not read)."""
        return None if self.raw_hex is None else len(self.raw_hex) // 2


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One stored read-out of a cube.

    Attributes:
        id: Identifier.
        device_id: The cube.
        taken_at: When it was taken (UTC).
        kind: ``datasheet`` (every characteristic) or ``accelerometer`` (a short recording).
        readings: The readings in the order they were taken.
        interval_ms: For a recording, the pause between two reads (else ``None``).
    """

    id: str
    device_id: str
    taken_at: datetime
    kind: str
    readings: tuple[Reading, ...]
    interval_ms: int | None = None


def short_uuid(uuid: str) -> str:
    """The short form of a UUID: 4 digits for standard ones, 8 for the vendor ones."""
    text = uuid.lower()
    if text.endswith(_BASE_SUFFIX) and text.startswith("0000"):
        return text[4:8]
    if text.endswith(_VENDOR_SUFFIX):
        return text[:8]
    return text


def is_forbidden(service: str) -> bool:
    """Whether a service is never read or written (the firmware-update mode)."""
    return service.lower() == DFU_SERVICE


def readable(properties: Sequence[str]) -> bool:
    """Whether a characteristic offers ``read``."""
    return "read" in properties


def name_of(uuid: str) -> str:
    """The German name of a characteristic (``Unbekannt`` when nothing is known)."""
    return KNOWN.get(short_uuid(uuid), ("Unbekannt", ""))[0]


def service_name(uuid: str) -> str:
    """The German name of a service (``Unbekannter Dienst`` when nothing is known)."""
    return SERVICES.get(short_uuid(uuid), "Unbekannter Dienst")


def interpret(reading: Reading) -> str | None:
    """The meaning of a value, or ``None`` when it is not known or was not read.

    Never guesses: an unexpected length gives a plain statement instead of a wrong number.
    """
    if reading.raw_hex is None:
        return None
    raw = bytes.fromhex(reading.raw_hex)
    kind = KNOWN.get(short_uuid(reading.uuid), ("", ""))[1]
    if kind == "text":
        text = raw.decode("utf-8", errors="replace").strip("\x00 ")
        return text or "(leer)"
    if kind == "percent":
        return f"{raw[0]} %" if len(raw) == 1 and raw[0] <= 100 else "Länge oder Wert unerwartet"
    if kind == "dbm":
        return f"{int.from_bytes(raw, 'little', signed=True)} dBm" if len(raw) == 1 else None
    if kind == "orientation":
        if len(raw) != 1:
            return "Länge unerwartet"
        value = raw[0]
        if value == 0:
            return "0 (neutral / Halterung)"
        return f"Seite {value}" if 1 <= value <= 8 else f"Wert {value} (nicht zuordenbar)"
    if kind == "button":
        return {0: "kurzer Druck", 1: "langer Druck"}.get(raw[0]) if len(raw) == 1 else None
    if kind == "length":
        return f"{len(raw)} Byte (Format nicht bestätigt, deshalb nicht gedeutet)"
    return None


def rows(readings: Sequence[Reading]) -> list[dict[str, Any]]:
    """The data sheet as table rows (plain values, ready for a table or a CSV)."""
    return [
        {
            "Dienst": f"{service_name(r.service)} ({short_uuid(r.service)})",
            "Characteristic": f"{name_of(r.uuid)} ({short_uuid(r.uuid)})",
            "Rechte": ", ".join(r.properties),
            "Wert (hex)": r.raw_hex if r.raw_hex is not None else "",
            "Länge": r.length if r.length is not None else "",
            "Deutung": interpret(r) or "",
            "Hinweis": r.error
            or ("" if readable(r.properties) else "nicht lesbar, nicht angefasst"),
        }
        for r in readings
    ]


def to_json(readings: Sequence[Reading]) -> list[dict[str, Any]]:
    """The stored form of a snapshot (a list of plain dictionaries)."""
    return [
        {
            "service": r.service,
            "uuid": r.uuid,
            "properties": list(r.properties),
            "raw_hex": r.raw_hex,
            "error": r.error,
        }
        for r in readings
    ]


def from_json(data: Sequence[Mapping[str, Any]]) -> list[Reading]:
    """Rebuild readings from their stored form (unknown or malformed entries are skipped)."""
    result: list[Reading] = []
    for item in data[:MAX_READINGS]:
        try:
            raw = item.get("raw_hex")
            if raw is not None:
                bytes.fromhex(str(raw))
            result.append(
                Reading(
                    str(item["service"]),
                    str(item["uuid"]),
                    tuple(str(p) for p in item.get("properties", [])),
                    None if raw is None else str(raw),
                    None if item.get("error") is None else str(item["error"]),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return result
