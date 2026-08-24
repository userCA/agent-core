"""Tests for skill evolution store implementations."""

import asyncio
import pytest
import tempfile
from pathlib import Path

from agent_core.skill_evolution.store import (
    InMemorySkillEvolutionStore,
    JsonlSkillEvolutionStore,
    create_skill_evolution_store,
)
from agent_core.skill_evolution.types import (
    SkillEvolutionTrace,
    ExecutionOutcome,
    PathStep,
)


class TestInMemorySkillEvolutionStore:
    """Test in-memory store implementation."""

    @pytest.fixture
    def store(self):
        return InMemorySkillEvolutionStore()

    @pytest.fixture
    def sample_trace(self):
        return SkillEvolutionTrace(
            trace_id="trace-1",
            user_query="Test query",
            skill_name="dev-process-backend",
            loaded_rules=["rule_1", "rule_2"],
            execution_outcome=ExecutionOutcome.SUCCESS,
        )

    async def test_save_and_retrieve(self, store, sample_trace):
        await store.save_trace(sample_trace)
        
        traces = await store.get_traces()
        assert len(traces) == 1
        assert traces[0].trace_id == "trace-1"

    async def test_filter_by_skill(self, store):
        trace1 = SkillEvolutionTrace(
            trace_id="t1",
            skill_name="skill-a",
            execution_outcome=ExecutionOutcome.SUCCESS,
        )
        trace2 = SkillEvolutionTrace(
            trace_id="t2",
            skill_name="skill-b",
            execution_outcome=ExecutionOutcome.SUCCESS,
        )
        
        await store.save_trace(trace1)
        await store.save_trace(trace2)
        
        # Filter by skill-a
        traces_a = await store.get_traces(skill_name="skill-a")
        assert len(traces_a) == 1
        assert traces_a[0].trace_id == "t1"

    async def test_filter_by_outcome(self, store):
        trace1 = SkillEvolutionTrace(
            trace_id="t1",
            execution_outcome=ExecutionOutcome.SUCCESS,
        )
        trace2 = SkillEvolutionTrace(
            trace_id="t2",
            execution_outcome=ExecutionOutcome.FAILURE,
        )
        
        await store.save_trace(trace1)
        await store.save_trace(trace2)
        
        # Filter by failure
        failures = await store.get_traces(outcome="failure")
        assert len(failures) == 1
        assert failures[0].execution_outcome == ExecutionOutcome.FAILURE

    async def test_get_traces_merges_feedback_overlay(self, store):
        main = SkillEvolutionTrace(
            trace_id="t1",
            skill_name="demo",
            user_query="q",
            run_id="run-1",
        )
        await store.save_trace(main)
        overlay = SkillEvolutionTrace(
            trace_id="t1-feedback",
            skill_name="",
            run_id="run-1",
            user_feedback="thumbs down",
            human_signal={"vote": "dislike"},
            execution_details={"type": "feedback", "original_run_id": "run-1"},
        )
        await store.save_trace(overlay)
        traces = await store.get_traces(skill_name="demo")
        assert len(traces) == 1
        assert traces[0].human_signal == {"vote": "dislike"}
        assert traces[0].user_feedback == "thumbs down"

    async def test_pagination(self, store):
        # Create 5 traces
        for i in range(5):
            await store.save_trace(SkillEvolutionTrace(
                trace_id=f"t{i}",
                timestamp=float(i),  # Use timestamp for ordering
            ))
        
        # Get first page
        page1 = await store.get_traces(limit=2, offset=0)
        assert len(page1) == 2
        
        # Get second page
        page2 = await store.get_traces(limit=2, offset=2)
        assert len(page2) == 2

    async def test_count(self, store):
        for i in range(3):
            await store.save_trace(SkillEvolutionTrace(trace_id=f"t{i}"))
        
        count = await store.get_trace_count()
        assert count == 3

    async def test_delete_old_traces(self, store):
        import time
        
        # Create old trace
        old_trace = SkillEvolutionTrace(
            trace_id="old",
            timestamp=time.time() - (40 * 86400),  # 40 days ago
        )
        await store.save_trace(old_trace)
        
        # Create recent trace
        new_trace = SkillEvolutionTrace(
            trace_id="new",
            timestamp=time.time(),
        )
        await store.save_trace(new_trace)
        
        # Delete traces older than 30 days
        deleted = await store.delete_old_traces(older_than_days=30)
        assert deleted == 1
        
        # Verify only recent trace remains
        traces = await store.get_traces()
        assert len(traces) == 1
        assert traces[0].trace_id == "new"


