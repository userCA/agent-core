"""Tests for enhanced BashTool with BashOperations."""

from __future__ import annotations

import asyncio

import pytest

from agent_core.tools.local.bash import BashTool
from agent_core.tools.base import ToolContext


@pytest.mark.asyncio
async def test_bash_tool_echo():
    tool = BashTool()
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"command": "echo hello"}, ctx)
    assert "hello" in result.content[0].text
    assert result.details is not None
    assert result.details.get("exit_code") == 0


@pytest.mark.asyncio
async def test_bash_tool_timeout():
    tool = BashTool()
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"command": "sleep 5", "timeout": 1}, ctx)
    assert "timed out" in result.content[0].text.lower()
    assert result.details.get("truncated") is True


@pytest.mark.asyncio
async def test_bash_tool_with_custom_bash_ops():
    from agent_core.tools.operations import BashResult

    class FakeBashOps:
        async def execute(self, command, *, cwd=None, timeout=None, env=None,
                          on_data=None, signal=None):
            return BashResult(stdout=f"FAKE:{command}", stderr="", returncode=0)

    tool = BashTool(bash_ops=FakeBashOps())
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"command": "ls"}, ctx)
    assert "FAKE:ls" in result.content[0].text


@pytest.mark.asyncio
async def test_bash_tool_definition_has_guidelines():
    tool = BashTool()
    assert len(tool.definition.prompt_guidelines) > 0
