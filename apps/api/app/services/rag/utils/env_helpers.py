"""
Environment variable helper utilities for RAG configuration.

This module provides type-safe environment variable parsing functions
that are shared across the RAG subsystem.
"""

from __future__ import annotations

import os


def env_bool(name: str, default: bool = False) -> bool:
    """
    Parse a boolean value from an environment variable.

    Recognizes "1", "true", "yes", "on" (case-insensitive) as True.
    Returns default if the variable is not set.

    Args:
        name: Environment variable name
        default: Default value if not set

    Returns:
        Parsed boolean value
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    """
    Parse an integer value from an environment variable.

    Returns default if the variable is not set or cannot be parsed.

    Args:
        name: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Parsed integer value
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    """
    Parse a float value from an environment variable.

    Returns default if the variable is not set or cannot be parsed.

    Args:
        name: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Parsed float value
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


__all__ = ["env_bool", "env_int", "env_float"]
