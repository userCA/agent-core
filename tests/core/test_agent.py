import asyncio

import pytest

from agent_core.core.errors import AgentHarnessError
from agent_core.core.events import MessageUpdate, SavePoint
from agent_core.core.state import AgentHarnessPhase, AgentState
from agent_core.providers.types import (
    StreamError,
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)

from tests.conftest import FakeProvider, fake_model, make_harness


def test_harness_prompt_collects_streaming_text():
    async def run():
        provider = FakeProvider()
        provider.queue_script([
            StreamTextDelta(text="Hi"),
            StreamTextDelta(text="!"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=2),
        ])
        harness = await make_harness(
            provider=provider,
            initial_state=AgentState(model=fake_model(), system_prompt="hello"),
        )
        deltas: list[str] = []

        async def on_event(evt):
            if isinstance(evt, MessageUpdate) and evt.delta.type == "text_delta":
                deltas.append(evt.delta.text)

        harness.subscribe(on_event)
        await harness.prompt("hi")
        assert "".join(deltas) == "Hi!"
        assert any(getattr(m, "role", None) == "user" for m in harness.state.messages)
        assistant = [m for m in harness.state.messages if getattr(m, "role", None) == "assistant"]
        assert len(assistant) == 1
        assert harness.state.is_streaming is False
        assert harness.state.error_message is None
        assert harness.phase == AgentHarnessPhase.IDLE

    asyncio.run(run())


def test_harness_prompt_double_call_raises_when_active():
    async def run():
        provider = FakeProvider()
        provider.queue_script([])
        harness = await make_harness(provider=provider)
        first = asyncio.create_task(harness.prompt("a"))
        await asyncio.sleep(0)
        with pytest.raises(AgentHarnessError, match="busy"):
            await harness.prompt("b")
        await first

    asyncio.run(run())


def test_harness_phase_idle_after_prompt():
    async def run():
        provider = FakeProvider()
        provider.queue_script([StreamMessageEnd(stop_reason="stop", input_tokens=0, output_tokens=0)])
        harness = await make_harness(provider=provider)
        assert harness.phase == AgentHarnessPhase.IDLE
        await harness.prompt("hi")
        assert harness.phase == AgentHarnessPhase.IDLE

    asyncio.run(run())


def test_harness_unsubscribe_removes_listener():
    async def run():
        provider = FakeProvider()
        provider.queue_script([StreamMessageEnd(stop_reason="stop", input_tokens=0, output_tokens=0)])
        harness = await make_harness(provider=provider)
        count = {"n": 0}

        async def listener(_):
            count["n"] += 1

        unsub = harness.subscribe(listener)
        unsub()
        await harness.prompt("x")
        assert count["n"] == 0

    asyncio.run(run())


