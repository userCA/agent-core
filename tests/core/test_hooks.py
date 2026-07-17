"""Tests for the unified AgentHooks system."""

import asyncio
import pytest

from agent_core.core.hooks import (
    AgentHooks,
    BeforeAgentStartHookEvent,
    ContextHookEvent,
    ToolCallHookEvent,
    ToolResultHookEvent,
)


def test_observe_fires_for_all_events():
    hooks = AgentHooks()
    seen = []

    hooks.observe(lambda evt: seen.append(evt.type))
    asyncio.run(hooks.emit(ContextHookEvent(messages=[])))
    asyncio.run(hooks.emit(ToolCallHookEvent(tool_name="x")))

    assert seen == ["context", "tool_call"]


def test_observe_unsubscribe():
    hooks = AgentHooks()
    seen = []

    unsub = hooks.observe(lambda evt: seen.append(evt.type))
    asyncio.run(hooks.emit(ContextHookEvent(messages=[])))
    unsub()
    asyncio.run(hooks.emit(ContextHookEvent(messages=[])))

    assert len(seen) == 1


def test_on_specific_type_only_fires_for_matching():
    hooks = AgentHooks()
    seen = []

    hooks.on("context", lambda evt: seen.append(evt.type))
    asyncio.run(hooks.emit(ToolCallHookEvent(tool_name="x")))
    asyncio.run(hooks.emit(ContextHookEvent(messages=[])))

    assert seen == ["context"]


def test_context_reducer_chain_transform():
    hooks = AgentHooks()

    def handler1(evt):
        return {"messages": evt.messages + ["injected_1"]}

    def handler2(evt):
        return {"messages": evt.messages + ["injected_2"]}

    hooks.on("context", handler1)
    hooks.on("context", handler2)

    result = asyncio.run(hooks.emit(ContextHookEvent(messages=["original"])))
    assert result["messages"] == ["original", "injected_1", "injected_2"]


def test_context_reducer_no_change_returns_none():
    hooks = AgentHooks()

    def noop_handler(evt):
        return None

    hooks.on("context", noop_handler)
    result = asyncio.run(hooks.emit(ContextHookEvent(messages=["a"])))
    assert result is None


def test_before_agent_start_reducer_accumulate():
    hooks = AgentHooks()

    def handler1(evt):
        return {"system_prompt": evt.system_prompt + "\n[handler1]"}

    def handler2(evt):
        return {"system_prompt": evt.system_prompt + "\n[handler2]", "message": "injected"}

    hooks.on("before_agent_start", handler1)
    hooks.on("before_agent_start", handler2)

    result = asyncio.run(hooks.emit(BeforeAgentStartHookEvent(prompt="hi", system_prompt="base")))
    assert "[handler1]" in result["system_prompt"]
    assert "[handler2]" in result["system_prompt"]
    assert result["messages"] == ["injected"]


def test_tool_call_early_exit_on_block():
    hooks = AgentHooks()

    def blocker(evt):
        return {"block": True, "reason": "forbidden"}

    def never_reached(evt):
        raise AssertionError("Should not be called after block")

    hooks.on("tool_call", blocker)
    hooks.on("tool_call", never_reached)

    result = asyncio.run(hooks.emit(ToolCallHookEvent(tool_name="dangerous")))
    assert result["block"] is True
    assert result["reason"] == "forbidden"


def test_tool_call_no_block_returns_none():
    hooks = AgentHooks()

    def allow(evt):
        return {"inject_metadata": {"extra": True}}

    hooks.on("tool_call", allow)

    result = asyncio.run(hooks.emit(ToolCallHookEvent(tool_name="safe")))
    assert result is None


def test_tool_result_patch_accumulation():
    """Tool result reducer patches result sequentially."""
    hooks = AgentHooks()
    calls = []

    def handler1(evt):
        calls.append("h1")
        return None  # no patch

    def handler2(evt):
        calls.append("h2")
        return None

    hooks.on("tool_result", handler1)
    hooks.on("tool_result", handler2)

    asyncio.run(hooks.emit(ToolResultHookEvent(tool_name="x", result="ok")))
    assert calls == ["h1", "h2"]


def test_async_handler():
    hooks = AgentHooks()

    async def async_handler(evt):
        return {"messages": evt.messages + ["async_injected"]}

    hooks.on("context", async_handler)

    result = asyncio.run(hooks.emit(ContextHookEvent(messages=["start"])))
    assert result["messages"] == ["start", "async_injected"]


def test_observer_exception_does_not_propagate():
    hooks = AgentHooks()

    def bad_observer(evt):
        raise ValueError("observer boom")

    hooks.observe(bad_observer)

    # Should not raise
    result = asyncio.run(hooks.emit(ContextHookEvent(messages=[])))
    assert result is None


def test_handler_exception_does_not_propagate():
    hooks = AgentHooks()

    def bad_handler(evt):
        raise ValueError("handler boom")

    def good_handler(evt):
        return {"messages": ["recovered"]}

    hooks.on("context", bad_handler)
    hooks.on("context", good_handler)

    result = asyncio.run(hooks.emit(ContextHookEvent(messages=[])))
    assert result["messages"] == ["recovered"]


def test_no_handlers_returns_none():
    hooks = AgentHooks()
    result = asyncio.run(hooks.emit(ContextHookEvent(messages=[])))
    assert result is None


def test_on_unsubscribe():
    hooks = AgentHooks()
    seen = []

    unsub = hooks.on("context", lambda evt: seen.append(1))
    asyncio.run(hooks.emit(ContextHookEvent(messages=[])))
    unsub()
    asyncio.run(hooks.emit(ContextHookEvent(messages=[])))

    assert len(seen) == 1
