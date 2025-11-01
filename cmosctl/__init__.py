"""
Command-line entry point for the CMOS toolkit.

Mission B1.2 introduces the Typer-based CLI with mission management commands.
Mission B2.1 adds conversational trigger helpers for automated workflows.
"""

from .cli import main
from .triggers import (
    MissionContext,
    MissionRunOutcome,
    TriggerRegistry,
    default_registry,
)

__all__ = ["main", "default_registry", "TriggerRegistry", "MissionContext", "MissionRunOutcome"]
