"""Lightweight research/docs recall helpers.

Mission B2.2 introduces prompt-ready lookup utilities over the curated
documentation folders so assistants can surface relevant pointers without
manually scanning the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Mapping


_ALLOWED_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}
_DEFAULT_KB_ROOT = Path(__file__).resolve().parents[1] / "cmos"


@dataclass(slots=True)
class RecallResult:
    """Path + excerpt payload returned by :func:`recall_knowledge`."""

    path: str
    title: str
    excerpt: str
    score: float
    line: int | None = None

    def as_dict(self) -> Mapping[str, object]:
        """Return a JSON-serialisable representation of the result."""

        payload: dict[str, object] = {
            "path": self.path,
            "title": self.title,
            "excerpt": self.excerpt,
            "score": round(self.score, 4),
        }
        if self.line is not None:
            payload["line"] = self.line
        return payload


@dataclass(slots=True)
class _IndexedSnippet:
    path: Path
    rel_path: str
    title: str
    section: str | None
    line: int
    text: str

    @property
    def excerpt(self) -> str:
        return _shorten(self.text)


_INDEX_CACHE: dict[Path, tuple[_IndexedSnippet, ...]] = {}
_INDEX_SIGNATURES: dict[Path, dict[Path, float]] = {}


def recall_knowledge(
    query: str,
    *,
    limit: int = 5,
    kb_root: Path | None = None,
) -> list[RecallResult]:
    """Return ranked research/doc snippets relevant to *query*.

    Parameters
    ----------
    query:
        Natural-language question or keyword filter.
    limit:
        Maximum number of snippets to return (default: 5).
    kb_root:
        Optional override that points at the ``cmos`` directory when the helper
        is embedded in alternative environments (such as tests).
    """

    normalized_query = " ".join(query.split()).strip()
    if not normalized_query:
        raise ValueError("Query must include at least one term.")

    query_tokens = _tokenize(normalized_query)
    if not query_tokens:
        raise ValueError("Query must include at least one alphanumeric term.")

    root = (kb_root or _DEFAULT_KB_ROOT).resolve()
    snippets = _load_index(root)
    query_lower = normalized_query.lower()

    scored: list[tuple[float, _IndexedSnippet]] = []
    for snippet in snippets:
        score = _score_snippet(snippet, query_tokens, query_lower)
        if score > 0:
            scored.append((score, snippet))

    if not scored:
        return []

    scored.sort(key=lambda item: (-item[0], item[1].rel_path, item[1].line))
    results: list[RecallResult] = []
    for score, snippet in scored[: limit if limit > 0 else len(scored)]:
        excerpt = snippet.excerpt
        if snippet.section and snippet.section not in excerpt:
            excerpt = f"{snippet.section}: {excerpt}"
        results.append(
            RecallResult(
                path=snippet.rel_path,
                title=snippet.title,
                excerpt=excerpt,
                score=score,
                line=snippet.line,
            )
        )
    return results


def rebuild_index(kb_root: Path | None = None) -> int:
    """Force a rebuild of the cached snippets.

    Returns the number of snippet entries after the refresh.
    """

    root = (kb_root or _DEFAULT_KB_ROOT).resolve()
    snippets = _build_index(root)
    _INDEX_CACHE[root] = snippets
    _INDEX_SIGNATURES[root] = _build_signature(snippets)
    return len(snippets)


def _load_index(root: Path) -> tuple[_IndexedSnippet, ...]:
    cached = _INDEX_CACHE.get(root)
    signature = _INDEX_SIGNATURES.get(root)
    if cached is not None and signature is not None:
        current_signature = _collect_signature(root)
        if current_signature == signature:
            return cached

    snippets = _build_index(root)
    _INDEX_CACHE[root] = snippets
    _INDEX_SIGNATURES[root] = _build_signature(snippets)
    return snippets


def _build_index(root: Path) -> tuple[_IndexedSnippet, ...]:
    sources = list(_iter_source_files(root))
    snippets: list[_IndexedSnippet] = []
    for path in sources:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        title, blocks = _extract_paragraphs(text)
        if not title:
            title = path.stem.replace("_", " ").replace("-", " ") or path.name
        rel_path = _relative_path(path, root)
        for block in blocks:
            snippets.append(
                _IndexedSnippet(
                    path=path,
                    rel_path=rel_path,
                    title=title,
                    section=block.section,
                    line=block.line,
                    text=block.text,
                )
            )
    return tuple(snippets)


def _build_signature(snippets: Iterable[_IndexedSnippet]) -> dict[Path, float]:
    signature: dict[Path, float] = {}
    for snippet in snippets:
        try:
            signature[snippet.path] = snippet.path.stat().st_mtime
        except FileNotFoundError:
            signature[snippet.path] = 0.0
    return signature


def _collect_signature(root: Path) -> dict[Path, float]:
    signature: dict[Path, float] = {}
    for path in _iter_source_files(root):
        try:
            signature[path] = path.stat().st_mtime
        except FileNotFoundError:
            signature[path] = 0.0
    return signature


def _iter_source_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return

    docs_dir = root / "docs"
    research_dir = root / "research"

    for directory in (docs_dir, research_dir):
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in _ALLOWED_SUFFIXES:
                yield path


def _relative_path(path: Path, root: Path) -> str:
    candidates = [root.parent, root]
    for candidate in candidates:
        try:
            relative = path.relative_to(candidate)
            return relative.as_posix()
        except ValueError:
            continue
    return path.resolve().as_posix()


def _extract_paragraphs(text: str) -> tuple[str, list["_Paragraph"]]:
    lines = text.splitlines()
    title = None
    section = None
    in_code_block = False
    buffer: list[str] = []
    start_line = 1
    blocks: list[_Paragraph] = []

    def flush() -> None:
        nonlocal buffer, start_line, blocks, section
        if not buffer:
            return
        paragraph = " ".join(line.strip() for line in buffer if line.strip())
        paragraph = _collapse_spaces(paragraph)
        if paragraph:
            blocks.append(_Paragraph(text=paragraph, line=start_line, section=section))
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


def _collapse_spaces(text: str) -> str:
    parts = text.split()
    return " ".join(parts)


def _shorten(text: str, *, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    truncated = text[: limit - 3].rstrip()
    return f"{truncated}..."


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    word = []
    for char in text.lower():
        if char.isalnum():
            word.append(char)
        else:
            if word:
                token = "".join(word)
                if len(token) > 1:
                    tokens.append(token)
                word = []
    if word:
        token = "".join(word)
        if len(token) > 1:
            tokens.append(token)
    return tokens


def _score_snippet(snippet: _IndexedSnippet, tokens: list[str], query_lower: str) -> float:
    text_lower = snippet.text.lower()
    values: dict[str, int] = {}
    for token in tokens:
        values[token] = text_lower.count(token)
    direct_hits = sum(values.values())
    if direct_hits == 0 and query_lower not in text_lower:
        matcher = SequenceMatcher(None, query_lower, text_lower)
        ratio = matcher.quick_ratio()
        return ratio if ratio > 0.6 else 0.0

    score = float(direct_hits)
    if query_lower in text_lower:
        score += 1.0

    unique_hits = sum(1 for token in set(tokens) if token in text_lower)
    score += 0.25 * unique_hits

    return score


@dataclass(slots=True)
class _Paragraph:
    text: str
    line: int
    section: str | None
