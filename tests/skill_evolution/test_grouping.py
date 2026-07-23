"""Tests for task grouping."""

from agent_core.skill_evolution.grouping import build_groups, normalize_task_key
from agent_core.skill_evolution.types import SkillEvolutionTrace


def test_normalize_task_key():
    assert normalize_task_key("  Fix   The BUG ") == "fix the bug"


def test_build_groups_min_size():
    traces = [
        SkillEvolutionTrace(trace_id=f"a{i}", skill_name="s", user_query="fix bug")
        for i in range(3)
    ] + [
        SkillEvolutionTrace(trace_id="b1", skill_name="s", user_query="other task"),
        SkillEvolutionTrace(trace_id="b2", skill_name="s", user_query="other task"),
    ]
    groups = build_groups(traces, min_size=3)
    assert len(groups) == 1
    assert len(groups[0]) == 3
    assert all(t.task_key == "fix bug" for t in groups[0])
