"""Tests for skill evolution type definitions."""

import pytest
from agent_core.skill_evolution.types import (
    ExecutionOutcome,
    SkillEvolutionTrace,
    PatchProposal,
    MergedProposal,
    ValidationResult,
)


class TestExecutionOutcome:
    """Test ExecutionOutcome enum."""

    def test_outcome_values(self):
        assert ExecutionOutcome.SUCCESS == "success"
        assert ExecutionOutcome.PARTIAL == "partial"
        assert ExecutionOutcome.FAILURE == "failure"
        assert ExecutionOutcome.REGRESSION == "regression"


class TestSkillEvolutionTrace:
    """Test SkillEvolutionTrace dataclass."""

    def test_create_trace(self):
        trace = SkillEvolutionTrace(
            trace_id="test-123",
            user_query="How do I fix this bug?",
            skill_name="dev-process-backend",
            loaded_rules=["rule_1", "rule_2"],
        )
        
        assert trace.trace_id == "test-123"
        assert trace.user_query == "How do I fix this bug?"
        assert trace.skill_name == "dev-process-backend"
        assert trace.loaded_rules == ["rule_1", "rule_2"]
        assert trace.execution_outcome == ExecutionOutcome.SUCCESS  # default

    def test_mark_success(self):
        trace = SkillEvolutionTrace(trace_id="t1")
        trace.mark_success(details={"key": "value"})
        
        assert trace.execution_outcome == ExecutionOutcome.SUCCESS
        assert trace.execution_details["key"] == "value"

    def test_mark_failure(self):
        trace = SkillEvolutionTrace(trace_id="t1")
        trace.mark_failure(error="Something went wrong", details={"code": 500})
        
        assert trace.execution_outcome == ExecutionOutcome.FAILURE
        assert trace.execution_details["error"] == "Something went wrong"
        assert trace.execution_details["code"] == 500

    def test_mark_regression(self):
        trace = SkillEvolutionTrace(trace_id="t1")
        trace.mark_regression(
            affected_rule="rule_14",
            details={"description": "Rule no longer matches"}
        )
        
        assert trace.execution_outcome == ExecutionOutcome.REGRESSION
        assert trace.regression_info["affected_rule"] == "rule_14"


class TestPatchProposal:
    """Test PatchProposal dataclass."""

    def test_create_proposal(self):
        proposal = PatchProposal(
            proposal_id="prop-1",
            source_traces=["trace-1", "trace-2"],
            skill_name="dev-process-backend",
            operation="add",
            new_content="New rule content",
            rationale="This fixes a common bug",
            confidence=0.8,
        )
        
        assert proposal.proposal_id == "prop-1"
        assert len(proposal.source_traces) == 2
        assert proposal.operation == "add"
        assert proposal.confidence == 0.8

    def test_to_dict(self):
        proposal = PatchProposal(
            proposal_id="p1",
            source_traces=["t1"],
            skill_name="test-skill",
            operation="modify",
            target_rule_id="rule_1",
            new_content="Updated content",
        )
        
        d = proposal.to_dict()
        assert d["proposal_id"] == "p1"
        assert d["operation"] == "modify"
        assert d["new_content"] == "Updated content"


class TestMergedProposal:
    """Test MergedProposal dataclass."""

    def test_empty_merge(self):
        merged = MergedProposal()
        assert len(merged.merged_proposals) == 0
        assert len(merged.conflicts) == 0
        assert len(merged.discarded) == 0

    def test_with_proposals(self):
        prop1 = PatchProposal(
            proposal_id="p1",
            source_traces=["t1"],
            skill_name="skill1",
            operation="add",
            confidence=0.9,
        )
        prop2 = PatchProposal(
            proposal_id="p2",
            source_traces=["t2"],
            skill_name="skill1",
            operation="modify",
            confidence=0.7,
        )
        
        merged = MergedProposal(
            merged_proposals=[prop1],
            conflicts=[(prop1, prop2, "Conflicting operations")],
            discarded=[prop2],
            merge_rationale="Test merge",
        )
        
        assert len(merged.merged_proposals) == 1
        assert len(merged.conflicts) == 1
        assert len(merged.discarded) == 1


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_accept_recommendation(self):
        result = ValidationResult(
            proposal_id="p1",
            score_delta=0.15,  # 15% improvement
            passed=True,
            test_results=[("test1", True, "✓ test1: 0.5 → 0.8")],
        )
        
        assert result.recommendation == "accept"
        assert result.passed is True

    def test_reject_recommendation(self):
        result = ValidationResult(
            proposal_id="p1",
            score_delta=-0.10,  # 10% degradation
            passed=False,
            test_results=[("test1", False, "✗ test1: 0.8 → 0.6")],
            failed_cases=["test1"],
        )
        
        assert result.recommendation == "reject"

    def test_needs_review_recommendation(self):
        result = ValidationResult(
            proposal_id="p1",
            score_delta=0.02,  # Small improvement, below threshold
            passed=False,
            test_results=[("test1", True, "✓ test1: 0.5 → 0.52")],
        )
        
        assert result.recommendation == "needs_review"
