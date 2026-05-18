"""Write tool — write or overwrite a file."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations


class WriteTool(Tool):
    def __init__(self, cwd: str = "", file_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
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
            prompt_guidelines=[
                "Always provide the full desired content of the file.",
            ],
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        path = params.get("path", "")
        content = params.get("content", "")

        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            file_ops = self._file_ops
            # Use mutation queue if available in context
            if ctx is not None and ctx.mutation_queue is not None:
                await ctx.mutation_queue.write_locked(file_ops, path, content)
            else:
                await file_ops.write(path, content)

            display: dict[str, Any] = {"operation": "write", "path": path}
            # Simple heuristic for code display hint
            if "." in os.path.basename(path):
                ext = os.path.basename(path).split(".")[-1]
                if ext in ("py", "js", "ts", "json", "yaml", "yml", "md", "sh", "go", "rs", "java"):
                    display["language"] = ext

            return ToolResult(
                content=[TextContent(text=f"File written successfully: {path}")],
                display=display,
            )
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_write_tool(cwd: str = "", file_ops: Any | None = None) -> WriteTool:
    return WriteTool(cwd, file_ops)


write_tool = WriteTool()
