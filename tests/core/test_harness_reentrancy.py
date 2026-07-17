"""Lifecycle hardening: reentrancy, next_turn/abort, run_when_idle, busy guards."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import pytest

from agent_core.core.content import TextContent
from agent_core.core.errors import AgentHarnessError
from agent_core.core.events import Settled
from agent_core.core.messages import UserMessage
from agent_core.core.state import AgentHarnessPhase, AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import (
    StreamEvent,
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.tools.base import ToolDefinition, ToolRegistry, ToolResult
from tests.conftest import FakeProvider, fake_model


class EchoTool:
    definition = ToolDefinition(
        name="echo",
        description="echo",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text=params.get("text", ""))])


def _harness(session_id: str = "re") -> tuple[AgentHarness, FakeProvider]:
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(EchoTool())
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=InMemoryStore(),
        session_id=session_id,
        initial_state=AgentState(model=fake_model(), tools=[EchoTool()]),
        tool_registry=registry,
    )
    return harness, provider


@pytest.mark.asyncio
async def test_busy_prompt_rejected():
    harness, provider = _harness("busy")
    provider.queue_script([
        StreamTextDelta(text="a"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    class SlowProvider(FakeProvider):
        async def stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
            self.calls.append(kwargs)
            await asyncio.sleep(0.05)
            events = self._scripts.pop(0) if self._scripts else []
            for e in events:
                yield e

    slow = SlowProvider()
    slow.queue_script([
        StreamTextDelta(text="slow"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    harness._provider = slow
    await harness.start()

    task = asyncio.create_task(harness.prompt("one"))
    await asyncio.sleep(0.01)
    with pytest.raises(AgentHarnessError) as ei:
        await harness.prompt("two")
    assert ei.value.code == "busy"
    await task


@pytest.mark.asyncio
async def test_next_turn_survives_abort():
    """next_turn enqueued during a turn must survive abort and apply on next prompt."""
    harness, _ = _harness("nt-abort")

    class SlowProvider(FakeProvider):
        async def stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
            self.calls.append(kwargs)
            await asyncio.sleep(0.05)
            events = self._scripts.pop(0) if self._scripts else []
            for e in events:
                yield e

    slow = SlowProvider()
    slow.queue_script([
        StreamTextDelta(text="slow"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    slow.queue_script([
        StreamTextDelta(text="after"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    harness._provider = slow
    await harness.start()

    async def enqueue_next_turn(evt):
        if evt.type == "agent_start":
            await harness.next_turn(
                UserMessage(content=[TextContent(text="queued")], timestamp=0.0)
            )

    harness.subscribe(enqueue_next_turn)
    task = asyncio.create_task(harness.prompt("run"))
    await asyncio.sleep(0.01)
    result = await harness.abort_and_wait()
    await task

    assert result["next_turn_count"] == 1
    assert harness._next_turn.item_count == 1

    await harness.prompt("again")
    user_texts = [
        m.content[0].text
        for m in harness.messages
        if getattr(m, "role", None) == "user" and m.content
    ]
    assert "queued" in user_texts
    assert user_texts.index("queued") < user_texts.index("again")


@pytest.mark.asyncio
async def test_run_when_idle_from_listener_no_deadlock():
    harness, provider = _harness("rwi")
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    await harness.start()

    called = asyncio.Event()

    async def listener(evt):
        if isinstance(evt, Settled):
            harness.run_when_idle(lambda: called.set())

    harness.subscribe(listener)
    await harness.prompt("hi")
    await asyncio.wait_for(called.wait(), timeout=1.0)
    assert harness.phase == AgentHarnessPhase.IDLE


@pytest.mark.asyncio
async def test_setter_from_turn_start_affects_save_point():
    """Runtime setter during turn updates next provider request via save point."""
    harness, provider = _harness("setter-sp")
    provider.queue_script([
        StreamToolCallStart(id="c1", name="echo"),
        StreamToolCallEnd(id="c1", arguments={"text": "x"}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    await harness.start()

    async def on_evt(evt):
        if evt.type == "turn_start":
            harness.set_stream_options({"headers": {"X-From": "listener"}})

    harness.subscribe(on_evt)
    await harness.prompt("go")

    assert len(provider.calls) >= 2
    assert harness.get_stream_options().get("headers", {}).get("X-From") == "listener"


@pytest.mark.asyncio
async def test_idle_follow_up_rejected_on_harness():
    harness, _ = _harness("idle-fu")
    await harness.start()
    with pytest.raises(AgentHarnessError) as ei:
        await harness.follow_up(UserMessage(content=[TextContent(text="x")], timestamp=0.0))
    assert ei.value.code == "invalid_state"


@pytest.mark.asyncio
async def test_getter_returns_latest_config_during_turn():
    harness, provider = _harness("getter")
    provider.queue_script([
        StreamToolCallStart(id="c1", name="echo"),
        StreamToolCallEnd(id="c1", arguments={"text": "x"}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    await harness.start()

    seen_level: list[str] = []

    async def on_evt(evt):
        if evt.type == "tool_execution_start":
            await harness.set_thinking_level("high")
            seen_level.append(harness.get_thinking_level())

    harness.subscribe(on_evt)
    await harness.prompt("go")
    assert seen_level == ["high"]
    assert harness.get_thinking_level() == "high"
