"""Dynamic guideline generation based on active tools."""

from __future__ import annotations

from typing import Callable

from agent_core.tools.base import ToolDefinition

GuidelineRule = Callable[[set[str]], str | None]

_DEFAULT_RULES: list[GuidelineRule] = [
    lambda tools: "Prefer grep/find/ls over bash when searching files."
    if {"grep", "find", "ls"} & tools else None,
    lambda tools: "Always use 'edit' for small changes instead of rewriting entire files."
    if "edit" in tools else None,
    lambda tools: "When using 'read', the output is automatically truncated if too large."
    if "read" in tools else None,
    lambda tools: "Before creating files, check if they already exist with 'ls'."
    if {"write", "edit"} & tools else None,
]


def generate_guidelines(tools: list[ToolDefinition], rules: list[GuidelineRule] | None = None) -> list[str]:
    """Generate dynamic guidelines based on active tool names."""
    tool_names = {t.name for t in tools}
    rules = rules or _DEFAULT_RULES
    guidelines: list[str] = []
    for rule in rules:
        guideline = rule(tool_names)
        if guideline:
            guidelines.append(guideline)
    return guidelines
