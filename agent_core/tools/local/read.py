"""Read tool — read file contents with optional line range."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import ImageContent, TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult


class ReadTool(Tool):
    def __init__(self, cwd: str = "") -> None:
        self._cwd = cwd or os.getcwd()
        self.definition = ToolDefinition(
            name="read",
            description="Read a file from the local filesystem. Supports optional offset and limit for partial reads.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "offset": {"type": "integer", "description": "Line offset to start reading from (1-indexed)", "minimum": 1},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read", "minimum": 1},
                },
                "required": ["path"],
            },
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = params.get("path", "")
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        offset = params.get("offset")
        limit = params.get("limit")

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if offset is not None or limit is not None:
                    lines = f.readlines()
                    start = (offset or 1) - 1
                    end = start + (limit or len(lines))
                    content = "".join(lines[start:end])
                else:
                    content = f.read()
            return ToolResult(content=[TextContent(text=content)])
        except FileNotFoundError:
            return ToolResult(content=[TextContent(text=f"File not found: {path}")], details={"error": "not_found"})
        except IsADirectoryError:
            return ToolResult(content=[TextContent(text=f"Path is a directory: {path}")], details={"error": "is_directory"})
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))], details={"error": "read_failed"})


def create_read_tool(cwd: str = "") -> ReadTool:
    return ReadTool(cwd)


read_tool = ReadTool()
