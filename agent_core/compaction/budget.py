"""Prompt budget pre-check helpers (L3 / Context engineering)."""

from __future__ import annotations

from typing import Any

from agent_core.compaction.strategies import total_tokens

PROMPT_BUDGET_EXCEEDED = "PROMPT_BUDGET_EXCEEDED"

DEFAULT_BUDGET_RATIO = 0.95


def estimate_prompt_tokens(
    messages: list[Any],
    *,
    system_prompt: str = "",
    tool_schemas: list[Any] | None = None,
) -> int:
    """Rough prompt token estimate (messages + system prompt + tool schemas)."""
    used = total_tokens(messages)
    if system_prompt:
        used += max(1, len(system_prompt) // 4 + 20)
    if tool_schemas:
        used += estimate_tool_tokens(tool_schemas)
    return used


def estimate_tool_tokens(tool_schemas: list[Any]) -> int:
    """Estimate token cost of tool definitions in the provider request."""
    import json
    total = 0
    for t in tool_schemas:
        if isinstance(t, dict):
            total += len(json.dumps(t)) // 4 + 5
        elif hasattr(t, "model_dump"):
            total += len(json.dumps(t.model_dump())) // 4 + 5
        elif hasattr(t, "definition"):
            d = t.definition
            if hasattr(d, "model_dump"):
                total += len(json.dumps(d.model_dump())) // 4 + 5
    return total


def prompt_budget_limit(
    *,
    context_window: int,
    max_output_tokens: int = 1024,
    ratio: float = DEFAULT_BUDGET_RATIO,
) -> int:
    """Usable input budget before a provider call.

    Returns 0 when the window/ratio cannot yield a meaningful input budget
    (caller should treat 0 as ``do not block``).

    Output reserve is capped at half of the usable window so a large
    ``max_output_tokens`` cannot collapse the input limit to 1 token.
    """
    if context_window <= 0 or ratio <= 0:
        return 0
    usable = int(context_window * ratio)
    if usable <= 1:
        return 0
    reserve = min(max(0, int(max_output_tokens)), usable // 2)
    return usable - reserve


def is_prompt_budget_exceeded(
    messages: list[Any],
    *,
    system_prompt: str = "",
    context_window: int,
    max_output_tokens: int = 1024,
    ratio: float = DEFAULT_BUDGET_RATIO,
    tool_schemas: list[Any] | None = None,
) -> tuple[bool, int, int]:
    """Return ``(exceeded, used_tokens, limit_tokens)``.

    When *limit* is 0 (misconfigured window/reserve), never reports exceeded.
    """
    if context_window <= 0 or ratio <= 0:
        return False, 0, 0
    limit = prompt_budget_limit(
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        ratio=ratio,
    )
    if limit <= 0:
        return False, 0, 0
    used = estimate_prompt_tokens(messages, system_prompt=system_prompt, tool_schemas=tool_schemas)
    return used >= limit, used, limit
