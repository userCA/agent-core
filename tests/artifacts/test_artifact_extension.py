"""Tests for ArtifactExternalizeExtension (L1 threshold externalization)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_core.artifacts.extension import ArtifactExternalizeExtension
from agent_core.artifacts.store import InMemoryArtifactStore
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


class EchoTool:
    definition = ToolDefinition(
        name="echo",
        description="echo",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text=params.get("text", ""))])


def _text_result(text: str, *, details=None) -> ToolResult:
    return ToolResult(content=[TextContent(text=text)], details=details)


@pytest.mark.asyncio
async def test_below_threshold_passthrough():
    store = InMemoryArtifactStore()
    ext = ArtifactExternalizeExtension(store, char_threshold=100, summary_chars=40)
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    result = _text_result("short")
    out = await ext.on_after_tool_call(ctx, SimpleNamespace(name="echo", id="c1"), result, False)
    assert out is None
    assert await store.get("anything") is None


@pytest.mark.asyncio
async def test_above_threshold_stores_and_replaces():
    store = InMemoryArtifactStore()
    ext = ArtifactExternalizeExtension(store, char_threshold=50, summary_chars=20)
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    full = "A" * 200
    result = _text_result(full, details={"source": "test"})
    out = await ext.on_after_tool_call(ctx, SimpleNamespace(name="echo", id="c1"), result, False)

    assert out is not None
    mutated = out["result"]
    assert mutated["details"]["__stored"] is True
    ref_id = mutated["details"]["__refId"]
    assert mutated["details"]["__chars"] == 200
    assert mutated["details"]["source"] == "test"
    assert "__refId" in mutated["details"]
    assert "original_details" not in mutated["details"]

    content_text = mutated["content"][0].text
    assert "[artifact_ref]" in content_text
    assert ref_id in content_text
    assert len(content_text) < 200

    art = await store.get(ref_id)
    assert art is not None
    assert art.content == full


@pytest.mark.asyncio
async def test_l2_fallback_for_large_body_keeps_raw_preview():
    store = InMemoryArtifactStore()
    ext = ArtifactExternalizeExtension(
        store,
        char_threshold=100,
        summary_chars=40,
        enable_l2_compress=True,
        compress_min_chars=10_000,
        compress_target_chars=2000,
        preview_chars=16,
    )
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    full = "FIELD_NAME=ok\n" + ("X" * 12_000)
    result = _text_result(full, details={"source": "big"})
    out = await ext.on_after_tool_call(ctx, SimpleNamespace(name="bash", id="c1"), result, False)
    assert out is not None
    d = out["result"]["details"]
    assert d["__compressMethod"] == "fallback"
    assert d["__fallbackTruncated"] is True
    assert d["__preview"] == full[:16]
    assert "FIELD_NAME" in d["__preview"]
    content = out["result"]["content"][0].text
    assert "[artifact_ref]" in content
    assert "preview:" not in content  # preview must not enter LLM envelope
    assert len(d["__summary"]) <= 2000
    art = await store.get(d["__refId"])
    assert art is not None
    assert art.content == full


@pytest.mark.asyncio
async def test_l2_llm_summary_does_not_rewrite_preview():
    store = InMemoryArtifactStore()

    async def compress_fn(t, *, target_chars, tool_name):
        return "LLM_REWROTE_EVERYTHING"

    ext = ArtifactExternalizeExtension(
        store,
        char_threshold=100,
        compress_fn=compress_fn,
        compress_min_chars=500,
        compress_target_chars=100,
        preview_chars=20,
    )
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    full = "PREFIX_MATCH_VALUE" + ("Y" * 600)
    out = await ext.on_after_tool_call(
        ctx, SimpleNamespace(name="echo", id="c1"), _text_result(full), False
    )
    assert out is not None
    d = out["result"]["details"]
    assert d["__compressMethod"] == "llm"
    assert d["__summary"] == "LLM_REWROTE_EVERYTHING"
    assert d["__preview"] == full[:20]
    assert d["__preview"].startswith("PREFIX_MATCH_VALUE")


@pytest.mark.asyncio
async def test_preserves_top_level_details_keys():
    """bash/plan/urls consumers read top-level details keys — must survive externalize."""
    store = InMemoryArtifactStore()
    ext = ArtifactExternalizeExtension(store, char_threshold=50, summary_chars=20)
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    result = _text_result(
        "Z" * 100,
        details={"exit_code": 0, "truncated": True, "urls": ["https://x"]},
    )
    out = await ext.on_after_tool_call(ctx, SimpleNamespace(name="bash", id="c1"), result, False)
    assert out is not None
    d = out["result"]["details"]
    assert d["exit_code"] == 0
    assert d["truncated"] is True
    assert d["urls"] == ["https://x"]
    assert d["__stored"] is True
    assert d["__refId"]


@pytest.mark.asyncio
async def test_skips_errors_and_already_stored():
    store = InMemoryArtifactStore()
    ext = ArtifactExternalizeExtension(store, char_threshold=10, summary_chars=5)
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    big = "X" * 100

    err_out = await ext.on_after_tool_call(
        ctx, SimpleNamespace(name="echo", id="c1"), _text_result(big), True
    )
    assert err_out is None

    already = _text_result(big, details={"__stored": True, "__refId": "existing"})
    skip = await ext.on_after_tool_call(
        ctx, SimpleNamespace(name="echo", id="c2"), already, False
    )
    assert skip is None


@pytest.mark.asyncio
async def test_harness_llm_sees_ref_not_full_body():
    store = InMemoryArtifactStore()
    ext = ArtifactExternalizeExtension(store, char_threshold=80, summary_chars=30)
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(EchoTool())
    big = "B" * 500
    provider.queue_script([
        StreamToolCallStart(id="c1", name="echo"),
        StreamToolCallEnd(id="c1", arguments={"text": big}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=InMemoryStore(),
        session_id="art-e2e",
        initial_state=AgentState(model=fake_model(), tools=[EchoTool()]),
        tool_registry=registry,
        extensions=[ext],
        tool_execution="sequential",
    )
    await harness.start()
    await harness.prompt("run")

    assert len(provider.calls) >= 2
    second_msgs = provider.calls[1]["messages"]
    tool_msgs = [m for m in second_msgs if m.get("role") == "tool"]
    assert tool_msgs
    body = tool_msgs[0]["content"]
    assert isinstance(body, str)
    assert "[artifact_ref]" in body
    assert big not in body
    assert "B" * 30 in body  # summary prefix retained

    # transcript message also ref-only; full body recoverable from store
    tool_results = [
        m for m in harness.state.messages if getattr(m, "role", None) == "tool_result"
    ]
    assert tool_results
    tr = tool_results[0]
    text = tr.content[0].text
    assert "[artifact_ref]" in text
    ref_id = tr.details["__refId"]
    art = await store.get(ref_id)
    assert art is not None
    assert art.content == big
