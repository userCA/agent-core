"""RunWorkflowTool and install_workflows factory tests."""

from __future__ import annotations

import asyncio

import pytest

from agent_core.core.content import TextContent
from agent_core.tools.base import ToolContext
from agent_core.workflows.tool import RunWorkflowTool


@pytest.mark.asyncio
async def test_run_workflow_tool_success(workflow_env):
    runner, _, _, _, _, _ = await workflow_env()
    tool = RunWorkflowTool(runner=runner)

    updates: list = []
    ctx = ToolContext(
        signal=asyncio.Event(),
        on_update=lambda r: updates.append(r),
    )

    result = await tool.execute("tc-1", {"name": "sample-ok"}, ctx)

    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text.startswith("[workflow:sample-ok] status=completed")
    assert result.details is not None
    assert result.details["workflow"]["status"] == "completed"
    assert result.details["workflow"]["result"] == {"ok": True}
    assert result.details["workflow"]["type"] == "workflow"
    assert len(updates) >= 1
    assert all(u.details["workflow"]["type"] == "workflow" for u in updates)


@pytest.mark.asyncio
async def test_run_workflow_inline_requires_dynamic_exec(workflow_env):
    runner, _, _, _, _, _ = await workflow_env()
    tool = RunWorkflowTool(runner=runner, enable_dynamic_exec=False)
    ctx = ToolContext(signal=asyncio.Event())

    inline = 'meta = {"name": "x"}\nasync def run(ctx):\n    return {}'
    result = await tool.execute("tc-2", {"inline_source": inline}, ctx)

    assert result.details["workflow"]["status"] == "failed"
    assert "enable_dynamic_exec" in (result.details["workflow"]["error_message"] or "")
