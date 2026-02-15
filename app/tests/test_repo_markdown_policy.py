from __future__ import annotations

from pathlib import Path


def test_root_directory_contains_no_markdown_files() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    markdown_files = sorted(path.name for path in repo_root.glob("*.md"))
    assert markdown_files == [], f"root markdown files must be moved to docs/: {markdown_files}"

