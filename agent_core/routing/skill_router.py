"""Keyword-based skill router — selects active skills per user message."""

from __future__ import annotations

from agent_core.resources.types import Skill


def route_skills(
    user_message: str,
    all_skills: list[Skill],
    *,
    max_skills: int = 10,
) -> list[Skill]:
    """Select skills whose trigger_keywords match the user message.

    Skills with no trigger_keywords are always included (backward compat).
    Matching is case-insensitive OR-semantics: any keyword hit activates the skill.
    Results are sorted by match count (descending), capped at max_skills.
    """
    if not all_skills:
        return []

    msg_lower = user_message.lower()
    always_active: list[Skill] = []
    scored: list[tuple[int, Skill]] = []

    for skill in all_skills:
        if skill.disable_model_invocation:
            continue
        if not skill.trigger_keywords:
            always_active.append(skill)
            continue
        hits = sum(
            1 for kw in skill.trigger_keywords
            if kw.lower() in msg_lower
        )
        if hits > 0:
            scored.append((hits, skill))

    # Sort by match count descending
    scored.sort(key=lambda x: x[0], reverse=True)
    matched = [s for _, s in scored]

    # Combine: matched first (by relevance), then always-active
    activated = matched + always_active
    return activated[:max_skills]


def validate_skill_groups(skills: list[Skill]) -> list[str]:
    """Cross-validate skill grouping consistency via the tools field.

    Returns a list of warning messages for skills whose tool sets have
    no overlap with other skills in the same category.
    """
    warnings: list[str] = []
    by_category: dict[str, list[Skill]] = {}
    for s in skills:
        if s.category:
            by_category.setdefault(s.category, []).append(s)

    for cat, group in by_category.items():
        tool_sets = [set(s.tools) for s in group if s.tools]
        if len(tool_sets) < 2:
            continue
        common = tool_sets[0]
        for ts in tool_sets[1:]:
            common = common & ts
        if not common:
            continue  # No shared tools at all — skip (weak signal)
        for skill in group:
            if skill.tools and not (set(skill.tools) & common):
                warnings.append(
                    f"Skill '{skill.name}' in category '{cat}' "
                    f"shares no common tools with other skills in the group"
                )
    return warnings
