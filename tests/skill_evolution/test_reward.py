"""Tests for HybridReward."""

import pytest

from agent_core.skill_evolution.reward import HybridReward, heuristic_reward, human_reward
from agent_core.skill_evolution.types import (
    ExecutionOutcome,
    PathStep,
    SkillEvolutionTrace,
)


def test_heuristic_success_higher_than_failure():
    ok = SkillEvolutionTrace(trace_id="a", execution_outcome=ExecutionOutcome.SUCCESS)
    bad = SkillEvolutionTrace(trace_id="b", execution_outcome=ExecutionOutcome.FAILURE)
    assert heuristic_reward(ok) > heuristic_reward(bad)


def test_heuristic_penalizes_error_steps_and_long_paths():
    short = SkillEvolutionTrace(
        trace_id="s",
        execution_outcome=ExecutionOutcome.SUCCESS,
        steps=[PathStep(tool_name="read", is_error=False)],
    )
    long_err = SkillEvolutionTrace(
        trace_id="l",
        execution_outcome=ExecutionOutcome.SUCCESS,
        steps=[PathStep(tool_name=f"t{i}", is_error=(i % 3 == 0)) for i in range(12)],
    )
    assert heuristic_reward(short) > heuristic_reward(long_err)


def test_human_reward_from_signal():
    t = SkillEvolutionTrace(trace_id="h", human_signal={"vote": "like"})
    assert human_reward(t) == 1.0
    t2 = SkillEvolutionTrace(trace_id="h2", human_signal={"vote": "dislike"})
    assert human_reward(t2) == -1.0
    assert human_reward(SkillEvolutionTrace(trace_id="n")) is None


@pytest.mark.asyncio
async def test_missing_human_and_judge_renormalizes_weights():
    rewarder = HybridReward(w_h=0.4, w_j=0.4, w_u=0.2, judge=None)
    trace = SkillEvolutionTrace(
        trace_id="t",
        execution_outcome=ExecutionOutcome.SUCCESS,
    )
    br = await rewarder.compute(trace)
    assert set(br.weights.keys()) == {"h"}
    assert abs(br.weights["h"] - 1.0) < 1e-9
    assert br.r_u is None
    assert br.r_j is None
    assert trace.reward == br.r


@pytest.mark.asyncio
async def test_compute_with_judge_and_human():
    async def judge(_t):
        return 0.9

    rewarder = HybridReward(w_h=0.4, w_j=0.4, w_u=0.2, judge=judge)
    trace = SkillEvolutionTrace(
        trace_id="t",
        execution_outcome=ExecutionOutcome.SUCCESS,
        human_signal={"vote": "like"},
    )
    br = await rewarder.compute(trace)
    assert set(br.weights.keys()) == {"h", "j", "u"}
    assert abs(sum(br.weights.values()) - 1.0) < 1e-9
    assert trace.reward is not None
