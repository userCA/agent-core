"""Edit tool — replace exact text in a file."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalFileOperations


class EditTool(Tool):
    def __init__(self, cwd: str = "", file_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._file_ops = file_ops or LocalFileOperations(cwd=self._cwd)
        self.definition = ToolDefinition(
            name="edit",
            description="Edit a file by replacing exact text. Prefer this over 'write' for small changes.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute file path"},
                    "old_string": {"type": "string", "description": "Exact text to replace"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_string", "new_string"],
            },
            prompt_guidelines=[
                "When editing files, prefer the 'edit' tool over 'write' for small changes.",
                "Always provide the exact old_string that appears in the file.",
            ],
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        path = params.get("path", "")
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")

        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        path = os.path.normpath(path)

        try:
            ok = await self._file_ops.edit(path, old_string, new_string)
            if not ok:
                return ToolResult(
                    content=[TextContent(text=f"Error: old_string not found in {path}")],
                    is_error=True,
                )
            return ToolResult(
                content=[TextContent(text=f"File edited successfully: {path}")],
                display={"operation": "edit", "path": path},
            )
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))], is_error=True)


def create_edit_tool(cwd: str = "", file_ops: Any | None = None) -> EditTool:
    return EditTool(cwd, file_ops)


edit_tool = EditTool()
