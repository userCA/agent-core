"""SSE mapping for plan progress frames (http_sse)."""

from __future__ import annotations

from agent_core.core.content import TextContent
from agent_core.core.events import ToolExecutionEnd, ToolExecutionUpdate
from agent_core.tools.base import ToolResult
from scene.http_sse.events import agent_event_to_sse_frames


def test_tool_update_emits_plan_frame():
    result = ToolResult(
        content=[TextContent(text="")],
        details={
            "plan": {
                "type": "plan",
                "phase": "replaced",
                "plan": {
                    "id": "p1",
                    "title": "Demo",
                    "status": "active",
                    "steps": [{"id": "s1", "title": "A", "status": "pending"}],
                    "version": 1,
                },
                "done": 0,
                "total": 1,
            }
        },
    )
    frames = agent_event_to_sse_frames(
        ToolExecutionUpdate(
            tool_name="manage_plan",
            tool_call_id="c1",
            args={},
            partial_result=result,
        )
    )
    assert any(
        f.get("event") == "plan" and f.get("phase") == "replaced" and f.get("plan", {}).get("id") == "p1"
        for f in frames
    )


def test_tool_end_includes_plan_and_tool_end():
    result = ToolResult(
        content=[TextContent(text="plan=Demo")],
        details={
            "plan": {
                "type": "plan",
                "phase": "completed",
                "plan": {
                    "id": "p1",
                    "title": "Demo",
                    "status": "completed",
                    "steps": [{"id": "s1", "title": "A", "status": "completed"}],
                    "version": 2,
                },
                "done": 1,
                "total": 1,
            }
        },
    )
    frames = agent_event_to_sse_frames(
        ToolExecutionEnd(
            tool_name="manage_plan",
            tool_call_id="c1",
            result=result,
            is_error=False,
        )
    )
    events = [f["event"] for f in frames]
    assert "plan" in events
    assert "tool_end" in events
    plan_frame = next(f for f in frames if f["event"] == "plan")
    assert plan_frame["phase"] == "completed"
    assert "type" not in plan_frame
