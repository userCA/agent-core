"""Centralized logging configuration for agent-core."""

from __future__ import annotations

import logging
import os
from typing import Any

DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the agent_core namespace prefix."""
    return logging.getLogger(f"agent_core.{name}")


def configure_logging(
    level: int | str = logging.INFO,
    fmt: str | None = None,
    handler: logging.Handler | None = None,
) -> None:
    """Configure root logging for agent-core.

    Reads AGENT_CORE_LOG_LEVEL from environment if no level is provided.
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    env_level = os.environ.get("AGENT_CORE_LOG_LEVEL")
    if env_level:
        level = getattr(logging, env_level.upper(), level)

    formatter = logging.Formatter(fmt or DEFAULT_FORMAT)
    h = handler or logging.StreamHandler()
    h.setFormatter(formatter)

    root = logging.getLogger("agent_core")
    root.setLevel(level)
    # Remove existing handlers to avoid duplicates on re-configuration
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(h)
