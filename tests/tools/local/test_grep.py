"""Tests for enhanced GrepTool with FileOperations."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from agent_core.tools.local.grep import GrepTool
from agent_core.tools.base import ToolContext


@pytest.mark.asyncio
async def test_grep_tool_finds_pattern():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
        f.write("def hello():\n    pass\n")
        path = f.name

    try:
        tool = GrepTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"pattern": "def hello", "path": path}, ctx)
        assert "def hello" in result.content[0].text
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_grep_tool_with_custom_file_ops():
    class FakeFileOps:
        async def grep(self, pattern, path, *, recursive=False):
            return [f"{path}/x.py:1:matched {pattern}"]

    tool = GrepTool(file_ops=FakeFileOps())
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"pattern": "foo", "path": "/dir"}, ctx)
    assert "matched foo" in result.content[0].text


@pytest.mark.asyncio
async def test_grep_tool_no_matches():
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = GrepTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"pattern": "zzzNeverMatchzzz", "path": tmpdir}, ctx)
        assert "no matches" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_grep_tool_invalid_regex():
    tool = GrepTool()
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"pattern": "[unclosed", "path": "."}, ctx)
    assert "invalid regex" in result.content[0].text.lower()
