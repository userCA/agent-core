"""SSE mapping for workflow progress frames."""

from __future__ import annotations

from agent_core.core.content import TextContent
from agent_core.core.events import ToolExecutionEnd, ToolExecutionUpdate
from agent_core.tools.base import ToolResult
from scene.http_sse.events import agent_event_to_sse_frames


def test_tool_update_emits_workflow_frame():
    result = ToolResult(
        content=[TextContent(text="")],
        details={
            "workflow": {
                "type": "workflow",
                "run_id": "r1",
                "name": "demo-e2e",
                "status": "running",
                "phase": "analyze",
                "phases": ["analyze", "summarize"],
                "log": ["analyzing 3 items"],
                "progress": {"completed_agents": 1, "total_agents": 3},
            }
        },
    )
    frames = agent_event_to_sse_frames(
        ToolExecutionUpdate(
            tool_name="run_workflow",
            tool_call_id="c1",
            args={},
            partial_result=result,
        )
    )
    assert any(
        f.get("event") == "workflow"
        and f.get("phase") == "analyze"
        and f.get("run_id") == "r1"
        for f in frames
    )


def test_tool_end_includes_workflow_and_tool_end():
    result = ToolResult(
        content=[TextContent(text="[workflow:demo-e2e] status=completed")],
        details={
            "workflow": {
                "type": "workflow",
                "run_id": "r1",
                "name": "demo-e2e",
                "status": "completed",
                "phase": "summarize",
            }
        },
    )
    frames = agent_event_to_sse_frames(
        ToolExecutionEnd(
            tool_name="run_workflow",
            tool_call_id="c1",
            args={},
            result=result,
            is_error=False,
        )
    )
    events = [f.get("event") for f in frames]
    assert "workflow" in events
    assert "tool_end" in events
