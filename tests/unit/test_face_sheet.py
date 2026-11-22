"""The sheet of a face in plain German, and the click geometry of the cube picture (AP-54)."""

import pytest

from octaledger.dashboard.cube import INNER_RADIUS, OUTER_RADIUS, face_at
from octaledger.dashboard.face_sheet import (
    HOLDER,
    FaceSheet,
    condition_text,
    control_sheet,
    export_text,
    holder_sheet,
    music_sheet,
    overview_rows,
    step_lines,
    time_sheet,
)

CONNECTIONS = [
    {"id": "c1", "kind": "homeassistant", "name": "Zuhause"},
    {"id": "c2", "kind": "player", "name": "Mein PC"},
]
SPECS = [
    {
        "kind": "homeassistant",
        "title": "Home Assistant",
        "actions": [
            {
                "id": "call_service",
                "label": "Dienst aufrufen",
                "fields": [
                    {"name": "domain", "label": "Bereich"},
                    {"name": "service", "label": "Dienst"},
                ],
            }
        ],
    },
    {
        "kind": "player",
        "title": "Lokaler Player",
        "actions": [
            {
                "id": "play_url",
                "label": "Stream abspielen",
                "fields": [{"name": "url", "label": "Adresse"}],
            }
        ],
    },
]


# ------------------------------------------------------------------------------- geometry


@pytest.mark.parametrize(
    ("dx", "dy", "face"),
    [
        (0, -100, 1),  # straight up
        (70, -70, 2),  # up right
        (100, 0, 3),
        (70, 70, 4),
        (0, 100, 5),
        (-70, 70, 6),
        (-100, 0, 7),
        (-70, -70, 8),
        (1, -100, 1),
        (-1, -100, 1),
    ],
)
def test_face_at_follows_the_drawing(dx: float, dy: float, face: int) -> None:
    assert face_at(dx, dy) == face


def test_the_centre_and_the_outside_are_no_face() -> None:
    assert face_at(0, 0) is None and face_at(INNER_RADIUS - 1, 0) is None
    assert face_at(OUTER_RADIUS + 1, 0) is None


def test_every_wedge_boundary_belongs_to_exactly_one_face() -> None:
    import math

    seen = {
        face_at(100 * math.cos(math.radians(a)), 100 * math.sin(math.radians(a)))
        for a in range(0, 360, 5)
    }
    assert seen == set(range(1, 9))


# ---------------------------------------------------------------------------- time cubes


def test_time_sheet_names_activity_project_tags_and_note() -> None:
    device = {"faces": {"3": {"activity_id": "a1", "project_id": "p1"}}}
    sheet = time_sheet(
        3,
        device,
        [{"id": "a1", "name": "Meeting"}],
        [{"id": "p1", "name": "Alpha"}],
        {"tag_names": ["Kunde", "Remote"], "note_template": "Thema: "},
    )
    text = " ".join(sheet.lines)
    assert "Meeting" in text and "Alpha" in text and "Kunde, Remote" in text and "Thema:" in text
    assert sheet.title == "Meeting" and sheet.summary == "Meeting · Alpha" and not sheet.empty


def test_an_unassigned_or_vanished_activity_is_said_plainly() -> None:
    assert time_sheet(1, {"faces": {}}, [], []).empty
    gone = time_sheet(2, {"faces": {"2": {"activity_id": "x", "project_id": None}}}, [], [])
    assert "nicht mehr vorhanden" in " ".join(gone.lines) and "Projekt:** keines" in " ".join(
        gone.lines
    )


# ---------------------------------------------------------------------- chains and music


def test_condition_text() -> None:
    assert condition_text(None) is None and condition_text({}) is None
    assert condition_text({"start": "08:00", "end": "18:00", "weekdays": ""}) == (
        "nur zwischen 08:00 und 18:00 Uhr"
    )
    both = condition_text({"start": "22:00", "end": "06:00", "weekdays": "1,2"})
    assert both == "nur zwischen 22:00 und 06:00 Uhr und nur an: Mo, Di"
    assert condition_text({"start": "", "end": "", "weekdays": "1,2,3,4,5,6,7"}) is None


