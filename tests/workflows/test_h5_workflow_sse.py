"""H5 SSE v1 mapping for workflow progress frames."""

from __future__ import annotations

from agent_core.core.content import TextContent
from agent_core.core.events import ToolExecutionEnd, ToolExecutionUpdate
from agent_core.tools.base import ToolResult
from scene.h5.events import agent_event_to_sse_json


def _as_list(out):
    if out is None:
        return []
    return out if isinstance(out, list) else [out]


def test_tool_update_emits_workflow_action():
    result = ToolResult(
        content=[TextContent(text="")],
        details={
            "workflow": {
                "type": "workflow",
                "run_id": "r1",
                "name": "demo-e2e",
                "status": "running",
                "phase": "analyze",
            }
        },
    )
    frames = _as_list(
        agent_event_to_sse_json(
            ToolExecutionUpdate(
                tool_name="run_workflow",
                tool_call_id="c1",
                args={},
                partial_result=result,
            )
        )
    )
    assert any(
        f.get("sse_event") == "action"
        and f["data"].get("actionType") == "workflow.update"
        and f["data"].get("phase") == "analyze"
        for f in frames
    )


def test_tool_end_includes_workflow_action():
    result = ToolResult(
        content=[TextContent(text="done")],
        details={
            "workflow": {
                "type": "workflow",
                "run_id": "r1",
                "name": "demo-e2e",
                "status": "completed",
            }
        },
    )
    frames = _as_list(
        agent_event_to_sse_json(
            ToolExecutionEnd(
                tool_name="run_workflow",
                tool_call_id="c1",
                args={},
                result=result,
                is_error=False,
            )
        )
    )
    action_types = [f["data"].get("actionType") for f in frames if f.get("sse_event") == "action"]
    assert "workflow.update" in action_types
