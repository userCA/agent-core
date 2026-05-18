"""Tests for enhanced WriteTool with FileOperations and mutation_queue."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from agent_core.tools.local.write import WriteTool
from agent_core.tools.base import ToolContext
from agent_core.tools.mutation_queue import FileMutationQueue


@pytest.mark.asyncio
async def test_write_tool_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteTool()
        ctx = ToolContext(signal=asyncio.Event())
        path = os.path.join(tmpdir, "out.txt")
        result = await tool.execute("tc1", {"path": path, "content": "hello world"}, ctx)
        assert "written successfully" in result.content[0].text
        assert result.display is not None
        assert result.display.get("operation") == "write"
        with open(path) as f:
            assert f.read() == "hello world"


@pytest.mark.asyncio
async def test_write_tool_with_mutation_queue():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = FileMutationQueue()
        tool = WriteTool()
        ctx = ToolContext(signal=asyncio.Event(), mutation_queue=queue)
        path = os.path.join(tmpdir, "queued.txt")
        result = await tool.execute("tc1", {"path": path, "content": "queued content"}, ctx)
        assert "written successfully" in result.content[0].text
        with open(path) as f:
            assert f.read() == "queued content"


@pytest.mark.asyncio
async def test_write_tool_display_hint_python():
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteTool()
        ctx = ToolContext(signal=asyncio.Event())
        path = os.path.join(tmpdir, "script.py")
        result = await tool.execute("tc1", {"path": path, "content": "print(1)"}, ctx)
        assert result.display is not None
        assert result.display.get("language") == "py"


@pytest.mark.asyncio
async def test_write_tool_display_hint_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = WriteTool()
        ctx = ToolContext(signal=asyncio.Event())
        path = os.path.join(tmpdir, "config.json")
        result = await tool.execute("tc1", {"path": path, "content": "{}"}, ctx)
        assert result.display is not None
        assert result.display.get("language") == "json"
