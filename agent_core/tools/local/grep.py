"""Grep tool — search file contents with regex."""

from __future__ import annotations

import os
import re
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult


class GrepTool(Tool):
    def __init__(self, cwd: str = "") -> None:
        self._cwd = cwd or os.getcwd()
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

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        pattern = params.get("pattern", "")
        path = params.get("path", "")
        include = params.get("include", "")

        if not path:
            path = self._cwd
        elif not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return ToolResult(content=[TextContent(text=f"Invalid regex: {exc}")])

        results: list[str] = []

        def search_file(file_path: str) -> None:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(f"{file_path}:{i}: {line.rstrip()}")
            except (IsADirectoryError, OSError):
                pass

        if os.path.isfile(path):
            search_file(path)
        elif os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                # Skip hidden directories
                if any(part.startswith(".") for part in root.split(os.sep) if part):
                    continue
                for name in sorted(files):
                    if name.startswith("."):
                        continue
                    if include and not self._glob_match(name, include):
                        continue
                    full = os.path.join(root, name)
                    search_file(full)

        if not results:
            return ToolResult(content=[TextContent(text=f"No matches found for pattern: {pattern}")])
        return ToolResult(content=[TextContent(text="\n".join(results[:500]))])

    @staticmethod
    def _glob_match(name: str, pattern: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(name, pattern)


def create_grep_tool(cwd: str = "") -> GrepTool:
    return GrepTool(cwd)


grep_tool = GrepTool()
