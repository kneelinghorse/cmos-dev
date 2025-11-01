"""Shared helpers for documentation and research indexing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Tuple


ALLOWED_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}
DEFAULT_KB_ROOT = Path(__file__).resolve().parents[1] / "cmos"


@dataclass(slots=True)
class Paragraph:
    """Normalized representation of a document paragraph."""

    text: str
    line: int
    section: str | None


def normalize_root(root: Path | None) -> Path:
    """Return the resolved knowledge base root directory."""

    return (root or DEFAULT_KB_ROOT).resolve()


def iter_source_files(root: Path) -> Iterator[Path]:
    """Yield research/doc files allowed for indexing."""

    docs_dir = root / "docs"
    research_dir = root / "research"

    for directory in (docs_dir, research_dir):
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES:
                yield path


def relative_path(path: Path, root: Path) -> str:
    """Compute a stable repository-relative path for *path*."""

    candidates = [root.parent, root]
    for candidate in candidates:
        try:
            return path.relative_to(candidate).as_posix()
        except ValueError:
            continue
    return path.resolve().as_posix()


def extract_paragraphs(text: str) -> Tuple[str, list[Paragraph]]:
    """Split a document into logical paragraphs with headings."""

    lines = text.splitlines()
    title = None
    section = None
    in_code_block = False
    buffer: list[str] = []
    start_line = 1
    blocks: list[Paragraph] = []

    def flush() -> None:
        nonlocal buffer, start_line, blocks, section
        if not buffer:
            return
        paragraph = " ".join(line.strip() for line in buffer if line.strip())
        paragraph = collapse_spaces(paragraph)
        if paragraph:
            blocks.append(Paragraph(text=paragraph, line=start_line, section=section))
        buffer = []

    for index, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            flush()
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if stripped.startswith("#"):
            flush()
            heading_text = stripped.lstrip("#").strip()
            if title is None and stripped.startswith("# "):
                title = heading_text if heading_text else None
            section = heading_text or section
            continue
        if not stripped:
            flush()
            continue
        if not buffer:
            start_line = index
        buffer.append(stripped)

    flush()

    if title is None:
        title = ""

    return title, blocks


def collapse_spaces(text: str) -> str:
    """Normalize whitespace runs inside *text*."""

    parts = text.split()
    return " ".join(parts)


def shorten(text: str, *, limit: int = 280) -> str:
    """Return a shortened snippet that fits within *limit* characters."""

    if len(text) <= limit:
        return text
    truncated = text[: limit - 3].rstrip()
    return f"{truncated}..."

