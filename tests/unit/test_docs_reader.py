"""Tests for reading the user documentation inside the dashboard."""

from pathlib import Path

from octaledger.dashboard.docs_reader import (
    DOCUMENTS,
    Chapter,
    clean_links,
    docs_dir,
    load_document,
    search,
    split_chapters,
)

SAMPLE = """# Titel

Einleitung mit [Testplan](TESTPLAN.md) und [Web](https://example.org/x).

**Inhalt**

1. [Was ist das?](#1-was-ist-das)
2. [Start](#2-start)

## 1. Was ist das?

Text eins.

```bash
## kein Kapitel, nur ein Kommentar im Codeblock
echo hi
```

## 2. Start

Siehe [Kapitel eins](#1-was-ist-das) oder [Datei](docs/X.md "Titel").
"""


def test_document_is_split_into_chapters_and_the_intro_loses_its_table_of_contents() -> None:
    intro, chapters = split_chapters(SAMPLE)
    assert [c.title for c in chapters] == ["1. Was ist das?", "2. Start"]
    assert intro.startswith("# Titel") and "Einleitung" in intro
    assert "Inhalt" not in intro and "#1-was-ist-das" not in intro  # the picker replaces it


def test_a_comment_line_in_a_code_block_does_not_start_a_chapter() -> None:
    _, chapters = split_chapters(SAMPLE)
    assert "## kein Kapitel" in chapters[0].body and len(chapters) == 2


def test_links_to_files_and_anchors_become_text_and_web_links_stay() -> None:
    intro, chapters = split_chapters(SAMPLE)
    assert "Testplan" in intro and "(TESTPLAN.md)" not in intro
    assert "[Web](https://example.org/x)" in intro
    assert chapters[1].body == "Siehe Kapitel eins oder Datei."
    assert clean_links("[a](b.md) [c](https://d.e)") == "a [c](https://d.e)"


def test_windows_line_endings_are_handled() -> None:
    _, chapters = split_chapters("# T\r\n\r\n## A\r\n\r\ntext\r\n\r\n## B\r\n")
    assert [c.title for c in chapters] == ["A", "B"] and chapters[0].body == "text"


def test_search_matches_title_and_text_case_insensitively() -> None:
    chapters = [Chapter("Start", "Bluetooth einschalten"), Chapter("Daten", "Sicherung")]
    assert search(chapters, "") == chapters
    assert search(chapters, "BLUETOOTH") == [chapters[0]]
    assert search(chapters, "daten") == [chapters[1]]
    assert search(chapters, "gibt es nicht") == []


def test_missing_or_oversized_documents_return_none(tmp_path: Path) -> None:
    assert load_document("fehlt.md", tmp_path) is None
    (tmp_path / "gross.md").write_text("x" * 10, encoding="utf-8")
    assert load_document("gross.md", tmp_path) == "x" * 10


def test_undecodable_documents_return_none(tmp_path: Path) -> None:
    (tmp_path / "kaputt.md").write_bytes(b"\xff\xfe\x00\x01")
    assert load_document("kaputt.md", tmp_path) is None


def test_the_shipped_documents_exist_and_have_chapters() -> None:
    assert docs_dir() is not None
    for _label, file_name in DOCUMENTS:
        text = load_document(file_name)
        assert text, file_name
        _, chapters = split_chapters(text)
        assert len(chapters) >= 3, file_name
        assert all(c.body for c in chapters), file_name
        assert "](#" not in "\n".join(c.body for c in chapters)  # no dead in-page anchors
