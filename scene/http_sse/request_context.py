"""Request-scoped context for passing HTTP headers into tool hooks."""

from __future__ import annotations

from contextvars import ContextVar

current_request_headers: ContextVar[dict[str, str]] = ContextVar(
    "current_request_headers", default={}
)
