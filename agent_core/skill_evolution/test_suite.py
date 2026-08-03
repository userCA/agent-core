"""Build validation test cases from skill evolution traces."""

from __future__ import annotations

from .store import SkillEvolutionStore
from .types import ExecutionOutcome, SkillEvolutionTrace, TestCase


def trace_to_test_case(trace: SkillEvolutionTrace) -> TestCase | None:
    query = (trace.user_query or "").strip()
    if not query:
        return None

    if trace.execution_outcome == ExecutionOutcome.SUCCESS:
        expected = "complete without tool errors"
        description = f"Regression: successful trace {trace.trace_id[:8]}"
    elif trace.execution_outcome in (ExecutionOutcome.FAILURE, ExecutionOutcome.PARTIAL):
        err = trace.execution_details.get("error", "avoid failure")
        expected = str(err)[:200]
        description = f"Fix failure: {trace.trace_id[:8]}"
    else:
        expected = "no_error"
        description = f"Trace {trace.trace_id[:8]}"

    return TestCase(
        test_id=trace.trace_id[:24],
        description=description,
        input_query=query[:500],
        expected_behavior=expected,
        success_criteria="no_error",
        tags=[trace.execution_outcome.value if hasattr(trace.execution_outcome, "value") else str(trace.execution_outcome)],
    )


def build_test_cases_from_traces(
    traces: list[SkillEvolutionTrace],
    *,
    max_cases: int = 5,
) -> list[TestCase]:
    """Convert traces to validation test cases (dedupe by query)."""
    seen: set[str] = set()
    cases: list[TestCase] = []
    for trace in traces:
        tc = trace_to_test_case(trace)
        if tc is None:
            continue
        key = tc.input_query.lower()
        if key in seen:
            continue
        seen.add(key)
        cases.append(tc)
        if len(cases) >= max_cases:
            break
    return cases


async def build_test_cases_from_trace_ids(
    store: SkillEvolutionStore,
    trace_ids: list[str],
    *,
    skill_name: str | None = None,
    max_cases: int = 5,
) -> list[TestCase]:
    """Load traces by id from store and build test cases."""
    if not trace_ids:
        return []

    id_set = set(trace_ids)
    traces = await store.get_traces(skill_name=skill_name, limit=5000)
    matched = [t for t in traces if t.trace_id in id_set]
    if not matched:
        # Fallback: scan without skill filter
        traces = await store.get_traces(limit=5000)
        matched = [t for t in traces if t.trace_id in id_set]

    # Preserve proposal source order
    by_id = {t.trace_id: t for t in matched}
    ordered = [by_id[tid] for tid in trace_ids if tid in by_id]
    return build_test_cases_from_traces(ordered, max_cases=max_cases)
