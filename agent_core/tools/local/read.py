"""Read tool — read file contents with optional line range and truncation."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations
from agent_core.tools.truncate import format_size, truncate_tail

DEFAULT_MAX_BYTES = 32_000
DEFAULT_MAX_LINES = 500


class ReadTool(Tool):
    def __init__(
        self,
        cwd: str = "",
        file_ops: Any | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_lines: int = DEFAULT_MAX_LINES,
    ) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
        self._max_bytes = max_bytes
        self._max_lines = max_lines
        self.definition = ToolDefinition(
            name="read",
            description="Read a file from the local filesystem. Supports optional offset and limit for partial reads. Large files are automatically truncated.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "offset": {"type": "integer", "description": "Line offset to start reading from (0-indexed)", "minimum": 0},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read", "minimum": 1},
                },
                "required": ["path"],
            },
            prompt_guidelines=[
                f"Files larger than {format_size(max_bytes)} or {max_lines} lines will be truncated.",
            ],
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        path = params.get("path", "")
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        offset = params.get("offset")
        limit = params.get("limit")

        try:
            content = await self._file_ops.read(path, offset=offset or 0, limit=limit)
            truncated = False
            lines = content.splitlines()
            if len(lines) > self._max_lines:
                content = "\n".join(lines[: self._max_lines]) + "\n... (truncated)"
                truncated = True
            elif len(content.encode("utf-8")) > self._max_bytes:
                content = truncate_tail(content, self._max_bytes, hint="... (truncated)")
                truncated = True

            return ToolResult(
                content=[TextContent(text=content)],
                details={"truncated": truncated, "path": path},
            )
        except FileNotFoundError:
            return ToolResult(content=[TextContent(text=f"File not found: {path}")], details={"error": "not_found"})
        except IsADirectoryError:
            return ToolResult(content=[TextContent(text=f"Path is a directory: {path}")], details={"error": "is_directory"})
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))], details={"error": "read_failed"})


def create_read_tool(cwd: str = "", file_ops: Any | None = None) -> ReadTool:
    return ReadTool(cwd, file_ops)


read_tool = ReadTool()
