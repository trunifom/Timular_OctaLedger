"""Tests for the redesigned GUI: grouped menu, status bar, first steps, quick start, assets."""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import octaledger.dashboard as dashboard_package
from octaledger.core.settings import FontSize, Theme
from octaledger.dashboard.nav import GROUPS
from octaledger.dashboard.theme import FONT_URL, PALETTES, css, native_theme_options
from octaledger.dashboard.views import PAGES
from tests.conftest import RunningApi
from tests.gui.test_gui_core import button, open_app, texts
from tests.gui.test_gui_devices_catalog import open_page

PACKAGE = Path(dashboard_package.__file__).parent


def goto(at: AppTest, slug: str) -> AppTest:
    return at.sidebar.button(key=f"nav_{slug}").click().run()


# ------------------------------------------------------------------------------- menu


def test_menu_is_grouped_by_task_in_the_documented_order() -> None:
    assert GROUPS == ("Alltag", "Einrichten", "System")
    order = {group: [p.slug for p in PAGES.values() if p.group == group] for group in GROUPS}
    assert order == {
        "Alltag": ["overview", "live", "journal", "statistics"],
        "Einrichten": ["devices", "catalog"],
        "System": ["data", "settings", "diagnostics"],
    }
    assert len(PAGES) == 9


def test_group_headings_are_shown_and_the_active_page_is_filled(api_server: RunningApi) -> None:
    at = open_app(api_server.client)
    headings = "".join(m.value for m in at.sidebar.markdown)
    for group in GROUPS:
        assert f'class="ol-nav-group">{group}<' in headings
    assert at.sidebar.button(key="nav_overview").proto.type == "primary"
    assert at.sidebar.button(key="nav_journal").proto.type == "secondary"
    goto(at, "journal")
    assert at.sidebar.button(key="nav_journal").proto.type == "primary"  # not colour alone: filled
    assert at.sidebar.button(key="nav_overview").proto.type == "secondary"


def test_every_entry_has_icon_text_and_tooltip_and_every_page_title_matches(
    api_server: RunningApi,
) -> None:
    at = open_app(api_server.client)
    for slug, page in PAGES.items():
        entry = at.sidebar.button(key=f"nav_{slug}")
        assert entry.label.startswith(":material/") and page.title in entry.label
        assert entry.help, slug
        goto(at, slug)
        assert not at.exception, slug
        assert at.header[0].value == page.title  # H1 equals the menu label


# --------------------------------------------------------------------------- status bar


