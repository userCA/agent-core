"""SSE mapping for delegation progress frames."""

from __future__ import annotations

from agent_core.core.content import TextContent
from agent_core.core.events import ToolExecutionEnd, ToolExecutionUpdate
from agent_core.tools.base import ToolResult
from scene.http_sse.events import agent_event_to_sse_frames


def test_tool_update_emits_delegation_frame():
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
    frames = agent_event_to_sse_frames(
        ToolExecutionUpdate(
            tool_name="delegate_task",
            tool_call_id="c1",
            args={},
            partial_result=result,
        )
    )
    assert any(f.get("event") == "delegation" and f.get("phase") == "agent_start" for f in frames)


def test_tool_end_includes_delegation_and_tool_end():
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
    frames = agent_event_to_sse_frames(
        ToolExecutionEnd(
            tool_name="delegate_task",
            tool_call_id="c1",
            result=result,
            is_error=False,
        )
    )
    events = [f["event"] for f in frames]
    assert "delegation" in events
    assert "tool_end" in events
