"""Guard tests for the documentation *inside* the dashboard.

Project rule (``CLAUDE.md`` section 6): every page explains itself ("So funktioniert diese
Seite") and **every** input has a help tooltip. Instead of trusting reviews, these tests read the
page modules and fail when a page or an input lacks its documentation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from octaledger.dashboard.docs_reader import DOCUMENTS, docs_dir, load_document, split_chapters
from octaledger.dashboard.views import PAGES

VIEWS = Path(__file__).resolve().parents[2] / "src" / "octaledger" / "dashboard" / "views"

#: Streamlit inputs and controls that must carry ``help=``: every field, every switch and (since
#: AP-34) every button, because the project promises an explanation for each control.
INPUTS = frozenset(
    {
        "button",
        "download_button",
        "form_submit_button",
        "text_input",
        "text_area",
        "number_input",
        "selectbox",
        "multiselect",
        "radio",
        "checkbox",
        "toggle",
        "slider",
        "date_input",
        "time_input",
        "file_uploader",
        "segmented_control",
        "pills",
        "color_picker",
    }
)

#: Pages that explain themselves differently (the start page *is* the explanation).
NO_PAGE_HELP = frozenset({"start"})


def _page_modules() -> list[Path]:
    return sorted(p for p in VIEWS.glob("*.py") if p.name != "__init__.py")


def _unhelped_inputs(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in INPUTS and not any(kw.arg == "help" for kw in node.keywords):
            problems.append(f"{path.name}:{node.lineno} {node.func.attr}")
    return problems


def test_every_input_of_every_page_has_a_help_text() -> None:
    problems = [problem for path in _page_modules() for problem in _unhelped_inputs(path)]
    assert problems == []


@pytest.mark.parametrize("slug", sorted(PAGES))
def test_every_page_explains_itself(slug: str) -> None:
    if slug in NO_PAGE_HELP:
        pytest.skip("the start page is itself the explanation")
    module = PAGES[slug].render.__module__.rsplit(".", 1)[-1]
    source = (VIEWS / f"{module}.py").read_text(encoding="utf-8")
    assert "page_help(" in source, f"page {slug} has no 'So funktioniert diese Seite' explanation"


def test_every_page_has_a_menu_description() -> None:
    # The description is the tooltip of the menu entry; an empty one leaves the user guessing.
    assert [slug for slug, page in PAGES.items() if len(page.description) < 20] == []


def test_every_document_offered_in_the_handbook_exists_and_has_chapters() -> None:
    folder = docs_dir()
    assert folder is not None
    for label, file_name in DOCUMENTS:
        text = load_document(file_name)
        assert text is not None, f"{label}: {file_name} not found"
        _, chapters = split_chapters(text)
        assert chapters, f"{label}: {file_name} has no '## ' chapters to pick from"
