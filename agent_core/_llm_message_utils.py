"""Internal helpers for inspecting LLM-format messages (provider-neutral dict shape)."""

from __future__ import annotations

from typing import Any


def latest_user_index(messages: list[dict[str, Any]]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            return i
    return len(messages)


def latest_user_text(messages: list[dict[str, Any]]) -> str | None:
    idx = latest_user_index(messages)
    if idx == len(messages):
        return None
    content = messages[idx].get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return "\n".join(p for p in parts if p) or None
    return None
