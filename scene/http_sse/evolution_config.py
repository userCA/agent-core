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


def build_skill_trace_collector() -> Any | None:
    """Return a SkillTraceCollector writing to the default jsonl store, or None."""
    if not skill_evolution_enabled():
        return None
    from agent_core.skill_evolution.collector import create_skill_trace_collector

    return create_skill_trace_collector(store_type="jsonl", enabled=True)
