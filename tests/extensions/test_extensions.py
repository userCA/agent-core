import pytest

from agent_core.core.events import AgentStart, TextDelta, MessageUpdate
from agent_core.core.hooks import AgentHooks
from agent_core.core.state import AgentState
from agent_core.extensions.base import ExtensionContext, ExtensionRunner


class _FakeHarness:
    state = AgentState()
    hooks = AgentHooks()
    session_id = "s1"

    def abort(self) -> None:
        pass


class FakeExtension:
    name = "fake"

    def __init__(self):
        self.events = []
        self.before_calls = []
        self.after_calls = []

    async def on_event(self, ctx, evt):
        self.events.append(evt.type)

    async def on_before_tool_call(self, ctx, tool_call):
        self.before_calls.append(tool_call)
        return None

    async def on_after_tool_call(self, ctx, tool_call, result, is_error):
        self.after_calls.append((tool_call, result, is_error))
        return None


class BlockingExtension:
    name = "blocker"

    async def on_before_tool_call(self, ctx, tool_call):
        return {"block": True, "reason": "forbidden"}

    async def on_after_tool_call(self, ctx, tool_call, result, is_error):
        return None

    async def on_event(self, ctx, evt):
        pass


class ErrorExtension:
    name = "error"

    async def on_event(self, ctx, evt):
        raise RuntimeError("boom")

    async def on_before_tool_call(self, ctx, tool_call):
        raise RuntimeError("boom")

    async def on_after_tool_call(self, ctx, tool_call, result, is_error):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_runner_forwards_events():
    ext = FakeExtension()
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    runner = ExtensionRunner([ext], ctx)

    await runner.on_event(AgentStart())
    assert "agent_start" in ext.events


@pytest.mark.asyncio
async def test_runner_before_tool_call():
    ext = FakeExtension()
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    runner = ExtensionRunner([ext], ctx)

    result = await runner.before_tool_call({"tool_call": {"name": "foo"}})
    assert result is None
    assert len(ext.before_calls) == 1


@pytest.mark.asyncio
async def test_runner_blocking_extension():
    ext = BlockingExtension()
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    runner = ExtensionRunner([ext], ctx)

    result = await runner.before_tool_call({"tool_call": {"name": "foo"}})
    assert result == {"block": True, "reason": "forbidden"}


@pytest.mark.asyncio
async def test_runner_error_isolation():
    bad = ErrorExtension()
    good = FakeExtension()
    ctx = ExtensionContext(session_id="s1", harness=_FakeHarness(), store=None)
    runner = ExtensionRunner([bad, good], ctx)

    await runner.on_event(AgentStart())
    assert "agent_start" in good.events

    result = await runner.before_tool_call({"tool_call": {"name": "foo"}})
    assert result is None
    assert len(good.before_calls) == 1
