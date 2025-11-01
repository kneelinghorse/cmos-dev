"""FTS-backed knowledge base helpers for research/docs search."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from . import db as db_commands
from ._knowledge import Paragraph, extract_paragraphs, iter_source_files, normalize_root, relative_path, shorten


@dataclass(slots=True)
class SearchHit:
    """Result payload returned by :func:`search_knowledge`."""

    path: str
    title: str
    section: str | None
    line: int | None
    snippet: str
    score: float

    def as_dict(self) -> Mapping[str, object]:
        payload: dict[str, object] = {
            "path": self.path,
            "title": self.title,
            "snippet": self.snippet,
            "score": round(self.score, 4),
        }
        if self.section:
            payload["section"] = self.section
        if self.line is not None:
            payload["line"] = self.line
        return payload


DEFAULT_VALIDATION_QUERIES: Sequence[str] = (
    "FTS5 search",
    "trigger registry",
    "Sprint transition",
)


def index_knowledge(
    *,
    db_path: Path | str = db_commands.DEFAULT_DB_PATH,
    kb_root: Path | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Index research/docs content into the SQLite FTS tables."""

    root = normalize_root(kb_root)
    stats: dict[str, int] = {"indexed": 0, "skipped": 0, "deleted": 0, "chunks": 0}

    if not root.exists():
        return stats

    sources = list(iter_source_files(root))
    seen_paths: set[str] = set()
    now = _utc_now_iso()

    with db_commands.connect(db_path) as conn:
        db_commands.migration_manager.apply_all(conn)
        existing_sources = {
            row["path"]: {"id": row["id"], "fingerprint": row["fingerprint"]}
            for row in conn.execute("SELECT id, path, fingerprint FROM kb_sources")
        }

        for path in sources:
            rel_path = relative_path(path, root)
            seen_paths.add(rel_path)
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="ignore")
            fingerprint = _fingerprint(text)
            title, paragraphs = extract_paragraphs(text)
            if not title:
                title = path.stem.replace("_", " ").replace("-", " ") or path.name

            existing = existing_sources.get(rel_path)
            if existing and not force and existing.get("fingerprint") == fingerprint:
                stats["skipped"] += 1
                continue

            if existing:
                source_id = existing["id"]
                _remove_source_chunks(conn, source_id)
                conn.execute(
                    """
                    UPDATE kb_sources
                    SET title = ?, fingerprint = ?, last_indexed_ts = ?
                    WHERE id = ?
                    """,
                    (title, fingerprint, now, source_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO kb_sources (path, title, fingerprint, last_indexed_ts)
                    VALUES (?, ?, ?, ?)
                    """,
                    (rel_path, title, fingerprint, now),
                )
                source_id = cursor.lastrowid
                existing_sources[rel_path] = {"id": source_id, "fingerprint": fingerprint}

            chunk_count = _insert_chunks(conn, source_id, paragraphs)
            stats["indexed"] += 1
            stats["chunks"] += chunk_count

        for rel_path, existing in existing_sources.items():
            if rel_path in seen_paths:
                continue
            source_id = existing["id"]
            _remove_source_chunks(conn, source_id)
            conn.execute("DELETE FROM kb_sources WHERE id = ?", (source_id,))
            stats["deleted"] += 1

        conn.commit()

    return stats


def search_knowledge(
    query: str,
    *,
    db_path: Path | str = db_commands.DEFAULT_DB_PATH,
    limit: int = 5,
) -> list[SearchHit]:
    """Execute an FTS5 search over indexed knowledge chunks."""

    normalized_query = " ".join(query.split()).strip()
    if not normalized_query:
        raise ValueError("Query must include at least one term.")

    limit_clause = max(limit, 0)

    with db_commands.connect(db_path) as conn:
        db_commands.migration_manager.apply_all(conn)
        conn.execute("PRAGMA case_sensitive_like = OFF;")
        sql = (
            """
            SELECT
                c.id AS chunk_id,
                s.path AS path,
                s.title AS title,
                c.section AS section,
                c.line AS line,
                c.text AS text,
                c.order_index AS order_index,
                bm25(kb_chunks_fts) AS rank
            FROM kb_chunks_fts
            JOIN kb_chunks c ON kb_chunks_fts.rowid = c.id
            JOIN kb_sources s ON c.source_id = s.id
            WHERE kb_chunks_fts MATCH ?
            ORDER BY rank ASC, s.path ASC, c.order_index ASC
            """
        )
        params: list[object] = [normalized_query]
        if limit_clause > 0:
            sql += " LIMIT ?"
            params.append(limit_clause)

        rows = conn.execute(sql, params).fetchall()

    results: list[SearchHit] = []
    for row in rows:
        score_raw = row["rank"] if row["rank"] is not None else 0.0
        score = 1.0 / (1.0 + max(score_raw, 0.0))
        snippet = shorten(row["text"])
        results.append(
            SearchHit(
                path=row["path"],
                title=row["title"] or row["path"],
                section=row["section"],
                line=row["line"],
                snippet=snippet,
                score=score,
            )
        )
    return results


def validate_queries(
    *,
    db_path: Path | str = db_commands.DEFAULT_DB_PATH,
    kb_root: Path | None = None,
    queries: Sequence[str] | None = None,
    limit: int = 3,
    refresh: bool = True,
) -> list[dict[str, object]]:
    """Run representative validation queries against the index."""

    if refresh:
        index_knowledge(db_path=db_path, kb_root=kb_root)

    sample_queries = list(queries) if queries else list(DEFAULT_VALIDATION_QUERIES)
    report: list[dict[str, object]] = []
    for query in sample_queries:
        hits = search_knowledge(query, db_path=db_path, limit=limit)
        report.append({"query": query, "hit_count": len(hits), "hits": [hit.as_dict() for hit in hits]})
    return report


def _fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _insert_chunks(conn: sqlite3.Connection, source_id: int, paragraphs: Iterable[Paragraph]) -> int:
    count = 0
    for index, block in enumerate(paragraphs):
        text = block.text.strip()
        if not text:
            continue
        cursor = conn.execute(
            """
            INSERT INTO kb_chunks (source_id, order_index, section, line, text)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_id, index, block.section, block.line, text),
        )
        chunk_id = cursor.lastrowid
        conn.execute("INSERT INTO kb_chunks_fts(rowid, text) VALUES (?, ?)", (chunk_id, text))
        count += 1
    return count


def _remove_source_chunks(conn: sqlite3.Connection, source_id: int) -> None:
    conn.execute(
        "DELETE FROM kb_chunks_fts WHERE rowid IN (SELECT id FROM kb_chunks WHERE source_id = ?)",
        (source_id,),
    )
    conn.execute("DELETE FROM kb_chunks WHERE source_id = ?", (source_id,))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
