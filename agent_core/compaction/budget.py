"""Prompt budget pre-check helpers (L3 / Context engineering)."""

from __future__ import annotations

from typing import Any

from agent_core.compaction.strategies import total_tokens

PROMPT_BUDGET_EXCEEDED = "PROMPT_BUDGET_EXCEEDED"

DEFAULT_BUDGET_RATIO = 0.95


def estimate_prompt_tokens(messages: list[Any], *, system_prompt: str = "") -> int:
    """Rough prompt token estimate (messages + system prompt)."""
    used = total_tokens(messages)
    if system_prompt:
        used += max(1, len(system_prompt) // 4 + 20)
    return used


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
    used = estimate_prompt_tokens(messages, system_prompt=system_prompt)
    return used >= limit, used, limit
