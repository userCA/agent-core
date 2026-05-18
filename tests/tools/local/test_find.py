"""Tests for enhanced FindTool with FileOperations."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from agent_core.tools.local.find import FindTool
from agent_core.tools.base import ToolContext


@pytest.mark.asyncio
async def test_find_tool_finds_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        open(os.path.join(tmpdir, "test.py"), "w").close()
        open(os.path.join(tmpdir, "main.py"), "w").close()

        tool = FindTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"pattern": "*.py", "path": tmpdir}, ctx)
        text = result.content[0].text
        assert "test.py" in text
        assert "main.py" in text


@pytest.mark.asyncio
async def test_find_tool_with_custom_file_ops():
    class FakeFileOps:
        async def find(self, path, *, name_pattern=None):
            return [f"{path}/fake.py"]

    tool = FindTool(file_ops=FakeFileOps())
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"pattern": "*.py", "path": "/dir"}, ctx)
    assert "fake.py" in result.content[0].text


@pytest.mark.asyncio
async def test_find_tool_no_results():
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = FindTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"pattern": "*.zzz", "path": tmpdir}, ctx)
        assert "no files found" in result.content[0].text.lower()