def test_harness_retries_on_retryable_error_then_succeeds():
    async def run():
        provider = FakeProvider()
        provider.queue_script([StreamError(message="HTTP 429", retryable=True)])
        provider.queue_script([
            StreamTextDelta(text="ok"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ])
        harness = await make_harness(
            provider=provider,
            max_retries=2,
            retry_base_delay=0.01,
            retry_max_delay=0.1,
        )
        deltas: list[str] = []

        async def on_event(evt):
            if isinstance(evt, MessageUpdate) and evt.delta.type == "text_delta":
                deltas.append(evt.delta.text)

        harness.subscribe(on_event)
        await harness.prompt("hi")
        assert "".join(deltas) == "ok"
        assistants = [m for m in harness.state.messages if getattr(m, "role", None) == "assistant"]
        assert len(assistants) == 1
        assert assistants[0].stop_reason == "stop"
        assert harness.state.error_message is None

    asyncio.run(run())


def test_harness_stops_after_max_retries():
    async def run():
        provider = FakeProvider()
        for _ in range(3):
            provider.queue_script([StreamError(message="HTTP 503", retryable=True)])
        harness = await make_harness(
            provider=provider,
            max_retries=2,
            retry_base_delay=0.01,
            retry_max_delay=0.1,
        )
        await harness.prompt("hi")
        assistants = [m for m in harness.state.messages if getattr(m, "role", None) == "assistant"]
        assert len(assistants) == 1
        assert assistants[0].stop_reason == "error"
        assert assistants[0].retryable_error is True

    asyncio.run(run())


def test_harness_does_not_retry_on_non_retryable_error():
    async def run():
        provider = FakeProvider()
        provider.queue_script([StreamError(message="HTTP 400", retryable=False)])
        provider.queue_script([StreamTextDelta(text="should not appear")])
        harness = await make_harness(
            provider=provider,
            max_retries=2,
            retry_base_delay=0.01,
            retry_max_delay=0.1,
        )
        await harness.prompt("hi")
        assert len(provider.calls) == 1
        assistants = [m for m in harness.state.messages if getattr(m, "role", None) == "assistant"]
        assert len(assistants) == 1
        assert assistants[0].stop_reason == "error"
        assert assistants[0].retryable_error is False

    asyncio.run(run())


def test_create_turn_snapshot():
    async def run():
        harness = await make_harness(
            initial_state=AgentState(
                model=fake_model(),
                system_prompt="be brief",
                thinking_level="low",
            ),
        )
        snap = harness.create_turn_snapshot()
        assert snap.system_prompt == "be brief"
        assert snap.thinking_level == "low"
        assert snap.model == harness.state.model
        assert snap.messages == []
        assert snap.tools == []
        with pytest.raises(Exception):
            snap.system_prompt = "changed"

    asyncio.run(run())


def test_save_point_emitted_during_tool_turn():
    from agent_core.core.content import TextContent
    from agent_core.tools.base import ToolDefinition, ToolRegistry, ToolResult

    class EchoTool:
        definition = ToolDefinition(
            name="echo", description="echo",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}},
        )

        async def execute(self, tool_call_id, params, ctx):
            return ToolResult(content=[TextContent(text=params.get("text", ""))])

    async def run():
        provider = FakeProvider()
        provider.queue_script([
            StreamToolCallStart(id="c1", name="echo"),
            StreamToolCallEnd(id="c1", arguments={"text": "hello"}),
            StreamMessageEnd(stop_reason="tool_calls", input_tokens=3, output_tokens=5),
        ])
        provider.queue_script([
            StreamTextDelta(text="done"),
            StreamMessageEnd(stop_reason="stop", input_tokens=3, output_tokens=1),
        ])
        registry = ToolRegistry()
        registry.register(EchoTool())
        harness = await make_harness(provider=provider, tool_registry=registry)
        events = []

        async def listener(evt):
            events.append(evt)

        harness.subscribe(listener)
        await harness.prompt("echo hello")
        save_points = [e for e in events if isinstance(e, SavePoint)]
        assert len(save_points) >= 1
        assert save_points[0].turn_count == 1

    asyncio.run(run())


def test_harness_hooks_observe():
    async def run():
        provider = FakeProvider()
        provider.queue_script([
            StreamTextDelta(text="ok"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ])
        harness = await make_harness(provider=provider)
        seen_types = []
        harness.hooks.observe(lambda evt: seen_types.append(evt.type))
        harness.hooks.on("context", lambda evt: None)
        await harness.prompt("hi")
        assert "context" in seen_types

    asyncio.run(run())


def test_harness_hooks_before_agent_start():
    async def run():
        provider = FakeProvider()
        provider.queue_script([StreamMessageEnd(stop_reason="stop", input_tokens=0, output_tokens=0)])
        harness = await make_harness(
            provider=provider,
            initial_state=AgentState(model=fake_model(), system_prompt="base"),
        )

        def inject(evt):
            return {"system_prompt": evt.system_prompt + " [injected]"}

        harness.hooks.on("before_agent_start", inject)
        await harness.prompt("hi")

    asyncio.run(run())


def test_harness_legacy_before_tool_call_via_hooks():
    async def run():
        provider = FakeProvider()
        provider.queue_script([StreamMessageEnd(stop_reason="stop", input_tokens=0, output_tokens=0)])

        def my_hook(call_ctx):
            return None

        harness = await make_harness(provider=provider, before_tool_call=my_hook)
        assert harness.hooks._handlers.get("tool_call") is not None

    asyncio.run(run())
