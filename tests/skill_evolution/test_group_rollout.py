"""Tests for GroupRollout and trigger policy."""

import pytest

from agent_core.core.events import AgentStart, TurnEnd
from agent_core.extensions.base import ExtensionContext
from agent_core.skill_evolution.collector import SkillTraceCollector
from agent_core.skill_evolution.group_rollout import (
    GroupRollout,
    should_trigger_group_rollout,
)
from agent_core.skill_evolution.store import InMemorySkillEvolutionStore


def test_trigger_off_by_default_policy():
    assert should_trigger_group_rollout(enabled=False, consecutive_failures=99) is False
    assert should_trigger_group_rollout(enabled=True, consecutive_failures=1) is False
    assert should_trigger_group_rollout(enabled=True, consecutive_failures=2) is True
    assert should_trigger_group_rollout(enabled=True, high_value_skill=True) is True


@pytest.mark.asyncio
async def test_group_rollout_tags_collector_and_clears():
    store = InMemorySkillEvolutionStore()
    collector = SkillTraceCollector(store)

    class FakeState:
        system_prompt = '<skill name="demo">d</skill>'
        messages = [type("U", (), {"role": "user", "content": "Fix Bug"})()]

    class FakeAgent:
        state = FakeState()

    class FakeMessage:
        error_message = None
        stop_reason = "stop"

    ctx = ExtensionContext(session_id="s", harness=FakeAgent(), store=store)
    seen_ids: list[str | None] = []

    async def runner(i: int, query: str):
        await collector.on_event(ctx, AgentStart())
        await collector.on_event(ctx, TurnEnd(message=FakeMessage(), tool_results=[]))
        traces = await store.get_traces()
        seen_ids.append(traces[0].group_id if traces else None)
        return i

    rollout = GroupRollout(collector=collector, g=3, parallel=False)
    result = await rollout.run("Fix Bug", runner)
    assert result.g == 3
    assert result.ok_count == 3
    assert result.task_key == "fix bug"
    assert len(set(seen_ids)) == 1
    assert seen_ids[0] == result.group_id
    assert collector._active_group_id is None


@pytest.mark.asyncio
async def test_group_rollout_captures_errors():
    async def runner(i: int, query: str):
        if i == 1:
            raise RuntimeError("boom")
        return i

    result = await GroupRollout(g=3, parallel=True).run("q", runner)
    assert result.ok_count == 2
    assert result.errors[1] is not None
