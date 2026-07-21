"""H4 working_memory tool + extension."""

from __future__ import annotations

import pytest

from agent_core.core.content import TextContent
from agent_core.core.state import AgentState
from agent_core.extensions.base import ExtensionContext
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta, StreamToolCallEnd, StreamToolCallStart
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.tools.base import ToolRegistry
from agent_core.working_memory import (
    WorkingMemoryExtension,
    WorkingMemoryStore,
    install_working_memory,
)
from tests.conftest import FakeProvider, fake_model


class _FakeHarness:
    state = AgentState()
    session_id = "wm1"

    def abort(self) -> None:
        pass

    async def set_active_tools(self, tool_names):
        pass


def test_insights_scroll_eviction():
    store = WorkingMemoryStore(max_insights=3)
    store.write_insight("a")
    store.write_insight("b")
    store.write_insight("c")
    store.write_insight("d")
    assert store.insights == ["d", "c", "b"]


@pytest.mark.asyncio
async def test_pinned_appended_to_system_prompt():
    store = WorkingMemoryStore()
    store.write_pinned("budget=100")
    ext = WorkingMemoryExtension(store)
    ctx = ExtensionContext(session_id="wm1", harness=_FakeHarness())
    out = await ext.on_before_agent_start(ctx, "hi", "base prompt")
    assert out is not None
    assert "budget=100" in out["system_prompt"]
    assert "## Pinned" in out["system_prompt"]


@pytest.mark.asyncio
async def test_insights_injected_before_latest_user():
    store = WorkingMemoryStore()
    store.write_insight("found id=42")
    ext = WorkingMemoryExtension(store)
    msgs = [
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "go"},
    ]
    out = await ext.transform_context(msgs, None)
    assert any("found id=42" in str(m.get("content", "")) for m in out)
    # Inserted immediately before the latest user message.
    user_idx = next(i for i, m in enumerate(out) if m.get("role") == "user" and m.get("content") == "go")
    assert out[user_idx - 1].get("role") == "system"
    assert "found id=42" in out[user_idx - 1]["content"]


def test_anthropic_accumulates_system_injections():
    from agent_core.providers.anthropic_provider import _convert_messages

    msgs = [
        {"role": "system", "content": "## Working Memory Insights\n1. note"},
        {"role": "user", "content": "go"},
    ]
    _, system = _convert_messages(msgs, "base prompt")
    assert "base prompt" in system
    assert "Working Memory Insights" in system
    assert "note" in system


@pytest.mark.asyncio
async def test_harness_working_memory_tool_roundtrip():
    provider = FakeProvider()
    registry = ToolRegistry()
    store, _, extensions = install_working_memory(registry)

    provider.queue_script([
        StreamToolCallStart(id="c0", name="working_memory"),
        StreamToolCallEnd(
            id="c0",
            arguments={"action": "write_insight", "content": "note-1"},
        ),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        store=InMemoryStore(),
        session_id="wm-e2e",
        initial_state=AgentState(
            model=fake_model(),
            tools=registry.to_definitions(),
            system_prompt="sys",
        ),
        tool_registry=registry,
        extensions=extensions,
        tool_execution="sequential",
    )
    await harness.start()
    await harness.prompt("remember")
    assert store.insights[0] == "note-1"
