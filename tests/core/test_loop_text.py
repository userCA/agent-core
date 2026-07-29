import asyncio

import pytest

from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.events import (
    AgentEnd,
    AgentStart,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    TurnEnd,
    TurnStart,
)
from agent_core.core.loop import agent_loop, run_agent_loop
from agent_core.core.messages import UserMessage
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta

from tests.conftest import FakeProvider, fake_model


async def _collect(gen):
    return [e async for e in gen]


def test_agent_loop_text_only():
    provider = FakeProvider()
    provider.queue_script(
        [
            StreamTextDelta(text="Hello"),
            StreamTextDelta(text=" world"),
            StreamMessageEnd(stop_reason="stop", input_tokens=3, output_tokens=2),
        ]
    )

    user_msg = UserMessage(content=[{"type": "text", "text": "hi"}], timestamp=0.0)

    async def llm_convert(msgs):
        return [{"role": "user", "content": "hi"}]

    async def auth_resolver(_: str) -> ProviderAuth:
        return ProviderAuth(api_key="k")

    context = AgentContext(
        system_prompt="be brief",
        messages=[user_msg],
    )
    config = AgentLoopConfig(
        model=fake_model(),
        stream_fn=provider.stream,
        convert_to_llm=llm_convert,
        auth_resolver=auth_resolver,
    )

    async def run():
        return await _collect(agent_loop([user_msg], context, config))

    events = asyncio.run(run())
    types = [type(e).__name__ for e in events]
    assert types[0] == "AgentStart"
    assert types[-1] == "AgentEnd"
    assert "TurnStart" in types
    assert "TurnEnd" in types
    text_updates = [
        e for e in events if isinstance(e, MessageUpdate) and e.delta.type == "text_delta"
    ]
    assert "".join(u.delta.text for u in text_updates) == "Hello world"
    end_msgs = [e for e in events if isinstance(e, MessageEnd) and getattr(e.message, "role", None) == "assistant"]
    assert len(end_msgs) == 1
    assert end_msgs[0].message.usage.input_tokens == 3


def test_run_agent_loop_emit_sink():
    """run_agent_loop pushes events via emit callback instead of yielding."""
    provider = FakeProvider()
    provider.queue_script(
        [
            StreamTextDelta(text="Hi"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ]
    )

    user_msg = UserMessage(content=[{"type": "text", "text": "hi"}], timestamp=0.0)

    async def llm_convert(msgs):
        return [{"role": "user", "content": "hi"}]

    async def auth_resolver(_: str) -> ProviderAuth:
        return ProviderAuth(api_key="k")

    context = AgentContext(
        system_prompt="be brief",
        messages=[user_msg],
    )
    config = AgentLoopConfig(
        model=fake_model(),
        stream_fn=provider.stream,
        convert_to_llm=llm_convert,
        auth_resolver=auth_resolver,
    )

    collected = []

    async def emit(evt):
        collected.append(evt)

    async def run():
        return await run_agent_loop([user_msg], context, config, emit)

    result = asyncio.run(run())

    types = [type(e).__name__ for e in collected]
    assert types[0] == "AgentStart"
    assert types[-1] == "AgentEnd"
    assert "TurnStart" in types
    assert "TurnEnd" in types
    # run_id is auto-generated and present in AgentStart event
    agent_start = next(e for e in collected if isinstance(e, AgentStart))
    assert agent_start.run_id.startswith("run-")
    # session_id is propagated to config
    assert config.session_id == ""  # not set in this test
    assert config.run_id == agent_start.run_id
    text_updates = [
        e for e in collected if isinstance(e, MessageUpdate) and e.delta.type == "text_delta"
    ]
    assert "".join(u.delta.text for u in text_updates) == "Hi"
    # run_agent_loop returns new assistant messages
    assert len(result) == 1
    assert result[0].content[0].text == "Hi"
