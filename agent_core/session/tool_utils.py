"""Shared tool-name helpers for AgentHarness."""

from __future__ import annotations

from typing import Any


def resolve_tool_name(tool: Any, index: int = 0) -> str:
    name = getattr(tool, "name", None)
    if name:
        return str(name)
    definition = getattr(tool, "definition", None)
    if definition is not None:
        def_name = getattr(definition, "name", None)
        if def_name:
            return str(def_name)
    return str(index)


def filter_active_tools(tools: list[Any], active_tool_names: list[str] | None) -> list[Any]:
    if active_tool_names is None:
        return list(tools)
    active = set(active_tool_names)
    return [
        t for i, t in enumerate(tools)
        if resolve_tool_name(t, i) in active
    ]


# Core tools that always retain full schema in catalog mode.
_CATALOG_ALWAYS_TOOLS = frozenset({
    "bash", "read", "write", "edit", "tool_detail",
    "working_memory", "manage_plan",
})


def filter_catalog_tools(tools: list[Any]) -> list[Any]:
    """In catalog mode, only keep core tools + tool_detail for provider schema."""
    return [
        t for i, t in enumerate(tools)
        if resolve_tool_name(t, i) in _CATALOG_ALWAYS_TOOLS
    ]
