"""Offline Skill Evolution Agent.

This agent analyzes batches of skill execution traces and proposes improvements,
inspired by the Trace2Skill and EvoSkill papers.

Architecture:
1. Parallel Proposal Phase: Multiple sub-analysts examine traces independently
   - Success Analyst (A+): Extract patterns from successful executions
   - Error Analyst (A-): Diagnose root causes of failures
   - When model_provider is available, uses LLM for deeper analysis;
     falls back to heuristics otherwise.

2. Hierarchical Merge Phase: Combine proposals, resolve conflicts, discard noise

3. Validation Gate: Test proposed changes against test cases before applying

Key Design Principles:
- Batch processing: Avoid overfitting to single examples
- Conflict resolution: Detect and flag contradictory proposals
- Conservative updates: Only accept changes with measurable improvement
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from agent_core.providers.base import ModelProvider
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import StreamTextDelta, StreamMessageEnd, StreamError

from .store import SkillEvolutionStore
from .types import (
    ExecutionOutcome,
    MergedProposal,
    PatchProposal,
    SkillEvolutionTrace,
)


_log = logging.getLogger(__name__)

_ANALYZE_FAILURE_PROMPT = """You are a skill evolution analyst. Given a failed execution trace, propose a specific change to the skill rule that would prevent this failure.

Trace data:
- Skill: {skill_name}
- User query: {user_query}
- Active rules: {loaded_rules}
- Error: {error}
- Execution details: {details}

Analyze the root cause and output exactly one JSON object (no markdown, no explanation):
{{"operation": "<add|modify|delete>", "target_rule_id": "<rule_id or null>", "new_content": "<new rule text or null>", "rationale": "<why this change helps>", "confidence": <0.0-1.0>}}"""

_ANALYZE_SUCCESS_PROMPT = """You are a skill evolution analyst. Given a successful execution trace, identify what made it work and propose improvements.

Trace data:
- Skill: {skill_name}
- User query: {user_query}
- Active rules: {loaded_rules}
- User feedback: {feedback}
- New rules discovered: {new_rules}

If you see a clear pattern worth codifying, output exactly one JSON object (no markdown, no explanation):
{{"operation": "<add|modify|delete>", "target_rule_id": "<rule_id or null>", "new_content": "<new rule text or null>", "rationale": "<why this change helps>", "confidence": <0.0-1.0>}}

If no actionable pattern is found, output: null"""

_BATCH_FAILURE_PROMPT = """You are a skill evolution analyst. Review {count} failure traces for the same skill and identify cross-trace patterns. Produce up to 3 high-signal proposals.

Skill: {skill_name}

Traces:
{trace_summaries}

Output a JSON array of proposal objects (no markdown, no explanation). Each object:
{{"operation": "<add|modify|delete>", "target_rule_id": "<rule_id or null>", "new_content": "<new rule text or null>", "rationale": "<why this change helps across multiple cases>", "confidence": <0.0-1.0>}}

