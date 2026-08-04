"""Shared skill evolution analyze service for HTTP endpoints and scheduler."""

from __future__ import annotations

import logging
from typing import Any

from scene.http_sse.evolution_pending import (
    add_pending_proposals,
    get_pending_proposals,
    get_pending_summary,
    has_pending_proposals,
    remove_pending_proposal,
)

_log = logging.getLogger(__name__)


def get_cached_proposals(skill_name: str) -> list[dict[str, Any]]:
    """Get pending proposals for a skill (alias for compatibility)."""
    return get_pending_proposals(skill_name)


def remove_cached_proposal(skill_name: str, proposal_id: str) -> dict[str, Any] | None:
    """Remove a pending proposal by ID (alias for compatibility)."""
    return remove_pending_proposal(proposal_id)


def get_pending_evolution_summary() -> dict[str, Any]:
    """Get summary of all pending proposals."""
    return get_pending_summary()


async def run_skill_evolution_analyze(
    *,
    skill_dir: str,
    skill_name: str,
    min_traces: int = 10,
    force: bool = False,
) -> dict[str, Any]:
    """Run offline evolution cycle and attach diffs; store proposals in pending store.

    Blocks if there are pending proposals for this skill (unless force=True).
    """
    from agent_core.skill_evolution import PatchProposal, create_validation_gate
    from scene.http_sse.evolution_config import build_offline_evolution_agent

    # Block if there are pending proposals for this skill
    if not force and has_pending_proposals(skill_name):
        pending = get_pending_proposals(skill_name)
        return {
            "skill_name": skill_name,
            "status": "blocked",
            "reason": f"There are {len(pending)} pending proposals for '{skill_name}' that must be approved or rejected before starting a new evolution cycle.",
            "pending_count": len(pending),
            "pending_proposals": [
                {
                    "proposal_id": p.get("proposal_id"),
                    "operation": p.get("operation"),
                    "target_rule_id": p.get("target_rule_id"),
                    "confidence": p.get("confidence"),
                    "pending_since": p.get("pending_since"),
                }
                for p in pending
            ],
            "hint": "Use /skills/evolution/proposals/{proposal_id}/accept or /reject to process pending proposals, or pass force=True to override.",
        }

    agent, analyzer = build_offline_evolution_agent()
    result = await agent.run_evolution_cycle(
        skill_name=skill_name,
        min_traces=min_traces,
    )

    base_response: dict[str, Any] = {
        "skill_name": skill_name,
        "analyzer": analyzer,
        "llm_enabled": analyzer == "llm",
    }

    if result.get("status") != "completed" or not result.get("final_proposals"):
        return {
            **base_response,
            "status": result.get("status", "error"),
            "reason": result.get("reason", result.get("message", "")),
            "trace_count": result.get("trace_count", result.get("traces_analyzed", 0)),
            "proposals": [],
            "diagnostics": {
                "analyzer": analyzer,
                "hint": (
                    "Connect LLM via EVOLUTION_PROVIDER / API keys for deeper analysis"
                    if analyzer == "heuristic"
                    else None
                ),
            },
        }

    gate = create_validation_gate(skill_dir=skill_dir)
    proposals_out: list[dict[str, Any]] = []

    for p_dict in result["final_proposals"]:
        proposal = PatchProposal(
            proposal_id=p_dict["proposal_id"],
            source_traces=p_dict.get("source_traces", []),
            skill_name=p_dict["skill_name"],
            operation=p_dict.get("operation", "add"),
            target_rule_id=p_dict.get("target_rule_id"),
            new_content=p_dict.get("new_content"),
            rationale=p_dict.get("rationale", ""),
            confidence=p_dict.get("confidence", 0.5),
        )
        diff = gate.diff_proposal(proposal)
        proposals_out.append({**p_dict, "diff": diff})

    # Store proposals in persistent pending store
    add_pending_proposals(proposals_out)
    _log.info(
        "Evolution cycle completed for skill=%s: %d proposals pending review",
        skill_name,
        len(proposals_out),
    )

    return {
        **base_response,
        "status": "completed",
        "cycle_id": result.get("cycle_id", ""),
        "traces_analyzed": result.get("traces_analyzed", 0),
        "proposals_generated": result.get("proposals_generated", 0),
        "conflicts": result.get("conflicts", 0),
        "discarded": result.get("discarded", 0),
        "proposals": proposals_out,
        "pending_summary": get_pending_summary(),
    }
