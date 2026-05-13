"""Token estimation and threshold strategies for compaction."""

from __future__ import annotations

from typing import Any


def estimate_tokens(message: Any) -> int:
    """Rough token estimation: ~4 chars per token + fixed overhead."""
    text_parts: list[str] = []
    role = getattr(message, "role", None)
    if role == "user":
        for c in getattr(message, "content", []):
            text_parts.append(getattr(c, "text", "") or str(c))
    elif role == "assistant":
        for c in getattr(message, "content", []):
            text_parts.append(getattr(c, "text", "") or str(c))
    elif role == "tool_result":
        for c in getattr(message, "content", []):
            text_parts.append(getattr(c, "text", "") or str(c))
    elif role == "custom":
        text_parts.append(str(getattr(message, "content", "")))

    total_chars = sum(len(p) for p in text_parts)
    return max(1, total_chars // 4 + 20)  # overhead per message


def total_tokens(messages: list[Any]) -> int:
    return sum(estimate_tokens(m) for m in messages)


def should_compact_threshold(
    messages: list[Any],
    *,
    context_window: int,
    threshold: float = 0.8,
) -> bool:
    tokens = total_tokens(messages)
    return tokens >= context_window * threshold
