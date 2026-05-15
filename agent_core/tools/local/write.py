"""Write tool — write or overwrite a file."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult


class WriteTool(Tool):
    def __init__(self, cwd: str = "") -> None:
        self._cwd = cwd or os.getcwd()
        self.definition = ToolDefinition(
            name="write",
            description="Write content to a file. Creates the file if it does not exist, overwrites it otherwise.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "content": {"type": "string", "description": "Content to write to the file"},
                },
                "required": ["path", "content"],
            },
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = params.get("path", "")
        content = params.get("content", "")

        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(content=[TextContent(text=f"File written successfully: {path}")])
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_write_tool(cwd: str = "") -> WriteTool:
    return WriteTool(cwd)


write_tool = WriteTool()