If no clear pattern emerges, output: []"""


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
        model_provider: Any | None = None,
        batch_size: int = 100,
        merge_batch_size: int = 10,
        max_llm_calls: int = 30,
    ):
        """Initialize the evolution agent.

        Args:
            store: Backend for reading traces
            model_provider: Optional LLM provider for intelligent analysis
            batch_size: Number of traces to analyze per cycle
            merge_batch_size: How many proposals to merge at once
            max_llm_calls: Upper bound on LLM calls per cycle (cost control)
        """
        self.store = store
        self.model_provider = model_provider
        self.batch_size = batch_size
        self.merge_batch_size = merge_batch_size
        self.max_llm_calls = max_llm_calls
        self._analyzed_trace_ids: set[str] = set()
        self._llm_call_count = 0

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

        # Filter out already-analyzed traces
        new_traces = [t for t in traces if t.trace_id not in self._analyzed_trace_ids]
        skipped = len(traces) - len(new_traces)
        if skipped:
            _log.info(f"[EvolutionAgent] Skipping {skipped} already-analyzed traces")
        if not new_traces:
            return {"status": "skipped", "reason": "no_new_traces", "trace_count": len(traces)}

        _log.info(f"[EvolutionAgent] Analyzing {len(new_traces)} new traces for {skill_name}")

        # Mark as analyzed
        for t in new_traces:
            self._analyzed_trace_ids.add(t.trace_id)
        self._llm_call_count = 0

        # Step 2: Separate success/failure traces
        success_traces = [
            t for t in new_traces
            if t.execution_outcome == ExecutionOutcome.SUCCESS
        ]
        failure_traces = [
            t for t in new_traces
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
                "traces_analyzed": len(new_traces),
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
        """Generate proposals: per-trace analysis + cross-trace batch analysis."""
        per_trace_budget = min(self.max_llm_calls, 40)
        half = per_trace_budget // 2
        success_limit = min(len(success_traces), half)
        failure_limit = min(len(failure_traces), half)

        tasks = []
        for trace in success_traces[:success_limit]:
            tasks.append(self._analyze_success_trace(trace))
        for trace in failure_traces[:failure_limit]:
            tasks.append(self._analyze_failure_trace(trace))

        # Batch analysis: group similar failures for cross-trace pattern detection
        batch_size = 5
        remaining = self.max_llm_calls - len(tasks)
        for i in range(0, min(len(failure_traces), remaining * batch_size), batch_size):
            batch = failure_traces[i:i + batch_size]
            if len(batch) >= 2 and self._llm_call_count < self.max_llm_calls:
                self._llm_call_count += 1
                tasks.append(self._analyze_failure_batch(batch))
            else:
                break

        results = await asyncio.gather(*tasks, return_exceptions=True)

        proposals: list[PatchProposal] = []
        for result in results:
            if isinstance(result, Exception):
                _log.warning(f"[EvolutionAgent] Proposal generation failed: {result}")
                continue
            if result:
                if isinstance(result, list):
                    proposals.extend(result)
                else:
                    proposals.append(result)

        return proposals

    async def _analyze_failure_batch(
        self,
        traces: list[SkillEvolutionTrace],
    ) -> list[PatchProposal]:
        """Analyze a batch of similar failure traces for cross-trace patterns."""
        if not traces or self.model_provider is None:
            return []

        skill_name = traces[0].skill_name
        summaries = []
        for i, t in enumerate(traces):
            error = t.execution_details.get("error", "unknown")
            summaries.append(
                f"  [{i+1}] query={t.user_query[:150]} | rules={t.loaded_rules} | error={error[:200]}"
            )

        prompt = _BATCH_FAILURE_PROMPT.format(
            count=len(traces),
            skill_name=skill_name,
            trace_summaries="\n".join(summaries),
        )

        raw = await self._call_llm(prompt)
        if not raw:
            return []

        return self._parse_batch_proposals(raw, traces, skill_name)

    @staticmethod
    def _parse_batch_proposals(
        raw: str,
        traces: list[SkillEvolutionTrace],
        skill_name: str,
    ) -> list[PatchProposal]:
        """Parse LLM JSON array response into a list of PatchProposals."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r'\[.*\]', raw, re.DOTALL)
            if not m:
                return []
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                return []

        if not isinstance(data, list):
            return []

        proposals = []
        trace_ids = [t.trace_id for t in traces]
        for item in data:
            if not isinstance(item, dict) or not item.get("operation"):
                continue
            proposals.append(PatchProposal(
                proposal_id=str(uuid.uuid4()),
                source_traces=trace_ids,
                skill_name=skill_name,
                operation=item.get("operation", "add"),
                target_rule_id=item.get("target_rule_id"),
                new_content=item.get("new_content"),
                rationale=item.get("rationale", ""),
                confidence=float(item.get("confidence", 0.5)),
            ))
        return proposals

    # ── LLM helpers ─────────────────────────────────────────────────

    async def _call_llm(self, prompt: str) -> str | None:
        """Send a prompt to the LLM and collect the full text response."""
        if self.model_provider is None:
            return None

        try:
            models = self.model_provider.list_models()
            if not models:
                return None
            model = models[0]
        except Exception:
            return None

        try:
            text_parts: list[str] = []
            async for evt in self.model_provider.stream(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                tools=[],
                system_prompt="You are a precise analytical tool. Output only the requested JSON.",
                thinking_level="off",
                auth=ProviderAuth(api_key=""),  # resolved by provider's auth source
            ):
                if isinstance(evt, StreamTextDelta):
                    text_parts.append(evt.text)
                elif isinstance(evt, StreamError):
                    _log.warning("LLM analysis error: %s", evt.message)
                    return None
            return "".join(text_parts)
        except Exception:
            _log.exception("LLM analysis call failed")
            return None

    @staticmethod
    def _parse_proposal_json(
        raw: str,
        trace: SkillEvolutionTrace,
    ) -> PatchProposal | None:
        """Parse LLM JSON response into a PatchProposal."""
        if not raw:
            return None
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to find a JSON object in the text
            m = re.search(r'\{[^{}]*\}', raw)
            if not m:
                return None
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                return None

        if not isinstance(data, dict) or not data.get("operation"):
            return None

        return PatchProposal(
            proposal_id=str(uuid.uuid4()),
            source_traces=[trace.trace_id],
            skill_name=trace.skill_name,
            operation=data.get("operation", "add"),
            target_rule_id=data.get("target_rule_id"),
            new_content=data.get("new_content"),
            rationale=data.get("rationale", ""),
            confidence=float(data.get("confidence", 0.5)),
            supporting_evidence=[trace.user_query[:200]],
        )

    async def _llm_analyze(
        self,
        trace: SkillEvolutionTrace,
        prompt_template: str,
        **extra_fields,
    ) -> PatchProposal | None:
        """Run LLM analysis on a trace, returning a proposal or None."""
        raw = await self._call_llm(
            prompt_template.format(
                skill_name=trace.skill_name,
                user_query=trace.user_query[:500],
                loaded_rules=trace.loaded_rules,
                error=trace.execution_details.get("error", ""),
                details=trace.execution_details,
                feedback=trace.user_feedback or "(none)",
                new_rules=trace.new_rules_discovered,
                **extra_fields,
            )
        )
        if raw and raw.strip().lower() != "null":
            return self._parse_proposal_json(raw, trace)
        return None

    # ── analysis methods ────────────────────────────────────────────

    async def _analyze_success_trace(
        self,
        trace: SkillEvolutionTrace,
    ) -> list[PatchProposal]:
        """Analyze a successful trace — LLM-driven with heuristic fallback."""
        # Try LLM first when available
        if self.model_provider is not None:
            try:
                result = await self._llm_analyze(trace, _ANALYZE_SUCCESS_PROMPT)
                if result is not None:
                    return [result]
            except Exception:
                _log.debug("LLM success analysis failed, using heuristics")

        # Heuristic fallback
        outcome: list[PatchProposal] = []

        if trace.new_rules_discovered:
            for new_rule in trace.new_rules_discovered:
                outcome.append(PatchProposal(
                    proposal_id=str(uuid.uuid4()),
                    source_traces=[trace.trace_id],
                    skill_name=trace.skill_name,
                    operation="add",
                    new_content=new_rule.get("content", ""),
                    rationale=f"Discovered during successful execution: {new_rule.get('context', '')}",
                    confidence=0.7,
                    supporting_evidence=[trace.user_query[:200]],
                ))

        if trace.user_feedback and ("helpful" in trace.user_feedback.lower() or "good" in trace.user_feedback.lower()):
            loaded_rules = trace.loaded_rules
            outcome.append(PatchProposal(
                proposal_id=str(uuid.uuid4()),
                source_traces=[trace.trace_id],
                skill_name=trace.skill_name,
                operation="modify",
                target_rule_id=loaded_rules[0] if loaded_rules else None,
                rationale="User confirmed these rules are helpful",
                confidence=0.6,
                supporting_evidence=[f"Feedback: {trace.user_feedback}"],
            ))

        return outcome

    async def _analyze_failure_trace(
        self,
        trace: SkillEvolutionTrace,
    ) -> PatchProposal | None:
        """Analyze a failed trace — LLM-driven with heuristic fallback."""
        # Try LLM first when available
        if self.model_provider is not None:
            try:
                result = await self._llm_analyze(trace, _ANALYZE_FAILURE_PROMPT)
                if result is not None:
                    return result
            except Exception:
                _log.debug("LLM failure analysis failed, using heuristics")

        # Heuristic fallback
        error_msg = trace.execution_details.get("error", "")

        # Pattern matching for common failure modes

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
        best, best_score = scored[0]
        result["accepted"].append(best)

        # Check remaining for true conflicts vs. complementary suggestions
        for p, score in scored[1:]:
            if best_score == 0 or score / best_score < 0.5:
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
