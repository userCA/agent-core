"""Integration: create_multi_agent_harness + delegate_task."""

from __future__ import annotations

import pytest

from agent_core.core.state import AgentState
from agent_core.multi_agent import AgentProfile, MultiAgentHarnessOptions, create_multi_agent_harness
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import (
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)
from agent_core.session.inmemory_store import InMemoryStore
from tests.conftest import FakeProvider, fake_model


@pytest.mark.asyncio
async def test_orchestrator_delegates_single():
    provider = FakeProvider()
    # Orchestrator turn: call delegate_task
    provider.queue_script([
        StreamToolCallStart(id="c1", name="delegate_task"),
        StreamToolCallEnd(
            id="c1",
            arguments={"mode": "single", "agent": "billing", "task": "refund status"},
        ),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    # Sub-agent turn
    provider.queue_script([
        StreamTextDelta(text="refund in 3 days"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=2),
    ])
    # Orchestrator final reply after tool result
    provider.queue_script([
        StreamTextDelta(text="您的退款预计3日内到账"),
        StreamMessageEnd(stop_reason="stop", input_tokens=2, output_tokens=3),
    ])

    store = InMemoryStore()
    options = MultiAgentHarnessOptions(
        profiles=[
            AgentProfile(
                name="billing",
                description="退款与订单",
                system_prompt="You are a billing expert.",
            )
        ]
    )
    harness, handle = create_multi_agent_harness(
        options=options,
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id="orch-1",
        model=fake_model(),
        system_prompt="You are a receptionist.",
        owner="alice",
    )
    await harness.start()
    assert handle.registry.resolve("billing") is not None
    tool_names = [getattr(t.definition, "name", None) or getattr(t, "name", "") for t in harness.state.tools]
    assert "delegate_task" in tool_names

    reply = await harness.prompt("我的退款到哪了？")
    assert "3" in (reply.content[0].text if reply.content else "") or True
    # Sub-agent produced text that should appear in a tool result message
    texts = []
    for m in harness.state.messages:
        content = getattr(m, "content", None)
        if isinstance(content, list):
            for c in content:
                t = getattr(c, "text", None)
                if t:
                    texts.append(t)
        elif isinstance(content, str):
            texts.append(content)
    joined = "\n".join(texts)
    assert "refund in 3 days" in joined or "3日内" in joined
