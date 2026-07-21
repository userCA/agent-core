"""Working memory flags for http_sse scene (H4)."""

from __future__ import annotations

import os
from typing import Any


def working_memory_enabled() -> bool:
    return os.environ.get("ENABLE_WORKING_MEMORY", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def install_scene_working_memory(
    tool_registry: Any,
    *,
    extensions: list[Any] | None = None,
) -> tuple[Any | None, list[Any]]:
    """Register working_memory when enabled; return (store|None, extensions)."""
    ext_list = list(extensions or [])
    if not working_memory_enabled():
        return None, ext_list
    from agent_core.working_memory import install_working_memory

    store, _, ext_list = install_working_memory(tool_registry, extensions=ext_list)
    return store, ext_list
