"""Wire real agent_runner into skill evolution validation gate."""

from __future__ import annotations

import os
from typing import Any

from agent_core.providers.auth import AuthSource


def evolution_agent_validation_enabled() -> bool:
    return os.environ.get("ENABLE_EVOLUTION_AGENT_VALIDATION", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def validation_max_turns() -> int:
    raw = os.environ.get("EVOLUTION_VALIDATION_MAX_TURNS", "3").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def validation_timeout_sec() -> float:
    raw = os.environ.get("EVOLUTION_VALIDATION_TIMEOUT_SEC", "60").strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 60.0


def validation_max_cases() -> int:
    raw = os.environ.get("EVOLUTION_VALIDATION_MAX_CASES", "5").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 5


def create_validation_agent_runner(skill_name: str) -> Any | None:
    """Build a per-skill ValidationHarnessRunner callable, or None if disabled."""
    if not evolution_agent_validation_enabled():
        return None

    from agent_core.skill_evolution.agent_runner import ValidationHarnessRunner
    from scene.http_sse.evolution_config import resolve_evolution_provider

    provider, mode = resolve_evolution_provider()
    if provider is None:
        return None

    provider_name = os.environ.get(
        "EVOLUTION_PROVIDER",
        os.environ.get("DEFAULT_PROVIDER", "openai"),
    ).strip().lower()

    if provider_name == "anthropic":
        auth = AuthSource.env("ANTHROPIC_API_KEY")
    elif provider_name == "minimax":
        auth = AuthSource.env("MINIMAX_API_KEY")
    else:
        auth = AuthSource.env("OPENAI_API_KEY")

    runner = ValidationHarnessRunner(
        skill_name=skill_name,
        provider=provider,
        auth_source=auth,
        max_turns=validation_max_turns(),
        timeout_sec=validation_timeout_sec(),
    )
    return runner


def build_evolution_validation_gate(skill_dir: str, skill_name: str) -> Any:
    """Create SkillValidationGate with agent runner + trace-derived test cases."""
    from agent_core.skill_evolution import create_validation_gate
    from agent_core.skill_evolution.store import JsonlSkillEvolutionStore

    agent_runner = create_validation_agent_runner(skill_name)
    return create_validation_gate(
        skill_dir=skill_dir,
        agent_runner=agent_runner,
        require_human_review=True,
        trace_store=JsonlSkillEvolutionStore(),
        max_validation_cases=validation_max_cases(),
    )
