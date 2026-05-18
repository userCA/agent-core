"""Tests for enhanced LsTool with FileOperations."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from agent_core.tools.local.ls import LsTool
from agent_core.tools.base import ToolContext


@pytest.mark.asyncio
async def test_ls_tool_lists_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        open(os.path.join(tmpdir, "a.txt"), "w").close()
        os.makedirs(os.path.join(tmpdir, "subdir"))

        tool = LsTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"path": tmpdir}, ctx)
        text = result.content[0].text
        assert "a.txt" in text
        assert "subdir" in text
        assert "[F]" in text
        assert "[D]" in text


@pytest.mark.asyncio
async def test_ls_tool_with_custom_file_ops():
    from agent_core.tools.operations import FileInfo

    class FakeFileOps:
        async def ls(self, path):
            return [FileInfo(name="fake.txt", path=f"{path}/fake.txt", is_dir=False, size=10)]

    tool = LsTool(file_ops=FakeFileOps())
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"path": "/anywhere"}, ctx)
    assert "fake.txt" in result.content[0].text


@pytest.mark.asyncio
async def test_ls_tool_not_found():
    tool = LsTool()
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"path": "/nonexistent/xxxx"}, ctx)
    assert "not found" in result.content[0].text.lower()
