"""Skill evolution / trace collector flags for http_sse scene."""

from __future__ import annotations

import os
from typing import Any


def skill_evolution_enabled() -> bool:
    return os.environ.get("ENABLE_SKILL_EVOLUTION", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def group_rollout_enabled() -> bool:
    """Active G-sample exploration; default OFF (costly)."""
    return os.environ.get("ENABLE_GROUP_ROLLOUT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def group_rollout_size() -> int:
    raw = os.environ.get("GROUP_ROLLOUT_G", "3").strip()
    try:
        g = int(raw)
    except ValueError:
        g = 3
    return max(2, g)


def skill_case_recall_enabled() -> bool:
    """Inject top-k path cases into context; default OFF."""
    return os.environ.get("ENABLE_SKILL_CASE_RECALL", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def build_skill_trace_collector() -> Any | None:
    """Return a SkillTraceCollector writing to the default jsonl store, or None."""
    if not skill_evolution_enabled():
        return None
    from agent_core.skill_evolution.collector import create_skill_trace_collector

    return create_skill_trace_collector(store_type="jsonl", enabled=True)


def build_skill_case_recall_extension(
    *,
    skill_dir: str,
    skill_names: list[str] | None = None,
) -> Any | None:
    """Return SkillCaseRecallExtension when ENABLE_SKILL_CASE_RECALL is on."""
    if not skill_case_recall_enabled():
        return None
    from agent_core.skill_evolution.case_recall import SkillCaseRecallExtension

    return SkillCaseRecallExtension(
        skill_dir=skill_dir,
        skill_names=skill_names or [],
        enabled=True,
    )
