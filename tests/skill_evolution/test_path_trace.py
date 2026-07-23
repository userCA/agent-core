"""Tests for PathStep and path-related SkillEvolutionTrace fields."""

from agent_core.skill_evolution.types import PathStep, SkillEvolutionTrace


def test_path_step_fields():
    step = PathStep(
        tool_name="bash",
        args_summary="ls -la",
        is_error=False,
        duration_ms=12.5,
    )
    assert step.tool_name == "bash"
    assert step.is_error is False
    assert step.duration_ms == 12.5


def test_trace_accepts_path_fields():
    trace = SkillEvolutionTrace(
        trace_id="t1",
        skill_name="demo",
        steps=[PathStep(tool_name="read", args_summary="f.py", is_error=False)],
        group_id="g1",
        task_key="fix-bug",
        reward=0.8,
        advantage=0.2,
        human_signal={"vote": "like"},
    )
    assert len(trace.steps) == 1
    assert trace.group_id == "g1"
    assert trace.task_key == "fix-bug"
    assert trace.reward == 0.8
    assert trace.advantage == 0.2
    assert trace.human_signal["vote"] == "like"


def test_trace_path_defaults_empty():
    trace = SkillEvolutionTrace(trace_id="t2")
    assert trace.steps == []
    assert trace.group_id is None
    assert trace.task_key == ""
    assert trace.reward is None
    assert trace.advantage is None
    assert trace.human_signal is None
