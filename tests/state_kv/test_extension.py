"""Extension + harness e2e for H3 parameterBindings."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_core.core.content import TextContent
from agent_core.core.state import AgentState
from agent_core.extensions.base import ExtensionContext
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import (
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.state_kv import (
    STATE_BIND_KEY,
    STATE_BOUND_KEY,
    STATE_KEY_MISSING,
    InMemorySessionStateStore,
    SessionStateBindingExtension,
    create_state_kv_extension,
)
from agent_core.tools.base import ToolDefinition, ToolRegistry, ToolResult
from tests.conftest import FakeProvider, fake_model


class _FakeHarness:
    state = AgentState()
    session_id = "s1"


class BindListTool:
    """Produces a large list bound into session state (not in LLM args later)."""

    definition = ToolDefinition(
        name="bind_list",
        description="bind a list into state",
        parameters={"type": "object", "properties": {}},
    )

    async def execute(self, tool_call_id, params, ctx):
        big = list(range(50))
        return ToolResult(
            content=[TextContent(text=f"bound {len(big)} ids to state.items")],
            details={STATE_BIND_KEY: {"items": big}},
        )


class ConsumeListTool:
    received: list | None = None

    definition = ToolDefinition(
        name="consume_list",
        description="consume bound list",
        parameters={
            "type": "object",
            "properties": {"items": {"type": "array"}},
            "required": ["items"],
        },
    )

    async def execute(self, tool_call_id, params, ctx):
        ConsumeListTool.received = params.get("items")
        n = len(ConsumeListTool.received or [])
        return ToolResult(content=[TextContent(text=f"got {n} items")])


@pytest.mark.asyncio
async def test_extension_binds_and_strips_payload():
    store = InMemorySessionStateStore()
    ext = SessionStateBindingExtension(store)
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    result = ToolResult(
        content=[TextContent(text="ok")],
        details={STATE_BIND_KEY: {"items": [1, 2]}, "keep": True},
    )
    out = await ext.on_after_tool_call(
        ctx, SimpleNamespace(name="bind_list", id="c1"), result, False
    )
    assert out is not None
    d = out["result"]["details"]
    assert STATE_BIND_KEY not in d
    assert d[STATE_BOUND_KEY] == ["items"]
    assert d["keep"] is True
    assert await store.get("s1", "items") == [1, 2]


@pytest.mark.asyncio
async def test_extension_resolves_placeholder_args():
    store = InMemorySessionStateStore()
    await store.set("s1", "items", [9, 8])
    ext = SessionStateBindingExtension(store)
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    tc = SimpleNamespace(
        name="consume",
        arguments={"items": "{{state.items}}", "mode": "fast"},
    )
    out = await ext.on_before_tool_call(ctx, tc)
    # Only placeholder keys — peer hook mutations to other keys stay intact
    assert out == {"mutated_args": {"items": [9, 8]}}


@pytest.mark.asyncio
async def test_extension_strips_invalid_bind_keys():
    store = InMemorySessionStateStore()
    ext = SessionStateBindingExtension(store)
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    result = ToolResult(
        content=[TextContent(text="ok")],
        details={STATE_BIND_KEY: {"bad-key": [1], "": "x"}},
    )
    out = await ext.on_after_tool_call(
        ctx, SimpleNamespace(name="bind_list", id="c1"), result, False
    )
    assert out is not None
    assert STATE_BIND_KEY not in out["result"]["details"]
    assert STATE_BOUND_KEY not in out["result"]["details"]
    assert await store.has("s1", "bad-key") is False


@pytest.mark.asyncio
async def test_extension_skips_bind_on_error():
    store = InMemorySessionStateStore()
    ext = SessionStateBindingExtension(store)
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    result = ToolResult(
        content=[TextContent(text="fail")],
        details={STATE_BIND_KEY: {"items": [1]}},
    )
    out = await ext.on_after_tool_call(
        ctx, SimpleNamespace(name="bind_list", id="c1"), result, True
    )
    assert out is None
    assert await store.has("s1", "items") is False


@pytest.mark.asyncio
async def test_extension_blocks_missing_key():
    store = InMemorySessionStateStore()
    ext = SessionStateBindingExtension(store)
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    tc = SimpleNamespace(name="consume", arguments={"items": "{{state.missing}}"})
    out = await ext.on_before_tool_call(ctx, tc)
    assert out is not None
    assert out.get("block") is True
    assert STATE_KEY_MISSING in out["reason"]


@pytest.mark.asyncio
async def test_harness_e2e_bind_then_inject():
    ConsumeListTool.received = None
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(BindListTool())
    registry.register(ConsumeListTool())
    store, ext = create_state_kv_extension()

    # Turn 1: bind
    provider.queue_script([
        StreamToolCallStart(id="c0", name="bind_list"),
        StreamToolCallEnd(id="c0", arguments={}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    # Turn 2: consume with placeholder only (no large array in LLM args)
    provider.queue_script([
        StreamToolCallStart(id="c1", name="consume_list"),
        StreamToolCallEnd(id="c1", arguments={"items": "{{state.items}}"}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        store=InMemoryStore(),
        session_id="sess-h3",
        initial_state=AgentState(
            system_prompt="",
            model=fake_model(),
            tools=registry.to_definitions(),
        ),
        tool_registry=registry,
        extensions=[ext],
        tool_execution="sequential",
    )
    await harness.start()
    await harness.prompt("go")

    assert ConsumeListTool.received == list(range(50))
    assert await store.get("sess-h3", "items") == list(range(50))
