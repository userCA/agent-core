"""H5 SSE v1 mapping for delegation progress frames."""

from __future__ import annotations

from agent_core.core.content import TextContent
from agent_core.core.events import ToolExecutionEnd, ToolExecutionUpdate
from agent_core.tools.base import ToolResult
from scene.h5.events import agent_event_to_sse_json


def _as_list(out):
    if out is None:
        return []
    return out if isinstance(out, list) else [out]


def test_tool_update_emits_delegation_action():
    result = ToolResult(
        content=[TextContent(text="")],
        details={
            "delegation": {
                "type": "delegation",
                "phase": "agent_start",
                "mode": "single",
                "delegation_id": "d1",
                "agent": "billing",
                "status": "running",
            }
        },
    )
    frames = _as_list(
        agent_event_to_sse_json(
            ToolExecutionUpdate(
                tool_name="delegate_task",
                tool_call_id="c1",
                args={},
                partial_result=result,
            )
        )
    )
    assert any(
        f.get("sse_event") == "action"
        and f["data"].get("actionType") == "delegation.update"
        and f["data"].get("phase") == "agent_start"
        for f in frames
    )


def test_tool_end_includes_delegation_and_tool_completed():
    result = ToolResult(
        content=[TextContent(text="done")],
        details={
            "delegation": {
                "type": "delegation",
                "phase": "end",
                "mode": "single",
                "delegation_id": "d1",
                "status": "completed",
            }
        },
    )
    frames = _as_list(
        agent_event_to_sse_json(
            ToolExecutionEnd(
                tool_name="delegate_task",
                tool_call_id="c1",
                result=result,
                is_error=False,
            )
        )
    )
    action_types = [f["data"].get("actionType") for f in frames if f.get("sse_event") == "action"]
    assert "delegation.update" in action_types
    assert "tool_call.completed" in action_types
