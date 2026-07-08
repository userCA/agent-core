"""AgentEvent to SSE v1 format conversion.

Returns ``{"sse_event": <channel>, "data": <dict>}`` dicts.
The *sse_event* value maps to the SSE ``event:`` channel field
(heart / message / content / action / state / companion).
"""

from __future__ import annotations

import time
from typing import Any

from agent_core.core.events import (
    AgentEvent,
    HumanInputRequired,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    TextDelta,
    ThinkingDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
    ToolCallDelta,
)


class _ContentTracker:
    """Track content-block lifecycle (start → delta×N → done)."""

    def __init__(self) -> None:
        self._counter = 0
        self._open_type: str | None = None
        self._open_id: str | None = None
        self._open_index: int = -1

    # -- helpers ---------------------------------------------------------------

    def _next_id(self) -> str:
        self._counter += 1
        return f"ct_{self._counter}"

    def open(self, block_type: str) -> dict[str, Any] | list[dict[str, Any]]:
        """Emit *phase=done* (if previous block open) + *phase=start* for a new block."""
        close_evt = self.close()  # close previous block if any
        self._open_id = self._next_id()
        self._open_index = self._counter - 1
        self._open_type = block_type
        start_evt: dict[str, Any] = {
            "sse_event": "content",
            "data": {
                "type": block_type,
                "contentId": self._open_id,
                "index": self._open_index,
                "phase": "start",
                "content": "",
            },
        }
        if close_evt is not None:
            return [close_evt, start_evt]
        return start_evt

    def close(self) -> dict[str, Any] | None:
        """Emit a *phase=done* event for the current open block (if any)."""
        if self._open_type is None:
            return None
        result = {
            "sse_event": "content",
            "data": {
                "type": self._open_type,
                "contentId": self._open_id,
                "index": self._open_index,
                "phase": "done",
                "content": "",
            },
        }
        self._open_type = None
        self._open_id = None
        return result

    def delta(self, block_type: str, text: str) -> dict[str, Any] | list[dict[str, Any]]:
        """Emit a *phase=delta* event, auto-opening a block if needed.

        When the block type changes, the returned value is a list that
        includes the ``close → start → delta`` sequence so that the
        content-block lifecycle is fully preserved.
        """
        if self._open_type != block_type:
            open_result = self.open(block_type)
            delta_evt: dict[str, Any] = {
                "sse_event": "content",
                "data": {
                    "type": block_type,
                    "contentId": self._open_id,
                    "index": self._open_index,
                    "phase": "delta",
                    "content": text,
                },
            }
            if isinstance(open_result, list):
                return [*open_result, delta_evt]
            return [open_result, delta_evt]
        return {
            "sse_event": "content",
            "data": {
                "type": block_type,
                "contentId": self._open_id,
                "index": self._open_index,
                "phase": "delta",
                "content": text,
            },
        }


def create_tracker() -> _ContentTracker:
    """Create an independent tracker instance for one SSE stream."""
    return _ContentTracker()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def agent_event_to_sse_json(
    evt: AgentEvent,
    tracker: _ContentTracker | None = None,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Convert an AgentEvent to v1 SSE format.

    Parameters
    ----------
    tracker : _ContentTracker
        Per-stream content-block tracker (required for content events).

    Returns
    -------
    dict   – single ``{sse_event, data}`` event
    list   – multiple events (e.g. content.done + message.end)
    None   – event should be silently dropped
    """

    # -- MessageStart (currently a no-op; server emits message.start) ---------
    if isinstance(evt, MessageStart):
        return None

    # -- MessageUpdate (text / thinking / tool-call deltas) --------------------
    if isinstance(evt, MessageUpdate):
        delta = evt.delta
        if isinstance(delta, TextDelta):
            return tracker.delta("text", delta.text) if tracker else None
        if isinstance(delta, ThinkingDelta):
            return tracker.delta("thinking", delta.text) if tracker else None
        if isinstance(delta, ToolCallDelta):
            return None
        return None

    # -- ToolExecutionStart ----------------------------------------------------
    if isinstance(evt, ToolExecutionStart):
        close_evt = tracker.close() if tracker else None
        result: dict[str, Any] = {
            "sse_event": "action",
            "data": {
                "actionType": "tool_call.started",
                "toolCallId": evt.tool_call_id,
                "name": evt.tool_name,
                "arguments": evt.args,
            },
        }
        if close_evt is not None:
            return [close_evt, result]
        return result

    # -- ToolExecutionUpdate ---------------------------------------------------
    if isinstance(evt, ToolExecutionUpdate):
        return {
            "sse_event": "action",
            "data": {
                "actionType": "tool_call.progress",
                "toolCallId": evt.tool_call_id,
                "output": _extract_result_text(evt.partial_result),
            },
        }

    # -- ToolExecutionEnd ------------------------------------------------------
    if isinstance(evt, ToolExecutionEnd):
        result_payload: dict[str, Any] = {
            "output": _extract_result_text(evt.result),
            "isError": evt.is_error,
        }
        if hasattr(evt.result, "display") and evt.result.display:
            result_payload["display"] = evt.result.display
        return {
            "sse_event": "action",
            "data": {
                "actionType": "tool_call.completed",
                "toolCallId": evt.tool_call_id,
                "result": result_payload,
            },
        }

    # -- HumanInputRequired ----------------------------------------------------
    if isinstance(evt, HumanInputRequired):
        return {
            "sse_event": "action",
            "data": {
                "actionType": "human_input.required",
                "toolCallId": evt.tool_call_id,
                "prompt": evt.prompt,
                "inputSchema": evt.input_schema,
                "timeoutSeconds": 300,
            },
        }

    # -- MessageEnd ------------------------------------------------------------
    if isinstance(evt, MessageEnd):
        events: list[dict[str, Any]] = []
        close_evt = tracker.close() if tracker else None
        if close_evt is not None:
            events.append(close_evt)

        msg = evt.message
        usage = None
        u = None
        if isinstance(msg, dict):
            u = msg.get("usage")
        elif hasattr(msg, "usage"):
            u = msg.usage
        if u:
            usage = {
                "input_tokens": getattr(u, "input_tokens", 0),
                "output_tokens": getattr(u, "output_tokens", 0),
                "cache_read_tokens": getattr(u, "cache_read_tokens", 0),
                "cache_write_tokens": getattr(u, "cache_write_tokens", 0),
            }

        stop_reason = "end_turn"
        if hasattr(msg, "stop_reason"):
            stop_reason = msg.stop_reason or "end_turn"

        events.append({
            "sse_event": "message",
            "data": {
                "type": "message.end",
                "messageId": getattr(msg, "id", "msg_0"),
                "stopReason": stop_reason,
                "completedAt": int(time.time()),
                "usage": usage,
            },
        })
        return events

    return None


# ---------------------------------------------------------------------------
# Companion helper
# ---------------------------------------------------------------------------


def companion_event_to_v1(evt: Any) -> dict[str, Any]:
    """Convert companion/bubble events to v1 format."""
    from agent_core.extensions.companion import CompanionBubbleEvent

    if isinstance(evt, CompanionBubbleEvent):
        return {
            "sse_event": "companion",
            "data": {
                "companionType": "bubble",
                "uid": evt.uid,
                "text": evt.bubble.text,
                "ttlMs": evt.bubble.ttl_ms,
                "priority": evt.bubble.priority,
            },
        }
    return {
        "sse_event": "companion",
        "data": {
            "companionType": "state",
            "uid": evt.uid,
            "emotion": evt.emotion,
            "eyeOverride": evt.eye_override,
            "frontendMood": evt.frontend_mood,
        },
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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
