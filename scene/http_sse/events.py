"""AgentEvent to SSE JSON event format conversion."""

from __future__ import annotations

from typing import Any

from agent_core.core.events import (
    AgentEvent,
    HumanInputRequired,
    MessageEnd,
    MessageUpdate,
    TextDelta,
    ThinkingDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolCallDelta,
)


def agent_event_to_sse_json(evt: AgentEvent) -> dict[str, Any] | None:
    """Convert an AgentEvent to an SSE JSON dict.

    Returns None for events that should not be sent to the client.
    """
    if isinstance(evt, MessageUpdate):
        delta = evt.delta
        if isinstance(delta, TextDelta):
            return {"event": "text_delta", "text": delta.text}
        elif isinstance(delta, ThinkingDelta):
            return {"event": "thinking_delta", "text": delta.text}
        elif isinstance(delta, ToolCallDelta):
            return None
        return None

    if isinstance(evt, ToolExecutionStart):
        return {
            "event": "tool_start",
            "tool_name": evt.tool_name,
            "args": evt.args,
        }

    if isinstance(evt, ToolExecutionEnd):
        return {
            "event": "tool_end",
            "tool_name": evt.tool_name,
            "result": _extract_result_text(evt.result),
            "is_error": evt.is_error,
        }

    if isinstance(evt, HumanInputRequired):
        return {
            "event": "human_input_required",
            "tool_call_id": evt.tool_call_id,
            "prompt": evt.prompt,
            "input_schema": evt.input_schema,
        }

    if isinstance(evt, MessageEnd):
        usage = None
        msg = evt.message
        u = None
        if isinstance(msg, dict):
            u = msg.get("usage")
        elif hasattr(msg, "usage"):
            u = msg.usage
        if u:
            usage = {
                "input_tokens": getattr(u, "input_tokens", 0),
                "output_tokens": getattr(u, "output_tokens", 0),
                "total_tokens": getattr(u, "total_tokens", 0),
            }
        return {"event": "message_end", "usage": usage}

    return None


def _extract_result_text(result: Any) -> str:
    """Extract text from a ToolResult."""
    if result is None:
        return ""
    if hasattr(result, "content") and result.content:
        for item in result.content:
            if hasattr(item, "text"):
                return item.text
    if hasattr(result, "text"):
        return result.text
    return str(result)