class TestJsonlSkillEvolutionStore:
    """Test JSONL-based persistent store."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def store(self, temp_dir):
        path = Path(temp_dir) / "traces.jsonl"
        return JsonlSkillEvolutionStore(str(path))

    async def test_save_creates_file(self, store, temp_dir):
        trace = SkillEvolutionTrace(
            trace_id="t1",
            skill_name="test-skill",
        )
        await store.save_trace(trace)
        
        # Check file was created
        storage_path = Path(temp_dir) / "traces.jsonl"
        assert storage_path.exists()
        
        # Check content
        content = storage_path.read_text()
        assert "t1" in content
        assert "test-skill" in content

    async def test_persistence_across_instances(self, temp_dir):
        path = Path(temp_dir) / "traces.jsonl"
        
        # First instance saves trace
        store1 = JsonlSkillEvolutionStore(str(path))
        await store1.save_trace(SkillEvolutionTrace(
            trace_id="persistent-trace",
            skill_name="test",
        ))
        
        # Second instance reads it back
        store2 = JsonlSkillEvolutionStore(str(path))
        traces = await store2.get_traces()
        assert len(traces) == 1
        assert traces[0].trace_id == "persistent-trace"

    async def test_filter_and_count(self, store):
        # Save mixed traces
        await store.save_trace(SkillEvolutionTrace(
            trace_id="t1",
            skill_name="skill-a",
            execution_outcome=ExecutionOutcome.SUCCESS,
        ))
        await store.save_trace(SkillEvolutionTrace(
            trace_id="t2",
            skill_name="skill-b",
            execution_outcome=ExecutionOutcome.FAILURE,
        ))
        
        # Test filtering - need to use .value for enum comparison
        skill_a = await store.get_traces(skill_name="skill-a")
        assert len(skill_a) == 1
        
        failures = await store.get_traces(outcome="failure")
        assert len(failures) == 1
        
        # Test counting
        total = await store.get_trace_count()
        assert total == 2
        
        skill_b_count = await store.get_trace_count(skill_name="skill-b")
        assert skill_b_count == 1

    async def test_analyzed_trace_cursor(self, store):
        await store.mark_traces_analyzed("skill-a", ["t1", "t2"])
        ids = await store.get_analyzed_trace_ids("skill-a")
        assert ids == {"t1", "t2"}
        await store.mark_traces_analyzed("skill-a", ["t3"])
        ids = await store.get_analyzed_trace_ids("skill-a")
        assert ids == {"t1", "t2", "t3"}


class TestCreateSkillEvolutionStore:
    """Test factory function."""

    def test_create_memory_store(self):
        store = create_skill_evolution_store("memory")
        assert isinstance(store, InMemorySkillEvolutionStore)

    def test_create_jsonl_store(self, tmp_path):
        path = str(tmp_path / "traces.jsonl")
        store = create_skill_evolution_store("jsonl", storage_path=path)
        assert isinstance(store, JsonlSkillEvolutionStore)

    def test_invalid_store_type(self):
        with pytest.raises(ValueError, match="Unknown store type"):
            create_skill_evolution_store("invalid")


class TestJsonlPathFieldsRoundtrip:
    async def test_jsonl_roundtrip_path_fields(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        store = JsonlSkillEvolutionStore(path)
        await store.save_trace(SkillEvolutionTrace(
            trace_id="rt1",
            skill_name="s",
            steps=[PathStep(
                tool_name="grep",
                args_summary="foo",
                is_error=True,
                error_summary="boom",
            )],
            group_id="g",
            task_key="tk",
            reward=0.5,
            advantage=-0.1,
            human_signal={"vote": "dislike"},
            execution_outcome=ExecutionOutcome.FAILURE,
        ))
        traces = await store.get_traces(skill_name="s")
        assert len(traces) == 1
        t = traces[0]
        assert t.steps[0].tool_name == "grep"
        assert t.steps[0].is_error is True
        assert t.steps[0].error_summary == "boom"
        assert t.group_id == "g"
        assert t.task_key == "tk"
        assert t.reward == 0.5
        assert t.advantage == -0.1
        assert t.human_signal["vote"] == "dislike"
        assert t.execution_outcome == ExecutionOutcome.FAILURE

    async def test_jsonl_legacy_row_without_steps(self, tmp_path):
        path = tmp_path / "legacy.jsonl"
        path.write_text(
            '{"trace_id":"old1","timestamp":1.0,"skill_name":"s",'
            '"execution_outcome":"success","loaded_rules":[],'
            '"execution_details":{},"new_rules_discovered":[]}\n',
            encoding="utf-8",
        )
        store = JsonlSkillEvolutionStore(path)
        traces = await store.get_traces(skill_name="s")
        assert len(traces) == 1
        assert traces[0].steps == []
        assert traces[0].group_id is None
        assert traces[0].execution_outcome == ExecutionOutcome.SUCCESS
