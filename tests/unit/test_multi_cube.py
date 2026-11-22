"""Several cubes at once: one title per target, stop only by the owner, conflicts noted (AP-55)."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from octaledger.application.device_service import DeviceService
from octaledger.application.tracking_service import Outcome
from octaledger.domain.conflict import WINDOW, conflict_note, conflicts, target_of
from octaledger.domain.models import DeviceMode, EventKind, RawEvent
from tests.unit.test_music_mode import PUBLIC, Env

SPEAKER = {"entity_id": "media_player.wohnzimmer"}
TRACK = "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"


# ------------------------------------------------------------------------- pure rules


def test_target_of_names_the_object_of_an_action() -> None:
    assert target_of({"action": "x", "entity_id": " light.a "}) == "entity_id=light.a"
    assert target_of({"light_id": "7"}) == "light_id=7"
    assert target_of({"topic": "home/lamp"}) == "topic=home/lamp"
    assert target_of({"action": "call", "path": "/x"}) is None


def test_only_different_commands_to_the_same_object_conflict() -> None:
    on = {"action": "turn", "entity_id": "light.a", "state": "on"}
    off = {"action": "turn", "entity_id": "light.a", "state": "off"}
    other = {"action": "turn", "entity_id": "light.b", "state": "off"}
    assert conflicts(off, on)
    assert not conflicts(on, dict(on))  # same command twice: harmless
    assert not conflicts(off, other)  # another object
    assert not conflicts({"action": "call"}, {"action": "call", "x": 1})  # no object named
    assert "Konflikt" in conflict_note("Büro", 2.4) and "vor 2 s" in conflict_note("Büro", 2.4)


# -------------------------------------------------------------------------- two cubes


class Two:
    """The music environment with a second music cube."""

    def __init__(self, env: Env) -> None:
        self.env = env
        self.a = env.cube
        devices = DeviceService(env.storage)
        self.b = devices.register("Küche").id
        devices.set_mode(self.b, DeviceMode.MUSIC)
        self.names = {self.a: "Musik", self.b: "Küche"}

    def event(self, device: str, kind: EventKind, value: int | None) -> RawEvent:
        self.env.sequence += 1
        return RawEvent(
            device_id=device,
            kind=kind,
            sequence=self.env.sequence,
            connection_id=f"c-{device[:4]}",
            raw_value=value,
            received_at=self.env.now,
        )

    def turn(self, device: str, face: int) -> Outcome:
        return self.env.tracking.record_event(
            self.event(device, EventKind.FACE_CHANGE, face)
        ).outcome

    def holder(self, device: str) -> Outcome:
        return self.env.tracking.record_event(self.event(device, EventKind.NEUTRAL, 0)).outcome

    def title(self, device: str, face: int, target: str, link: str, label: str, **kw: Any) -> None:
        self.env.music.set_title(device, face, target, link, label, **kw)

    def state(self, device: str) -> Any:
        return next(s for s in self.env.music.state() if s["device_id"] == device)["playing"]

    def owners(self) -> dict[str, str]:
        with self.env.storage.read() as repos:
            return {
                key.removeprefix("music_owner:"): value
                for key, value in repos.state.items().items()
                if key.startswith("music_owner:")
            }


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def settle(env: Env) -> None:
    """Send everything, also the steps that wait for a short delay (Home Assistant volume)."""
    env.send_all()
    env.now += timedelta(seconds=1)
    env.send_all()


@pytest.fixture
def two(env: Env) -> Two:
    return Two(env)


def test_the_cube_that_started_last_owns_the_target_and_replaces_the_other(
    env: Env, two: Two
) -> None:
    two.title(two.a, 1, env.radio, f"https://{PUBLIC}/a.mp3", "Radio A")
    two.title(two.b, 1, env.radio, f"https://{PUBLIC}/b.mp3", "Radio B")
    two.turn(two.a, 1)
    env.send_all()
    assert two.state(two.a)["label"] == "Radio A"
    env.now += timedelta(seconds=1)
    two.turn(two.b, 1)
    env.send_all()
    assert two.state(two.a) is None  # replaced: A no longer thinks it is playing
    assert two.state(two.b)["label"] == "Radio B"
    assert list(two.owners()) == [env.radio]
    note = next(j.note for j in env.jobs() if j.label == "Radio B" and j.note)
    assert note == "Ersetzt die Musik von Musik."


def test_the_holder_of_a_replaced_cube_does_not_stop_the_new_music(env: Env, two: Two) -> None:
    two.title(two.a, 1, env.radio, f"https://{PUBLIC}/a.mp3", "Radio A")
    two.title(two.b, 1, env.radio, f"https://{PUBLIC}/b.mp3", "Radio B")
    two.turn(two.a, 1)
    env.send_all()
    two.turn(two.b, 1)
    env.send_all()
    sent_before = len(env.sent)
    assert two.holder(two.a) is Outcome.STORED  # A has nothing playing any more
    env.send_all()
    assert len(env.sent) == sent_before
    assert two.state(two.b)["label"] == "Radio B"  # B keeps playing


def test_a_stop_that_was_queued_before_the_takeover_is_not_sent(env: Env, two: Two) -> None:
    two.title(two.a, 1, env.radio, f"https://{PUBLIC}/a.mp3", "Radio A")
    two.title(two.b, 1, env.radio, f"https://{PUBLIC}/b.mp3", "Radio B")
    two.turn(two.a, 1)
    env.send_all()
    two.turn(two.b, 1)  # queued, not sent yet
    env.now += timedelta(milliseconds=50)  # real events never share a timestamp
    assert two.holder(two.a) is Outcome.MUSIC_STOPPED  # A still thinks it owns the target
    env.send_all()  # B's play goes first, then A's stop meets a foreign owner
    stops = [s for s in env.sent if s.get("action") == "stop"]
    assert stops == []
    assert two.state(two.b)["label"] == "Radio B"
    refused = [j for j in env.jobs() if j.device_id == two.a and j.face is None]
    assert refused and refused[-1].status.value == "expired"
    assert "gehört jetzt Küche" in (refused[-1].last_error or "")


def test_different_targets_do_not_disturb_each_other(env: Env, two: Two) -> None:
    two.title(two.a, 1, env.radio, f"https://{PUBLIC}/a.mp3", "Radio A")
    two.title(two.b, 2, env.ha, TRACK, "Sonos Titel", options=SPEAKER)
    two.turn(two.a, 1)
    two.turn(two.b, 2)
    settle(env)
    assert two.state(two.a)["label"] == "Radio A" and two.state(two.b)["label"] == "Sonos Titel"
    assert len(two.owners()) == 2
    two.holder(two.a)
    env.send_all()
    assert two.state(two.a) is None and two.state(two.b)["label"] == "Sonos Titel"


def test_two_speakers_of_one_connection_are_two_targets(env: Env, two: Two) -> None:
    kitchen = {"entity_id": "media_player.kueche"}
    two.title(two.a, 1, env.ha, TRACK, "Wohnzimmer", options=SPEAKER)
    two.title(two.b, 1, env.ha, TRACK, "Küche", options=kitchen)
    two.turn(two.a, 1)
    two.turn(two.b, 1)
    settle(env)
    assert two.state(two.a)["label"] == "Wohnzimmer" and two.state(two.b)["label"] == "Küche"
    assert len(two.owners()) == 2  # nobody replaced anybody


def test_the_owner_stops_and_releases_the_target(env: Env, two: Two) -> None:
    two.title(two.a, 1, env.radio, f"https://{PUBLIC}/a.mp3", "Radio A")
    two.turn(two.a, 1)
    env.send_all()
    assert two.holder(two.a) is Outcome.MUSIC_STOPPED
    env.send_all()
    assert env.sent[-1] == {"kind": "player", "action": "stop"}
    assert two.owners() == {} and two.state(two.a) is None


def test_the_older_state_without_a_target_still_works(env: Env, two: Two) -> None:
    from octaledger.domain.music import NowPlaying

    assert NowPlaying(1, "x", "i", "2026-01-01T00:00:00+00:00").target == ""


# ----------------------------------------------------------------------- smart home


class Control:
    """Two smart-home cubes that act on Home Assistant entities."""

    def __init__(self, env: Env) -> None:
        self.env = env
        devices = DeviceService(env.storage)
        self.a = devices.register("Eins").id
        self.b = devices.register("Zwei").id
        devices.set_mode(self.a, DeviceMode.CONTROL)
        devices.set_mode(self.b, DeviceMode.CONTROL)

    def assign(self, device: str, face: int, entity: str, volume: int) -> None:
        self.env.service.assign_steps(
            device,
            face,
            [
                {
                    "integration_id": self.env.ha,
                    "label": f"Lautstärke {volume}",
                    "params": {"action": "media_volume", "entity_id": entity, "volume": volume},
                    "delay_ms": 0,
                }
            ],
        )

    def turn(self, device: str, face: int) -> None:
        self.env.sequence += 1
        self.env.tracking.record_event(
            RawEvent(
                device_id=device,
                kind=EventKind.FACE_CHANGE,
                sequence=self.env.sequence,
                connection_id="c",
                raw_value=face,
                received_at=self.env.now,
            )
        )

    def notes(self) -> list[str | None]:
        return [j.note for j in self.env.jobs()]


@pytest.fixture
def control(env: Env) -> Control:
    return Control(env)


def test_different_commands_to_one_object_from_two_cubes_are_marked(
    env: Env, control: Control
) -> None:
    control.assign(control.a, 1, "media_player.x", 10)
    control.assign(control.b, 1, "media_player.x", 90)
    control.turn(control.a, 1)
    env.now += timedelta(seconds=2)
    control.turn(control.b, 1)
    first, second = control.notes()
    assert first is None
    assert second is not None and "Konflikt" in second and "Eins" in second and "vor 2 s" in second
    env.send_all()  # both are still sent, in order: the later one wins
    assert [s["volume"] for s in env.sent] == [10, 90]


def test_no_conflict_for_the_same_command_another_object_or_after_the_window(
    env: Env, control: Control
) -> None:
    control.assign(control.a, 1, "media_player.x", 10)
    control.assign(control.b, 1, "media_player.x", 10)  # same command
    control.assign(control.b, 2, "media_player.y", 90)  # another object
    control.assign(control.b, 3, "media_player.x", 90)  # same object, different command
    control.turn(control.a, 1)
    env.now += timedelta(seconds=1)
    control.turn(control.b, 1)
    control.turn(control.b, 2)
    assert control.notes() == [None, None, None]
    env.now += WINDOW + timedelta(seconds=1)  # long after
    control.turn(control.b, 3)
    assert control.notes()[-1] is None


def test_one_cube_never_conflicts_with_itself(env: Env, control: Control) -> None:
    control.assign(control.a, 1, "media_player.x", 10)
    control.assign(control.a, 2, "media_player.x", 90)
    control.turn(control.a, 1)
    env.now += timedelta(seconds=1)
    control.turn(control.a, 2)
    assert control.notes() == [None, None]


def test_owners_lists_who_controls_which_target(env: Env, two: Two) -> None:
    two.title(two.a, 1, env.radio, f"https://{PUBLIC}/a.mp3", "Radio A")
    two.title(two.b, 2, env.ha, TRACK, "Sonos Titel", options=SPEAKER)
    two.turn(two.a, 1)
    two.turn(two.b, 2)
    settle(env)
    owners = {o["target"]: o for o in env.music.owners()}
    assert owners["Radio PC"]["alias"] == "Musik" and owners["Radio PC"]["label"] == "Radio A"
    assert owners["Sonos · media_player.wohnzimmer"]["alias"] == "Küche"
    two.holder(two.a)
    env.send_all()
    assert [o["target"] for o in env.music.owners()] == ["Sonos · media_player.wohnzimmer"]
