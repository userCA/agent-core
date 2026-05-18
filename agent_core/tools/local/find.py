"""Find tool — find files by name pattern."""

from __future__ import annotations

import fnmatch
import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations


class FindTool(Tool):
    def __init__(self, cwd: str = "", file_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
        self.definition = ToolDefinition(
            name="find",
            description="Find files by name pattern in a directory tree.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Filename pattern to search for (supports * and ? wildcards)"},
                    "path": {"type": "string", "description": "Directory to search in. Defaults to current working directory."},
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        pattern = params.get("pattern", "")
        path = params.get("path", "")

        if not path:
            path = self._cwd
        elif not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            results = await self._file_ops.find(path, name_pattern=None)
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])

        # Apply glob pattern filter (fnmatch supports * and ? wildcards)
        filtered: list[str] = []
        for file_path in results:
            if fnmatch.fnmatch(os.path.basename(file_path), pattern):
                # Skip hidden directories/files for usability
                if not any(part.startswith(".") for part in file_path.split(os.sep) if part):
                    filtered.append(file_path)

        if not filtered:
            return ToolResult(content=[TextContent(text=f"No files found matching: {pattern}")])
        return ToolResult(content=[TextContent(text="\n".join(filtered[:500]))])


def create_find_tool(cwd: str = "", file_ops: Any | None = None) -> FindTool:
    return FindTool(cwd, file_ops)


find_tool = FindTool()
