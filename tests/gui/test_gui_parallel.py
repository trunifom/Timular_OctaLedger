"""GUI test for AP-55: the overview says who controls what; the history shows conflict notes."""

from datetime import datetime, timezone

from tests.conftest import RunningApi
from tests.gui.test_gui_devices_catalog import open_page


def markdown_text(at) -> str:  # type: ignore[no-untyped-def]
    return " ".join(str(m.value) for m in at.markdown)


def test_nothing_is_shown_while_nobody_controls_anything(api_server: RunningApi) -> None:
    api_server.client.register_device("Büro")
    at = open_page(api_server, "overview")
    assert "Wer steuert was?" not in markdown_text(at)


def test_the_overview_lists_owner_target_and_title(api_server: RunningApi) -> None:
    cube = api_server.client.register_device("Musik")
    connection = api_server.client.create_integration(
        "fake", "Wohnzimmer", {"host": "h", "password": "richtig"}
    )
    with api_server.storage.transaction() as repos:
        repos.state.set(
            f"music_owner:{connection['id']}",
            '{"device_id": "%s", "label": "Lofi", "since": "%s"}'
            % (cube["id"], datetime.now(timezone.utc).isoformat()),
        )
    at = open_page(api_server, "overview")
    assert not at.exception
    page = markdown_text(at)
    assert "Wer steuert was?" in page and "Wohnzimmer" in page
    assert "① Musik" in page and "Lofi" in page
    assert any("immer nur ein Titel" in c.value for c in at.caption)
