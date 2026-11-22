"""Identity of a cube: number, colour, API and backup (AP-51)."""

import json
from pathlib import Path

import pytest

from octaledger.domain.device_identity import (
    PALETTE,
    badge,
    color_name,
    next_free_color,
    numbering,
)
from tests.unit.test_api import Env, FakeAgent


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path, FakeAgent())


# ----------------------------------------------------------------------- pure functions


def test_palette_has_eight_distinct_colours() -> None:
    colours = [c for c, _ in PALETTE]
    assert len(set(colours)) == 8 and all(c.startswith("#") and len(c) == 7 for c in colours)


def test_next_free_color_skips_used_ones_and_wraps() -> None:
    assert next_free_color([]) == PALETTE[0][0]
    assert next_free_color([PALETTE[0][0], PALETTE[1][0].lower()]) == PALETTE[2][0]
    assert next_free_color([c for c, _ in PALETTE]) == PALETTE[0][0]  # all taken: start over


def test_numbering_follows_registration_time_with_stable_ties() -> None:
    result = numbering([("b", "2026-01-02"), ("a", "2026-01-02"), ("c", "2026-01-01")])
    assert result == {"c": 1, "a": 2, "b": 3}


def test_badge_and_colour_name() -> None:
    assert badge(1) == "①" and badge(20) == "⑳" and badge(21) == "(21)"
    assert color_name("#0072b2") == "Blau" and color_name("#123456") == "Eigene Farbe"


# ------------------------------------------------------------------------ the service


def test_cubes_get_different_colours_and_numbers(env: Env) -> None:
    first = env.post("/devices", {"alias": "Büro"}).json()
    second = env.post("/devices", {"alias": "Wohnzimmer"}).json()
    assert (first["number"], second["number"]) == (1, 2)
    assert first["color"] != second["color"]
    assert first["badge"] == "①" and second["badge"] == "②"
    assert first["color_name"] and second["color_name"]


def test_a_colour_can_be_chosen_and_is_validated(env: Env) -> None:
    cube = env.post("/devices", {"alias": "Büro"}).json()
    changed = env.call("PATCH", f"/devices/{cube['id']}", json={"color": "#112233"}).json()
    assert changed["color"] == "#112233" and changed["color_name"] == "Eigene Farbe"
    assert changed["alias"] == "Büro"  # untouched
    bad = env.call("PATCH", f"/devices/{cube['id']}", json={"color": "red"})
    assert bad.status_code == 422
    empty = env.call("PATCH", f"/devices/{cube['id']}", json={})
    assert empty.status_code == 422


def test_rename_and_colour_in_one_request(env: Env) -> None:
    cube = env.post("/devices", {"alias": "Büro"}).json()
    both = env.call(
        "PATCH", f"/devices/{cube['id']}", json={"alias": "Küche", "color": "#009E73"}
    ).json()
    assert both["alias"] == "Küche" and both["color"] == "#009E73"


def test_a_cube_without_stored_colour_shows_the_colour_of_its_number(env: Env) -> None:
    from octaledger.domain.models import Device

    with env.storage.transaction() as repos:
        repos.devices.add(Device(alias="Alt"))  # as registered before AP-51: no colour
    info = env.context.devices.list_devices()[0]
    assert info.device.color == "" and info.color == PALETTE[0][0] and info.number == 1


def test_the_colour_survives_a_backup_and_old_backups_still_load(env: Env) -> None:
    cube = env.post("/devices", {"alias": "Büro"}).json()
    env.call("PATCH", f"/devices/{cube['id']}", json={"color": "#112233"})
    text = env.context.exports.create_backup_text()
    data = json.loads(text)
    assert data["data"]["devices"][0]["color"] == "#112233"
    del data["data"]["devices"][0]["color"]  # a file written before AP-51
    data["checksum"] = env.context.exports._checksum(data["data"])  # noqa: SLF001
    env.context.exports.restore_backup_text(json.dumps(data))
    assert env.context.devices.list_devices()[0].color == PALETTE[0][0]  # default of number 1
