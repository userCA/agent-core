"""Tests for enhanced ReadTool with FileOperations and truncation."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from agent_core.tools.local.read import ReadTool
from agent_core.tools.base import ToolContext


@pytest.mark.asyncio
async def test_read_tool_basic():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line1\nline2\nline3\n")
        path = f.name

    try:
        tool = ReadTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"path": path}, ctx)
        assert "line1" in result.content[0].text
        assert result.details is not None
        assert result.details.get("truncated") is False
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_read_tool_with_offset_limit():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("line1\nline2\nline3\nline4\nline5\n")
        path = f.name

    try:
        tool = ReadTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"path": path, "offset": 1, "limit": 2}, ctx)
        text = result.content[0].text
        assert text == "line2\nline3\n"
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_read_tool_line_truncation():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        for i in range(600):
            f.write(f"line{i}\n")
        path = f.name

    try:
        tool = ReadTool(max_lines=10)
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"path": path}, ctx)
        text = result.content[0].text
        assert "... (truncated)" in text
        assert result.details.get("truncated") is True
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_read_tool_byte_truncation():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("x" * 50000)
        path = f.name

    try:
        tool = ReadTool(max_bytes=1000)
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"path": path}, ctx)
        text = result.content[0].text
        assert "... (truncated)" in text
        assert result.details.get("truncated") is True
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_read_tool_not_found():
    tool = ReadTool()
    ctx = ToolContext(signal=asyncio.Event())
    result = await tool.execute("tc1", {"path": "/nonexistent/file.txt"}, ctx)
    assert "not found" in result.content[0].text.lower()
    assert result.details.get("error") == "not_found"


@pytest.mark.asyncio
async def test_read_tool_is_directory():
    with tempfile.TemporaryDirectory() as d:
        tool = ReadTool()
        ctx = ToolContext(signal=asyncio.Event())
        result = await tool.execute("tc1", {"path": d}, ctx)
        assert "directory" in result.content[0].text.lower()
        assert result.details.get("error") == "is_directory"
