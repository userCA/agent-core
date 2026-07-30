"""Token estimation and threshold strategies for compaction."""

from __future__ import annotations

from typing import Any


# Fixed token cost for non-text content blocks (image/audio/video).
# A typical image costs ~1000-2000 tokens in most LLM APIs regardless of
# base64 size. Using a fixed estimate avoids massive over-counting.
_NON_TEXT_TOKEN_COST = 1500


def _content_text(c: Any) -> tuple[str, int]:
    """Return (text, extra_tokens) for a content block.

    TextContent: extract .text, no extra cost.
    Non-text (image/audio/...): empty text, fixed token cost.
    """
    text = getattr(c, "text", None)
    if text:
        return str(text), 0
    ctype = getattr(c, "type", None)
    if ctype in ("image", "audio", "video"):
        return "", _NON_TEXT_TOKEN_COST
    # Unknown content — use short repr, not full str(c) which may embed
    # large base64 data.
    return repr(c)[:200], 0


def estimate_tokens(message: Any) -> int:
    """Rough token estimation: ~4 chars per token + fixed overhead."""
    text_parts: list[str] = []
    extra_tokens = 0
    role = getattr(message, "role", None)
    if role in ("user", "assistant", "tool_result"):
        for c in getattr(message, "content", []):
            t, cost = _content_text(c)
            if t:
                text_parts.append(t)
            extra_tokens += cost
    elif role == "custom":
        text_parts.append(str(getattr(message, "content", "")))

    total_chars = sum(len(p) for p in text_parts)
    return max(1, total_chars // 4 + 20) + extra_tokens  # overhead per message


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
