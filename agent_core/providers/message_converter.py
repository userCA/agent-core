"""Default OpenAI-format message converter — used when the provider has no native converter."""

from __future__ import annotations

import json as _json
from typing import Any

from agent_core.core.content import ImageContent, TextContent, ToolCallContent
from agent_core.core.messages import AssistantMessage, CustomMessage, ToolResultMessage, UserMessage

_MAX_TOOL_ARGS_CHARS = 4000


def create_default_converter(tool_result_max_chars: int = 4000):
    """Return a ConvertToLlm callable that formats messages to OpenAI-compatible dicts."""

    async def convert(messages: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, UserMessage):
                content = _user_content_to_openai(m.content)
                out.append({"role": "user", "content": content})
            elif isinstance(m, AssistantMessage):
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": "".join(c.text for c in m.content if isinstance(c, TextContent)),
                }
                tool_calls = [c for c in m.content if isinstance(c, ToolCallContent)]
                if tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": _truncate_tool_args(tc.arguments)},
                        }
                        for tc in tool_calls
                    ]
                out.append(msg)
            elif isinstance(m, ToolResultMessage):
                text_parts = "".join(c.text for c in m.content if isinstance(c, TextContent))
                if len(text_parts) > tool_result_max_chars:
                    text_parts = text_parts[:tool_result_max_chars] + f"\n...[truncated, {len(text_parts)} chars total]"
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": text_parts})
            elif isinstance(m, CustomMessage) and m.custom_type == "compaction_summary":
                text = m.content if isinstance(m.content, str) else str(m.content)
                out.append({
                    "role": "system",
                    "content": f"[Earlier conversation summary]\n{text}",
                })
        return out

    return convert


def _truncate_tool_args(args: Any) -> str:
    """Serialize tool call arguments, truncating to _MAX_TOOL_ARGS_CHARS.

    Prevents large payloads (e.g. base64 images from HITL) from bloating
    the context window when serialized into the LLM message history.
    """
    text = _json.dumps(args)
    if len(text) <= _MAX_TOOL_ARGS_CHARS:
        return text
    return text[:_MAX_TOOL_ARGS_CHARS] + f'\n...[truncated, {len(text)} chars total]'


def _to_openai_image_url(data: str, mime_type: str) -> str:
    """Accept http(s) URL, data URI, or raw base64."""
    text = (data or "").strip()
    if text.startswith("http://") or text.startswith("https://") or text.startswith("data:"):
        return text
    return f"data:{mime_type};base64,{text}"


def _user_content_to_openai(content: list[Any]) -> Any:
    parts: list[dict[str, Any]] = []
    only_text = True
    for c in content:
        if isinstance(c, TextContent):
            parts.append({"type": "text", "text": c.text})
        elif isinstance(c, ImageContent):
            parts.append({
                "type": "image_url",
                "image_url": {"url": _to_openai_image_url(c.data, c.mime_type)},
            })
            only_text = False
        elif isinstance(c, dict):
            t = c.get("type")
            if t == "text":
                parts.append({"type": "text", "text": c.get("text", "")})
            elif t == "image":
                data = c.get("data", "")
                mime = c.get("mime_type", "image/png")
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": _to_openai_image_url(data, mime)},
                })
                only_text = False
    if only_text:
        return "".join(p["text"] for p in parts)
    return parts
