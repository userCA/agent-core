"""Pytest wrapper for skill evolution E2E verification (CI)."""

from __future__ import annotations

import pytest

from agent_core.skill_evolution.e2e_verify import run_skill_evolution_e2e


@pytest.mark.asyncio
async def test_skill_evolution_e2e_closed_loop():
    """Fixture traces → analyze → validate → apply → audit (no network)."""
    result = await run_skill_evolution_e2e(use_live_runner=False, use_jsonl_store=True)
    assert result.ok, result.summary()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not __import__("os").environ.get("OPENAI_API_KEY")
    and not __import__("os").environ.get("MINIMAX_API_KEY"),
    reason="No LLM API key for live E2E",
)
async def test_skill_evolution_e2e_live_runner():
    """Optional live run with real LLM."""
    result = await run_skill_evolution_e2e(use_live_runner=True)
    assert result.proposals_generated > 0, result.summary()
    assert any(s.name == "analyze" and s.ok for s in result.steps), result.summary()
