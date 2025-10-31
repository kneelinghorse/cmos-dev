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
