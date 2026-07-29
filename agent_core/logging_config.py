"""Centralized logging configuration for agent-core.

Provides context-aware structured logging via :mod:`contextvars`.
When :func:`set_log_context` is called (typically at the start of an
agent run), all subsequent log records automatically carry
``session_id``, ``run_id`` and ``turn_index`` fields.
"""

from __future__ import annotations

import contextvars
import logging
import os
from typing import Any

# -- Context variables propagated across async tasks ---------------------------
_log_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("log_session_id", default="")
_log_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("log_run_id", default="")
_log_turn_index: contextvars.ContextVar[int] = contextvars.ContextVar("log_turn_index", default=0)


def set_log_context(
    *,
    session_id: str = "",
    run_id: str = "",
    turn_index: int = 0,
) -> None:
    """Set logging context for the current async task.

    All log records emitted after this call will carry the provided fields
    as ``extra`` attributes, usable by :class:`ContextFormatter`.
    """
    if session_id:
        _log_session_id.set(session_id)
    if run_id:
        _log_run_id.set(run_id)
    _log_turn_index.set(turn_index)


def get_log_context() -> dict[str, Any]:
    """Return the current logging context as a dict."""
    return {
        "session_id": _log_session_id.get(),
        "run_id": _log_run_id.get(),
        "turn_index": _log_turn_index.get(),
    }


class ContextFormatter(logging.Formatter):
    """Formatter that prepends ``[session_id|run_id|turn]`` to each record.

    Fields are only included when non-empty, keeping output clean for
    code paths that have not yet set a context.
    """

    def format(self, record: logging.LogRecord) -> str:
        parts: list[str] = []
        sid = _log_session_id.get()
        rid = _log_run_id.get()
        turn = _log_turn_index.get()
        if sid:
            parts.append(f"session={sid}")
        if rid:
            parts.append(f"run={rid}")
        if turn:
            parts.append(f"turn={turn}")
        prefix = f"[{', '.join(parts)}] " if parts else ""
        record.msg = f"{prefix}{record.msg}"
        return super().format(record)


DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the agent_core namespace prefix."""
    return logging.getLogger(f"agent_core.{name}")


def configure_logging(
    level: int | str = logging.INFO,
    fmt: str | None = None,
    handler: logging.Handler | None = None,
    *,
    use_context_formatter: bool = True,
) -> None:
    """Configure root logging for agent-core.

    Reads AGENT_CORE_LOG_LEVEL from environment if no level is provided.
    When *use_context_formatter* is True (default), the handler uses
    :class:`ContextFormatter` which injects ``session_id``, ``run_id``
    and ``turn_index`` from the current async context.
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    env_level = os.environ.get("AGENT_CORE_LOG_LEVEL")
    if env_level:
        level = getattr(logging, env_level.upper(), level)

    if use_context_formatter:
        formatter: logging.Formatter = ContextFormatter(fmt or DEFAULT_FORMAT)
    else:
        formatter = logging.Formatter(fmt or DEFAULT_FORMAT)
    h = handler or logging.StreamHandler()
    h.setFormatter(formatter)

    root = logging.getLogger("agent_core")
    root.setLevel(level)
    # Remove existing handlers to avoid duplicates on re-configuration
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(h)
