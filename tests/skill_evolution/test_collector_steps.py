"""Tests: SkillTraceCollector rebuilds PathStep sequences from tool events."""

from agent_core.core.events import AgentStart, ToolExecutionEnd, ToolExecutionStart, TurnEnd
from agent_core.extensions.base import ExtensionContext
from agent_core.skill_evolution.collector import SkillTraceCollector
from agent_core.skill_evolution.store import InMemorySkillEvolutionStore


class _FakeState:
    system_prompt = '<skill name="demo">desc</skill>'
    messages = [type("U", (), {"role": "user", "content": "  Fix The Bug  "})()]


class _FakeAgent:
    state = _FakeState()


class _FakeMessage:
    error_message = None
    stop_reason = "stop"


async def test_collector_records_tool_steps():
    store = InMemorySkillEvolutionStore()
    collector = SkillTraceCollector(store)
    ctx = ExtensionContext(session_id="s1", harness=_FakeAgent(), store=store)

    await collector.on_event(ctx, AgentStart())
    await collector.on_event(
        ctx,
        ToolExecutionStart(
            tool_call_id="c1",
            tool_name="read",
            args={"path": "a.py"},
        ),
    )
    await collector.on_event(
        ctx,
        ToolExecutionEnd(
            tool_call_id="c1",
            tool_name="read",
            result="ok",
            is_error=False,
        ),
    )
    await collector.on_event(
        ctx,
        ToolExecutionStart(
            tool_call_id="c2",
            tool_name="bash",
            args={"command": "false"},
        ),
    )
    await collector.on_event(
        ctx,
        ToolExecutionEnd(
            tool_call_id="c2",
            tool_name="bash",
            result="exit 1",
            is_error=True,
        ),
    )
    await collector.on_event(ctx, TurnEnd(message=_FakeMessage(), tool_results=[]))

    traces = await store.get_traces()
    assert len(traces) == 1
    t = traces[0]
    assert len(t.steps) == 2
    assert t.steps[0].tool_name == "read"
    assert t.steps[0].is_error is False
    assert t.steps[0].tool_call_id == "c1"
    assert "path" in t.steps[0].args_summary
    assert "a.py" in t.steps[0].args_summary
    assert t.steps[1].tool_name == "bash"
    assert t.steps[1].is_error is True
    assert "exit" in t.steps[1].error_summary
    assert t.task_key == "fix the bug"


async def test_collector_summarizes_and_truncates_args():
    summary = SkillTraceCollector._summarize_args(
        {"path": "a.py", "content": "x" * 500},
        max_len=80,
    )
    assert len(summary) <= 80
    assert "path" in summary


async def test_agent_start_clears_pending_steps():
    store = InMemorySkillEvolutionStore()
    collector = SkillTraceCollector(store)
    ctx = ExtensionContext(session_id="s1", harness=_FakeAgent(), store=store)

    await collector.on_event(ctx, AgentStart())
    await collector.on_event(
        ctx,
        ToolExecutionEnd(tool_call_id="c1", tool_name="read", result="ok", is_error=False),
    )
    await collector.on_event(ctx, AgentStart())  # new run
    await collector.on_event(ctx, TurnEnd(message=_FakeMessage(), tool_results=[]))

    traces = await store.get_traces()
    assert len(traces) == 1
    assert traces[0].steps == []
