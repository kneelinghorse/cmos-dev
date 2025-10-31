"""
Database schema helpers for CMOS.

The SQL statements mirror the authoritative definitions in
`cmos/docs/cmos-technical_architecture-v2-simplified.md`.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, Sequence

# Ordered collection of SQL statements that must run during initialization.
SCHEMA_STATEMENTS: Sequence[str] = (
    """
    CREATE TABLE IF NOT EXISTS missions (
      id TEXT PRIMARY KEY,
      sprint_id TEXT,
      name TEXT,
      status TEXT DEFAULT 'Queued',
      created_at TEXT DEFAULT (datetime('now')),
      completed_at TEXT,
      notes TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT DEFAULT (datetime('now')),
      mission_id TEXT,
      action TEXT,
      agent TEXT,
      summary TEXT,
      details TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS project_state (
      key TEXT PRIMARY KEY,
      value TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS decisions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT DEFAULT (datetime('now')),
      mission_id TEXT,
      title TEXT,
      rationale TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS facts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT DEFAULT (datetime('now')),
      mission_id TEXT,
      kind TEXT,
      content TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS kb_sources (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      path TEXT UNIQUE,
      last_indexed_ts TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS kb_chunks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_id INTEGER REFERENCES kb_sources(id),
      text TEXT
    );
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts
    USING fts5(text, content='kb_chunks', content_rowid='id');
    """,
)

PRAGMAS: Sequence[str] = (
    "PRAGMA foreign_keys = ON;",
)


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """Ensure SQLite pragmas required by the project are set."""
    for pragma in PRAGMAS:
        conn.execute(pragma)


def apply_schema(conn: sqlite3.Connection, statements: Iterable[str] | None = None) -> None:
    """
    Apply the CMOS schema to the provided SQLite connection.

    Parameters
    ----------
    conn:
        An open sqlite3.Connection where the schema should be applied.
    statements:
        Optional override of the SQL statements to execute.
    """
    apply_pragmas(conn)
    for statement in statements or SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.commit()
