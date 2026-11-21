"""The browser player: adapter state, link handling, the embedded page and the API (AP-50)."""

import pytest

from octaledger.core.errors import ValidationError
from octaledger.dashboard.views.player import player_document
from octaledger.domain.music_source import parse_source
from octaledger.infrastructure.integrations.browser import BrowserAdapter
from octaledger.infrastructure.integrations.registry import default_adapters
from tests.conftest import RunningApi

TIMEOUT = 1.0
VIDEO = "dQw4w9WgXcQ"


@pytest.fixture
def browser(api_server: RunningApi) -> BrowserAdapter:
    """The test server only knows fakes; register the real browser adapter in it."""
    adapter = BrowserAdapter()
    api_server.context.integrations._adapters["browser"] = adapter  # type: ignore[union-attr]  # noqa: SLF001
    return adapter


def run(adapter: BrowserAdapter, **params: object) -> None:
    adapter.execute({}, {}, params, timeout=TIMEOUT)


def test_registered_and_music_capable() -> None:
    adapter = default_adapters()["browser"]
    assert adapter.spec.music_capable and not adapter.spec.can_pair


def test_play_then_stop_changes_the_state_and_the_nonce() -> None:
    adapter = BrowserAdapter()
    assert adapter.state()["playing"] is False and adapter.state()["nonce"] == 0
    run(adapter, action="browser_play", video_id=VIDEO, list_id="PLabcdefghijk123", volume=30)
    state = adapter.state()
    assert state == {
        "playing": True,
        "video_id": VIDEO,
        "list_id": "PLabcdefghijk123",
        "volume": 30,
        "nonce": 1,
    }
    run(adapter, action="browser_stop")
    stopped = adapter.state()
    assert stopped["playing"] is False and stopped["nonce"] == 2 and stopped["volume"] == 30
    run(adapter, action="browser_play", video_id=VIDEO, volume=30)  # same title again
    assert adapter.state()["nonce"] == 3  # a repeat is a new command


def test_unknown_action_is_refused() -> None:
    with pytest.raises(ValidationError):
        run(BrowserAdapter(), action="nope")


def test_check_needs_nothing() -> None:
    assert "Musik-Player" in BrowserAdapter().check({}, {}, timeout=TIMEOUT)


def test_only_youtube_sources() -> None:
    adapter = BrowserAdapter()
    plays = adapter.music_play_params(
        parse_source(f"https://www.youtube.com/watch?v={VIDEO}&list=PLabcdefghijk123"), 40, {}
    )
    assert plays == [
        {"action": "browser_play", "video_id": VIDEO, "volume": 40, "list_id": "PLabcdefghijk123"}
    ]
    assert adapter.music_play_params(parse_source(f"https://youtu.be/{VIDEO}"), 40, {}) == [
        {"action": "browser_play", "video_id": VIDEO, "volume": 40}
    ]
    for other in ("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC", "https://r.example/a"):
        with pytest.raises(ValidationError):
            adapter.music_play_params(parse_source(other), 40, {})
    assert adapter.music_stop_params({}) == {"action": "browser_stop"}


@pytest.mark.parametrize(
    "params",
    [
        {"action": "browser_play", "video_id": "short"},
        {"action": "browser_play", "video_id": "<script>alert1"},
        {"action": "browser_play", "video_id": VIDEO, "list_id": "x y"},
        {"action": "browser_play"},
    ],
)
def test_ids_are_validated(params: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BrowserAdapter().validate_action(params)


# --------------------------------------------------------------------------- the page


def test_stopped_state_loads_nothing_external() -> None:
    page = player_document({"playing": False, "video_id": VIDEO})
    assert "youtube" not in page and "<script" not in page


def test_player_page_contains_the_ids_and_is_stable() -> None:
    state = {"playing": True, "video_id": VIDEO, "list_id": "", "volume": 150, "nonce": 7}
    page = player_document(state)
    assert VIDEO in page and "iframe_api" in page and "youtube-nocookie" in page
    assert '"volume": 100' in page  # clamped
    # the nonce does not change the text, so a refresh keeps the running player
    assert page == player_document({**state, "nonce": 8})
    assert "Wiedergabe freischalten" in page


def test_a_bad_id_never_reaches_the_page() -> None:
    evil = {"playing": True, "video_id": '"></script><script>alert(1)//', "volume": 50}
    page = player_document(evil)
    assert "alert" not in page and "iframe_api" not in page
    listed = player_document(
        {"playing": True, "video_id": VIDEO, "list_id": "</script>", "volume": 50}
    )
    assert "</script><" not in listed and '"list": ""' in listed


def test_api_returns_the_wanted_state(api_server: RunningApi, browser: BrowserAdapter) -> None:
    assert api_server.client.browser_player_state()["playing"] is False
    run(browser, action="browser_play", video_id=VIDEO, volume=20)
    state = api_server.client.browser_player_state()
    assert state["playing"] is True and state["video_id"] == VIDEO and state["volume"] == 20


def test_playing_actions_mark_now_playing() -> None:
    from octaledger.application.music_state import PLAY_ACTIONS

    assert {"browser_play", "spotify_play"} <= PLAY_ACTIONS
