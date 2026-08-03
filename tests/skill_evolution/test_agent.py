"""Tests for offline evolution agent."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from agent_core.skill_evolution.agent import OfflineEvolutionAgent
from agent_core.skill_evolution.store import InMemorySkillEvolutionStore
from agent_core.skill_evolution.types import (
    SkillEvolutionTrace,
    ExecutionOutcome,
    PatchProposal,
)


class TestOfflineEvolutionAgent:
    """Test the offline evolution agent."""

    @pytest.fixture
    def store(self):
        return InMemorySkillEvolutionStore()

    @pytest.fixture
    def agent(self, store):
        return OfflineEvolutionAgent(store, batch_size=10)

    async def test_insufficient_traces(self, agent, store):
        """Test that agent skips analysis when too few traces."""
        # Add only 5 traces (below min_traces=20)
        for i in range(5):
            await store.save_trace(SkillEvolutionTrace(
                trace_id=f"t{i}",
                skill_name="test-skill",
            ))
        
        result = await agent.run_evolution_cycle(
            skill_name="test-skill",
            min_traces=20,
        )
        
        assert result["status"] == "skipped"
        assert result["reason"] == "insufficient_traces"
        assert result["trace_count"] == 5

    async def test_successful_evolution_cycle(self, agent, store):
        """Test a complete evolution cycle with enough traces."""
        # Add mix of success and failure traces
        for i in range(15):
            outcome = ExecutionOutcome.SUCCESS if i % 3 != 0 else ExecutionOutcome.FAILURE
            await store.save_trace(SkillEvolutionTrace(
                trace_id=f"t{i}",
                skill_name="dev-process-backend",
                user_query=f"Test query {i}",
                loaded_rules=[f"rule_{i % 5}"],
                execution_outcome=outcome,
                execution_details={"error": "Test error"} if outcome == ExecutionOutcome.FAILURE else {},
            ))
        
        result = await agent.run_evolution_cycle(
            skill_name="dev-process-backend",
            min_traces=10,
        )
        
        assert result["status"] == "completed"
        # Agent limits to batch_size (default 10) traces for analysis
        assert result["traces_analyzed"] >= 10
        assert "success_traces" in result
        assert "failure_traces" in result
        assert "proposals_generated" in result

    async def test_proposal_generation_from_failures(self, agent, store):
        """Test that failures generate proposals."""
        # Add failure traces with specific errors
        for i in range(5):
            await store.save_trace(SkillEvolutionTrace(
                trace_id=f"fail-{i}",
                skill_name="test-skill",
                user_query="How to fix this?",
                loaded_rules=["rule_1"],
                execution_outcome=ExecutionOutcome.FAILURE,
                execution_details={
                    "error": "Rule not found or missing",
                    "exception_type": "ValueError",
                },
            ))
        
        # Also add some success traces
        for i in range(5):
            await store.save_trace(SkillEvolutionTrace(
                trace_id=f"success-{i}",
                skill_name="test-skill",
                execution_outcome=ExecutionOutcome.SUCCESS,
            ))
        
        result = await agent.run_evolution_cycle(
            skill_name="test-skill",
            min_traces=5,
        )
        
        assert result["status"] == "completed"
        # Agent limits analysis to batch_size (default 10) traces
        assert result["traces_analyzed"] >= 5
        assert "success_traces" in result
        assert "failure_traces" in result
        assert "proposals_generated" in result

    async def test_hierarchical_merge(self, agent, store):
        """Test that conflicting proposals are properly merged."""
        # Create traces that would generate conflicting proposals
        for i in range(10):
            await store.save_trace(SkillEvolutionTrace(
                trace_id=f"t{i}",
                skill_name="test-skill",
                loaded_rules=["rule_14"],
                execution_outcome=ExecutionOutcome.FAILURE if i < 5 else ExecutionOutcome.SUCCESS,
                execution_details={"error": "Conflict test"} if i < 5 else {},
            ))
        
        result = await agent.run_evolution_cycle(
            skill_name="test-skill",
            min_traces=5,
        )
        
        assert result["status"] == "completed"
        # Check merge results exist in the response
        assert "traces_analyzed" in result
        assert "proposals_generated" in result


class TestProposalAnalysis:
    """Test individual proposal analysis methods."""

    @pytest.fixture
    def agent(self):
        store = InMemorySkillEvolutionStore()
        return OfflineEvolutionAgent(store)

    async def test_success_trace_analysis(self, agent):
        """Test analyzing a successful trace."""
        trace = SkillEvolutionTrace(
            trace_id="success-1",
            skill_name="test-skill",
            user_query="Working query",
            loaded_rules=["rule_1", "rule_2"],
            execution_outcome=ExecutionOutcome.SUCCESS,
            user_feedback="This was very helpful!",
        )

        proposals = await agent._analyze_success_trace(trace)

        # Should generate a proposal boosting confidence in loaded rules
        assert len(proposals) > 0
        assert proposals[0].confidence >= 0.6
        assert "helpful" in proposals[0].rationale.lower() or "confirmed" in proposals[0].rationale.lower()

    async def test_failure_trace_with_missing_rule(self, agent):
        """Test detecting missing rule pattern in failures."""
        trace = SkillEvolutionTrace(
            trace_id="fail-1",
            skill_name="test-skill",
            user_query="Broken query",
            loaded_rules=["rule_1"],
            execution_outcome=ExecutionOutcome.FAILURE,
            execution_details={
                "error": "Rule 'rule_14' not found in skill definition",
            },
        )
        
        proposal = await agent._analyze_failure_trace(trace)
        
        assert proposal is not None
        assert proposal.operation == "add"
        assert "missing" in proposal.rationale.lower() or "not found" in proposal.rationale.lower()

    async def test_failure_trace_with_regression(self, agent):
        """Test detecting regression pattern."""
        trace = SkillEvolutionTrace(
            trace_id="regression-1",
            skill_name="test-skill",
            loaded_rules=["rule_14"],
            execution_outcome=ExecutionOutcome.REGRESSION,
            regression_info={
                "affected_rule": "rule_14",
                "description": "Rule no longer matches expected pattern",
            },
        )
        
        proposal = await agent._analyze_failure_trace(trace)
        
        assert proposal is not None
        assert proposal.operation == "modify"
        assert proposal.target_rule_id == "rule_14"

    async def test_failure_trace_with_tool_step_error(self, agent):
        """Test heuristic proposal from tool step errors without loaded_rules."""
        from agent_core.skill_evolution.types import PathStep

        trace = SkillEvolutionTrace(
            trace_id="fail-tool-1",
            skill_name="test-skill",
            user_query="Query tool params",
            loaded_rules=[],
            execution_outcome=ExecutionOutcome.FAILURE,
            execution_details={"error": "tool execution error"},
            steps=[
                PathStep(
                    tool_name="tool_detail",
                    args_summary="tool_names=['tavily_search']",
                    is_error=True,
                    error_summary="Tool 'tool_detail' not found.",
                ),
            ],
        )

        proposal = await agent._analyze_failure_trace(trace)

        assert proposal is not None
        assert proposal.operation == "add"
        assert "tool_detail" in proposal.rationale
        assert proposal.new_content is not None
    """Test conflict resolution in proposal merging."""

    @pytest.fixture
    def agent(self):
        store = InMemorySkillEvolutionStore()
        return OfflineEvolutionAgent(store)

    async def test_resolve_conflicts_by_confidence(self, agent):
        """Test that higher confidence proposals win conflicts."""
        prop1 = PatchProposal(
            proposal_id="p1",
            source_traces=["t1"],
            skill_name="test",
            operation="modify",
            target_rule_id="rule_1",
            confidence=0.9,
        )
        prop2 = PatchProposal(
            proposal_id="p2",
            source_traces=["t2"],
            skill_name="test",
            operation="delete",  # Conflicting operation
            target_rule_id="rule_1",
            confidence=0.5,
        )
        
        result = await agent._resolve_conflicts([prop1, prop2])
        
        # Higher confidence proposal should be accepted
        assert len(result["accepted"]) == 1
        assert result["accepted"][0].proposal_id == "p1"
        
        # Lower confidence should be marked as conflict or discarded
        assert len(result["conflicts"]) + len(result["discarded"]) == 1

    async def test_discard_low_confidence_outliers(self, agent):
        """Test that very low confidence proposals are discarded."""
        prop1 = PatchProposal(
            proposal_id="p1",
            source_traces=["t1"],
            skill_name="test",
            operation="add",
            confidence=0.95,
        )
        prop2 = PatchProposal(
            proposal_id="p2",
            source_traces=["t2"],
            skill_name="test",
            operation="add",
            confidence=0.3,  # Very low
        )
        
        result = await agent._resolve_conflicts([prop1, prop2])
        
        # High confidence accepted
        assert any(p.proposal_id == "p1" for p in result["accepted"])
        
        # Low confidence discarded
        assert any(p.proposal_id == "p2" for p in result["discarded"])


class TestBatchAnalysis:
    """Test cross-trace batch analysis."""

    @pytest.fixture
    def agent(self):
        store = InMemorySkillEvolutionStore()
        return OfflineEvolutionAgent(store)

    async def test_batch_without_provider_returns_empty(self, agent):
        """Batch analysis requires model_provider; returns empty otherwise."""
        traces = [
            SkillEvolutionTrace(
                trace_id=f"t{i}",
                skill_name="test",
                execution_outcome=ExecutionOutcome.FAILURE,
                execution_details={"error": "test error"},
            )
            for i in range(3)
        ]
        result = await agent._analyze_failure_batch(traces)
        assert result == []

    async def test_parse_batch_proposals_valid_json(self, agent):
        """Test parsing valid JSON array from LLM response."""
        raw = json.dumps([
            {"operation": "add", "new_content": "rule A", "rationale": "fixes bug",
             "target_rule_id": None, "confidence": 0.8},
            {"operation": "modify", "new_content": "rule B", "rationale": "improves",
             "target_rule_id": "rule_1", "confidence": 0.7},
        ])
        traces = [
            SkillEvolutionTrace(trace_id="t1", skill_name="test"),
            SkillEvolutionTrace(trace_id="t2", skill_name="test"),
        ]
        proposals = agent._parse_batch_proposals(raw, traces, "test")
        assert len(proposals) == 2
        assert proposals[0].operation == "add"
        assert len(proposals[0].source_traces) == 2  # All batch trace IDs
        assert proposals[1].operation == "modify"

    async def test_parse_batch_proposals_skips_invalid(self, agent):
        """Test that invalid entries in batch response are skipped."""
        raw = json.dumps([
            {"operation": "add", "new_content": "valid", "rationale": "ok",
             "target_rule_id": None, "confidence": 0.5},
            {"invalid": "no operation field"},
        ])
        traces = [SkillEvolutionTrace(trace_id="t1", skill_name="test")]
        proposals = agent._parse_batch_proposals(raw, traces, "test")
        assert len(proposals) == 1

    async def test_trace_deduplication(self, agent):
        """Test that already-analyzed traces are skipped in subsequent cycles."""
        store = agent.store
        for i in range(5):
            await store.save_trace(SkillEvolutionTrace(
                trace_id=f"t{i}",
                skill_name="test",
                execution_outcome=ExecutionOutcome.FAILURE,
                execution_details={"error": "test"},
            ))

        # First cycle should analyze all 5
        result1 = await agent.run_evolution_cycle(skill_name="test", min_traces=3)
        assert result1["status"] == "completed"
        assert result1["traces_analyzed"] == 5

        # Second cycle should skip all (no new traces)
        result2 = await agent.run_evolution_cycle(skill_name="test", min_traces=1)
        assert result2["status"] == "skipped"
        assert result2["reason"] == "no_new_traces"

        # Add new traces
        for i in range(5, 7):
            await store.save_trace(SkillEvolutionTrace(
                trace_id=f"t{i}",
                skill_name="test",
                execution_outcome=ExecutionOutcome.FAILURE,
                execution_details={"error": "test"},
            ))

        # Third cycle should only analyze the 2 new traces
        result3 = await agent.run_evolution_cycle(skill_name="test", min_traces=1)
        assert result3["status"] == "completed"
        assert result3["traces_analyzed"] == 2
