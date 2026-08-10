from agent_core.workflows.types import WorkflowCheckpoint


def test_checkpoint_roundtrip():
    c = WorkflowCheckpoint(
        run_id="r1",
        workflow_name="demo",
        status="running",
        completed_phases=["a"],
        phase_outputs={"a": {"ok": True}},
        args={"x": 1},
        agent_invocation_count=2,
        updated_at=1.0,
    )
    data = c.model_dump()
    assert WorkflowCheckpoint.model_validate(data).run_id == "r1"
