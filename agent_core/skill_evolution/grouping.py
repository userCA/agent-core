"""Task grouping for GRPO-style relative skill scoring."""

from __future__ import annotations

from collections import defaultdict

from .types import SkillEvolutionTrace


def normalize_task_key(query: str, max_len: int = 120) -> str:
    """Normalize a user query into a stable task key."""
    return " ".join((query or "").strip().lower().split())[:max_len]


def ensure_task_keys(traces: list[SkillEvolutionTrace]) -> None:
    """Fill empty task_key from user_query in-place."""
    for t in traces:
        if not t.task_key:
            t.task_key = normalize_task_key(t.user_query)


def build_groups(
    traces: list[SkillEvolutionTrace],
    min_size: int = 3,
) -> list[list[SkillEvolutionTrace]]:
    """Group traces by (skill_name, task_key); drop groups smaller than min_size."""
    ensure_task_keys(traces)
    buckets: dict[tuple[str, str], list[SkillEvolutionTrace]] = defaultdict(list)
    for t in traces:
        if not t.skill_name or not t.task_key:
            continue
        buckets[(t.skill_name, t.task_key)].append(t)

    groups = [g for g in buckets.values() if len(g) >= min_size]
    # Stable order: larger groups first, then by key
    groups.sort(key=lambda g: (-len(g), g[0].skill_name, g[0].task_key))
    return groups
