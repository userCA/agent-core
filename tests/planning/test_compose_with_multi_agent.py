"""Planning + multi_agent can be composed without coupling."""

from __future__ import annotations

import pytest

from agent_core.multi_agent import AgentProfile, MultiAgentHarnessOptions, create_multi_agent_harness
from agent_core.planning import install_planning
from agent_core.providers.auth import AuthSource
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.tools.base import ToolRegistry
from tests.conftest import FakeProvider, fake_model


@pytest.mark.asyncio
async def test_install_planning_then_multi_agent_registers_both_tools():
    registry = ToolRegistry()
    store = InMemoryStore()
    await install_planning(
        registry,
        store=store,
        session_id="s1",
        owner="u1",
        restore=False,
    )
    options = MultiAgentHarnessOptions(
        profiles=[
            AgentProfile(
                name="billing",
                description="billing helper",
                system_prompt="You are billing.",
            )
        ]
    )
    harness, handle = create_multi_agent_harness(
        options=options,
        provider=FakeProvider(),
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id="s1",
        model=fake_model(),
        tools=[],
        system_prompt="orchestrator",
        owner="u1",
        tool_registry=registry,
    )
    names = {info.name for info in registry.list()}
    assert "manage_plan" in names
    assert "delegate_task" in names
    assert harness is not None
    assert handle is not None
