"""A bug on one page must neither show a stack trace nor blank the app (error handling)."""

import dataclasses

import pytest

from octaledger.core.logging import recent_log_lines
from octaledger.dashboard.views import PAGES
from tests.conftest import RunningApi
from tests.gui.test_gui_core import open_app


def broken_page(client: object, tz: str) -> None:
    raise KeyError("secret-looking-internal-name")


def test_an_unexpected_error_is_logged_and_shown_calmly(
    api_server: RunningApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(PAGES, "journal", dataclasses.replace(PAGES["journal"], render=broken_page))
    at = open_app(api_server.client)
    at.sidebar.button(key="nav_journal").click().run()
    assert not at.exception  # no stack trace on the page
    assert any("unerwarteter Fehler" in e.value for e in at.error)
    assert any("Fehlercode: OL-GENERIC-000" in c.value for c in at.caption)
    assert "secret-looking-internal-name" not in " ".join(str(m.value) for m in at.markdown)
    # the traceback went to the log (the dashboard configures the in-memory sink itself)
    logged = " | ".join(recent_log_lines())
    assert "Unexpected error on page journal" in logged and "KeyError" in logged
    # the menu still works: another page opens normally
    at.sidebar.button(key="nav_overview").click().run()
    assert not at.exception and not any("unerwarteter Fehler" in e.value for e in at.error)
