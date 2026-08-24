#!/usr/bin/env python3
"""Live skill evolution verification against production trace store + skill dir.

Unlike ``verify_skill_evolution_e2e.py`` (isolated fixture + optional mock runner),
this script uses:

- ``~/.agent-core/skill-evolution-traces.jsonl`` (default Jsonl store)
- ``<repo>/.pi/skills/`` skill files
- Real ``ValidationHarnessRunner`` (LLM) when API keys are configured

Examples:

    export OPENAI_API_KEY=sk-...
    export EVOLUTION_PROVIDER=openai   # or minimax + MINIMAX_API_KEY

    # Analyze + validate only (no disk write)
    python scripts/verify_skill_evolution_live.py --skill code-review

    # Full loop including apply (creates SKILL.md.bak)
    python scripts/verify_skill_evolution_live.py --skill code-review --apply

    # Via running server instead:
    PORT=8001 python -m scene.http_sse.server
    curl -s http://localhost:8001/skills/evolution/summary | jq
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _has_llm_credentials() -> bool:
    provider = os.environ.get(
        "EVOLUTION_PROVIDER",
        os.environ.get("DEFAULT_PROVIDER", "openai"),
    ).strip().lower()
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if provider == "minimax":
        return bool(os.environ.get("MINIMAX_API_KEY"))
    return bool(os.environ.get("OPENAI_API_KEY"))


async def _run(*, skill_name: str, min_traces: int, apply: bool) -> int:
    from agent_core.skill_evolution import PatchProposal, write_audit_entry
    from scene.http_sse.evolution_service import run_skill_evolution_analyze
    from scene.http_sse.evolution_validation import build_evolution_validation_gate

    skill_dir = _REPO_ROOT / ".pi" / "skills"
    skill_path = skill_dir / skill_name / "SKILL.md"
    if not skill_path.is_file():
        print(f"ERROR: skill not found: {skill_path}", file=sys.stderr)
        return 1

    if not _has_llm_credentials():
        print(
            "ERROR: no LLM credentials for live validation.\n"
            "Set OPENAI_API_KEY (or MINIMAX_API_KEY + EVOLUTION_PROVIDER=minimax).",
            file=sys.stderr,
        )
        return 1

    print(f"=== Live skill evolution: {skill_name} ===")
    print(f"skill_dir: {skill_dir}")
    print(f"traces:    {Path.home() / '.agent-core/skill-evolution-traces.jsonl'}")

    analyze = await run_skill_evolution_analyze(
        skill_dir=str(skill_dir),
        skill_name=skill_name,
        min_traces=min_traces,
    )
    print(f"\n[analyze] status={analyze.get('status')} analyzer={analyze.get('analyzer')}")
    proposals = analyze.get("proposals") or []
    print(f"[analyze] proposals={len(proposals)} traces_analyzed={analyze.get('traces_analyzed', 0)}")
    if not proposals:
        print(f"[analyze] reason={analyze.get('reason') or analyze.get('message') or 'n/a'}")
        return 1

    p_dict = proposals[0]
    proposal = PatchProposal(
        proposal_id=p_dict["proposal_id"],
        source_traces=p_dict.get("source_traces", []),
        skill_name=p_dict["skill_name"],
        operation=p_dict.get("operation", "add"),
        target_rule_id=p_dict.get("target_rule_id"),
        new_content=p_dict.get("new_content"),
        rationale=p_dict.get("rationale", ""),
        confidence=float(p_dict.get("confidence", 0.5)),
    )
    print(f"[analyze] top proposal: op={proposal.operation} confidence={proposal.confidence:.2f}")
    if proposal.new_content:
        print(f"[analyze] new_content: {proposal.new_content[:160]}...")

    gate = build_evolution_validation_gate(str(skill_dir), skill_name)
    validation = await gate.validate(proposal)
    print(
        f"\n[validate] recommendation={validation.recommendation} "
        f"delta={validation.score_delta:+.3f} passed={validation.passed}"
    )
    for _tid, _improved, msg in validation.test_results[:5]:
        print(f"  {msg}")

    ok = validation.passed or validation.recommendation == "accept"
    if not ok:
        print("\nRESULT: validation did not pass — skill file unchanged.")
        return 1

    if not apply:
        print("\nRESULT: validate OK (dry-run, use --apply to write SKILL.md)")
        return 0

    applied = await gate.apply_proposal(proposal, backup=True, force=False)
    audit_id = ""
    if applied:
        audit_id = write_audit_entry(
            proposal_id=proposal.proposal_id,
            skill_name=skill_name,
            action="accept",
            operation=proposal.operation,
            target_rule_id=proposal.target_rule_id,
            diff_summary=(proposal.new_content or "")[:200],
            rationale=proposal.rationale,
            validation_score=validation.score_delta,
        )
    print(f"\n[apply] applied={applied} audit_id={audit_id[:8] + '...' if audit_id else 'none'}")
    print("RESULT: PASS" if applied else "RESULT: apply failed")
    return 0 if applied else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Live skill evolution verification")
    parser.add_argument("--skill", default="code-review", help="Skill name (default: code-review)")
    parser.add_argument("--min-traces", type=int, default=10, help="Min traces for analyze")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply top proposal after validation (creates .md.bak backup)",
    )
    args = parser.parse_args()
    return asyncio.run(
        _run(skill_name=args.skill, min_traces=args.min_traces, apply=args.apply)
    )


if __name__ == "__main__":
    raise SystemExit(main())
