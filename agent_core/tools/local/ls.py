"""Ls tool — list directory contents."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult


class LsTool(Tool):
    def __init__(self, cwd: str = "") -> None:
        self._cwd = cwd or os.getcwd()
        self.definition = ToolDefinition(
            name="ls",
            description="List the contents of a directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the directory. Defaults to current working directory."},
                },
                "required": [],
            },
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = params.get("path", "")
        if not path:
            path = self._cwd
        elif not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            entries = os.listdir(path)
            lines = [f"Contents of {path}:", ""]
            for name in sorted(entries):
                full = os.path.join(path, name)
                prefix = "[D]" if os.path.isdir(full) else "[F]"
                lines.append(f"{prefix} {name}")
            return ToolResult(content=[TextContent(text="\n".join(lines))])
        except FileNotFoundError:
            return ToolResult(content=[TextContent(text=f"Directory not found: {path}")])
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_ls_tool(cwd: str = "") -> LsTool:
    return LsTool(cwd)


ls_tool = LsTool()
