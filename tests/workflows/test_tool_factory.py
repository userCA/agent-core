"""RunWorkflowTool and install_workflows factory tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_core.core.content import TextContent
from agent_core.multi_agent import AgentProfile, MultiAgentHarnessOptions, create_multi_agent_harness
from agent_core.providers.auth import AuthSource
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.tools.base import ToolContext, ToolRegistry
from agent_core.workflows import WorkflowOptions, install_workflows
from agent_core.workflows.tool import RunWorkflowTool
from tests.conftest import FakeProvider, fake_model

FIXTURES = Path(__file__).parent / "fixtures"


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


@pytest.mark.asyncio
async def test_install_with_multi_agent_combo():
    provider = FakeProvider()
    store = InMemoryStore()
    tool_registry = ToolRegistry()
    options = MultiAgentHarnessOptions(
        profiles=[
            AgentProfile(
                name="worker",
                description="General worker",
                system_prompt="You are a worker.",
            )
        ]
    )
    harness, ma = create_multi_agent_harness(
        options=options,
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id="orch-wf-1",
        model=fake_model(),
        system_prompt="You are an orchestrator.",
        owner="alice",
        tool_registry=tool_registry,
    )
    handle = install_workflows(
        tool_registry=tool_registry,
        sub_agent_runner=ma.runner,
        profile_registry=ma.registry,
        parent_harness=harness,
        session_store=store,
        session_id="orch-wf-1",
        owner="alice",
        options=WorkflowOptions(
            search_paths=[str(FIXTURES)],
            include_builtin_recipes=False,
        ),
    )
    assert tool_registry.get("run_workflow") is not None
    assert tool_registry.get("delegate_task") is not None
    names = {meta.name for meta in handle.list_workflows()}
    assert "sample-ok" in names
