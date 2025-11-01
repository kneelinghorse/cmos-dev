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

from ._knowledge import extract_paragraphs, iter_source_files, normalize_root, relative_path, shorten


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
        return shorten(self.text)


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

    root = normalize_root(kb_root)
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

    root = normalize_root(kb_root)
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
    sources = list(iter_source_files(root))
    snippets: list[_IndexedSnippet] = []
    for path in sources:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        title, paragraphs = extract_paragraphs(text)
        if not title:
            title = path.stem.replace("_", " ").replace("-", " ") or path.name
        rel_path = relative_path(path, root)
        for block in paragraphs:
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
    for path in iter_source_files(root):
        try:
            signature[path] = path.stat().st_mtime
        except FileNotFoundError:
            signature[path] = 0.0
    return signature


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
