"""Grep tool — search file contents with regex."""

from __future__ import annotations

import fnmatch
import os
import re
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations


class GrepTool(Tool):
    def __init__(self, cwd: str = "", file_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
        self.definition = ToolDefinition(
            name="grep",
            description="Search for a pattern in files using regular expressions.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regular expression pattern to search for"},
                    "path": {"type": "string", "description": "File or directory to search in. Defaults to current working directory."},
                    "include": {"type": "string", "description": "Glob pattern for files to include (e.g. '*.py')"},
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        pattern = params.get("pattern", "")
        path = params.get("path", "")
        include = params.get("include", "")

        if not path:
            path = self._cwd
        elif not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        # Validate regex up-front for friendlier errors
        try:
            re.compile(pattern)
        except re.error as exc:
            return ToolResult(content=[TextContent(text=f"Invalid regex: {exc}")])

        try:
            results = await self._file_ops.grep(pattern, path, recursive=True)
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])

        # Filter by include glob pattern (applied to filename)
        if include:
            filtered: list[str] = []
            for line in results:
                # Each result line is "file_path:line:content"
                file_part = line.split(":", 1)[0]
                if fnmatch.fnmatch(os.path.basename(file_part), include):
                    filtered.append(line)
            results = filtered

        # Filter out hidden directories/files for usability
        results = [
            r for r in results
            if not any(part.startswith(".") for part in r.split(":", 1)[0].split(os.sep) if part)
        ]

        if not results:
            return ToolResult(content=[TextContent(text=f"No matches found for pattern: {pattern}")])
        return ToolResult(content=[TextContent(text="\n".join(results[:500]))])


def create_grep_tool(cwd: str = "", file_ops: Any | None = None) -> GrepTool:
    return GrepTool(cwd, file_ops)


grep_tool = GrepTool()