def test_status_bar_is_on_every_page(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Meeting")
    for slug in PAGES:
        at = open_page(api_server, slug)
        assert "Keine Zeiterfassung läuft" in texts(at), slug


def test_disconnected_tracker_triggers_a_visible_warning(api_server: RunningApi) -> None:
    device = api_server.client.register_device("Büro")
    api_server.client.set_device_address(device["id"], "AA:BB")
    at = open_page(api_server, "journal")  # any page, not only the overview
    assert any("liefert gerade keine Werte" in w.value for w in at.warning)
    assert "Büro: nicht verbunden" in texts(at)


def test_no_tracker_is_neutral_not_alarming(api_server: RunningApi) -> None:
    at = open_app(api_server.client)
    assert "Kein Tracker eingerichtet" in texts(at)
    assert not any("liefert gerade keine Werte" in w.value for w in at.warning)


def test_running_entry_shows_in_the_bar_with_stop_on_other_pages(api_server: RunningApi) -> None:
    activity = api_server.client.create_item("activities", "Meeting")
    api_server.client.start_tracking(activity["id"])
    at = open_page(api_server, "statistics")
    assert "Meeting" in texts(at) and at.button(key="bar_stop") is not None
    at.button(key="bar_stop").click().run()
    assert api_server.client.status()["tracking"]["running"] is None


def test_uncertain_entries_get_a_jump_to_the_review(api_server: RunningApi) -> None:
    from octaledger.domain.models import Quality

    activity = api_server.client.create_item("activities", "Meeting")
    api_server.client.start_tracking(activity["id"])
    with api_server.storage.transaction() as repos:
        running = repos.sessions.get_running()
        assert running is not None
        repos.sessions.set_quality(running.id, Quality.UNCERTAIN)
    at = open_page(api_server, "statistics")
    assert any("unsicher" in w.value for w in at.warning)
    at.button(key="bar_review").click().run()
    assert at.header[0].value == "Zeitjournal"


# ----------------------------------------------------------------------- first steps


def test_first_steps_guide_progress_and_navigation(api_server: RunningApi) -> None:
    at = open_app(api_server.client)
    assert "0 von 5 erledigt" in texts(at)
    at.button(key="step_0").click().run()  # "Zur Verwaltung"
    assert at.header[0].value == "Verwaltung"
    api_server.client.create_item("activities", "Meeting")
    at = goto(at, "overview")
    assert "1 von 5 erledigt" in texts(at)
    assert at.button(key="step_1") is not None  # the next open step now points to the devices


def test_first_steps_can_be_hidden(api_server: RunningApi) -> None:
    at = open_app(api_server.client)
    assert any("Erste Schritte" in m.value for m in at.markdown)
    at.button(key="hide_steps").click().run()
    assert not any("Erste Schritte" in m.value for m in at.markdown)


def test_first_steps_disappear_when_the_setup_is_complete(api_server: RunningApi) -> None:
    client = api_server.client
    activity = client.create_item("activities", "Meeting")
    device = client.register_device("Büro")
    client.set_device_address(device["id"], "AA:BB")
    client.assign_face(device["id"], 1, activity["id"])
    client.start_tracking(activity["id"])
    at = open_app(client)
    assert not any("Erste Schritte" in m.value for m in at.markdown)


# --------------------------------------------------------------------------- quick start


def test_quick_start_tile_starts_an_activity_with_one_click(api_server: RunningApi) -> None:
    client = api_server.client
    meeting = client.create_item("activities", "Meeting")
    client.create_item("activities", "Code")
    at = open_app(client)
    at.button(key=f"quick_{meeting['id']}").click().run()
    assert client.status()["tracking"]["activity"]["name"] == "Meeting"


def test_quick_start_ranks_by_recent_usage_and_limits_to_four(api_server: RunningApi) -> None:
    from datetime import datetime, timezone

    client = api_server.client
    names = ["Anna", "Berta", "Cäsar", "Dora", "Emil", "Zoe"]
    ids = {n: client.create_item("activities", n)["id"] for n in names}
    now = datetime.now(timezone.utc)
    for i in range(3):  # Zoe is used most, although she is last alphabetically
        client.add_session(
            ids["Zoe"], now - timedelta(days=3, hours=i + 1), now - timedelta(days=3, hours=i)
        )
    at = open_app(client)
    tiles = [b.key for b in at.button if str(b.key).startswith("quick_")]
    assert len(tiles) == 4 and tiles[0] == f"quick_{ids['Zoe']}"
    assert f"quick_{ids['Emil']}" not in tiles  # the 5th alphabetical one is not shown


def test_today_block_shows_totals_and_entries(api_server: RunningApi) -> None:
    activity = api_server.client.create_item("activities", "Meeting")
    api_server.client.start_tracking(activity["id"])
    at = open_app(api_server.client)
    assert {m.label for m in at.metric} >= {"Heute", "Diese Woche"}
    table = at.dataframe[0].value
    assert list(table["Tätigkeit"]) == ["Meeting"] and list(table["Ende"]) == ["läuft"]
    assert any("Mit Projekt oder Notiz starten" in e.label for e in at.expander)


# -------------------------------------------------------------- journal, stats, diagnostics


def test_journal_quick_ranges_set_the_dates(api_server: RunningApi) -> None:
    at = open_page(api_server, "journal")
    at.button(key="range_yesterday").click().run()
    yesterday = date.today() - timedelta(days=1)
    assert at.date_input(key="journal_from").value == yesterday
    assert at.date_input(key="journal_to").value == yesterday
    at.button(key="range_today").click().run()
    assert at.date_input(key="journal_from").value == date.today()
    at.button(key="range_month").click().run()
    assert at.date_input(key="journal_from").value == date.today() - timedelta(days=29)


def test_statistics_filters_are_folded_into_an_expander(api_server: RunningApi) -> None:
    api_server.client.create_item("activities", "Meeting")
    at = open_page(api_server, "statistics")
    assert any(e.label == "Filter (Tätigkeit, Projekt, Gerät)" for e in at.expander)
    assert at.selectbox(key="stat_activity") is not None  # still reachable


def test_diagnostics_has_a_traffic_light_summary(api_server: RunningApi) -> None:
    at = open_page(api_server, "diagnostics")
    rendered = texts(at)
    assert "Agent" in rendered and "Kein Tracker eingerichtet" in rendered
    assert "noch nicht geprüft" in rendered
    button(at, "Datenbank prüfen").click().run()
    assert any("in Ordnung" in s.value for s in at.success)
    assert "in Ordnung" in texts(at)  # the summary on top is up to date as well


# ---------------------------------------------------------------- design system assets


def test_self_hosted_font_is_shipped_and_referenced() -> None:
    font = PACKAGE / "static" / "Inter-Variable.woff2"
    assert font.read_bytes()[:4] == b"wOF2" and font.stat().st_size > 10_000
    assert (PACKAGE / "static" / "OFL.txt").read_text(encoding="utf-8").startswith("Copyright")
    assert FONT_URL.endswith("Inter-Variable.woff2") and FONT_URL in css(
        Theme.LIGHT, FontSize.NORMAL
    )
    root = Path(__file__).resolve().parents[2]
    assert 'octaledger.dashboard" = ["static/*"]' in (root / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "enableStaticServing = true" in (root / ".streamlit" / "config.toml").read_text(
        encoding="utf-8"
    )
    cli_source = (PACKAGE.parent / "cli.py").read_text(encoding="utf-8")
    assert "--server.enableStaticServing" in cli_source


def test_no_external_font_or_script_hosts_are_referenced() -> None:
    """GDPR: nothing may be loaded from a third-party CDN (Google Fonts etc.)."""
    for name in ("light", "dark"):
        stylesheet = css(Theme(name), FontSize.NORMAL)
        assert not re.search(r"https?://", stylesheet), name
    for path in PACKAGE.rglob("*.py"):
        assert "fonts.googleapis" not in path.read_text(encoding="utf-8"), path


def test_css_has_readability_features() -> None:
    stylesheet = css(Theme.DARK, FontSize.LARGE)
    assert "tabular-nums" in stylesheet  # running timers must not jitter
    assert ":focus-visible" in stylesheet and "outline: 3px" in stylesheet  # visible keyboard focus
    assert "font-size: 20px" in stylesheet and "max-width: 1200px" in stylesheet
    assert "border-radius: 12px" in stylesheet and "box-shadow" not in stylesheet


def test_ui_texts_use_entry_not_session_for_time_records() -> None:
    """Terminology: 'Eintrag' for a booked time span; 'Sitzung' only means the browser session."""
    allowed = ("diese Sitzung", "neuen Sitzung")
    for path in PACKAGE.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "Sitzung" in line:
                assert any(token in line for token in allowed), f"{path.name}: {line.strip()}"


@pytest.mark.parametrize("theme", list(Theme))
def test_both_schemes_define_the_same_css_structure(theme: Theme) -> None:
    stylesheet = css(theme, FontSize.NORMAL)
    for selector in (".st-key-statusbar", ".ol-nav-group", '[class*="st-key-nav_"]', ".ol-card"):
        assert selector in stylesheet


def test_package_has_no_pages_folder_next_to_the_entry_script() -> None:
    """Streamlit turns ``pages/`` beside the entry script into an automatic (broken) menu."""
    assert not (PACKAGE / "pages").exists()


@pytest.mark.parametrize("theme", list(Theme))
def test_native_theme_matches_the_palette(theme: Theme) -> None:
    """Pop-ups, date fields and tables follow Streamlit's native theme, not only our CSS."""
    options = native_theme_options(theme)
    palette = PALETTES[theme]
    assert options["theme.base"] == theme.value
    assert options["theme.backgroundColor"] == palette.background
    assert options["theme.secondaryBackgroundColor"] == palette.surface
    assert options["theme.textColor"] == palette.text
