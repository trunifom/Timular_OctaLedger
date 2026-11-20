"""GUI tests for the shell and the overview page (AppTest against the real API server)."""

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from octaledger.core.settings import FontSize, Theme
from octaledger.dashboard.pages import PAGES
from octaledger.dashboard.theme import (
    FONT_PIXELS,
    PALETTES,
    contrast_ratio,
    css,
)
from octaledger.dashboard.ui import (
    display_settings,
    format_hm,
    format_hms,
    format_local,
    to_local,
)
from octaledger.dashboard_client.client import ApiClient
from tests.conftest import API_TOKEN, RunningApi, free_port


def app_script() -> None:
    """Script executed by AppTest (must be self-contained)."""
    from octaledger.dashboard.main import run

    run()


def open_app(client: ApiClient | None, **state: Any) -> AppTest:
    """Run the dashboard once with an injected client and optional session state."""
    at = AppTest.from_function(app_script, default_timeout=30)
    if client is not None:
        at.session_state["_client"] = client
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def texts(at: AppTest) -> str:
    """All markdown/caption/info text of the page joined (for substring checks)."""
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += (
        [e.value for e in at.error] + [w.value for w in at.warning] + [i.value for i in at.info]
    )
    return "\n".join(str(p) for p in parts)


def button(at: AppTest, label: str) -> Any:
    matches = [b for b in at.button if label in b.label]
    assert matches, f"no button containing {label!r}; have {[b.label for b in at.button]}"
    return matches[0]


@pytest.fixture
def client(api_server: RunningApi) -> ApiClient:
    return api_server.client


# --------------------------------------------------------------------------------- shell


def test_app_renders_without_exceptions(client: ApiClient) -> None:
    at = open_app(client)
    assert not at.exception
    assert at.header[0].value == "Übersicht"
    assert "Keine Zeiterfassung läuft" in texts(at)
    assert at.sidebar.radio(key="nav").options == list(PAGES)  # navigation shows every page
    assert at.sidebar.radio(key="nav").options[0] == "🏠 Übersicht"
    assert any("Agent läuft" in c.value for c in at.sidebar.caption)


def test_every_visible_input_and_button_has_a_help_text(client: ApiClient) -> None:
    client.create_item("activities", "Meeting")
    at = open_app(client)
    widgets = [*at.sidebar.button, *at.sidebar.radio, *at.selectbox, *at.text_input]
    widgets += [b for b in at.button if not getattr(b, "form_id", "")]
    assert widgets, "page has no inputs?"
    for widget in widgets:
        assert widget.help, f"{widget.key or widget.label} has no help text"


def test_page_help_expander_exists(client: ApiClient) -> None:
    at = open_app(client)
    assert any("So funktioniert die Übersicht" in e.label for e in at.expander)


# ---------------------------------------------------------------------------- theme/font


def test_theme_toggle_switches_css_and_is_persisted(client: ApiClient) -> None:
    at = open_app(client)
    assert "color-scheme: light" in texts(at) and button(at, "Dunkel")
    at.sidebar.button(key="btn_theme").click().run()
    assert "color-scheme: dark" in texts(at) and PALETTES[Theme.DARK].background in texts(at)
    assert button(at, "Hell")  # the button now offers the way back
    assert client.get_settings()["display"]["theme"] == "dark"  # survives a new session
    at.sidebar.button(key="btn_theme").click().run()
    assert (
        "color-scheme: light" in texts(at) and client.get_settings()["display"]["theme"] == "light"
    )


def test_font_size_toggle_switches_between_exactly_two_steps(client: ApiClient) -> None:
    at = open_app(client)
    assert f"font-size: {FONT_PIXELS[FontSize.NORMAL]}px" in texts(at)
    at.sidebar.button(key="btn_font").click().run()
    assert f"font-size: {FONT_PIXELS[FontSize.LARGE]}px" in texts(at)
    assert "Kleiner" in at.sidebar.button(key="btn_font").label
    assert client.get_settings()["display"]["font_size"] == "large"
    at.sidebar.button(key="btn_font").click().run()
    assert f"font-size: {FONT_PIXELS[FontSize.NORMAL]}px" in texts(at)


def test_saved_preferences_are_applied_in_a_new_session(client: ApiClient) -> None:
    client.update_settings(
        {"display": {"theme": "dark", "font_size": "large", "timezone": "Europe/Zurich"}}
    )
    at = open_app(client)
    assert "color-scheme: dark" in texts(at) and "font-size: 20px" in texts(at)


def test_preference_still_works_for_the_session_if_saving_fails(client: ApiClient) -> None:
    at = open_app(client)
    at.session_state["_client"] = ApiClient(
        f"http://127.0.0.1:{free_port()}", API_TOKEN, timeout=(0.3, 0.5)
    )
    at.sidebar.button(key="btn_theme").click().run()
    assert not at.exception
    assert "color-scheme: dark" in texts(at)  # applied locally even though it could not be saved


def test_palettes_meet_wcag_aa_contrast() -> None:
    for theme, palette in PALETTES.items():
        assert contrast_ratio(palette.text, palette.background) >= 7, theme
        assert contrast_ratio(palette.text, palette.surface) >= 7, theme
        assert contrast_ratio(palette.muted, palette.background) >= 4.5, theme
        assert contrast_ratio(palette.on_primary, palette.primary) >= 4.5, theme
        assert contrast_ratio(palette.primary, palette.background) >= 4.5, theme
        for status in (palette.success, palette.warning, palette.danger):
            assert contrast_ratio(status, palette.background) >= 4.5, (theme, status)


