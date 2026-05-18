"""Tests for EditTool."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from agent_core.tools.local.edit import EditTool
from agent_core.tools.base import ToolContext


@pytest.fixture
def edit_tool():
    return EditTool()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.mark.asyncio
async def test_edit_tool_replaces_text(edit_tool, tmp_dir):
    path = os.path.join(tmp_dir, "file.txt")
    with open(path, "w") as f:
        f.write("hello old world")

    ctx = ToolContext(signal=asyncio.Event())
    result = await edit_tool.execute(
        "tc1",
        {"path": path, "old_string": "old", "new_string": "new"},
        ctx,
    )
    assert "successfully" in result.content[0].text.lower()

    with open(path, "r") as f:
        assert f.read() == "hello new world"


@pytest.mark.asyncio
async def test_edit_tool_missing_old_string(edit_tool, tmp_dir):
    path = os.path.join(tmp_dir, "file.txt")
    with open(path, "w") as f:
        f.write("hello world")

    ctx = ToolContext(signal=asyncio.Event())
    result = await edit_tool.execute(
        "tc1",
        {"path": path, "old_string": "missing", "new_string": "new"},
        ctx,
    )
    assert result.content[0].text.startswith("Error")
