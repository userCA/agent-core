"""Tests for group-relative advantages."""

from agent_core.skill_evolution.relative_score import assign_advantages, score_group
from agent_core.skill_evolution.types import ExecutionOutcome, SkillEvolutionTrace


def test_assign_advantages_mean_centered():
    group = [
        SkillEvolutionTrace(trace_id="a", reward=0.2),
        SkillEvolutionTrace(trace_id="b", reward=0.5),
        SkillEvolutionTrace(trace_id="c", reward=0.8),
    ]
    assign_advantages(group, fill_missing_reward=False)
    assert abs(group[0].advantage - (-0.3)) < 1e-9
    assert abs(group[1].advantage - 0.0) < 1e-9
    assert abs(group[2].advantage - 0.3) < 1e-9


async def test_score_group_fills_reward_and_advantage():
    group = [
        SkillEvolutionTrace(trace_id="a", execution_outcome=ExecutionOutcome.FAILURE),
        SkillEvolutionTrace(trace_id="b", execution_outcome=ExecutionOutcome.PARTIAL),
        SkillEvolutionTrace(trace_id="c", execution_outcome=ExecutionOutcome.SUCCESS),
    ]
    await score_group(group)
    assert all(t.reward is not None for t in group)
    assert all(t.advantage is not None for t in group)
    assert abs(sum(t.advantage for t in group)) < 1e-9
    assert group[2].advantage > group[0].advantage
