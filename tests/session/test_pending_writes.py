"""Pending session writes and runtime setter semantics (Harness P0)."""

from __future__ import annotations

import asyncio

import pytest

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
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.store import ModelChangeEntry
from agent_core.tools.base import ToolDefinition, ToolRegistry, ToolResult
from tests.conftest import FakeProvider, fake_model


def _model(provider: str = "fake", model_id: str = "fake-2") -> Model:
    return Model(provider=provider, id=model_id, context_window=4096, max_output_tokens=1024)


def _make_harness(session_id: str = "pw") -> tuple[AgentHarness, InMemoryStore, FakeProvider]:
    provider = FakeProvider()
    store = InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id=session_id,
        initial_state=AgentState(model=fake_model()),
    )
    return harness, store, provider


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
    harness, store, _ = _make_harness("idle-model")
    await harness.start()

    new_model = _model()
    await harness.set_model(new_model)

    snap = await store.load_session("idle-model")
    changes = [e for e in snap.entries if isinstance(e, ModelChangeEntry)]
    assert len(changes) == 1
    assert changes[0].model_id == "fake-2"
    assert harness._pending_writes == []


@pytest.mark.asyncio
async def test_busy_set_model_flushes_at_save_point():
    """Busy set_model enqueues; flush at save point writes ModelChangeEntry."""
    harness, store, provider = _make_harness("busy-model")
    registry = ToolRegistry()
    registry.register(EchoTool())
    harness._tool_registry = registry

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
            assert harness.phase == AgentHarnessPhase.TURN
            await harness.set_model(new_model)

    harness.subscribe(on_event)
    await harness.start()
    await harness.prompt("run tools")

    snap = await store.load_session("busy-model")
    changes = [e for e in snap.entries if isinstance(e, ModelChangeEntry)]
    assert len(changes) >= 1
    assert changes[-1].model_id == "fake-2"


@pytest.mark.asyncio
async def test_set_model_persist_failure_does_not_commit():
    """Persist failure must not update in-memory model."""
    harness, store, _ = _make_harness("persist-fail")
    await harness.start()

    original = harness.get_model()

    async def fail_append(session_id, entry):
        raise OSError("disk full")

    store.append_entry = fail_append  # type: ignore[method-assign]

    from agent_core.core.errors import AgentHarnessError

    with pytest.raises(AgentHarnessError) as exc_info:
        await harness.set_model(_model())
    assert exc_info.value.code == "session"
    assert harness.get_model() == original
