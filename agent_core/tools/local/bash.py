"""Bash tool — execute shell commands with streaming and timeout support."""

from __future__ import annotations

import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalBashOperations


class BashTool(Tool):
    def __init__(self, cwd: str = "", bash_ops: Any | None = None) -> None:
        self._cwd = cwd or os.getcwd()
        self._bash_ops = bash_ops or LocalBashOperations(cwd=self._cwd)
        self.definition = ToolDefinition(
            name="bash",
            description="Execute a bash shell command. Use with caution.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds. Default is 60.", "minimum": 1, "maximum": 300},
                },
                "required": ["command"],
            },
            prompt_guidelines=[
                "Prefer grep/find/ls over bash when searching files.",
                "Commands run in the current working directory unless cd is used.",
            ],
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None) -> ToolResult:
        command = params.get("command", "")
        timeout = params.get("timeout", 60)

        try:
            result = await self._bash_ops.execute(command, timeout=float(timeout))
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            if not output.strip():
                output = "(no output)"

            return ToolResult(
                content=[TextContent(text=output)],
                details={"exit_code": result.returncode, "truncated": result.truncated},
            )
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_bash_tool(cwd: str = "", bash_ops: Any | None = None) -> BashTool:
    return BashTool(cwd, bash_ops)


bash_tool = BashTool()
