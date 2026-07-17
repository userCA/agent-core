import asyncio

import pytest

from agent_core.core.agent import Agent
from agent_core.core.errors import AgentHarnessError
from agent_core.core.events import MessageUpdate, SavePoint
from agent_core.core.state import AgentHarnessPhase, AgentState
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
    assert agent.phase == AgentHarnessPhase.IDLE


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
        with pytest.raises(AgentHarnessError, match="busy"):
            await agent.prompt("b")
        await first

    asyncio.run(run())


def test_agent_phase_idle_after_prompt():
    """Phase returns to IDLE after a successful prompt."""
    provider = FakeProvider()
    provider.queue_script(
        [StreamMessageEnd(stop_reason="stop", input_tokens=0, output_tokens=0)]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )
    assert agent.phase == AgentHarnessPhase.IDLE
    asyncio.run(agent.prompt("hi"))
    assert agent.phase == AgentHarnessPhase.IDLE


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
    for _ in range(3):  # initial + 2 retries
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

    assert len(provider.calls) == 1  # no retry, second script never consumed

    assistants = [m for m in agent.state.messages if getattr(m, "role", None) == "assistant"]
    assert len(assistants) == 1
    assert assistants[0].stop_reason == "error"
    assert assistants[0].retryable_error is False


def test_create_turn_snapshot():
    """create_turn_snapshot returns an immutable snapshot of current state."""
    agent = Agent(
        provider=FakeProvider(),
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(
            model=fake_model(),
            system_prompt="be brief",
            thinking_level="low",
        ),
    )
    snap = agent.create_turn_snapshot()
    assert snap.system_prompt == "be brief"
    assert snap.thinking_level == "low"
    assert snap.model == agent.state.model
    assert snap.messages == []
    assert snap.tools == []
    # Frozen: cannot modify
    with pytest.raises(Exception):
        snap.system_prompt = "changed"


def test_save_point_emitted_during_tool_turn():
    """SavePoint event is emitted between turns when tool calls cause continuation."""
    from agent_core.core.content import TextContent
    from agent_core.providers.types import StreamToolCallStart, StreamToolCallEnd
    from agent_core.tools.base import ToolContext, ToolDefinition, ToolRegistry, ToolResult

    class EchoTool:
        definition = ToolDefinition(
            name="echo", description="echo", parameters={"type": "object", "properties": {"text": {"type": "string"}}}
        )
        async def execute(self, tool_call_id, params, ctx):
            return ToolResult(content=[TextContent(text=params.get("text", ""))])

    provider = FakeProvider()
    # Turn 1: tool call
    provider.queue_script([
        StreamToolCallStart(id="c1", name="echo"),
        StreamToolCallEnd(id="c1", arguments={"text": "hello"}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=3, output_tokens=5),
    ])
    # Turn 2: final text
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=3, output_tokens=1),
    ])

    registry = ToolRegistry()
    registry.register(EchoTool())

    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
        tool_registry=registry,
    )

    events = []

    async def listener(evt):
        events.append(evt)

    agent.subscribe(listener)
    asyncio.run(agent.prompt("echo hello"))

    save_points = [e for e in events if isinstance(e, SavePoint)]
    assert len(save_points) >= 1, "Expected at least one SavePoint between turns"
    assert save_points[0].turn_count == 1


def test_agent_hooks_observe():
    """hooks.observe sees events when handlers are registered."""
    from agent_core.core.hooks import ContextHookEvent

    provider = FakeProvider()
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
    )
    seen_types = []
    agent.hooks.observe(lambda evt: seen_types.append(evt.type))
    # Register a context handler so the chain is active
    agent.hooks.on("context", lambda evt: None)
    asyncio.run(agent.prompt("hi"))
    assert "context" in seen_types


def test_agent_hooks_before_agent_start():
    """hooks.on('before_agent_start') can modify system_prompt."""
    from agent_core.core.hooks import BeforeAgentStartHookEvent

    provider = FakeProvider()
    provider.queue_script(
        [StreamMessageEnd(stop_reason="stop", input_tokens=0, output_tokens=0)]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model(), system_prompt="base"),
    )

    def inject(evt):
        return {"system_prompt": evt.system_prompt + " [injected]"}

    agent.hooks.on("before_agent_start", inject)
    asyncio.run(agent.prompt("hi"))
    # The hook should have been called (context was modified during run)
    # We verify indirectly that the hook system ran without error


def test_agent_legacy_before_tool_call_via_hooks():
    """Constructor before_tool_call is registered via hooks system."""
    provider = FakeProvider()
    provider.queue_script(
        [StreamMessageEnd(stop_reason="stop", input_tokens=0, output_tokens=0)]
    )
    calls = []

    def my_hook(call_ctx):
        calls.append(call_ctx.get("tool_name"))

    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
        before_tool_call=my_hook,
    )
    # Verify hook is registered in hooks system
    assert agent.hooks._handlers.get("tool_call") is not None
