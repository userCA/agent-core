"""Memory feature flags and shared store for http_sse scene."""

from __future__ import annotations

import os
from typing import Any

_SHARED_INMEMORY: Any | None = None


def memory_enabled() -> bool:
    return os.environ.get("ENABLE_MEMORY", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def resolve_memory_backend(explicit: str = "") -> str:
    """Return backend name, or empty string when memory is off.

    *explicit* (ChatAssistant.create argument) wins when non-empty.
    Otherwise ENABLE_MEMORY + MEMORY_BACKEND (default ``inmemory``).
    """
    if explicit.strip():
        return explicit.strip()
    if not memory_enabled():
        return ""
    return os.environ.get("MEMORY_BACKEND", "inmemory").strip() or "inmemory"


def shared_inmemory_store() -> Any:
    """Process-wide inmemory store so session rebuilds keep recalls."""
    global _SHARED_INMEMORY
    if _SHARED_INMEMORY is None:
        from agent_core.memory.adapters import InMemoryMemoryStore

        _SHARED_INMEMORY = InMemoryMemoryStore()
    return _SHARED_INMEMORY


def build_memory_extensions(
    backend: str, config: dict[str, Any], session_id: str
) -> list[Any]:
    if not backend:
        return []
    from agent_core.memory.extension import MemoryExtension

    if backend == "inmemory":
        store = shared_inmemory_store()
    elif backend == "mem0":
        from agent_core.memory.adapters import Mem0MemoryStore

        store = Mem0MemoryStore()
    elif backend == "openviking":
        from agent_core.memory.adapters import OpenVikingMemoryStore

        store = OpenVikingMemoryStore(
            url=config.get("url", "http://localhost:1933"),
            api_key=config.get("api_key", ""),
            api_keys=config.get("api_keys"),
            resolve_api_key=config.get("resolve_api_key"),
        )
    else:
        return []
    return [MemoryExtension(store=store, session_id=session_id)]
