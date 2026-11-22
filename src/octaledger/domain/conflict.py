"""Two cubes, one target: when commands contradict each other (pure rules).

Several cubes may control the same room. Nothing is merged silently: commands are sent in the
order they arrive (the later one wins), and when two **different** cubes send **different**
commands to the **same object** within a short window, the later job gets a note saying so, which
the history shows. Same command twice is harmless and not a conflict.

The "object" is whatever the action names: a Home Assistant entity, a Hue light/group/scene, an
MQTT topic. Actions without such a field (a web address call) are never compared.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Final

#: Commands of different cubes closer than this are checked for a conflict.
WINDOW: Final = timedelta(seconds=5)
#: The parameters that name the object an action acts on, in the order they are tried.
TARGET_KEYS: Final = ("entity_id", "light_id", "group_id", "scene_id", "topic")


def target_of(params: Mapping[str, Any]) -> str | None:
    """The object an action acts on (``None`` when the action names none)."""
    for key in TARGET_KEYS:
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return f"{key}={value.strip()}"
    return None


def conflicts(new: Mapping[str, Any], other: Mapping[str, Any]) -> bool:
    """Whether two commands act on the same object but differ (so one undoes the other)."""
    target = target_of(new)
    return target is not None and target == target_of(other) and dict(new) != dict(other)


def conflict_note(other_name: str, seconds: float) -> str:
    """The note of the later job."""
    return (
        f"Konflikt: {other_name} hat vor {max(0, round(seconds))} s dasselbe Ziel anders "
        "angesteuert. Der später gesendete Befehl gilt."
    )
