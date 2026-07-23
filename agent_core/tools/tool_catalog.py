"""Meta-tool: tool_detail — lets the LLM query full schema for any registered tool on demand."""

from __future__ import annotations

import json
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import ToolContext, ToolDefinition, ToolRegistry, ToolResult


class ToolCatalogTool:
    """Meta-tool that returns full parameter definitions for requested tools.

    Used in catalog mode where the system prompt only contains a lightweight
    tool directory (name + one-line description).  When the LLM needs to call
    a tool whose full schema was not included in the provider request, it
    calls ``tool_detail`` first to retrieve the complete definition.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self.definition = ToolDefinition(
            name="tool_detail",
            description=(
                "获取指定工具的完整参数说明。"
                "当你需要调用某个工具但不确定参数格式时使用。"
                "支持一次查询多个工具。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要查询详情的工具名列表",
                    },
                },
                "required": ["tool_names"],
            },
            prompt_snippet="查询工具的完整参数定义",
        )

    async def execute(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        names = params.get("tool_names", [])
        parts: list[str] = []
        for name in names:
            tool = self._registry.get(name)
            if tool is None:
                parts.append(f"[{name}] — not found")
                continue
            d = tool.definition
            schema_text = json.dumps(d.parameters, indent=2, ensure_ascii=False)
            lines = [
                f"### {d.name}",
                f"",
                f"{d.description}",
                f"",
                f"**Parameters:**",
                f"```json",
                schema_text,
                f"```",
            ]
            if d.prompt_guidelines:
                lines.append("")
                lines.append("**Guidelines:**")
                for g in d.prompt_guidelines:
                    lines.append(f"- {g}")
            parts.append("\n".join(lines))

        text = "\n\n---\n\n".join(parts) if parts else "No tools specified."
        return ToolResult(content=[TextContent(text=text)])
