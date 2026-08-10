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
    ToolExecutionUpdate,
    ToolCallDelta,
)


def _delegation_from_result(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None
    details = getattr(result, "details", None)
    if not isinstance(details, dict):
        return None
    payload = details.get("delegation")
    if not isinstance(payload, dict) or payload.get("type") != "delegation":
        return None
    frame = {"event": "delegation", **payload}
    frame.pop("type", None)
    return frame


def _workflow_from_result(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None
    details = getattr(result, "details", None)
    if not isinstance(details, dict):
        return None
    payload = details.get("workflow")
    if not isinstance(payload, dict) or payload.get("type") != "workflow":
        return None
    frame = {"event": "workflow", **payload}
    frame.pop("type", None)
    return frame


def _plan_from_result(result: Any) -> dict[str, Any] | None:
    if result is None:
        return None
    details = getattr(result, "details", None)
    if not isinstance(details, dict):
        return None
    payload = details.get("plan")
    if not isinstance(payload, dict) or payload.get("type") != "plan":
        return None
    frame = {"event": "plan", **payload}
    frame.pop("type", None)
    return frame


def agent_event_to_sse_frames(evt: AgentEvent) -> list[dict[str, Any]]:
    """Convert an AgentEvent to zero or more SSE JSON frames."""
    frames: list[dict[str, Any]] = []

    if isinstance(evt, MessageUpdate):
        delta = evt.delta
        if isinstance(delta, TextDelta):
            frames.append({"event": "text_delta", "text": delta.text})
        elif isinstance(delta, ThinkingDelta):
            frames.append({"event": "thinking_delta", "text": delta.text})
        return frames

    if isinstance(evt, ToolExecutionStart):
        frames.append(
            {
                "event": "tool_start",
                "tool_name": evt.tool_name,
                "tool_call_id": evt.tool_call_id,
                "args": evt.args,
            }
        )
        return frames

    if isinstance(evt, ToolExecutionUpdate):
        deleg = _delegation_from_result(evt.partial_result)
        if deleg is not None:
            frames.append(deleg)
        plan = _plan_from_result(evt.partial_result)
        if plan is not None:
            frames.append(plan)
        workflow = _workflow_from_result(evt.partial_result)
        if workflow is not None:
            frames.append(workflow)
        text = _extract_result_text(evt.partial_result)
        if text or (deleg is None and plan is None and workflow is None):
            frames.append(
                {
                    "event": "tool_update",
                    "tool_name": evt.tool_name,
                    "result": text,
                }
            )
        return frames

    if isinstance(evt, ToolExecutionEnd):
        deleg = _delegation_from_result(evt.result)
        if deleg is not None:
            frames.append(deleg)
        plan = _plan_from_result(evt.result)
        if plan is not None:
            frames.append(plan)
        workflow = _workflow_from_result(evt.result)
        if workflow is not None:
            frames.append(workflow)
        result_dict: dict[str, Any] = {
            "event": "tool_end",
            "tool_name": evt.tool_name,
            "tool_call_id": evt.tool_call_id,
            "result": _extract_result_text(evt.result),
            "is_error": evt.is_error,
        }
        if hasattr(evt.result, "display") and evt.result.display:
            result_dict["display"] = evt.result.display
        frames.append(result_dict)
        return frames

    if isinstance(evt, HumanInputRequired):
        frames.append(
            {
                "event": "human_input_required",
                "tool_call_id": evt.tool_call_id,
                "prompt": evt.prompt,
                "input_schema": evt.input_schema,
            }
        )
        return frames

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
        frames.append({"event": "message_end", "usage": usage})
        return frames

    return frames


def agent_event_to_sse_json(evt: AgentEvent) -> dict[str, Any] | None:
    """Convert an AgentEvent to a single SSE JSON dict (backward compatible).

    Prefer non-delegation/plan frames when multiple are produced.
    """
    frames = agent_event_to_sse_frames(evt)
    if not frames:
        return None
    for frame in frames:
        if frame.get("event") not in ("delegation", "plan", "workflow"):
            return frame
    return frames[0]


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
