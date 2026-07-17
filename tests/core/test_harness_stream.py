"""Harness stream options and provider hook semantics (P1)."""

from __future__ import annotations

import pytest

from agent_core.core.content import TextContent
from agent_core.core.state import AgentState
from agent_core.core.stream_options import apply_stream_options_patch, clone_stream_options
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta, StreamToolCallEnd, StreamToolCallStart
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


def _tool_harness(session_id: str = "stream") -> tuple[AgentHarness, FakeProvider]:
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(EchoTool())
    store = InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id=session_id,
        initial_state=AgentState(model=fake_model(), tools=[EchoTool()]),
        tool_registry=registry,
    )
    return harness, provider


@pytest.mark.asyncio
async def test_stream_options_apply_patch_delete_header():
    base = {"headers": {"a": "1", "b": "2"}}
    patched = apply_stream_options_patch(base, {"headers": {"b": None, "c": "3"}})
    assert patched["headers"] == {"a": "1", "c": "3"}


def test_clone_stream_options_copies_nested_maps():
    opts = {"headers": {"x": "1"}, "metadata": {"y": "2"}}
    cloned = clone_stream_options(opts)
    cloned["headers"]["x"] = "changed"
    assert opts["headers"]["x"] == "1"


@pytest.mark.asyncio
async def test_set_stream_options_affects_next_turn_only():
    """Busy set_stream_options applies at save point on the next provider call."""
    harness, provider = _tool_harness("opts-next-turn")
    provider.queue_script([
        StreamToolCallStart(id="c1", name="echo"),
        StreamToolCallEnd(id="c1", arguments={"text": "hi"}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    switched = False

    async def on_event(evt):
        nonlocal switched
        if evt.type == "turn_start" and not switched:
            switched = True
            harness.set_stream_options({"headers": {"X-Turn": "2"}})

    harness.subscribe(on_event)
    await harness.start()
    harness.set_stream_options({"headers": {"X-Turn": "1"}})
    await harness.prompt("run")

    assert len(provider.calls) >= 2
    first_opts = provider.calls[0].get("stream_options") or {}
    second_opts = provider.calls[1].get("stream_options") or {}
    assert first_opts.get("headers", {}).get("X-Turn") == "1"
    assert second_opts.get("headers", {}).get("X-Turn") == "2"


@pytest.mark.asyncio
async def test_before_provider_request_hook_patches_options():
    harness, provider = _tool_harness("req-hook")
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    await harness.start()
    harness.set_stream_options({"headers": {"base": "yes"}})

    harness.hooks.on(
        "before_provider_request",
        lambda evt: {"stream_options": {"headers": {"hook": "patched"}}},
    )
    await harness.prompt("hi")

    opts = provider.calls[0].get("stream_options") or {}
    assert opts.get("headers", {}).get("base") == "yes"
    assert opts.get("headers", {}).get("hook") == "patched"


@pytest.mark.asyncio
async def test_before_provider_request_hook_deletes_header():
    harness, provider = _tool_harness("req-delete")
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    await harness.start()
    harness.set_stream_options({"headers": {"drop-me": "x", "keep": "y"}})

    harness.hooks.on(
        "before_provider_request",
        lambda evt: {"stream_options": {"headers": {"drop-me": None}}},
    )
    await harness.prompt("hi")

    headers = (provider.calls[0].get("stream_options") or {}).get("headers") or {}
    assert "drop-me" not in headers
    assert headers.get("keep") == "y"


@pytest.mark.asyncio
async def test_before_provider_payload_hook_transforms_messages():
    harness, provider = _tool_harness("payload-hook")
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    await harness.start()

    def patch_payload(evt):
        payload = dict(evt.payload)
        payload["messages"] = [{"role": "user", "content": "transformed"}]
        return {"payload": payload}

    harness.hooks.on("before_provider_payload", patch_payload)
    await harness.prompt("original")

    assert provider.calls[0]["messages"] == [{"role": "user", "content": "transformed"}]


@pytest.mark.asyncio
async def test_after_provider_response_hook_observed():
    harness, provider = _tool_harness("resp-hook")
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    await harness.start()

    seen: list[str] = []
    harness.hooks.on(
        "after_provider_response",
        lambda evt: seen.append(evt.type) or None,
    )
    await harness.prompt("hi")

    assert "after_provider_response" in seen
