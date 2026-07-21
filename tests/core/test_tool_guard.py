"""Tests for DuplicateToolCallGuard (H1)."""

from __future__ import annotations

import pytest

from agent_core.core.content import TextContent
from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.loop import run_agent_loop
from agent_core.core.messages import UserMessage
from agent_core.core.tool_guard import (
    DUPLICATE_TOOL_CALL,
    DuplicateToolCallGuard,
    tool_call_fingerprint,
)
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import (
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)
from agent_core.tools.base import ToolDefinition, ToolRegistry, ToolResult
from tests.conftest import FakeProvider, fake_model


def test_fingerprint_stable():
    a = tool_call_fingerprint("echo", {"b": 1, "a": 2})
    b = tool_call_fingerprint("echo", {"a": 2, "b": 1})
    assert a == b
    assert a != tool_call_fingerprint("echo", {"a": 3})


def test_guard_allows_then_blocks():
    guard = DuplicateToolCallGuard(max_repeats=3)
    assert guard.check("echo", {"x": 1}) is None
    assert guard.check("echo", {"x": 1}) is None
    assert guard.check("echo", {"x": 1}) is None
    blocked = guard.check("echo", {"x": 1})
    assert blocked is not None
    assert DUPLICATE_TOOL_CALL in blocked


def test_guard_resets_on_different_args():
    guard = DuplicateToolCallGuard(max_repeats=2)
    assert guard.check("echo", {"x": 1}) is None
    assert guard.check("echo", {"x": 1}) is None
    assert guard.check("echo", {"x": 1}) is not None
    assert guard.check("echo", {"x": 2}) is None
    assert guard.check("echo", {"x": 2}) is None
    assert guard.check("echo", {"x": 2}) is not None


def test_guard_resets_on_different_tool_name():
    guard = DuplicateToolCallGuard(max_repeats=2)
    assert guard.check("echo", {"x": 1}) is None
    assert guard.check("echo", {"x": 1}) is None
    assert guard.check("other", {"x": 1}) is None
    assert guard.check("other", {"x": 1}) is None
    assert guard.check("other", {"x": 1}) is not None


def test_guard_blocked_does_not_append():
    guard = DuplicateToolCallGuard(max_repeats=1)
    assert guard.check("echo", {"x": 1}) is None
    assert guard.check("echo", {"x": 1}) is not None
    assert guard.check("echo", {"x": 1}) is not None  # still blocked


def test_fingerprint_circular_does_not_raise():
    a: dict = {}
    a["self"] = a
    fp = tool_call_fingerprint("echo", a)
    assert "echo:" in fp


class EchoTool:
    definition = ToolDefinition(
        name="echo",
        description="echo",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
    )
    calls = 0

    async def execute(self, tool_call_id, params, ctx):
        EchoTool.calls += 1
        return ToolResult(content=[TextContent(text=params.get("text", ""))])


@pytest.mark.asyncio
async def test_loop_blocks_fourth_identical_tool_call():
    EchoTool.calls = 0
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(EchoTool())

    # 4 identical tool turns, then stop
    for i in range(4):
        provider.queue_script([
            StreamToolCallStart(id=f"c{i}", name="echo"),
            StreamToolCallEnd(id=f"c{i}", arguments={"text": "same"}),
            StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
        ])
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    async def convert(msgs):
        return [{"role": "user", "content": "go"}]

    async def auth_resolver(_n):
        return ProviderAuth(api_key="k")

    events: list = []

    async def emit(evt):
        events.append(evt)

    context = AgentContext(
        system_prompt="",
        messages=[],
        tools=[EchoTool.definition],
    )
    config = AgentLoopConfig(
        model=fake_model(),
        stream_fn=provider.stream,
        convert_to_llm=convert,
        auth_resolver=auth_resolver,
        tool_registry=registry,
        tool_execution="sequential",
        duplicate_tool_max_repeats=3,
        prompt_budget_ratio=None,
    )
    await run_agent_loop(
        [UserMessage(content=[TextContent(text="go")], timestamp=0)],
        context,
        config,
        emit,
    )

    # First 3 execute; 4th blocked without calling tool
    assert EchoTool.calls == 3
    tool_ends = [e for e in events if getattr(e, "type", None) == "tool_execution_end"]
    assert any(
        getattr(e, "is_error", False)
        and DUPLICATE_TOOL_CALL in str(getattr(getattr(e, "result", None), "content", ""))
        for e in tool_ends
    )


@pytest.mark.asyncio
async def test_loop_disable_duplicate_guard():
    EchoTool.calls = 0
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(EchoTool())

    for i in range(5):
        provider.queue_script([
            StreamToolCallStart(id=f"d{i}", name="echo"),
            StreamToolCallEnd(id=f"d{i}", arguments={"text": "same"}),
            StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
        ])
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    async def convert(msgs):
        return [{"role": "user", "content": "go"}]

    async def auth_resolver(_n):
        return ProviderAuth(api_key="k")

    async def emit(evt):
        pass

    context = AgentContext(system_prompt="", messages=[], tools=[EchoTool.definition])
    config = AgentLoopConfig(
        model=fake_model(),
        stream_fn=provider.stream,
        convert_to_llm=convert,
        auth_resolver=auth_resolver,
        tool_registry=registry,
        tool_execution="sequential",
        duplicate_tool_max_repeats=None,
        prompt_budget_ratio=None,
    )
    await run_agent_loop(
        [UserMessage(content=[TextContent(text="go")], timestamp=0)],
        context,
        config,
        emit,
    )
    assert EchoTool.calls == 5


@pytest.mark.asyncio
async def test_parallel_batch_counts_toward_streak():
    EchoTool.calls = 0
    provider = FakeProvider()
    registry = ToolRegistry()
    registry.register(EchoTool())

    # One turn with 4 identical parallel tool calls → 3 execute, 1 blocked
    provider.queue_script([
        StreamToolCallStart(id="p0", name="echo"),
        StreamToolCallEnd(id="p0", arguments={"text": "same"}),
        StreamToolCallStart(id="p1", name="echo"),
        StreamToolCallEnd(id="p1", arguments={"text": "same"}),
        StreamToolCallStart(id="p2", name="echo"),
        StreamToolCallEnd(id="p2", arguments={"text": "same"}),
        StreamToolCallStart(id="p3", name="echo"),
        StreamToolCallEnd(id="p3", arguments={"text": "same"}),
        StreamMessageEnd(stop_reason="tool_calls", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    async def convert(msgs):
        return [{"role": "user", "content": "go"}]

    async def auth_resolver(_n):
        return ProviderAuth(api_key="k")

    events: list = []

    async def emit(evt):
        events.append(evt)

    context = AgentContext(system_prompt="", messages=[], tools=[EchoTool.definition])
    config = AgentLoopConfig(
        model=fake_model(),
        stream_fn=provider.stream,
        convert_to_llm=convert,
        auth_resolver=auth_resolver,
        tool_registry=registry,
        tool_execution="parallel",
        duplicate_tool_max_repeats=3,
        prompt_budget_ratio=None,
    )
    await run_agent_loop(
        [UserMessage(content=[TextContent(text="go")], timestamp=0)],
        context,
        config,
        emit,
    )
    assert EchoTool.calls == 3
    tool_ends = [e for e in events if getattr(e, "type", None) == "tool_execution_end"]
    assert sum(1 for e in tool_ends if getattr(e, "is_error", False)) >= 1
