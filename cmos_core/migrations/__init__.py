"""
Lightweight migration registry.

The MVP only needs a placeholder so future missions can register migrations
without changing the database initialization code.
"""

from __future__ import annotations

import sqlite3
from typing import Callable, Iterator, List, Tuple

MigrationCallback = Callable[[sqlite3.Connection], None]


class MigrationManager:
    """In-memory registry that can apply migrations in insertion order."""

    def __init__(self) -> None:
        self._migrations: List[Tuple[str, MigrationCallback]] = []

    def register(self, name: str, func: MigrationCallback) -> None:
        if any(existing == name for existing, _ in self._migrations):
            raise ValueError(f"Migration '{name}' already registered")
        self._migrations.append((name, func))

    def names(self) -> Iterator[str]:
        for name, _ in self._migrations:
            yield name

    def apply_all(self, conn: sqlite3.Connection) -> None:
        for _, func in self._migrations:
            func(conn)


migration_manager = MigrationManager()

# Placeholder example to illustrate usage in documentation or tests. The
# function is intentionally a no-op so the initialization step has no side
# effects beyond schema creation.


def _baseline(conn: sqlite3.Connection) -> None:
    """Baseline migration placeholder."""


migration_manager.register("baseline", _baseline)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _ensure_kb_metadata(conn: sqlite3.Connection) -> None:
    if _column_exists(conn, "kb_sources", "title") is False:
        conn.execute("ALTER TABLE kb_sources ADD COLUMN title TEXT")
    if _column_exists(conn, "kb_sources", "fingerprint") is False:
        conn.execute("ALTER TABLE kb_sources ADD COLUMN fingerprint TEXT")
    if _column_exists(conn, "kb_chunks", "order_index") is False:
        conn.execute("ALTER TABLE kb_chunks ADD COLUMN order_index INTEGER")
    if _column_exists(conn, "kb_chunks", "section") is False:
        conn.execute("ALTER TABLE kb_chunks ADD COLUMN section TEXT")
    if _column_exists(conn, "kb_chunks", "line") is False:
        conn.execute("ALTER TABLE kb_chunks ADD COLUMN line INTEGER")
    conn.commit()


migration_manager.register("kb_metadata_columns", _ensure_kb_metadata)
