"""Shared skill evolution analyze service for HTTP endpoints and scheduler."""

from __future__ import annotations

from typing import Any

_evolution_cache: dict[str, list[dict[str, Any]]] = {}


def get_evolution_cache() -> dict[str, list[dict[str, Any]]]:
    return _evolution_cache


def get_cached_proposals(skill_name: str) -> list[dict[str, Any]]:
    return _evolution_cache.get(skill_name, [])


def set_cached_proposals(skill_name: str, proposals: list[dict[str, Any]]) -> None:
    _evolution_cache[skill_name] = proposals


def remove_cached_proposal(skill_name: str, proposal_id: str) -> None:
    proposals = _evolution_cache.get(skill_name, [])
    _evolution_cache[skill_name] = [
        p for p in proposals if p.get("proposal_id") != proposal_id
    ]


async def run_skill_evolution_analyze(
    *,
    skill_dir: str,
    skill_name: str,
    min_traces: int = 10,
) -> dict[str, Any]:
    """Run offline evolution cycle and attach diffs; cache proposals on success."""
    from agent_core.skill_evolution import PatchProposal, create_validation_gate
    from scene.http_sse.evolution_config import build_offline_evolution_agent

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

    set_cached_proposals(skill_name, proposals_out)

    return {
        **base_response,
        "status": "completed",
        "cycle_id": result.get("cycle_id", ""),
        "traces_analyzed": result.get("traces_analyzed", 0),
        "proposals_generated": result.get("proposals_generated", 0),
        "conflicts": result.get("conflicts", 0),
        "discarded": result.get("discarded", 0),
        "proposals": proposals_out,
    }
