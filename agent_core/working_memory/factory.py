"""install_working_memory — register tool + extension."""

from __future__ import annotations

from typing import Any

from agent_core.session.tool_utils import resolve_tool_name
from agent_core.tools.base import ToolRegistry
from agent_core.working_memory.extension import WorkingMemoryExtension
from agent_core.working_memory.store import WorkingMemoryStore
from agent_core.working_memory.tool import WorkingMemoryTool


def install_working_memory(
    tool_registry: ToolRegistry,
    *,
    store: WorkingMemoryStore | None = None,
    extensions: list[Any] | None = None,
    max_insights: int = 12,
) -> tuple[WorkingMemoryStore, WorkingMemoryTool, list[Any]]:
    """Register ``working_memory`` and append ``WorkingMemoryExtension``."""
    mem = store if store is not None else WorkingMemoryStore(max_insights=max_insights)
    tool = WorkingMemoryTool(store=mem)
    name = resolve_tool_name(tool)
    if tool_registry.get(name) is None:
        tool_registry.register(tool)

    ext_list = list(extensions or [])
    if not any(getattr(e, "name", None) == "working_memory" for e in ext_list):
        ext_list.append(WorkingMemoryExtension(mem))
    return mem, tool, ext_list
