"""H5 SSE v1 mapping for plan progress frames."""

from __future__ import annotations

from agent_core.core.content import TextContent
from agent_core.core.events import ToolExecutionEnd, ToolExecutionUpdate
from agent_core.tools.base import ToolResult
from scene.h5.events import agent_event_to_sse_json


def _as_list(out):
    if out is None:
        return []
    return out if isinstance(out, list) else [out]


def test_tool_update_emits_plan_action():
    result = ToolResult(
        content=[TextContent(text="")],
        details={
            "plan": {
                "type": "plan",
                "phase": "updated",
                "plan": {
                    "id": "p1",
                    "title": "Demo",
                    "status": "active",
                    "steps": [{"id": "s1", "title": "A", "status": "in_progress"}],
                    "version": 2,
                },
                "done": 0,
                "total": 1,
            }
        },
    )
    frames = _as_list(
        agent_event_to_sse_json(
            ToolExecutionUpdate(
                tool_name="manage_plan",
                tool_call_id="c1",
                args={},
                partial_result=result,
            )
        )
    )
    assert any(
        f.get("sse_event") == "action"
        and f["data"].get("actionType") == "plan.update"
        and f["data"].get("phase") == "updated"
        and f["data"].get("plan", {}).get("id") == "p1"
        for f in frames
    )


def test_tool_end_includes_plan_and_tool_completed():
    result = ToolResult(
        content=[TextContent(text="done")],
        details={
            "plan": {
                "type": "plan",
                "phase": "completed",
                "plan": {
                    "id": "p1",
                    "title": "Demo",
                    "status": "completed",
                    "steps": [{"id": "s1", "title": "A", "status": "completed"}],
                    "version": 3,
                },
                "done": 1,
                "total": 1,
            }
        },
    )
    frames = _as_list(
        agent_event_to_sse_json(
            ToolExecutionEnd(
                tool_name="manage_plan",
                tool_call_id="c1",
                result=result,
                is_error=False,
            )
        )
    )
    action_types = [f["data"].get("actionType") for f in frames if f.get("sse_event") == "action"]
    assert "plan.update" in action_types
    assert "tool_call.completed" in action_types
    plan_data = next(f["data"] for f in frames if f["data"].get("actionType") == "plan.update")
    assert plan_data["phase"] == "completed"
    assert "type" not in plan_data
