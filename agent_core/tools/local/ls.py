"""Ls tool — list directory contents."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations


class LsTool(Tool):
    def __init__(self, cwd: str = "", file_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
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

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        path = params.get("path", "")
        if not path:
            path = self._cwd
        elif not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            infos = await self._file_ops.ls(path)
            lines = [f"Contents of {path}:", ""]
            for info in infos:
                prefix = "[D]" if info.is_dir else "[F]"
                lines.append(f"{prefix} {info.name}")
            return ToolResult(content=[TextContent(text="\n".join(lines))])
        except FileNotFoundError:
            return ToolResult(content=[TextContent(text=f"Directory not found: {path}")])
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_ls_tool(cwd: str = "", file_ops: Any | None = None) -> LsTool:
    return LsTool(cwd, file_ops)


ls_tool = LsTool()
