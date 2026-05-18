"""Extract one-line tool snippets for system prompts."""

from __future__ import annotations

from agent_core.tools.base import ToolDefinition


def extract_snippet(definition: ToolDefinition) -> str:
    """Extract a one-line description for a tool.

    Priority:
    1. ToolDefinition.prompt_snippet
    2. First sentence of description (truncated to 80 chars)
    3. Tool name
    """
    if definition.prompt_snippet:
        return definition.prompt_snippet

    if definition.description:
        sentence = definition.description.split(".")[0].strip()
        if len(sentence) > 80:
            sentence = sentence[:77] + "..."
        return sentence

    return definition.name
