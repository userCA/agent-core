"""Tests for prompt budget pre-check."""

from __future__ import annotations

import pytest

from agent_core.compaction.budget import (
    PROMPT_BUDGET_EXCEEDED,
    estimate_prompt_tokens,
    is_prompt_budget_exceeded,
    prompt_budget_limit,
)
from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.content import TextContent
from agent_core.core.loop import run_agent_loop
from agent_core.core.messages import UserMessage
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import Model, StreamMessageEnd, StreamTextDelta
from tests.conftest import FakeProvider


def _big_user(n: int = 4000) -> UserMessage:
    return UserMessage(content=[TextContent(text="x" * n)], timestamp=0)


def test_prompt_budget_limit_and_estimate():
    limit = prompt_budget_limit(context_window=1000, max_output_tokens=100, ratio=0.95)
    assert limit == int(1000 * 0.95) - 100
    msgs = [_big_user(400)]  # ~100+ tokens
    used = estimate_prompt_tokens(msgs, system_prompt="sys")
    assert used > 0


def test_is_prompt_budget_exceeded():
    msgs = [_big_user(8000)]
    exceeded, used, limit = is_prompt_budget_exceeded(
        msgs,
        context_window=500,
        max_output_tokens=50,
        ratio=0.9,
    )
    assert exceeded is True
    assert used >= limit

    ok, _, _ = is_prompt_budget_exceeded(
        [UserMessage(content=[TextContent(text="hi")], timestamp=0)],
        context_window=100_000,
        max_output_tokens=1024,
        ratio=0.95,
    )
    assert ok is False


def test_large_max_output_does_not_collapse_limit_to_block_short():
    """When max_output ≈ window, still leave room for a short prompt."""
    limit = prompt_budget_limit(
        context_window=4096, max_output_tokens=4096, ratio=0.95
    )
    assert limit >= 1
    exceeded, _, _ = is_prompt_budget_exceeded(
        [UserMessage(content=[TextContent(text="hi")], timestamp=0)],
        context_window=4096,
        max_output_tokens=4096,
        ratio=0.95,
    )
    assert exceeded is False


@pytest.mark.asyncio
async def test_loop_aborts_without_provider_call_when_over_budget():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="should not run"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    model = Model(
        provider="fake",
        id="fake-1",
        context_window=200,
        max_output_tokens=50,
    )

    async def convert(msgs):
        return [{"role": "user", "content": "x"}]

    async def auth_resolver(_name):
        return ProviderAuth(api_key="k")

    events: list = []

    async def emit(evt):
        events.append(evt)

    context = AgentContext(
        system_prompt="s",
        messages=[],
        tools=[],
    )
    config = AgentLoopConfig(
        model=model,
        stream_fn=provider.stream,
        convert_to_llm=convert,
        auth_resolver=auth_resolver,
        prompt_budget_ratio=0.9,
        compact_callback=None,
    )
    user = _big_user(5000)
    assistants = await run_agent_loop([user], context, config, emit)

    assert provider.calls == []  # never streamed
    assert assistants
    assert assistants[0].error_message == PROMPT_BUDGET_EXCEEDED
    assert assistants[0].stop_reason == "error"
    assert PROMPT_BUDGET_EXCEEDED in assistants[0].content[0].text


@pytest.mark.asyncio
async def test_loop_compacts_then_proceeds():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    model = Model(
        provider="fake",
        id="fake-1",
        context_window=200,
        max_output_tokens=50,
    )
    compacted = {"done": False}

    async def compact_cb(messages):
        # Shrink to a tiny transcript so budget passes.
        messages.clear()
        messages.append(
            UserMessage(content=[TextContent(text="hi")], timestamp=0)
        )
        compacted["done"] = True
        return True

    async def convert(msgs):
        return [{"role": "user", "content": "hi"}]

    async def auth_resolver(_name):
        return ProviderAuth(api_key="k")

    events: list = []

    async def emit(evt):
        events.append(evt)

    context = AgentContext(system_prompt="", messages=[], tools=[])
    config = AgentLoopConfig(
        model=model,
        stream_fn=provider.stream,
        convert_to_llm=convert,
        auth_resolver=auth_resolver,
        prompt_budget_ratio=0.9,
        compact_callback=compact_cb,
    )
    await run_agent_loop([_big_user(5000)], context, config, emit)

    assert compacted["done"] is True
    assert len(provider.calls) == 1
    last = [e for e in events if getattr(e, "type", None) == "message_end"]
    assert last
    assert getattr(last[-1].message, "error_message", None) is None


@pytest.mark.asyncio
async def test_loop_budget_disabled_skips_check():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    model = Model(provider="fake", id="fake-1", context_window=200, max_output_tokens=50)

    async def convert(msgs):
        return [{"role": "user", "content": "x"}]

    async def auth_resolver(_name):
        return ProviderAuth(api_key="k")

    events: list = []

    async def emit(evt):
        events.append(evt)

    context = AgentContext(system_prompt="", messages=[], tools=[])
    config = AgentLoopConfig(
        model=model,
        stream_fn=provider.stream,
        convert_to_llm=convert,
        auth_resolver=auth_resolver,
        prompt_budget_ratio=None,
        compact_callback=None,
    )
    await run_agent_loop([_big_user(5000)], context, config, emit)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_loop_compact_false_still_aborts():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="no"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    model = Model(provider="fake", id="fake-1", context_window=200, max_output_tokens=50)

    async def compact_cb(messages):
        return False

    async def convert(msgs):
        return [{"role": "user", "content": "x"}]

    async def auth_resolver(_name):
        return ProviderAuth(api_key="k")

    events: list = []

    async def emit(evt):
        events.append(evt)

    context = AgentContext(system_prompt="", messages=[], tools=[])
    config = AgentLoopConfig(
        model=model,
        stream_fn=provider.stream,
        convert_to_llm=convert,
        auth_resolver=auth_resolver,
        prompt_budget_ratio=0.9,
        compact_callback=compact_cb,
    )
    assistants = await run_agent_loop([_big_user(5000)], context, config, emit)
    assert provider.calls == []
    assert assistants[0].error_message == PROMPT_BUDGET_EXCEEDED
