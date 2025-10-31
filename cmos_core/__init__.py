"""
Core utilities for interacting with the CMOS persistence layer.

This package intentionally uses only the Python standard library so that
early missions can run in constrained environments without extra dependencies.
"""

from . import schema

__all__ = ["schema"]
