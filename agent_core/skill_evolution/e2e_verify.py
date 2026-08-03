"""End-to-end verification for the skill evolution closed loop.

Runs entirely in isolated temp directories by default (CI-safe, no network):

    seed traces → analyze → validate (mock or live agent_runner) → apply → audit

Usage (library):

    from agent_core.skill_evolution.e2e_verify import run_skill_evolution_e2e

    result = await run_skill_evolution_e2e(use_live_runner=False)
    assert result.ok, result.summary()
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_core.skill_evolution.agent import OfflineEvolutionAgent
from agent_core.skill_evolution.audit import read_audit_log, write_audit_entry
from agent_core.skill_evolution.store import InMemorySkillEvolutionStore, JsonlSkillEvolutionStore
from agent_core.skill_evolution.types import (
    ExecutionOutcome,
    PatchProposal,
    PathStep,
    SkillEvolutionTrace,
)
from agent_core.skill_evolution.validation import SkillValidationGate


DEFAULT_SKILL_NAME = "e2e-test-skill"
DEFAULT_MIN_TRACES = 10


@dataclass
class E2EStepResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class E2EResult:
    ok: bool
    skill_name: str
    steps: list[E2EStepResult] = field(default_factory=list)
    proposals_generated: int = 0
    validation_passed: bool = False
    validation_recommendation: str = ""
    score_delta: float = 0.0
    skill_file_changed: bool = False
    audit_written: bool = False
    workdir: str = ""

    def summary(self) -> str:
        lines = [
            f"Skill evolution E2E: {'PASS' if self.ok else 'FAIL'}",
            f"  skill={self.skill_name} workdir={self.workdir}",
            f"  proposals={self.proposals_generated} validation={self.validation_recommendation} "
            f"delta={self.score_delta:+.3f}",
            f"  skill_changed={self.skill_file_changed} audit={self.audit_written}",
        ]
        for step in self.steps:
            mark = "✓" if step.ok else "✗"
            lines.append(f"  [{mark}] {step.name}: {step.detail}")
        return "\n".join(lines)


def _seed_skill(skill_dir: Path, skill_name: str) -> Path:
    skill_path = skill_dir / skill_name / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(
        f"---\nname: {skill_name}\ndescription: E2E test skill\n---\n\n"
        f"# {skill_name}\n\n"
        "## 规则 1：Verify inputs\n"
        "Always validate user intent before responding.\n\n---\n",
        encoding="utf-8",
    )
    return skill_path


async def _seed_traces(store: InMemorySkillEvolutionStore | JsonlSkillEvolutionStore, skill_name: str, count: int) -> int:
    for i in range(count):
        await store.save_trace(
            SkillEvolutionTrace(
                trace_id=f"e2e-fail-{i}",
                timestamp=time.time() - i,
                user_query="查询 tavily_search 工具的完整参数说明",
                skill_name=skill_name,
                loaded_rules=["rule_1"],
                execution_outcome=ExecutionOutcome.FAILURE,
                execution_details={"error": "Tool 'tool_detail' not found"},
                steps=[
                    PathStep(
                        tool_name="tool_detail",
                        args_summary="tool_names=['tavily_search']",
                        is_error=True,
                        error_summary="Tool 'tool_detail' not found.",
                        tool_call_id=f"call_{i}",
                    ),
                ],
            )
        )
    return count


def _build_mock_agent_runner(proposal: PatchProposal):
    """Score higher only when patched skill content includes the proposal body."""

    needle = (proposal.new_content or "").strip()
    if not needle:
        needle = "verify it exists in the active tool set"

    async def _runner(skill_content: str, input_query: str) -> dict[str, Any]:
        hit = needle in skill_content
        return {
            "success": True,
            "score": 1.0 if hit else 0.2,
            "response_text": "validation ok" if hit else "missing rule",
        }

    return _runner


def _build_live_agent_runner(skill_name: str):
    from agent_core.skill_evolution.agent_runner import ValidationHarnessRunner
    from scene.http_sse.evolution_validation import create_validation_agent_runner

    runner = create_validation_agent_runner(skill_name)
    if runner is None:
        raise RuntimeError(
            "Live agent_runner unavailable — set EVOLUTION_PROVIDER and API keys, "
            "or run without --live"
        )
    return runner


async def run_skill_evolution_e2e(
    *,
    skill_name: str = DEFAULT_SKILL_NAME,
    min_traces: int = DEFAULT_MIN_TRACES,
    use_live_runner: bool = False,
    workdir: Path | None = None,
    use_jsonl_store: bool = False,
) -> E2EResult:
    """Execute the full evolution loop in an isolated directory."""
    steps: list[E2EStepResult] = []
    owns_workdir = workdir is None
    root = Path(tempfile.mkdtemp(prefix="skill-evolution-e2e-")) if workdir is None else workdir
    root.mkdir(parents=True, exist_ok=True)

    skill_dir = root / "skills"
    audit_path = root / "audit.jsonl"
    trace_path = root / "traces.jsonl"

    skill_path = _seed_skill(skill_dir, skill_name)
    original_content = skill_path.read_text(encoding="utf-8")

    if use_jsonl_store:
        store: InMemorySkillEvolutionStore | JsonlSkillEvolutionStore = JsonlSkillEvolutionStore(trace_path)
    else:
        store = InMemorySkillEvolutionStore()

    try:
        seeded = await _seed_traces(store, skill_name, max(min_traces + 5, 15))
        steps.append(E2EStepResult("seed_traces", seeded >= min_traces, f"{seeded} traces"))

        agent = OfflineEvolutionAgent(store, batch_size=50)
        analyze = await agent.run_evolution_cycle(skill_name=skill_name, min_traces=min_traces)
        proposals = analyze.get("final_proposals") or []
        proposals_generated = len(proposals)
        analyze_ok = analyze.get("status") == "completed" and proposals_generated > 0
        steps.append(
            E2EStepResult(
                "analyze",
                analyze_ok,
                f"status={analyze.get('status')} proposals={proposals_generated} "
                f"reason={analyze.get('reason') or analyze.get('message') or ''}",
            )
        )
        if not analyze_ok:
            return E2EResult(
                ok=False,
                skill_name=skill_name,
                steps=steps,
                proposals_generated=proposals_generated,
                workdir=str(root),
            )

        proposal_data = proposals[0]
        proposal = PatchProposal(
            proposal_id=proposal_data["proposal_id"],
            source_traces=proposal_data.get("source_traces", []),
            skill_name=proposal_data["skill_name"],
            operation=proposal_data.get("operation", "add"),
            target_rule_id=proposal_data.get("target_rule_id"),
            new_content=proposal_data.get("new_content"),
            rationale=proposal_data.get("rationale", ""),
            confidence=float(proposal_data.get("confidence", 0.5)),
        )
        if use_live_runner:
            agent_runner = _build_live_agent_runner(skill_name)
        else:
            agent_runner = _build_mock_agent_runner(proposal)

        gate = SkillValidationGate(
            skill_dir=skill_dir,
            test_threshold=0.05,
            agent_runner=agent_runner,
            require_human_review=False,
            trace_store=store,
            max_validation_cases=3,
        )
        validation = await gate.validate(proposal)
        validation_ok = validation.passed or validation.recommendation == "accept"
        steps.append(
            E2EStepResult(
                "validate",
                validation_ok,
                f"recommendation={validation.recommendation} delta={validation.score_delta:+.3f}",
            )
        )

        applied = False
        if validation_ok:
            applied = await gate.apply_proposal(proposal, backup=True, force=False)
        steps.append(E2EStepResult("apply", applied, "SKILL.md updated" if applied else "apply failed"))

        new_content = skill_path.read_text(encoding="utf-8")
        skill_changed = new_content != original_content
        steps.append(
            E2EStepResult(
                "skill_file",
                skill_changed,
                "content changed" if skill_changed else "unchanged",
            )
        )

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
                path=audit_path,
            )
        audit_entries = read_audit_log(skill_name=skill_name, path=audit_path)
        audit_ok = bool(audit_id) and any(e.get("action") == "accept" for e in audit_entries)
        steps.append(
            E2EStepResult(
                "audit",
                audit_ok,
                f"audit_id={audit_id[:8]}..." if audit_id else "no audit",
            )
        )

        all_ok = all(s.ok for s in steps)
        return E2EResult(
            ok=all_ok,
            skill_name=skill_name,
            steps=steps,
            proposals_generated=proposals_generated,
            validation_passed=validation.passed,
            validation_recommendation=validation.recommendation,
            score_delta=validation.score_delta,
            skill_file_changed=skill_changed,
            audit_written=audit_ok,
            workdir=str(root),
        )
    finally:
        if owns_workdir and not _keep_workdir():
            import shutil

            shutil.rmtree(root, ignore_errors=True)


def _keep_workdir() -> bool:
    import os

    return os.environ.get("SKILL_EVOLUTION_E2E_KEEP_WORKDIR", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
