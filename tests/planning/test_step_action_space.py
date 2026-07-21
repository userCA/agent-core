"""H4: plan step suggested_tools → set_active_tools."""

from __future__ import annotations

import pytest

from agent_core.core.content import TextContent
from agent_core.core.state import AgentState
from agent_core.planning import PlanningContextExtension, PlanStore, install_planning
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import (
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.tools.base import ToolDefinition, ToolRegistry, ToolResult
from agent_core.working_memory import install_working_memory
from tests.conftest import FakeProvider, fake_model


class ReadTool:
    definition = ToolDefinition(
        name="read",
        description="read",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text="ok")])


class WriteTool:
    definition = ToolDefinition(
        name="write",
        description="write",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text="ok")])


@pytest.mark.asyncio
async def test_step_suggested_tools_filters_first_llm_call():
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(ReadTool())
    registry.register(WriteTool())

    extensions: list = []
    plan_store, _, extensions = await install_planning(registry, extensions=extensions)
    _, _, extensions = install_working_memory(registry, extensions=extensions)

    plan_store.replace(
        title="Demo",
        steps=[
            {
                "id": "s1",
                "title": "Read files",
                "status": "in_progress",
                "suggested_tools": ["read"],
            },
            {
                "id": "s2",
                "title": "Write files",
                "status": "pending",
                "suggested_tools": ["write"],
            },
        ],
    )

    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        store=InMemoryStore(),
        session_id="h4-step",
        initial_state=AgentState(
            model=fake_model(),
            tools=registry.to_definitions(),
        ),
        tool_registry=registry,
        extensions=extensions,
        tool_execution="sequential",
    )
    await harness.start()
    await harness.prompt("go")

    assert len(provider.calls) >= 1
    raw_tools = provider.calls[0].get("tools") or []
    tool_names = {t.get("function", {}).get("name") for t in raw_tools}
    assert "read" in tool_names
    assert "manage_plan" in tool_names
    assert "working_memory" in tool_names
    assert "write" not in tool_names


@pytest.mark.asyncio
async def test_plan_step_serdes_suggested_tools():
    store = PlanStore()
    plan = store.replace(
        title="T",
        steps=[{"id": "a", "title": "A", "suggested_tools": ["read", "grep"]}],
    )
    assert plan.steps[0].suggested_tools == ["read", "grep"]
    restored = type(plan).from_dict(plan.to_dict())
    assert restored.steps[0].suggested_tools == ["read", "grep"]
