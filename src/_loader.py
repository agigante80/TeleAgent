"""Shared helper for conditional module loading — used by factory.py and main.py."""
from __future__ import annotations

from pathlib import Path


def _module_file_exists(rel_path: str) -> bool:
    """Return True if the Python source file exists at *rel_path* relative to repo root."""
    root = Path(__file__).parent.parent
    return (root / rel_path).is_file()
