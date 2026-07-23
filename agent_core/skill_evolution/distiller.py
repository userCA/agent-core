"""Distill group-relative advantages into skill path rules and cases."""

from __future__ import annotations

import uuid

from .types import PatchProposal, PathStep, SkillEvolutionTrace


def _tool_sequence(steps: list[PathStep]) -> str:
    if not steps:
        return "(no tools)"
    return " → ".join(s.tool_name for s in steps)


def distill_group(
    traces: list[SkillEvolutionTrace],
    *,
    tau: float = 0.15,
    skill_name: str | None = None,
) -> list[PatchProposal]:
    """Turn high/low advantage traces into path-preference and case proposals."""
    if not traces:
        return []

    skill = skill_name or traces[0].skill_name
    group_ids = sorted({t.group_id for t in traces if t.group_id})
    proposals: list[PatchProposal] = []

    for t in traces:
        if t.advantage is None:
            continue
        if abs(t.advantage) <= tau:
            continue

        seq = _tool_sequence(t.steps or [])
        source = [t.trace_id]

        if t.advantage > tau:
            proposals.append(
                PatchProposal(
                    proposal_id=str(uuid.uuid4()),
                    source_traces=source,
                    skill_name=skill,
                    operation="add",
                    target_rule_id=None,
                    new_content=(
                        f"[Path Preference] Prefer tool sequence: {seq}. "
                        f"(task_key={t.task_key or normalize_hint(t)})"
                    ),
                    rationale=(
                        f"Positive advantage A={t.advantage:.3f} relative to group; "
                        "distill as preferred path."
                    ),
                    confidence=min(0.9, 0.5 + abs(t.advantage)),
                    supporting_evidence=[seq],
                    case_polarity="positive",
                    source_group_ids=group_ids,
                    expected_delta_r=abs(t.advantage),
                )
            )
            proposals.append(
                PatchProposal(
                    proposal_id=str(uuid.uuid4()),
                    source_traces=source,
                    skill_name=skill,
                    operation="add_case",
                    new_content=f"POSITIVE\nquery: {t.user_query[:200]}\npath: {seq}\n",
                    rationale="Store positive path case for few-shot recall.",
                    confidence=min(0.85, 0.45 + abs(t.advantage)),
                    case_polarity="positive",
                    source_group_ids=group_ids,
                )
            )
        else:
            proposals.append(
                PatchProposal(
                    proposal_id=str(uuid.uuid4()),
                    source_traces=source,
                    skill_name=skill,
                    operation="add",
                    new_content=(
                        f"[Path Preference] Avoid tool sequence: {seq}. "
                        f"(task_key={t.task_key or normalize_hint(t)})"
                    ),
                    rationale=(
                        f"Negative advantage A={t.advantage:.3f} relative to group; "
                        "distill as anti-pattern."
                    ),
                    confidence=min(0.9, 0.5 + abs(t.advantage)),
                    supporting_evidence=[seq],
                    case_polarity="negative",
                    source_group_ids=group_ids,
                    expected_delta_r=abs(t.advantage),
                )
            )
            proposals.append(
                PatchProposal(
                    proposal_id=str(uuid.uuid4()),
                    source_traces=source,
                    skill_name=skill,
                    operation="add_case",
                    new_content=f"NEGATIVE\nquery: {t.user_query[:200]}\npath: {seq}\n",
                    rationale="Store negative path case for few-shot recall.",
                    confidence=min(0.85, 0.45 + abs(t.advantage)),
                    case_polarity="negative",
                    source_group_ids=group_ids,
                )
            )

    return proposals


def normalize_hint(trace: SkillEvolutionTrace) -> str:
    return " ".join((trace.user_query or "").strip().lower().split())[:80]
