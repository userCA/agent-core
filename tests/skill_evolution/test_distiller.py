"""Tests for path preference / case distillation."""

from agent_core.skill_evolution.distiller import distill_group
from agent_core.skill_evolution.types import PathStep, SkillEvolutionTrace


def _trace(tid: str, adv: float, tools: list[str]) -> SkillEvolutionTrace:
    return SkillEvolutionTrace(
        trace_id=tid,
        skill_name="demo",
        user_query="fix bug",
        task_key="fix bug",
        group_id="g1",
        advantage=adv,
        steps=[PathStep(tool_name=t) for t in tools],
    )


def test_distill_positive_and_negative():
    traces = [
        _trace("hi", 0.3, ["read", "edit"]),
        _trace("mid", 0.0, ["read", "bash", "edit"]),
        _trace("lo", -0.3, ["bash", "bash", "bash"]),
    ]
    props = distill_group(traces, tau=0.15)
    ops = {(p.operation, p.case_polarity) for p in props}
    assert ("add", "positive") in ops
    assert ("add_case", "positive") in ops
    assert ("add", "negative") in ops
    assert ("add_case", "negative") in ops
    # mid within tau → ignored
    assert all(p.source_traces != ["mid"] for p in props)


def test_distill_respects_tau():
    traces = [_trace("a", 0.1, ["read"]), _trace("b", -0.1, ["bash"])]
    assert distill_group(traces, tau=0.15) == []
