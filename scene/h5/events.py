"""AgentEvent to SSE v1 format conversion.

Returns ``{"sse_event": <channel>, "data": <dict>}`` dicts.
The *sse_event* value maps to the SSE ``event:`` channel field
(heart / message / content / action / state / companion).
"""

from __future__ import annotations

import re
import time
from typing import Any

from agent_core.core.events import (
    AgentEvent,
    HumanInputRequired,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    SkillEnd,
    SkillStart,
    TextDelta,
    ThinkingDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
    ToolCallDelta,
)

# Tool names that produce image output
_IMAGE_TOOL_NAMES = frozenset({"generate_image", "generate_images", "edit_image"})


def _delegation_action(result: Any) -> dict[str, Any] | None:
    """Map ToolResult.details.delegation → action event (H5 SSE v1)."""
    if result is None:
        return None
    details = getattr(result, "details", None)
    if not isinstance(details, dict):
        return None
    payload = details.get("delegation")
    if not isinstance(payload, dict) or payload.get("type") != "delegation":
        return None
    data = {"actionType": "delegation.update", **payload}
    data.pop("type", None)
    return {"sse_event": "action", "data": data}


def _plan_action(result: Any) -> dict[str, Any] | None:
    """Map ToolResult.details.plan → action event (H5 SSE v1)."""
    if result is None:
        return None
    details = getattr(result, "details", None)
    if not isinstance(details, dict):
        return None
    payload = details.get("plan")
    if not isinstance(payload, dict) or payload.get("type") != "plan":
        return None
    data = {"actionType": "plan.update", **payload}
    data.pop("type", None)
    return {"sse_event": "action", "data": data}


def _workflow_action(result: Any) -> dict[str, Any] | None:
    """Map ToolResult.details.workflow → action event (H5 SSE v1)."""
    if result is None:
        return None
    details = getattr(result, "details", None)
    if not isinstance(details, dict):
        return None
    payload = details.get("workflow")
    if not isinstance(payload, dict) or payload.get("type") != "workflow":
        return None
    data = {"actionType": "workflow.update", **payload}
    data.pop("type", None)
    return {"sse_event": "action", "data": data}


