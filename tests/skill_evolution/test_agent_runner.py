"""Tests for ValidationHarnessRunner and test suite builders."""

from __future__ import annotations

import pytest

from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.skill_evolution.agent_runner import (
    ValidationHarnessRunner,
    score_agent_run,
    text_overlap,
)
from agent_core.skill_evolution.store import InMemorySkillEvolutionStore
from agent_core.skill_evolution.test_suite import (
    build_test_cases_from_trace_ids,
    build_test_cases_from_traces,
)
from agent_core.skill_evolution.types import ExecutionOutcome, SkillEvolutionTrace, TestCase
from tests.conftest import FakeProvider, fake_model


def test_text_overlap_chinese():
    assert text_overlap("生成视频", "请生成一个视频") > 0.2


@pytest.mark.asyncio
async def test_validation_harness_runner_success():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="Done following skill rules."),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=3),
    ])
    runner = ValidationHarnessRunner(
        skill_name="demo-skill",
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        model=fake_model(),
        max_turns=1,
        timeout_sec=10.0,
    )
    content = "---\nname: demo-skill\n---\n\n## 规则 1：Always be concise\n"
    result = await runner.run(content, "help me")
    assert result.success is True
    assert result.score == 1.0
    assert "Done" in result.response_text


@pytest.mark.asyncio
async def test_validation_gate_uses_agent_runner():
    from agent_core.skill_evolution.validation import SkillValidationGate

    calls: list[tuple[str, str]] = []

    async def fake_runner(skill_content: str, input_query: str) -> dict:
        calls.append((skill_content, input_query))
        improved = "Important new rule" in skill_content
        return {"success": improved, "score": 1.0 if improved else 0.0, "response_text": ""}

    gate = SkillValidationGate(
        skill_dir="/tmp/unused",
        test_threshold=0.05,
        agent_runner=fake_runner,
    )

    old = "---\nname: t\n---\n\n## 规则 1：Old\n"
    new = old + "\n\n## 新增规则：Important new rule\n"

    async def load(_name: str):
        return old

    gate._load_skill_content = load  # type: ignore[method-assign]

    proposal = __import__(
        "agent_core.skill_evolution.types", fromlist=["PatchProposal"]
    ).PatchProposal(
        proposal_id="p1",
        source_traces=["t1"],
        skill_name="t",
        operation="add",
        new_content="Important new rule",
    )
    cases = [
        TestCase(
            test_id="tc1",
            description="d",
            input_query="test query",
            expected_behavior="works",
            success_criteria="no_error",
        )
    ]
    result = await gate.validate(proposal, cases)
    assert len(calls) == 2
    assert result.score_delta > 0
    assert result.recommendation == "accept"


@pytest.mark.asyncio
async def test_build_test_cases_from_traces():
    traces = [
        SkillEvolutionTrace(
            trace_id="abc-123",
            skill_name="demo",
            user_query="生成视频",
            execution_outcome=ExecutionOutcome.FAILURE,
            execution_details={"error": "tool not found"},
        ),
    ]
    cases = build_test_cases_from_traces(traces)
    assert len(cases) == 1
    assert cases[0].input_query == "生成视频"


@pytest.mark.asyncio
async def test_build_test_cases_from_trace_ids():
    store = InMemorySkillEvolutionStore()
    await store.save_trace(
        SkillEvolutionTrace(
            trace_id="trace-001",
            skill_name="demo",
            user_query="fix bug",
            execution_outcome=ExecutionOutcome.SUCCESS,
        )
    )
    cases = await build_test_cases_from_trace_ids(store, ["trace-001"], skill_name="demo")
    assert len(cases) == 1
    assert cases[0].test_id == "trace-001"


def test_score_agent_run_with_callable_criteria():
    tc = TestCase(
        test_id="1",
        description="d",
        input_query="q",
        expected_behavior="x",
        success_criteria=lambda r: r.get("response_text") == "ok",
    )
    assert score_agent_run({"success": True, "response_text": "ok"}, tc) == 1.0
    assert score_agent_run({"success": True, "response_text": "no"}, tc) == 0.0
