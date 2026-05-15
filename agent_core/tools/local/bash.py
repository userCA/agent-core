"""Bash tool — execute shell commands."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult


class BashTool(Tool):
    def __init__(self, cwd: str = "") -> None:
        self._cwd = cwd or os.getcwd()
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
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        command = params.get("command", "")
        timeout = params.get("timeout", 60)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n" + stderr.decode("utf-8", errors="replace")
            return ToolResult(
                content=[TextContent(text=output or "(no output)")],
                details={"exit_code": proc.returncode},
            )
        except asyncio.TimeoutError:
            return ToolResult(
                content=[TextContent(text=f"Command timed out after {timeout} seconds")],
                details={"error": "timeout"},
            )
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_bash_tool(cwd: str = "") -> BashTool:
    return BashTool(cwd)


bash_tool = BashTool()
