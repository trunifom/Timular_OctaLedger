"""GUI tests for AP-56: the data sheet reads, shows, stores and exports - read only."""

from collections.abc import Iterator

import pytest

from octaledger.dashboard.views.datasheet import safe_cell, sample_rows, sheet_rows, to_csv
from octaledger.domain.readout import Reading
from tests.conftest import FakeAgent, RunningApi
from tests.gui.test_gui_devices_catalog import open_page

PAGE = "datasheet"
ORIENT = "c7e70012-c847-11e6-8175-8c89a55d403c"
ACCEL = "c7e70011-c847-11e6-8175-8c89a55d403c"
SERVICE = "c7e70010-c847-11e6-8175-8c89a55d403c"


@pytest.fixture
def agent(api_server: RunningApi) -> Iterator[FakeAgent]:
    fake = FakeAgent()
    fake.readings = [
        Reading(SERVICE, ORIENT, ("notify", "read"), "03"),
        Reading(
            "0000180a-0000-1000-8000-00805f9b34fb",
            "00002a24-0000-1000-8000-00805f9b34fb",
            ("read",),
            b"Tracker_001".hex(),
        ),
        Reading(
            "c7e70020-c847-11e6-8175-8c89a55d403c",
            "c7e70022-c847-11e6-8175-8c89a55d403c",
            ("write",),
        ),
    ]
    api_server.context.agent = fake
    yield fake


def connected(api: RunningApi, agent: FakeAgent) -> str:
    cube = api.client.register_device("Büro")
    api.client.set_device_address(cube["id"], "AA:BB")
    api.client.connect_device(cube["id"])
    assert agent.started == [cube["id"]]
    return str(cube["id"])


def test_empty_state_and_help(api_server: RunningApi) -> None:
    at = open_page(api_server, PAGE)
    assert at.header[0].value == "Würfel-Datenblatt"
    assert any("So funktioniert das Datenblatt" in e.label for e in at.expander)
    assert any("noch kein Würfel eingerichtet" in i.value for i in at.info)


def test_a_cube_that_is_not_connected_cannot_be_read_but_explains_why(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    api_server.client.register_device("Büro")
    at = open_page(api_server, PAGE)
    assert any("nicht verbunden" in w.value for w in at.warning)
    assert next(b for b in at.button if b.key == "datasheet_take").disabled
    assert agent.read_calls == []


def test_reading_shows_words_for_known_values_and_raw_for_the_rest(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    did = connected(api_server, agent)
    at = open_page(api_server, PAGE)
    take = next(b for b in at.button if b.key == "datasheet_take")
    assert not take.disabled and take.help
    take.click().run()
    assert not at.exception
    assert agent.read_calls == [(did, "datasheet", 0, 500)]
    table = at.dataframe[0].value
    by_name = {row["Characteristic"]: row for _, row in table.iterrows()}
    assert by_name["Lage (aktive Seite) (c7e70012)"]["Deutung"] == "Seite 3"
    assert by_name["Modell (2a24)"]["Deutung"] == "Tracker_001"
    unread = by_name["Unbekannt (c7e70022)"]
    assert unread["Wert (hex)"] == "" and unread["Hinweis"] == "nicht lesbar, nicht angefasst"
    assert any("3 Angaben, davon 2 gelesen" in c.value for c in at.caption)


def test_the_read_out_is_stored_and_can_be_deleted(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    did = connected(api_server, agent)
    at = open_page(api_server, PAGE)
    next(b for b in at.button if b.key == "datasheet_take").click().run()
    assert len(api_server.client.snapshots(did)) == 1
    delete = next(b for b in at.button if b.key.startswith("datasheet_delete_"))
    assert delete.help
    delete.click().run()
    assert not at.exception
    assert api_server.client.snapshots(did) == []
    assert any("Noch nichts ausgelesen" in i.value for i in at.info)


def test_the_recording_asks_for_a_limited_time_and_shows_only_raw_values(
    api_server: RunningApi, agent: FakeAgent
) -> None:
    did = connected(api_server, agent)
    agent.readings = [
        Reading(SERVICE, ACCEL, ("read",), bytes([i, 0, 0, 0, 0, 0]).hex()) for i in range(4)
    ]
    at = open_page(api_server, PAGE)
    at.slider(key="datasheet_seconds").set_value(5)
    next(b for b in at.button if b.key == "datasheet_record").click().run()
    assert not at.exception
    assert agent.read_calls[-1] == (did, "accelerometer", 5, 500)
    assert any("4 Messungen" in m.value and "6 Byte" in m.value for m in at.markdown)
    assert any("4 verschiedene Werte" in c.value for c in at.caption)
    assert not any("Deutung" in str(col) for col in at.dataframe[0].value.columns)  # raw only


def test_both_exports_are_offered(api_server: RunningApi, agent: FakeAgent) -> None:
    connected(api_server, agent)
    at = open_page(api_server, PAGE)
    next(b for b in at.button if b.key == "datasheet_take").click().run()
    assert len(at.get("download_button")) == 2


# ----------------------------------------------------------------------- pure helpers


def test_csv_neutralises_formulas_from_the_cube() -> None:
    assert safe_cell("=1+1") == "'=1+1" and safe_cell("-8 dBm") == "'-8 dBm"
    assert safe_cell("Seite 3") == "Seite 3"
    text = to_csv([{"a": "=cmd", "b": "ok"}])
    assert text.startswith("﻿") and "'=cmd" in text and "a;b" in text
    assert to_csv([]) == ""
    assert ";;" in to_csv([{"a": "x", "b": None, "c": "y"}])  # a missing value is an empty cell


def test_row_builders() -> None:
    snapshot = {
        "interval_ms": 200,
        "readings": [
            {"raw_hex": "0a0b", "length": 2},
            {"raw_hex": None, "length": None},
        ],
    }
    assert sample_rows(snapshot)[1]["Zeit seit Beginn (ms)"] == 200
    assert sample_rows(snapshot)[0]["Länge (Byte)"] == 2
    assert sheet_rows is not None
