import asyncio

import pytest

from agent_core.core.agent import Agent
from agent_core.core.events import MessageUpdate
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamError, StreamMessageEnd, StreamTextDelta

from tests.conftest import FakeProvider, fake_model


def test_agent_prompt_collects_streaming_text():
    provider = FakeProvider()
    provider.queue_script(
        [
            StreamTextDelta(text="Hi"),
            StreamTextDelta(text="!"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=2),
        ]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model(), system_prompt="hello"),
    )
    deltas: list[str] = []

    async def on_event(evt):
        if isinstance(evt, MessageUpdate) and evt.delta.type == "text_delta":
            deltas.append(evt.delta.text)

    agent.subscribe(on_event)
    asyncio.run(agent.prompt("hi"))

    assert "".join(deltas) == "Hi!"
    assert any(getattr(m, "role", None) == "user" for m in agent.state.messages)
    assistant = [m for m in agent.state.messages if getattr(m, "role", None) == "assistant"]
    assert len(assistant) == 1
    assert agent.state.is_streaming is False
    assert agent.state.error_message is None


def test_agent_prompt_double_call_raises_when_active():
    provider = FakeProvider()
    provider.queue_script([])
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )

    async def run():
        first = asyncio.create_task(agent.prompt("a"))
        await asyncio.sleep(0)  # let _active_run be set
        with pytest.raises(RuntimeError):
            await agent.prompt("b")
        await first

    asyncio.run(run())


def test_agent_unsubscribe_removes_listener():
    provider = FakeProvider()
    provider.queue_script(
        [StreamMessageEnd(stop_reason="stop", input_tokens=0, output_tokens=0)]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )
    count = {"n": 0}

    async def listener(_):
        count["n"] += 1

    unsub = agent.subscribe(listener)
    unsub()
    asyncio.run(agent.prompt("x"))
    assert count["n"] == 0


def test_agent_retries_on_retryable_error_then_succeeds():
    provider = FakeProvider()
    provider.queue_script(
        [StreamError(message="HTTP 429", retryable=True)]
    )
    provider.queue_script(
        [
            StreamTextDelta(text="ok"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
        max_retries=2,
        retry_base_delay=0.01,
        retry_max_delay=0.1,
    )

    deltas: list[str] = []

    async def on_event(evt):
        if isinstance(evt, MessageUpdate) and evt.delta.type == "text_delta":
            deltas.append(evt.delta.text)

    agent.subscribe(on_event)
    asyncio.run(agent.prompt("hi"))

    assert "".join(deltas) == "ok"
    assistants = [m for m in agent.state.messages if getattr(m, "role", None) == "assistant"]
    assert len(assistants) == 1
    assert assistants[0].stop_reason == "stop"
    assert agent.state.error_message is None


def test_agent_stops_after_max_retries():
    provider = FakeProvider()
    for _ in range(4):
        provider.queue_script(
            [StreamError(message="HTTP 503", retryable=True)]
        )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
        max_retries=2,
        retry_base_delay=0.01,
        retry_max_delay=0.1,
    )

    asyncio.run(agent.prompt("hi"))

    assistants = [m for m in agent.state.messages if getattr(m, "role", None) == "assistant"]
    assert len(assistants) == 1
    assert assistants[0].stop_reason == "error"
    assert assistants[0].retryable_error is True


def test_agent_does_not_retry_on_non_retryable_error():
    provider = FakeProvider()
    provider.queue_script(
        [StreamError(message="HTTP 400", retryable=False)]
    )
    provider.queue_script(
        [StreamTextDelta(text="should not appear")]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
        max_retries=2,
        retry_base_delay=0.01,
        retry_max_delay=0.1,
    )

    asyncio.run(agent.prompt("hi"))

    assistants = [m for m in agent.state.messages if getattr(m, "role", None) == "assistant"]
    assert len(assistants) == 1
    assert assistants[0].stop_reason == "error"
    assert assistants[0].retryable_error is False
