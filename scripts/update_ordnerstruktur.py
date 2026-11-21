"""Regenerate the file list in ``docs/ORDNERSTRUKTUR.md`` from the files Git knows about.

Run from the project root after adding or removing files::

    .venv\\Scripts\\python.exe scripts\\update_ordnerstruktur.py

The list contains every tracked file plus new files that are not ignored, so it is correct
before the commit. ``tests/unit/test_documentation.py`` fails when a source or documentation
file is missing from the list, which is the reminder to run this script.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TARGET = Path("docs/ORDNERSTRUKTUR.md")
FENCE_START = "```text\n"
FENCE_END = "\n```"


def git_files() -> list[str]:
    """Return all tracked and untracked-but-not-ignored files, sorted case-insensitively."""
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted({line for line in output.splitlines() if line}, key=str.lower)


def main() -> int:
    """Rewrite the fenced list in the document; keep the file's own line endings."""
    raw = TARGET.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    start = text.index(FENCE_START) + len(FENCE_START)
    end = text.index(FENCE_END, start)
    block = "octaledger/\n" + "\n".join(f"  {name}" for name in git_files())
    TARGET.write_bytes((text[:start] + block + text[end:]).replace("\n", newline).encode("utf-8"))
    print(f"{TARGET}: {len(git_files())} files listed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