def test_css_contains_both_schemes_and_sizes() -> None:
    light, dark = css(Theme.LIGHT, FontSize.NORMAL), css(Theme.DARK, FontSize.LARGE)
    assert "color-scheme: light" in light and "color-scheme: dark" in dark
    assert "font-size: 16px" in light and "font-size: 20px" in dark
    assert PALETTES[Theme.LIGHT].background in light and PALETTES[Theme.DARK].background in dark


# ------------------------------------------------------------------------ agent / setup


def test_unreachable_agent_shows_a_helpful_page_not_a_crash() -> None:
    dead = ApiClient(f"http://127.0.0.1:{free_port()}", API_TOKEN, timeout=(0.3, 0.5))
    at = open_app(dead)
    assert not at.exception
    assert any("nicht erreichbar" in e.value for e in at.error)
    assert "OL-API-002" in texts(at) and "octaledger agent" in texts(at)
    assert button(at, "Neu laden")
    assert at.sidebar.radio(key="nav") is not None  # the shell still works


def test_missing_token_shows_setup_help(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTALEDGER_DATA_DIR", str(tmp_path / "empty"))
    at = open_app(None)
    assert not at.exception
    assert any("noch kein API-Token" in e.value for e in at.error)
    assert any("Einrichtung" in e.label for e in at.expander)


# ----------------------------------------------------------------------------- overview


def test_start_pause_resume_stop_flow(client: ApiClient) -> None:
    client.create_item("activities", "Meeting", "#112233")
    at = open_app(client)
    button(at, "Start").click().run()
    assert client.status()["tracking"]["running"] is not None
    assert "Meeting" in texts(at) and button(at, "Pause")

    button(at, "Pause").click().run()
    assert client.status()["tracking"]["paused"] is True
    assert "Pausiert" in texts(at)

    button(at, "Fortsetzen").click().run()
    assert client.status()["tracking"]["running"] is not None

    button(at, "Stopp").click().run()
    assert client.status()["tracking"]["running"] is None
    assert "Keine Zeiterfassung läuft" in texts(at)


def test_start_with_project_and_note(client: ApiClient) -> None:
    client.create_item("activities", "Code")
    project = client.create_item("projects", "Alpha")
    at = open_app(client)
    at.selectbox(key="start_project").select_index(1)
    at.text_input(key="start_note").input("  Release  ")
    button(at, "Start").click().run()
    running = client.status()["tracking"]
    assert running["project"]["id"] == project["id"]
    assert running["running"]["note"] == "Release"
    assert "Alpha" in texts(at)


def test_overview_without_activities_explains_what_to_do(client: ApiClient) -> None:
    at = open_app(client)
    assert any("Verwaltung" in i.value and "Tätigkeit" in i.value for i in at.info)


def test_user_text_is_html_escaped(client: ApiClient) -> None:
    evil = client.create_item("activities", "<img src=x onerror=alert(1)>")
    client.start_tracking(evil["id"])
    at = open_app(client)
    rendered = texts(at)
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert "<img src=x onerror" not in rendered


def test_uncertain_sessions_are_called_out(api_server: RunningApi) -> None:
    from octaledger.domain.models import Quality

    client = api_server.client
    activity = client.create_item("activities", "Meeting")
    client.start_tracking(activity["id"])
    with api_server.storage.transaction() as repos:
        running = repos.sessions.get_running()
        assert running is not None
        repos.sessions.set_quality(running.id, Quality.UNCERTAIN)
    at = open_app(client)
    assert any("unsicher" in w.value for w in at.warning)


def test_tracker_box_without_and_with_device(client: ApiClient) -> None:
    at = open_app(client)
    assert any("noch kein Tracker registriert" in i.value for i in at.info)
    client.register_device("Büro <b>")
    at = open_app(client)
    rendered = texts(at)
    assert "Büro &lt;b&gt;" in rendered and "aktiv" in rendered and "Nicht verbunden" in rendered


# ------------------------------------------------------------------------------ helpers


@pytest.mark.parametrize(
    "seconds, hms, hm",
    [
        (0, "0:00:00", "0 min"),
        (59, "0:00:59", "0 min"),
        (3725, "1:02:05", "1 h 02 min"),
        (5400, "1:30:00", "1 h 30 min"),
        (-5, "0:00:00", "0 min"),
        (360000, "100:00:00", "100 h 00 min"),
    ],
)
def test_duration_formatting(seconds: int, hms: str, hm: str) -> None:
    assert format_hms(seconds) == hms and format_hm(seconds) == hm


def test_local_time_formatting() -> None:
    assert format_local("2026-01-05T08:00:00+00:00", "Europe/Zurich") == "05.01.2026 09:00"
    assert (
        format_local("2026-07-05T08:00:00+00:00", "Europe/Zurich", with_seconds=True)
        == "05.07.2026 10:00:00"
    )
    assert format_local(None, "UTC") == "–" and to_local("", "UTC") is None


def test_display_settings_fall_back_to_defaults_on_bad_input() -> None:
    assert display_settings(None).theme is Theme.LIGHT
    assert display_settings({"display": {"theme": "neon"}}).theme is Theme.LIGHT
    assert display_settings({"display": {"theme": "dark"}}).theme is Theme.DARK
    assert display_settings({"display": "garbage"}).theme is Theme.LIGHT  # type: ignore[dict-item]
