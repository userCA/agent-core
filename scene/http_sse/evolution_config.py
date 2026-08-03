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


def build_skill_trace_collector(skills: list[Any] | None = None) -> Any | None:
    """Return a SkillTraceCollector writing to the default jsonl store, or None."""
    if not skill_evolution_enabled():
        return None
    from agent_core.skill_evolution.collector import create_skill_trace_collector

    return create_skill_trace_collector(store_type="jsonl", enabled=True, skills=skills)


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


def resolve_evolution_provider() -> tuple[Any | None, str]:
    """Resolve LLM provider for offline evolution analysis.

    Returns:
        (provider_or_none, analyzer_mode) where analyzer_mode is "llm" or "heuristic"
    """
    provider_name = os.environ.get(
        "EVOLUTION_PROVIDER",
        os.environ.get("DEFAULT_PROVIDER", "openai"),
    ).strip().lower()

    try:
        from agent_core.providers.anthropic_provider import AnthropicProvider
        from agent_core.providers.openai_provider import OpenAIProvider
        from agent_core.providers.types import Model

        if provider_name == "anthropic":
            return AnthropicProvider(), "llm"
        if provider_name == "minimax":
            provider = OpenAIProvider(
                base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"),
                provider_name="minimax",
                models=[
                    Model(
                        provider="minimax",
                        id="minimax-m2.7",
                        context_window=256_000,
                        max_output_tokens=4096,
                    ),
                ],
            )
            return provider, "llm"
        if provider_name == "openai":
            return OpenAIProvider(), "llm"
        return OpenAIProvider(), "llm"
    except Exception:
        return None, "heuristic"


def build_offline_evolution_agent() -> tuple[Any, str]:
    """Create OfflineEvolutionAgent with optional LLM provider from env."""
    from agent_core.skill_evolution import create_offline_evolution_agent

    provider, mode = resolve_evolution_provider()
    agent = create_offline_evolution_agent("jsonl", model_provider=provider)
    return agent, mode
