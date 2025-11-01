"""
Command-line entry point for the CMOS toolkit.

Mission B1.2 introduces the Typer-based CLI with mission management commands.
Mission B2.1 adds conversational trigger helpers for automated workflows.
"""

from .cli import main
from .kb import SearchHit, index_knowledge, search_knowledge, validate_queries
from .recall import RecallResult, recall_knowledge, rebuild_index
from .triggers import (
    MissionContext,
    MissionRunOutcome,
    TriggerRegistry,
    default_registry,
)

__all__ = [
    "main",
    "default_registry",
    "TriggerRegistry",
    "MissionContext",
    "MissionRunOutcome",
    "recall_knowledge",
    "RecallResult",
    "rebuild_index",
    "search_knowledge",
    "SearchHit",
    "index_knowledge",
    "validate_queries",
]
