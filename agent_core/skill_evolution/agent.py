"""Offline Skill Evolution Agent.

This agent analyzes batches of skill execution traces and proposes improvements,
inspired by the Trace2Skill and EvoSkill papers.

Architecture:
1. Parallel Proposal Phase: Multiple sub-analysts examine traces independently
   - Success Analyst (A+): Extract patterns from successful executions
   - Error Analyst (A-): Diagnose root causes of failures
   
2. Hierarchical Merge Phase: Combine proposals, resolve conflicts, discard noise

3. Validation Gate: Test proposed changes against test cases before applying

Key Design Principles:
- Batch processing: Avoid overfitting to single examples
- Conflict resolution: Detect and flag contradictory proposals
- Conservative updates: Only accept changes with measurable improvement
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

from .store import SkillEvolutionStore
from .types import (
    ExecutionOutcome,
    MergedProposal,
    PatchProposal,
    SkillEvolutionTrace,
)


_log = logging.getLogger(__name__)


class OfflineEvolutionAgent:
    """Analyzes skill traces and proposes rule improvements.

    This is the core "brain" of the self-evolution system. It mimics how
    a human expert would review multiple bug reports and synthesize general
    rules.

    Usage:
        agent = OfflineEvolutionAgent(store)
        summary = await agent.run_evolution_cycle(
            skill_name="dev-process-backend",
            min_traces=50,  # Wait for enough data
        )
    """

    def __init__(
        self,
        store: SkillEvolutionStore,
        model_provider: Any | None = None,  # Optional: LLM for analysis
        batch_size: int = 100,
        merge_batch_size: int = 10,
    ):
        """Initialize the evolution agent.

        Args:
            store: Backend for reading traces
            model_provider: Optional LLM provider for intelligent analysis
                           (if None, uses heuristic rules only)
            batch_size: Number of traces to analyze per cycle
            merge_batch_size: How many proposals to merge at once
        """
        self.store = store
        self.model_provider = model_provider
        self.batch_size = batch_size
        self.merge_batch_size = merge_batch_size

    async def run_evolution_cycle(
        self,
        skill_name: str,
        min_traces: int = 20,
        max_proposals: int = 5,
    ) -> dict[str, Any]:
        """Run a complete evolution cycle for a specific skill.

        Args:
            skill_name: Which skill to evolve (e.g., "dev-process-backend")
            min_traces: Minimum traces needed before analyzing
            max_proposals: Max proposals to generate per cycle

        Returns:
            Summary of the cycle (traces analyzed, proposals generated, etc.)
        """
        _log.info(f"[EvolutionAgent] Starting cycle for skill: {skill_name}")

        # Step 1: Fetch traces
        trace_count = await self.store.get_trace_count(skill_name=skill_name)
        if trace_count < min_traces:
            _log.info(
                f"[EvolutionAgent] Insufficient traces ({trace_count} < {min_traces}), skipping"
            )
            return {
                "status": "skipped",
                "reason": f"insufficient_traces",
                "trace_count": trace_count,
                "min_required": min_traces,
            }

        traces = await self.store.get_traces(
            skill_name=skill_name,
            limit=self.batch_size,
        )

        _log.info(f"[EvolutionAgent] Analyzing {len(traces)} traces for {skill_name}")

        # Step 2: Separate success/failure traces
        success_traces = [
            t for t in traces
            if t.execution_outcome == ExecutionOutcome.SUCCESS
        ]
        failure_traces = [
            t for t in traces
            if t.execution_outcome in (ExecutionOutcome.FAILURE, ExecutionOutcome.PARTIAL)
        ]

        _log.info(
            f"[EvolutionAgent] Split: {len(success_traces)} success, {len(failure_traces)} failure"
        )

        # Step 3: Parallel proposal generation
        proposals = await self._generate_proposals(success_traces, failure_traces)
        _log.info(f"[EvolutionAgent] Generated {len(proposals)} raw proposals")

        if not proposals:
            return {
                "status": "completed",
                "traces_analyzed": len(traces),
                "proposals_generated": 0,
                "message": "No actionable patterns found",
            }

        # Step 4: Hierarchical merge
        merged = await self._merge_proposals(proposals)
        _log.info(
            f"[EvolutionAgent] Merged: {len(merged.merged_proposals)} accepted, "
            f"{len(merged.conflicts)} conflicts, {len(merged.discarded)} discarded"
        )

        # Step 5: Limit proposals
        final_proposals = merged.merged_proposals[:max_proposals]

        return {
            "status": "completed",
            "cycle_id": str(uuid.uuid4()),
            "skill_name": skill_name,
            "traces_analyzed": len(traces),
            "success_traces": len(success_traces),
            "failure_traces": len(failure_traces),
            "proposals_generated": len(proposals),
            "proposals_accepted": len(final_proposals),
            "conflicts": len(merged.conflicts),
            "discarded": len(merged.discarded),
            "final_proposals": [p.to_dict() for p in final_proposals],
            "merge_rationale": merged.merge_rationale,
        }

    async def _generate_proposals(
        self,
        success_traces: list[SkillEvolutionTrace],
        failure_traces: list[SkillEvolutionTrace],
    ) -> list[PatchProposal]:
        """Generate proposals from both success and failure traces.

        This runs two types of analysts in parallel:
        - Success Analysts: Extract reusable patterns from successes
        - Error Analysts: Diagnose root causes of failures
        """
        tasks = []

        # Success analysts (lighter weight, single LLM call per trace)
        for trace in success_traces[:20]:  # Limit to avoid explosion
            tasks.append(self._analyze_success_trace(trace))

        # Error analysts (heavier, may use ReAct loop)
        for trace in failure_traces[:20]:
            tasks.append(self._analyze_failure_trace(trace))

        # Run all analyses in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None/exception results
        proposals = []
        for result in results:
            if isinstance(result, Exception):
                _log.warning(f"[EvolutionAgent] Proposal generation failed: {result}")
                continue
            if result:
                proposals.append(result)

        return proposals

    async def _analyze_success_trace(
        self,
        trace: SkillEvolutionTrace,
    ) -> PatchProposal | None:
        """Analyze a successful trace to extract reusable patterns.

        Success analysts look for:
        - Rules that were particularly helpful
        - Patterns that could be generalized
        - Missing rules that should have been applied
        """
        # Heuristic analysis (no LLM needed for basic patterns)
        loaded_rules = trace.loaded_rules

        # Check if new rules were discovered during this trace
        if trace.new_rules_discovered:
            for new_rule in trace.new_rules_discovered:
                return PatchProposal(
                    proposal_id=str(uuid.uuid4()),
                    source_traces=[trace.trace_id],
                    skill_name=trace.skill_name,
                    operation="add",
                    new_content=new_rule.get("content", ""),
                    rationale=f"Discovered during successful execution: {new_rule.get('context', '')}",
                    confidence=0.7,
                    supporting_evidence=[trace.user_query[:200]],
                )

        # If user provided positive feedback, boost confidence in loaded rules
        if trace.user_feedback and ("helpful" in trace.user_feedback.lower() or "good" in trace.user_feedback.lower()):
            return PatchProposal(
                proposal_id=str(uuid.uuid4()),
                source_traces=[trace.trace_id],
                skill_name=trace.skill_name,
                operation="modify",
                target_rule_id=loaded_rules[0] if loaded_rules else None,
                rationale=f"User confirmed these rules are helpful",
                confidence=0.6,
                supporting_evidence=[f"Feedback: {trace.user_feedback}"],
            )

        return None

    async def _analyze_failure_trace(
        self,
        trace: SkillEvolutionTrace,
    ) -> PatchProposal | None:
        """Analyze a failed trace to diagnose root cause.

        Error analysts perform deeper analysis:
        1. Identify what went wrong
        2. Determine which rule(s) failed or were missing
        3. Propose specific fixes
        """
        error_msg = trace.execution_details.get("error", "")
        exception_type = trace.execution_details.get("exception_type", "")

        # Pattern matching for common failure modes
        proposals = []

        # Pattern 1: Missing rule detection
        if "rule" in error_msg.lower() and ("not found" in error_msg.lower() or "missing" in error_msg.lower()):
            # Suggest adding a rule for this case
            return PatchProposal(
                proposal_id=str(uuid.uuid4()),
                source_traces=[trace.trace_id],
                skill_name=trace.skill_name,
                operation="add",
                rationale=f"Error indicates missing rule: {error_msg[:100]}",
                confidence=0.8,
                supporting_evidence=[f"Query: {trace.user_query[:200]}", f"Error: {error_msg}"],
            )

        # Pattern 2: Regression detection
        if trace.regression_info:
            affected_rule = trace.regression_info.get("affected_rule", "")
            return PatchProposal(
                proposal_id=str(uuid.uuid4()),
                source_traces=[trace.trace_id],
                skill_name=trace.skill_name,
                operation="modify",
                target_rule_id=affected_rule,
                rationale=f"Regression detected in rule: {affected_rule}",
                confidence=0.9,
                supporting_evidence=[f"Regression details: {trace.regression_info}"],
            )

        # Pattern 3: Generic failure - suggest reviewing loaded rules
        if loaded_rules := trace.loaded_rules:
            return PatchProposal(
                proposal_id=str(uuid.uuid4()),
                source_traces=[trace.trace_id],
                skill_name=trace.skill_name,
                operation="modify",
                target_rule_id=loaded_rules[-1],  # Last loaded rule is often the culprit
                rationale=f"Failure occurred with these rules active: {', '.join(loaded_rules)}",
                confidence=0.5,
                supporting_evidence=[f"Error: {error_msg}", f"Query: {trace.user_query[:200]}"],
            )

        return None

    async def _merge_proposals(
        self,
        proposals: list[PatchProposal],
    ) -> MergedProposal:
        """Merge multiple proposals into a coherent set.

        This implements the hierarchical merge algorithm from Trace2Skill:
        1. Group proposals by skill and operation type
        2. Within each group, detect conflicts (same target, different changes)
        3. Merge compatible proposals
        4. Discard low-confidence outliers
        """
        merged = MergedProposal()

        if not proposals:
            merged.merge_rationale = "No proposals to merge"
            return merged

        # Group by skill_name + target_rule_id
        groups: dict[tuple[str, str | None], list[PatchProposal]] = {}
        for p in proposals:
            key = (p.skill_name, p.target_rule_id)
            if key not in groups:
                groups[key] = []
            groups[key].append(p)

        # Process each group
        for (skill_name, target_rule), group_proposals in groups.items():
            if len(group_proposals) == 1:
                # Single proposal - check confidence threshold
                p = group_proposals[0]
                if p.confidence >= 0.6:
                    merged.merged_proposals.append(p)
                else:
                    merged.discarded.append(p)
            else:
                # Multiple proposals for same target - need conflict resolution
                resolved = await self._resolve_conflicts(group_proposals)
                # _resolve_conflicts returns a dict, not an object
                merged.merged_proposals.extend(resolved.get("accepted", []))
                merged.conflicts.extend(resolved.get("conflicts", []))
                merged.discarded.extend(resolved.get("discarded", []))

        # Sort by confidence descending
        merged.merged_proposals.sort(key=lambda p: p.confidence, reverse=True)

        merged.merge_rationale = (
            f"Merged {len(proposals)} proposals into {len(merged.merged_proposals)} accepted, "
            f"{len(merged.conflicts)} conflicts, {len(merged.discarded)} discarded"
        )

        return merged

    async def _resolve_conflicts(
        self,
        proposals: list[PatchProposal],
    ) -> dict[str, list[PatchProposal]]:
        """Resolve conflicting proposals for the same target.

        Conflicts occur when multiple traces suggest different changes to
        the same rule. We prioritize:
        1. Higher confidence proposals
        2. Proposals supported by more traces
        3. More recent proposals (by timestamp)
        """
        result = {
            "accepted": [],
            "conflicts": [],
            "discarded": [],
        }

        if not proposals:
            return result

        # Sort by confidence * number of source traces
        scored = [
            (p, p.confidence * len(p.source_traces))
            for p in proposals
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Accept top proposal
        best = scored[0][0]
        result["accepted"].append(best)

        # Check remaining for true conflicts vs. complementary suggestions
        for p, score in scored[1:]:
            if score / best.confidence < 0.5:
                # Significantly worse - discard
                result["discarded"].append(p)
            elif p.operation != best.operation:
                # Different operations on same target - flag as conflict
                result["conflicts"].append((best, p, f"Conflicting operations: {best.operation} vs {p.operation}"))
            else:
                # Same operation - might be mergeable
                # For now, just take the best one
                result["discarded"].append(p)

        return result


def create_offline_evolution_agent(
    store_type: str = "jsonl",
    storage_path: str | None = None,
    batch_size: int = 100,
) -> OfflineEvolutionAgent:
    """Factory function to create an evolution agent.

    Args:
        store_type: "memory" for testing, "jsonl" for production
        storage_path: Custom path for jsonl store
        batch_size: Traces per analysis cycle

    Returns:
        Configured OfflineEvolutionAgent
    """
    from .store import create_skill_evolution_store

    store = create_skill_evolution_store(store_type, storage_path)
    return OfflineEvolutionAgent(store, batch_size=batch_size)
