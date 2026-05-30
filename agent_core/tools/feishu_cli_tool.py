"""Feishu CLI tool — wrap lark-cli for agent-driven Feishu operations.

Install:  npm install -g @larksuite/cli
Requires: lark-cli in PATH, app credentials configured via lark-cli config init

Gives the agent access to 200+ Feishu operations: send messages, manage
calendars, query documents, create tasks, etc.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import shlex

from agent_core.core.content import TextContent
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult

_log = logging.getLogger(__name__)

LARK_CLI = shutil.which("lark-cli") or "lark-cli"
TIMEOUT_DEFAULT = 30


class FeishuCLITool(Tool):
    """Execute Feishu/Lark operations via the official lark-cli tool.

    The agent can use this tool to:
    - Send messages to chats/users
    - Query and manage calendars
    - Access documents, sheets, and knowledge bases
    - Manage approvals, tasks, and more
    """

    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="feishu",
            description=(
                "Execute Feishu/Lark operations via the official lark-cli. "
                "Install with: npm install -g @larksuite/cli"
                "\n\n"
                "Common commands:\n"
                "  lark-cli im +messages-send --as bot --chat-id <id> --text <text>\n"
                "  lark-cli im +messages-list --as bot --chat-id <id> --page-size 10\n"
                "  lark-cli calendar +agenda --as user\n"
                "  lark-cli drive +docs-search --as user --query <q>\n"
                "  lark-cli task +tasks-list --as user\n"
                "\nUse --as bot for bot actions, --as user for user actions."
                "Output is JSON; use jq or string parsing as needed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "The lark-cli command to execute (without the 'lark-cli' prefix). "
                            "Example: 'im +messages-send --as bot --chat-id oc_xxx --text Hello'"
                        ),
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds. Default 30, max 120.",
                        "minimum": 1,
                        "maximum": 120,
                    },
                },
                "required": ["command"],
            },
            prompt_snippet=(
                "feishu $ARGUMENTS — Execute Feishu/Lark operations via lark-cli.\n"
                "Available: send messages, query calendar, search docs, manage tasks, etc.\n"
                "Use --as bot for bot-scoped actions, --as user for user-scoped."
            ),
            timeout_seconds=60,
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext | None
    ) -> ToolResult:
        raw = params.get("command", "").strip()
        if not raw:
            return ToolResult(content=[TextContent(text="Error: 'command' parameter is required")])

        # Sanitize input — prevent shell injection
        try:
            args = shlex.split(raw)
        except ValueError as e:
            return ToolResult(content=[TextContent(text=f"Invalid command syntax: {e}")])

        # Build full command
        full_cmd = [LARK_CLI] + args
        timeout = min(int(params.get("timeout", TIMEOUT_DEFAULT)), 120)

        _log.info("lark-cli: %s", " ".join(full_cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "NO_COLOR": "1"},
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            output = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()
            exit_code = proc.returncode or 0

            # Try to pretty-print JSON output
            if output.startswith("{") or output.startswith("["):
                try:
                    parsed = json.loads(output)
                    output = json.dumps(parsed, ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    pass

            result_text = output or "(no output)"
            if exit_code != 0:
                result_text = f"Error (exit {exit_code}):\n{err or output}"
            elif err:
                result_text += f"\n\n(stderr):\n{err}"

            truncated = len(result_text) > 8000
            if truncated:
                result_text = result_text[:8000] + "\n... (truncated)"

            return ToolResult(
                content=[TextContent(text=result_text)],
                details={"exit_code": exit_code, "truncated": truncated},
            )

        except asyncio.TimeoutError:
            return ToolResult(
                content=[TextContent(text=f"Command timed out after {timeout}s")],
                details={"exit_code": -1, "timeout": True},
            )
        except FileNotFoundError:
            return ToolResult(
                content=[TextContent(
                    text="lark-cli not found. Install: npm install -g @larksuite/cli\n"
                         "Then configure: lark-cli config init --new"
                )]
            )
        except Exception as exc:
            return ToolResult(content=[TextContent(text=f"Error: {exc}")])


feishu_cli_tool = FeishuCLITool()
