"""Tests for local filesystem and bash tools."""

from __future__ import annotations

import asyncio
import os
import tempfile

from agent_core.tools.local import (
    BashTool,
    FindTool,
    GrepTool,
    LsTool,
    ReadTool,
    WriteTool,
)
from agent_core.tools.base import ToolContext


async def test_read_tool():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line1\nline2\nline3\n")
        path = f.name

    try:
        tool = ReadTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"path": path}, ctx)
        assert "line1" in result.content[0].text

        result = await tool.execute("tc1", {"path": path, "offset": 2, "limit": 1}, ctx)
        assert result.content[0].text == "line2\n"
    finally:
        os.unlink(path)


async def test_read_tool_not_found():
    tool = ReadTool()
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"path": "/nonexistent/file.txt"}, ctx)
    assert "not found" in result.content[0].text.lower()


async def test_ls_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        open(os.path.join(tmpdir, "a.txt"), "w").close()
        os.makedirs(os.path.join(tmpdir, "subdir"))

        tool = LsTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"path": tmpdir}, ctx)
        text = result.content[0].text
        assert "a.txt" in text
        assert "subdir" in text


async def test_grep_tool():
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


async def test_find_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        open(os.path.join(tmpdir, "test.py"), "w").close()
        open(os.path.join(tmpdir, "main.py"), "w").close()

        tool = FindTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"pattern": "*.py", "path": tmpdir}, ctx)
        text = result.content[0].text
        assert "test.py" in text
        assert "main.py" in text


async def test_write_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteTool()
        ctx = ToolContext(signal=asyncio.Event())
        path = os.path.join(tmpdir, "out.txt")
        result = await tool.execute("tc1", {"path": path, "content": "hello world"}, ctx)
        assert "written successfully" in result.content[0].text
        with open(path) as f:
            assert f.read() == "hello world"


async def test_bash_tool():
    tool = BashTool()
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"command": "echo hello"}, ctx)
    assert "hello" in result.content[0].text


async def test_bash_tool_timeout():
    tool = BashTool()
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"command": "sleep 5", "timeout": 1}, ctx)
    assert "timed out" in result.content[0].text.lower()
