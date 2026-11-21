"""Read the user documentation (Markdown files in ``docs/``) so the dashboard can show it.

Responsibility
--------------
The start page lets users read the whole user documentation without leaving the program. The
documents stay ordinary Markdown files in ``docs/`` (single source of truth, also readable on
GitHub); this module only finds them, splits them into chapters and makes them fit a web page:

* the documents on offer cover **users** (handbook, installation, glossary) and **developers**
  (architecture, interface, data model, adapter guide, software documentation, security),
* a document is split at its ``## `` headings, so one chapter is shown at a time,
* the table of contents with in-page anchors is dropped (the chapter picker replaces it),
* links to other project files cannot work inside the dashboard, so only their text is kept;
  external ``https://`` links stay clickable.

Pure functions, no Streamlit: everything is unit-tested.

Limits: the documents are found next to the source tree (``<project>/docs``). In an installation
without the project folder the page shows a hint instead of the text.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import octaledger

logger = logging.getLogger(__name__)

#: Documents offered on the start page: ``(label, file name)``; the order is the picker order.
DOCUMENTS: Final = (
    ("Benutzerhandbuch", "BENUTZERHANDBUCH.md"),
    ("Installation und Betrieb", "INSTALLATION.md"),
    ("Glossar", "GLOSSAR.md"),
    ("Architektur", "ARCHITEKTUR.md"),
    ("Schnittstelle (API)", "API.md"),
    ("Datenmodell", "DATENMODELL.md"),
    ("Rezepte: Node-RED und mehr", "REZEPTE.md"),
    ("Anbindungen entwickeln (Adapter)", "ADAPTER_ENTWICKLUNG.md"),
    ("Software-Dokumentation", "SOFTWAREDOKUMENTATION.md"),
    ("Grenzen und Quellen", "QUELLEN_UND_GRENZEN.md"),
    ("Geplante Erweiterungen", "UMSETZUNGSPLAN.md"),
    ("Sicherheit", "SECURITY.md"),
)

#: Offered documents that live in the project root instead of ``docs/`` (an allow-list: a file
#: name is never taken from the user, so this cannot be used to read arbitrary files).
ROOT_DOCUMENTS: Final = frozenset({"SECURITY.md"})

#: Documents larger than this are not shown (a defensive bound, the real files are far smaller).
MAX_BYTES: Final = 2 * 1024 * 1024

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_TOC_LINE = re.compile(r"^\s*\d+\.\s+\[[^\]]+\]\(#[^)]*\)\s*$")


@dataclass(frozen=True, slots=True)
class Chapter:
    """One ``## `` section of a document."""

    title: str
    body: str


def project_dir() -> Path:
    """Return the project folder (the one that contains ``docs`` next to the source tree)."""
    return Path(octaledger.__file__).resolve().parents[2]


def docs_dir() -> Path | None:
    """Return the ``docs`` folder of the project, or ``None`` if it is not available."""
    candidate = project_dir() / "docs"
    return candidate if candidate.is_dir() else None


def clean_links(text: str) -> str:
    """Keep external links, reduce every other link (files, anchors) to its text."""

    def replace(match: re.Match[str]) -> str:
        """Keep web links, reduce every other link to its visible text."""
        label, target = match.group(1), match.group(2)
        return match.group(0) if target.startswith(("https://", "http://")) else label

    return _LINK.sub(replace, text)


def split_chapters(markdown: str) -> tuple[str, list[Chapter]]:
    """Split a document into its introduction and its ``## `` chapters.

    Lines inside fenced code blocks never start a chapter. The table-of-contents list (numbered
    anchor links) and the bold "Inhalt" label are removed from the introduction.

    Returns:
        ``(introduction, chapters)``; the introduction still contains the ``# `` title.
    """
    intro: list[str] = []
    chapters: list[tuple[str, list[str]]] = []
    in_fence = False
    for line in markdown.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            chapters.append((line[3:].strip(), []))
            continue
        (chapters[-1][1] if chapters else intro).append(line)
    cleaned = [
        line
        for line in intro
        if not _TOC_LINE.match(line) and line.strip() not in ("**Inhalt**", "Inhalt")
    ]
    return (
        clean_links("\n".join(cleaned)).strip(),
        [Chapter(title, clean_links("\n".join(body)).strip()) for title, body in chapters],
    )


def load_document(file_name: str, directory: Path | None = None) -> str | None:
    """Return the text of a document, or ``None`` if it is missing, too large or unreadable."""
    if directory is not None:
        folder: Path | None = directory
    elif file_name in ROOT_DOCUMENTS:
        folder = project_dir()
    else:
        folder = docs_dir()
    if folder is None:
        return None
    path = folder / file_name
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("Could not read the documentation file %s", file_name, exc_info=True)
        return None


def search(chapters: list[Chapter], term: str) -> list[Chapter]:
    """Chapters whose title or text contains ``term`` (case-insensitive); all if it is empty."""
    needle = term.strip().casefold()
    if not needle:
        return chapters
    return [c for c in chapters if needle in c.title.casefold() or needle in c.body.casefold()]
