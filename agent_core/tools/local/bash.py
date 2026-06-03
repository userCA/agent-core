"""Bash tool — execute shell commands with streaming and timeout support."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Callable

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult
from agent_core.tools.operations_local import LocalBashOperations
from agent_core.tools.truncate import format_size, truncate_head

DEFAULT_MAX_CHARS = 50_000
DEFAULT_MAX_LINES = 200

BashSpawnHook = Callable[[dict[str, Any]], dict[str, Any]]


class BashTool(Tool):
    def __init__(
        self,
        cwd: str = "",
        bash_ops: Any | None = None,
        *,
        command_prefix: str | None = None,
        spawn_hook: BashSpawnHook | None = None,
    ) -> None:
        self._cwd = cwd or os.getcwd()
        self._bash_ops = bash_ops or LocalBashOperations(cwd=self._cwd)
        self._command_prefix = command_prefix
        self._spawn_hook = spawn_hook
        self.definition = ToolDefinition(
            name="bash",
            description="Execute a bash shell command. Use with caution.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds. Default is 60.",
                        "minimum": 1,
                        "maximum": 300,
                    },
                },
                "required": ["command"],
            },
            prompt_guidelines=[
                "Prefer grep/find/ls over bash when searching files.",
                "Commands run in the current working directory unless cd is used.",
            ],
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None
    ) -> ToolResult:
        command = params.get("command", "")
        timeout = params.get("timeout", 60)

        if self._command_prefix:
            command = f"{self._command_prefix}\n{command}"

        if self._spawn_hook:
            spawn_ctx = {"command": command, "cwd": self._cwd, "env": {}}
            spawn_ctx = self._spawn_hook(spawn_ctx)
            command = spawn_ctx.get("command", command)

        def _on_data(data: bytes) -> None:
            if ctx is not None and ctx.on_update is not None:
                ctx.on_update(
                    ToolResult(
                        content=[TextContent(text=data.decode("utf-8", errors="replace"))]
                    )
                )

        try:
            result = await self._bash_ops.execute(
                command,
                timeout=float(timeout),
                on_data=_on_data,
                signal=ctx.signal if ctx is not None else None,
            )

            output = result.stdout
            if result.stderr and result.stderr != result.stdout:
                output = f"{output}\n{result.stderr}" if output else result.stderr

            # Tail truncation: keep last portion (most recent output is most relevant)
            truncation_info = None
            full_output_path = result.full_output_path
            if len(output) > DEFAULT_MAX_CHARS or output.count("\n") > DEFAULT_MAX_LINES:
                truncation_info = {
                    "total_chars": len(output),
                    "total_lines": output.count("\n") + 1,
                    "max_chars": DEFAULT_MAX_CHARS,
                    "max_lines": DEFAULT_MAX_LINES,
                }
                # Save full output to temp file before truncating
                if not full_output_path:
                    try:
                        fd, full_output_path = tempfile.mkstemp(
                            prefix="bash-output-", suffix=".log"
                        )
                        os.close(fd)
                        with open(full_output_path, "w", encoding="utf-8") as f:
                            f.write(output)
                    except OSError:
                        full_output_path = None

                output = truncate_head(output, DEFAULT_MAX_CHARS)
                # Also apply line limit
                lines = output.splitlines()
                if len(lines) > DEFAULT_MAX_LINES:
                    kept = lines[-DEFAULT_MAX_LINES:]
                    output = f"... ({len(lines) - DEFAULT_MAX_LINES} lines skipped)\n" + "\n".join(kept)
                result.truncated = True

            if not output.strip():
                output = "(no output)"

            details: dict[str, Any] = {
                "exit_code": result.returncode,
                "truncated": result.truncated,
            }
            if full_output_path:
                details["full_output_path"] = full_output_path
            if truncation_info:
                details["truncation_info"] = truncation_info

            return ToolResult(
                content=[TextContent(text=output)],
                details=details,
            )
        except Exception as exc:
            return ToolResult(content=[TextContent(text=str(exc))])


def create_bash_tool(
    cwd: str = "",
    bash_ops: Any | None = None,
    *,
    command_prefix: str | None = None,
    spawn_hook: BashSpawnHook | None = None,
) -> BashTool:
    return BashTool(cwd, bash_ops, command_prefix=command_prefix, spawn_hook=spawn_hook)


bash_tool = BashTool()
