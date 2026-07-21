"""Tests for L4 DataBus / inspect_artifact."""

from __future__ import annotations

import json

import pytest

from agent_core.artifacts import (
    ArtifactRefIndex,
    InMemoryArtifactStore,
    InspectArtifactTool,
    apply_fetch_budget,
    build_outline,
    create_artifact_extension,
    install_databus,
    search_text,
)
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
from agent_core.tools.base import ToolDefinition, ToolRegistry, ToolResult
from tests.conftest import FakeProvider, fake_model


class _FakeHarness:
    state = AgentState()
    session_id = "s1"

    def abort(self) -> None:
        pass

    async def set_active_tools(self, tool_names):
        pass


class BigEchoTool:
    definition = ToolDefinition(
        name="big_echo",
        description="echo big",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text=params.get("text", ""))])


def test_apply_fetch_budget_degradation_order():
    small = "x" * 100
    payload, level = apply_fetch_budget(small)
    assert level == "full"
    assert payload == small

    big = "KEY=alpha\n" + ("Y" * 8000)
    payload, level = apply_fetch_budget(big)
    assert level == "summary"
    assert len(payload) <= 1000
    assert "enhanced_summary" in payload or "chars=" in payload

    tiny_budget, level2 = apply_fetch_budget(big, budget_chars=80)
    assert level2 in ("summary", "truncated")
    assert len(tiny_budget) <= 80


def test_search_and_outline():
    text = "foo=1\nbar=2\nfoo=3\n"
    hits = search_text(text, "foo")
    assert len(hits) == 2
    assert hits[0]["line"] == 1
    outline = build_outline(text)
    assert "chars=" in outline


@pytest.mark.asyncio
async def test_inspect_rejects_cross_session_ref():
    store = InMemoryArtifactStore()
    index = ArtifactRefIndex()
    ref_a = await store.put("secret-a", meta={"session_id": "A"})
    index.register(ref_id=ref_a, session_id="A", chars=8, summary="secret-a")
    tool_b = InspectArtifactTool(store=store, ref_index=index, session_id="B")
    out = await tool_b.execute(
        "t", {"action": "get_context", "ref_id": ref_a}, type("C", (), {})()
    )
    assert "not found" in out.content[0].text.lower()


@pytest.mark.asyncio
async def test_inspect_get_context_after_externalize():
    store = InMemoryArtifactStore()
    index = ArtifactRefIndex()
    _, ext = create_artifact_extension(
        store, char_threshold=50, summary_chars=20, ref_index=index, enable_l2_compress=False
    )
    ctx = ExtensionContext(session_id="sess-c6", harness=_FakeHarness())
    body = "SECRET_TOKEN=abc123\n" + ("Z" * 200)
    result = ToolResult(content=[TextContent(text=body)])
    out = await ext.on_after_tool_call(
        ctx, type("TC", (), {"name": "big_echo", "id": "c1"})(), result, False
    )
    assert out is not None
    ref_id = out["result"]["details"]["__refId"]
    assert index.get("sess-c6", ref_id) is not None

    tool = InspectArtifactTool(store=store, ref_index=index, session_id="sess-c6")
    listed = await tool.execute("t0", {"action": "list_refs"}, type("C", (), {})())
    data = json.loads(listed.content[0].text)
    assert data["count"] == 1
    assert data["refs"][0]["ref_id"] == ref_id

    got = await tool.execute(
        "t1", {"action": "get_context", "ref_id": ref_id}, type("C", (), {})()
    )
    assert "SECRET_TOKEN=abc123" in got.content[0].text
    assert got.details["inspect"]["degradation"] == "full"

    search = await tool.execute(
        "t2",
        {"action": "search", "ref_id": ref_id, "query": "SECRET_TOKEN"},
        type("C", (), {})(),
    )
    hits = json.loads(search.content[0].text)["hits"]
    assert hits and "SECRET_TOKEN" in hits[0]["snippet"]


@pytest.mark.asyncio
async def test_harness_databus_e2e():
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(BigEchoTool())
    store = InMemoryArtifactStore()
    index = ArtifactRefIndex()
    _, art_ext = create_artifact_extension(
        store, char_threshold=80, summary_chars=40, ref_index=index, enable_l2_compress=False
    )
    _, inspect_tool, extensions = install_databus(
        registry,
        store=store,
        session_id="c6-e2e",
        ref_index=index,
        extensions=[art_ext],
    )

    big = "ID=42\n" + ("Q" * 300)
    provider.queue_script([
        StreamToolCallStart(id="c0", name="big_echo"),
        StreamToolCallEnd(id="c0", arguments={"text": big}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamToolCallStart(id="c1", name="inspect_artifact"),
        StreamToolCallEnd(
            id="c1",
            arguments={"action": "list_refs"},
        ),
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
        session_id="c6-e2e",
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
    await harness.prompt("store then list")

    assert index.list_for_session("c6-e2e")
    # Second LLM call should see Artifact Ref Index in system (via before_agent_start
    # on that turn) — at least store has the body.
    ref_id = index.list_for_session("c6-e2e")[0].ref_id
    art = await store.get(ref_id)
    assert art is not None
    assert "ID=42" in art.content
