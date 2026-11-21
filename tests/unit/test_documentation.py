"""Guard tests: the documentation must stay complete and consistent with the code.

Documentation rots silently, so these tests turn the project's documentation rules into failures:

* every module, class and function of the source tree has a docstring,
* every API route is listed in ``docs/API.md``,
* every file of the source tree and of ``docs/`` is listed in ``docs/ORDNERSTRUKTUR.md``,
* every relative link between Markdown files points to an existing file.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "octaledger"
DOCS = ROOT / "docs"

_ROUTE = re.compile(r"@(?:router|public)\.(get|post|put|patch|delete)\(\s*\"(/[^\"]*)\"")
_PLACEHOLDER = re.compile(r"\{[^}]*\}")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")


def _missing_docstrings() -> list[str]:
    """Locations (file:line name) of modules, classes and functions lacking a docstring."""
    missing: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = path.relative_to(ROOT).as_posix()
        if path.name != "__init__.py" or path.stat().st_size > 0:
            if ast.get_docstring(tree) is None:
                missing.append(f"{relative}: module")
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue
            if node.name.startswith("__") and node.name.endswith("__"):
                continue  # dunder methods are documented by the language
            if ast.get_docstring(node) is None:
                missing.append(f"{relative}:{node.lineno} {node.name}")
    return missing


def test_every_module_class_and_function_has_a_docstring() -> None:
    assert _missing_docstrings() == []


def _route_signatures() -> set[tuple[str, str]]:
    """``(METHOD, normalised path)`` of every literal route declared in routes.py."""
    text = (SRC / "api" / "routes.py").read_text(encoding="utf-8")
    return {(m.upper(), _PLACEHOLDER.sub("{}", p)) for m, p in _ROUTE.findall(text)}


def test_routes_are_found() -> None:
    # Guards the regular expression itself: a restructured routes.py must not pass silently.
    assert len(_route_signatures()) >= 45


def test_every_route_is_documented_in_the_api_reference() -> None:
    reference = _PLACEHOLDER.sub("{}", (DOCS / "API.md").read_text(encoding="utf-8"))
    undocumented = [
        f"{method} {path}"
        for method, path in sorted(_route_signatures())
        if not re.search(re.escape(f"{method} {path}") + r"(?![\w/{-])", reference)
    ]
    assert undocumented == []


@pytest.mark.parametrize("kind", ["activities", "projects"])
@pytest.mark.parametrize(
    "method_and_suffix",
    ["GET ", "POST ", "PATCH |/{}", "POST |/{}/archive", "DELETE |/{}"],
)
def test_catalogue_routes_are_documented(kind: str, method_and_suffix: str) -> None:
    # These five routes per kind are registered in a loop, so the regular expression above
    # cannot see them.
    reference = _PLACEHOLDER.sub("{}", (DOCS / "API.md").read_text(encoding="utf-8"))
    method, _, suffix = method_and_suffix.partition("|")
    assert f"{method.strip()} /{kind}{suffix}" in reference


def test_every_source_and_doc_file_is_in_the_folder_structure_document() -> None:
    listing = (DOCS / "ORDNERSTRUKTUR.md").read_text(encoding="utf-8")
    files = [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]
    files += list(DOCS.glob("*.md"))
    files += list(DOCS.glob("images/*"))
    missing = sorted(
        p.relative_to(ROOT).as_posix()
        for p in files
        if p.relative_to(ROOT).as_posix() not in listing
    )
    assert missing == []


def _markdown_files() -> list[Path]:
    files = sorted(DOCS.glob("*.md"))
    files += [
        ROOT / name for name in ("README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md")
    ]
    return [p for p in files if p.exists()]


def test_relative_markdown_links_point_to_existing_files() -> None:
    broken: list[str] = []
    for document in _markdown_files():
        text = document.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)  # links in code samples are examples
        for target in _LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            file_part = target.split("#", 1)[0]
            if file_part and not (document.parent / file_part).resolve().exists():
                broken.append(f"{document.relative_to(ROOT).as_posix()} -> {target}")
    assert broken == []
