"""Harness lifecycle semantics: active tools, failure, compact, abort (P0)."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import pytest

from agent_core.core.agent import Agent
from agent_core.core.content import TextContent
from agent_core.core.events import AbortEvent, Settled
from agent_core.core.state import AgentHarnessPhase, AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import (
    Model,
    StreamEvent,
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.session import AgentSession
from agent_core.session.store import MessageEntry
from agent_core.tools.base import ToolDefinition, ToolRegistry, ToolResult
from tests.conftest import FakeProvider, fake_model


class AddTool:
    definition = ToolDefinition(
        name="add",
        description="add",
        parameters={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text=str(params["a"] + params["b"]))])


class MulTool:
    definition = ToolDefinition(
        name="mul",
        description="mul",
        parameters={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text=str(params["a"] * params["b"]))])


def _session_with_tools(session_id: str = "life") -> tuple[AgentSession, InMemoryStore, FakeProvider]:
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(AddTool())
    registry.register(MulTool())
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        initial_state=AgentState(model=fake_model(), tools=[AddTool(), MulTool()]),
        tool_registry=registry,
    )
    store = InMemoryStore()
    session = AgentSession(agent=agent, store=store, session_id=session_id)
    return session, store, provider


@pytest.mark.asyncio
async def test_set_active_tools_filters_next_turn():
    """set_active_tools during turn affects tool list on the next provider request."""
    session, _, provider = _session_with_tools("active-tools")

    provider.queue_script([
        StreamToolCallStart(id="c1", name="add"),
        StreamToolCallEnd(id="c1", arguments={"a": 1, "b": 2}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    switched = False

    async def on_event(evt):
        nonlocal switched
        if evt.type == "turn_start" and not switched:
            switched = True
            await session.set_active_tools(["mul"])

    session.subscribe(on_event)
    await session.start()
    await session.prompt("compute")

    assert len(provider.calls) >= 2
    second_tools = provider.calls[1].get("tools") or []
    tool_names = {t.get("function", {}).get("name") for t in second_tools}
    assert tool_names == {"mul"}


@pytest.mark.asyncio
async def test_failure_message_persisted_via_harness():
    """Loop exception must persist error assistant via harness store path."""

    class FailProvider(FakeProvider):
        async def stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
            self.calls.append(kwargs)
            raise RuntimeError("provider exploded")
            yield  # pragma: no cover

    provider = FailProvider()
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        initial_state=AgentState(model=fake_model()),
    )
    store = InMemoryStore()
    session = AgentSession(agent=agent, store=store, session_id="fail")
    await session.start()

    await session.prompt("trigger failure")

    snap = await store.load_session("fail")
    messages = [e for e in snap.entries if isinstance(e, MessageEntry)]
    error_msgs = [
        e for e in messages
        if e.message.get("role") == "assistant" and e.message.get("error_message")
    ]
    assert len(error_msgs) >= 1


@pytest.mark.asyncio
async def test_compact_hook_cancel():
    """session_before_compact hook cancel must skip compaction."""
    session, store, _ = _session_with_tools("compact-cancel")
    await session.start()

    session.hooks.on("session_before_compact", lambda _evt: {"cancel": True})

    result = await session._agent.compact()
    assert result is None
    assert session.phase == AgentHarnessPhase.IDLE
    assert not any(e.type == "compaction" for e in (await store.load_session("compact-cancel")).entries)


@pytest.mark.asyncio
async def test_abort_and_wait_settled_before_abort():
    """abort_and_wait must emit Settled before AbortEvent."""
    session, _, provider = _session_with_tools("abort-order")

    class SlowProvider(FakeProvider):
        async def stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
            self.calls.append(kwargs)
            await asyncio.sleep(0.05)
            events = self._scripts.pop(0) if self._scripts else []
            for e in events:
                await asyncio.sleep(0)
                yield e

    slow = SlowProvider()
    slow.queue_script([
        StreamTextDelta(text="slow"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    session._agent._provider = slow

    events: list[str] = []

    async def listener(evt):
        events.append(evt.type)

    session.subscribe(listener)
    await session.start()

    run_task = asyncio.create_task(session.prompt("wait"))
    await asyncio.sleep(0.01)
    await session.abort_and_wait()
    await run_task

    assert "settled" in events
    assert "abort" in events
    assert events.index("settled") < events.index("abort")

    abort_evt = next(e for e in events if e == "abort")
    # After Task 6, AbortEvent carries message lists; for now check event exists
    assert abort_evt == "abort"