def steps() -> list[dict]:
    return [
        {
            "integration_id": "c1",
            "label": "Licht an",
            "params": {"action": "call_service", "domain": "light", "service": "turn_on"},
            "delay_ms": 0,
            "continue_on_error": False,
            "enabled": True,
            "condition": None,
        },
        {
            "integration_id": "c1",
            "label": "Licht an",
            "params": {"action": "call_service", "domain": "light", "service": "turn_off"},
            "delay_ms": 500,
            "continue_on_error": True,
            "enabled": False,
            "condition": {"start": "08:00", "end": "09:00", "weekdays": "5"},
        },
    ]


def test_step_lines_show_connection_action_values_delay_errors_and_condition() -> None:
    first, second = step_lines(steps(), CONNECTIONS, SPECS)
    assert "Schritt 1" in first and "„Zuhause“ (Home Assistant)" in first
    assert "Dienst aufrufen" in first and "Bereich: light" in first and "Dienst: turn_on" in first
    assert "Schritt 2" in second and "wartet vorher 500 ms" in second
    assert "trotzdem weiter" in second and "nur an: Fr" in second and "ausgeschaltet" in second


def test_a_missing_connection_is_named_not_hidden() -> None:
    lines = step_lines([{**steps()[0], "integration_id": "weg"}], CONNECTIONS, SPECS)
    assert "Verbindung nicht mehr vorhanden" in lines[0]


def test_control_sheet_summarises_the_whole_chain() -> None:
    sheet = control_sheet(4, steps(), CONNECTIONS, SPECS)
    assert sheet.title == "Licht an" and sheet.summary == "Licht an (2 Schritte)"
    assert any("löst diese Kette aus" in line for line in sheet.lines)
    assert control_sheet(4, [], CONNECTIONS, SPECS).empty


def test_music_sheet_names_title_target_and_volume_and_silence() -> None:
    music = [
        {
            "integration_id": "c2",
            "label": "Lofi Radio",
            "params": {"action": "play_url", "url": "https://radio.example/live.mp3", "volume": 35},
            "delay_ms": 0,
            "continue_on_error": False,
            "enabled": True,
            "condition": None,
        }
    ]
    sheet = music_sheet(2, music, CONNECTIONS, SPECS)
    text = " ".join(sheet.lines)
    assert "Lofi Radio" in text and "„Mein PC“" in text and "35 %" in text
    assert sheet.summary == "♪ Lofi Radio auf „Mein PC“"
    silent = music_sheet(5, [], CONNECTIONS, SPECS)
    assert silent.empty and "Stille" in silent.summary and "beendet die Musik" in silent.lines[0]


def test_holder_sheet_says_what_the_holder_does() -> None:
    stop = holder_sheet({"base_action": "stop", "stop_delay_ms": 0, "default_volume": 50})
    assert stop.face == HOLDER and "sofort" in stop.summary and "beendet" in stop.summary
    pause = holder_sheet({"base_action": "pause", "stop_delay_ms": 2500, "default_volume": 30})
    assert "2.5 Sekunden" in " ".join(pause.lines) and "pausiert" in pause.summary
    assert "30 %" in " ".join(pause.lines)


# ----------------------------------------------------------------------------- the export


def test_overview_and_export_cover_every_face_and_the_holder() -> None:
    sheets = [FaceSheet(1, "A", "Aktion A", ("**Name:** A",)), holder_sheet({})]
    rows = overview_rows(sheets)
    assert rows[0] == {"Seite": "1", "Einstellung": "Aktion A"}
    assert rows[1]["Seite"] == "Halterung"
    text = export_text("Büro", "Musik", sheets)
    assert "„Büro“ – Bereich Musik" in text and "Seite 1: Aktion A" in text
    assert "Halterung:" in text and "**" not in text  # plain text, no Markdown marks
