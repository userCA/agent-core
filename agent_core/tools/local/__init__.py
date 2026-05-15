"""Local filesystem and bash tools for agent sessions."""

from __future__ import annotations

from typing import Any

from agent_core.tools.local.bash import BashTool, bash_tool, create_bash_tool
from agent_core.tools.local.confirm import ConfirmTool, confirm_tool, create_confirm_tool
from agent_core.tools.local.find import FindTool, create_find_tool, find_tool
from agent_core.tools.local.grep import GrepTool, create_grep_tool, grep_tool
from agent_core.tools.local.ls import LsTool, create_ls_tool, ls_tool
from agent_core.tools.local.read import ReadTool, create_read_tool, read_tool
from agent_core.tools.local.write import WriteTool, create_write_tool, write_tool

__all__ = [
    "BashTool",
    "bash_tool",
    "create_bash_tool",
    "ConfirmTool",
    "confirm_tool",
    "create_confirm_tool",
    "FindTool",
    "find_tool",
    "create_find_tool",
    "GrepTool",
    "grep_tool",
    "create_grep_tool",
    "LsTool",
    "ls_tool",
    "create_ls_tool",
    "ReadTool",
    "read_tool",
    "create_read_tool",
    "WriteTool",
    "write_tool",
    "create_write_tool",
    "create_all_tools",
    "create_coding_tools",
    "create_read_only_tools",
]


def create_all_tools(cwd: str = "") -> dict[str, Any]:
    return {
        "read": create_read_tool(cwd),
        "bash": create_bash_tool(cwd),
        "write": create_write_tool(cwd),
        "grep": create_grep_tool(cwd),
        "find": create_find_tool(cwd),
        "ls": create_ls_tool(cwd),
        "confirm": create_confirm_tool(),
    }


def create_coding_tools(cwd: str = "") -> dict[str, Any]:
    return {
        "read": create_read_tool(cwd),
        "bash": create_bash_tool(cwd),
        "write": create_write_tool(cwd),
    }


def create_read_only_tools(cwd: str = "") -> dict[str, Any]:
    return {
        "read": create_read_tool(cwd),
        "grep": create_grep_tool(cwd),
        "find": create_find_tool(cwd),
        "ls": create_ls_tool(cwd),
    }

