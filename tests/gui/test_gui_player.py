"""GUI test of the page "Musik-Player": nothing is loaded before the user agrees."""

import pytest

from octaledger.infrastructure.integrations.browser import BrowserAdapter
from tests.conftest import RunningApi
from tests.gui.test_gui_core import texts
from tests.gui.test_gui_devices_catalog import open_page


@pytest.fixture
def browser(api_server: RunningApi) -> BrowserAdapter:
    """The test server only knows fakes; register the real browser adapter in it."""
    adapter = BrowserAdapter()
    api_server.context.integrations._adapters["browser"] = adapter  # type: ignore[union-attr]  # noqa: SLF001
    return adapter


def test_consent_comes_first_then_the_player(
    api_server: RunningApi, browser: BrowserAdapter
) -> None:
    at = open_page(api_server, "player")
    assert at.header[0].value == "Musik-Player"
    assert any("So funktioniert der Musik-Player" in e.label for e in at.expander)
    assert "youtube.com" in texts(at)
    assert not any("iframe" in str(e).lower() for e in at.main)  # nothing external yet
    button = next(b for b in at.button if b.key == "player_consent_button")
    assert button.help
    button.click().run()
    assert not at.exception
    assert any("Es spielt nichts" in c.value for c in at.caption)


def test_state_is_shown_after_consent(api_server: RunningApi, browser: BrowserAdapter) -> None:
    browser.execute(
        {}, {}, {"action": "browser_play", "video_id": "dQw4w9WgXcQ", "volume": 40}, timeout=1
    )
    at = open_page(api_server, "player")
    next(b for b in at.button if b.key == "player_consent_button").click().run()
    assert not at.exception
    assert any("Jetzt läuft der Titel" in c.value for c in at.caption)
