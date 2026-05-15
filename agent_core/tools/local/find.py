"""Find tool — find files by name pattern."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult


class FindTool(Tool):
    def __init__(self, cwd: str = "") -> None:
        self._cwd = cwd or os.getcwd()
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

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        import fnmatch

        pattern = params.get("pattern", "")
        path = params.get("path", "")

        if not path:
            path = self._cwd
        elif not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        results: list[str] = []

        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                # Skip hidden directories
                if any(part.startswith(".") for part in root.split(os.sep) if part):
                    continue
                for name in sorted(files):
                    if name.startswith("."):
                        continue
                    if fnmatch.fnmatch(name, pattern):
                        results.append(os.path.join(root, name))
        elif os.path.isfile(path) and fnmatch.fnmatch(os.path.basename(path), pattern):
            results.append(path)

        if not results:
            return ToolResult(content=[TextContent(text=f"No files found matching: {pattern}")])
        return ToolResult(content=[TextContent(text="\n".join(results[:500]))])


def create_find_tool(cwd: str = "") -> FindTool:
    return FindTool(cwd)


find_tool = FindTool()
