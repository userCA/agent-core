"""Integration: group → score → distill inside OfflineEvolutionAgent."""

from agent_core.skill_evolution.agent import OfflineEvolutionAgent
from agent_core.skill_evolution.store import InMemorySkillEvolutionStore
from agent_core.skill_evolution.types import (
    ExecutionOutcome,
    PathStep,
    SkillEvolutionTrace,
)


async def test_evolution_cycle_emits_path_proposals_from_group():
    store = InMemorySkillEvolutionStore()
    # Same task_key, different path quality (need >= min_traces and group size 3)
    configs = [
        (ExecutionOutcome.SUCCESS, ["read", "edit"], "a"),
        (ExecutionOutcome.PARTIAL, ["bash", "read", "edit"], "b"),
        (ExecutionOutcome.FAILURE, ["bash", "bash", "bash"], "c"),
    ]
    for i in range(20):
        outcome, tools, suffix = configs[i % 3]
        await store.save_trace(
            SkillEvolutionTrace(
                trace_id=f"t-{i}",
                skill_name="path-skill",
                user_query="Fix the bug",
                task_key="fix the bug",
                execution_outcome=outcome,
                steps=[PathStep(tool_name=t) for t in tools],
            )
        )

    agent = OfflineEvolutionAgent(store, batch_size=50)
    result = await agent.run_evolution_cycle(
        skill_name="path-skill",
        min_traces=10,
        max_proposals=10,
    )
    assert result["status"] == "completed"
    finals = result.get("final_proposals") or []
    # At least one path preference or case proposal should appear
    assert any(
        p.get("operation") in ("add", "add_case")
        and (
            "Path Preference" in (p.get("new_content") or "")
            or p.get("case_polarity") in ("positive", "negative")
        )
        for p in finals
    ), finals
