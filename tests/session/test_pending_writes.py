"""Pending session writes and runtime setter semantics (Harness P0)."""

from __future__ import annotations

import asyncio

import pytest

from agent_core.core.agent import Agent
from agent_core.core.content import TextContent
from agent_core.core.state import AgentHarnessPhase, AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import (
    Model,
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.session import AgentSession
from agent_core.session.store import ModelChangeEntry
from agent_core.tools.base import ToolDefinition, ToolRegistry, ToolResult
from tests.conftest import FakeProvider, fake_model


def _model(provider: str = "fake", model_id: str = "fake-2") -> Model:
    return Model(provider=provider, id=model_id, context_window=4096, max_output_tokens=1024)


def _make_session(session_id: str = "pw") -> tuple[AgentSession, InMemoryStore, FakeProvider]:
    provider = FakeProvider()
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        initial_state=AgentState(model=fake_model()),
    )
    store = InMemoryStore()
    session = AgentSession(agent=agent, store=store, session_id=session_id)
    return session, store, provider


class EchoTool:
    definition = ToolDefinition(
        name="echo",
        description="echo",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text=params.get("text", ""))])


@pytest.mark.asyncio
async def test_idle_set_model_persists_immediately():
    """Idle set_model must write ModelChangeEntry immediately, not enqueue."""
    session, store, _ = _make_session("idle-model")
    await session.start()

    new_model = _model()
    await session.set_model(new_model)

    snap = await store.load_session("idle-model")
    changes = [e for e in snap.entries if isinstance(e, ModelChangeEntry)]
    assert len(changes) == 1
    assert changes[0].model_id == "fake-2"
    assert session._pending_writes == []


@pytest.mark.asyncio
async def test_busy_set_model_flushes_at_save_point():
    """Busy set_model enqueues; flush at save point writes ModelChangeEntry."""
    session, store, provider = _make_session("busy-model")
    registry = ToolRegistry()
    registry.register(EchoTool())
    session._agent._tool_registry = registry

    provider.queue_script([
        StreamToolCallStart(id="c1", name="echo"),
        StreamToolCallEnd(id="c1", arguments={"text": "hi"}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    new_model = _model()
    saw_turn = False

    async def on_event(evt):
        nonlocal saw_turn
        if evt.type == "turn_start" and not saw_turn:
            saw_turn = True
            assert session.phase == AgentHarnessPhase.TURN
            await session.set_model(new_model)

    session.subscribe(on_event)
    await session.start()
    await session.prompt("run tools")

    snap = await store.load_session("busy-model")
    changes = [e for e in snap.entries if isinstance(e, ModelChangeEntry)]
    assert len(changes) >= 1
    assert changes[-1].model_id == "fake-2"


@pytest.mark.asyncio
async def test_set_model_persist_failure_does_not_commit():
    """Persist failure must not update in-memory model."""
    session, store, _ = _make_session("persist-fail")
    await session.start()

    original = session.get_model()

    async def fail_append(session_id, entry):
        raise OSError("disk full")

    store.append_entry = fail_append  # type: ignore[method-assign]

    from agent_core.core.errors import AgentHarnessError

    with pytest.raises(AgentHarnessError) as exc_info:
        await session.set_model(_model())
    assert exc_info.value.code == "session"
    assert session.get_model() == original
