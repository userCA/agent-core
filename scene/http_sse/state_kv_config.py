"""Session State KV flags for http_sse scene (H3)."""

from __future__ import annotations

import os
from typing import Any

_SHARED_STORE: Any | None = None


def state_kv_enabled() -> bool:
    return os.environ.get("ENABLE_STATE_KV", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def shared_state_store() -> Any:
    """Process-wide InMemorySessionStateStore (MVP; lost on restart)."""
    global _SHARED_STORE
    if _SHARED_STORE is None:
        from agent_core.state_kv import InMemorySessionStateStore

        _SHARED_STORE = InMemorySessionStateStore()
    return _SHARED_STORE


def build_state_kv_extension() -> tuple[Any, Any] | tuple[None, None]:
    """Return ``(store, extension)`` when enabled, else ``(None, None)``."""
    if not state_kv_enabled():
        return None, None

    from agent_core.state_kv import create_state_kv_extension

    store = shared_state_store()
    _, ext = create_state_kv_extension(store)
    return store, ext