class _ContentTracker:
    """Track content-block lifecycle (start → delta×N → done)."""

    def __init__(self, *, message_id: str = "msg_0") -> None:
        self._counter = 0
        self._open_type: str | None = None
        self._open_id: str | None = None
        self._open_index: int = -1
        # Image URLs emitted as content blocks — used to strip markdown duplicates
        self._image_urls: set[str] = set()
        # Buffer for partial markdown across streaming deltas
        self._strip_buffer: str = ""
        # Message ID for consistent message.end (must match message.start)
        self.message_id: str = message_id

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
        self._open_index = -1
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

    def emit_snapshot(self, block_type: str, url: str, meta: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Emit a snapshot-mode content block (start + done) for non-streaming media."""
        close_evt = self.close()  # close any open text/thinking block
        cid = self._next_id()
        idx = self._counter - 1
        start: dict[str, Any] = {
            "sse_event": "content",
            "data": {
                "type": block_type,
                "contentId": cid,
                "index": idx,
                "phase": "start",
                "content": "",
            },
        }
        done_data: dict[str, Any] = {
            "type": block_type,
            "contentId": cid,
            "index": idx,
            "phase": "done",
            "content": url,
        }
        if meta:
            done_data["meta"] = meta
        done: dict[str, Any] = {"sse_event": "content", "data": done_data}
        if close_evt is not None:
            return [close_evt, start, done]
        return [start, done]

    def record_image_url(self, url: str) -> None:
        """Record an image URL so that duplicate markdown references can be stripped."""
        self._image_urls.add(url)

    def strip_image_markdown(self, text: str) -> str:
        """Remove ![...](url) patterns referencing known image URLs.

        Uses an internal buffer to handle partial markdown that spans
        multiple streaming deltas (e.g. ``![im`` + ``age](url)``).
        """
        if not self._image_urls:
            return text
        # Prepend buffered partial from previous delta
        combined = self._strip_buffer + text
        self._strip_buffer = ""
        for url in self._image_urls:
            escaped = re.escape(url)
            combined = re.sub(rf'!\[[^\]]*\]\({escaped}\)\s*', '', combined)
        # Keep tail that might be an incomplete ![...](url) pattern
        safe_end = len(combined)
        if '![' in combined:
            last_open = combined.rfind('![')
            # Check if the pattern is still open (no closing ')' after it)
            after = combined[last_open:]
            if '](' in after and ')' not in after.split('](', 1)[1]:
                safe_end = last_open
            elif '](' not in after:
                safe_end = last_open
        self._strip_buffer = combined[safe_end:]
        result = combined[:safe_end]
        if not result.strip() or result.strip() in (":", "：", "。"):
            return ""
        return result


def create_tracker(*, message_id: str = "msg_0") -> _ContentTracker:
    """Create an independent tracker instance for one SSE stream."""
    return _ContentTracker(message_id=message_id)


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
            if tracker:
                stripped = tracker.strip_image_markdown(delta.text)
                if not stripped:
                    return None
                return tracker.delta("text", stripped)
            return None
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
        events: list[dict[str, Any]] = []
        deleg = _delegation_action(evt.partial_result)
        if deleg is not None:
            events.append(deleg)
        plan = _plan_action(evt.partial_result)
        if plan is not None:
            events.append(plan)
        workflow = _workflow_action(evt.partial_result)
        if workflow is not None:
            events.append(workflow)
        text = _extract_result_text(evt.partial_result)
        if text or (deleg is None and plan is None and workflow is None):
            events.append({
                "sse_event": "action",
                "data": {
                    "actionType": "tool_call.progress",
                    "toolCallId": evt.tool_call_id,
                    "output": text,
                },
            })
        return events[0] if len(events) == 1 else events

    # -- ToolExecutionEnd ------------------------------------------------------
    if isinstance(evt, ToolExecutionEnd):
        result_payload: dict[str, Any] = {
            "output": _extract_result_text(evt.result),
            "isError": evt.is_error,
        }
        if hasattr(evt.result, "display") and evt.result.display:
            result_payload["display"] = evt.result.display

        events: list[dict[str, Any]] = []

        deleg = _delegation_action(evt.result)
        if deleg is not None:
            events.append(deleg)
        plan = _plan_action(evt.result)
        if plan is not None:
            events.append(plan)
        workflow = _workflow_action(evt.result)
        if workflow is not None:
            events.append(workflow)

        # Emit image content blocks for image generation tools
        if evt.tool_name in _IMAGE_TOOL_NAMES and not evt.is_error and tracker:
            image_urls, image_meta = _extract_image_info(evt.result)
            for url in image_urls:
                tracker.record_image_url(url)
                meta = dict(image_meta) if image_meta else {}
                meta["name"] = url.rsplit("/", 1)[-1] if "/" in url else "image.png"
                meta["format"] = _guess_format(url)
                meta["progress"] = 100
                snap_events = tracker.emit_snapshot("image", url, meta)
                events.extend(snap_events)

        events.append({
            "sse_event": "action",
            "data": {
                "actionType": "tool_call.completed",
                "toolCallId": evt.tool_call_id,
                "name": evt.tool_name,
                "result": result_payload,
            },
        })
        return events if len(events) > 1 else events[0]

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

    # -- SkillStart ------------------------------------------------------------
    if isinstance(evt, SkillStart):
        close_evt = tracker.close() if tracker else None
        result: dict[str, Any] = {
            "sse_event": "action",
            "data": {
                "actionType": "skill.started",
                "skillId": evt.skill_name,
                "skillName": evt.skill_name,
                "skillDescription": evt.skill_description,
            },
        }
        if close_evt is not None:
            return [close_evt, result]
        return result

    # -- SkillEnd --------------------------------------------------------------
    if isinstance(evt, SkillEnd):
        return {
            "sse_event": "action",
            "data": {
                "actionType": "skill.completed",
                "skillId": evt.skill_name,
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

        # Map internal stop_reason to spec StopReason values
        _STOP_REASON_MAP: dict[str, str] = {
            "stop": "end_turn",
            "end_turn": "end_turn",
            "tool_use": "tool_use",
            "length": "max_tokens",
            "content_filter": "error",
            "error": "error",
            "aborted": "cancelled",
        }
        raw_stop = getattr(msg, "stop_reason", None) or "stop"
        stop_reason = _STOP_REASON_MAP.get(raw_stop, "end_turn")

        end_data: dict[str, Any] = {
            "type": "message.end",
            "messageId": tracker.message_id if tracker else "msg_0",
            "stopReason": stop_reason,
            "completedAt": int(time.time()),
        }
        if usage is not None:
            end_data["usage"] = usage

        events.append({
            "sse_event": "message",
            "data": end_data,
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


def _extract_image_info(result: Any) -> tuple[list[str], dict[str, Any] | None]:
    """Extract image URLs and metadata from a ToolResult."""
    urls: list[str] = []
    meta: dict[str, Any] | None = None
    if result is None:
        return urls, meta
    # Check details dict (used by AgnesImageTool)
    if hasattr(result, "details") and isinstance(result.details, dict):
        detail_urls = result.details.get("urls", [])
        if detail_urls:
            urls.extend(detail_urls)
        size = result.details.get("size", "")
        if size:
            meta = {"size": size}
            m = re.match(r"(\d+)\s*x\s*(\d+)", str(size))
            if m:
                meta["width"] = int(m.group(1))
                meta["height"] = int(m.group(2))
    # Check content list for ImageContent items
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "type") and item.type == "image" and hasattr(item, "data"):
                if item.data not in urls:
                    urls.append(item.data)
    # Fallback: scan text content for markdown image URLs
    if not urls and hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                for m in re.finditer(r'!\[[^\]]*\]\(([^)]+)\)', item.text):
                    u = m.group(1)
                    if u.startswith(('http://', 'https://', '/')) and u not in urls:
                        urls.append(u)
    return urls, meta


def _guess_format(url: str) -> str:
    """Guess image format from URL."""
    for ext in ("png", "jpg", "jpeg", "gif", "webp", "svg"):
        if f".{ext}" in url.lower():
            return ext
    return "png"
