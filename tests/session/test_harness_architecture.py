"""AgentHarness architecture: no Agent dependency, direct loop invocation."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from agent_core.core.content import TextContent
from agent_core.core.messages import AssistantMessage, Usage
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from tests.conftest import FakeProvider, fake_model, make_harness


@pytest.mark.asyncio
async def test_harness_constructed_without_agent():
    """AgentHarness can be constructed without Agent class."""
    provider = FakeProvider()
    store = InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id="arch-no-agent",
        initial_state=AgentState(model=fake_model()),
    )
    await harness.start()
    assert harness.state.model is not None
    assert harness._provider is provider


@pytest.mark.asyncio
async def test_prompt_calls_run_agent_loop_directly():
    """prompt() must invoke run_agent_loop from the harness module."""
    provider = FakeProvider()
    harness = await make_harness(provider=provider)

    assistant = AssistantMessage(
        content=[TextContent(text="ok")],
        usage=Usage(),
        stop_reason="stop",
        provider="fake",
        model="fake-1",
        timestamp=time.time(),
    )

    with patch("agent_core.session.harness.run_agent_loop") as mock_loop:
        mock_loop.return_value = [assistant]
        await harness.prompt("hello")
        mock_loop.assert_called_once()
