"""Skill Self-Evolution System.

This package implements automatic skill optimization based on execution traces,
inspired by Trace2Skill and EvoSkill research papers.

Architecture Overview:
─────────────────────────────────────────────────┐
│           Skill Evolution Pipeline              │
─────────────────────────────────────────────────┤
│                                                  │
│  1. Trace Collection (collector.py)             │
│     ├─→ Captures skill usage during agent runs  │
│     └─→ Stores to persistent log                │
│                                                  │
│  2. Offline Analysis (agent.py)                 │
│     ├─→ Reads batch of traces                   │
│     ├─→ Parallel proposal generation            │
│     │    ├─ Success Analysts                    │
│     │    └─ Error Analysts                      │
│     └─→ Hierarchical merge                      │
│                                                  │
│  3. Validation Gate (validation.py)             │
│     ├─→ Tests proposals against test suite      │
│     └─→ Only accepts improvements               │
│                                                  │
│  4. Skill Update                                │
│     └─→ Atomically applies accepted changes     │
│                                                  │
└─────────────────────────────────────────────────┘

Quick Start:
    from agent_core.skill_evolution import (
        create_skill_trace_collector,
        create_offline_evolution_agent,
        create_validation_gate,
    )

    # 1. Set up trace collection (runs automatically with agent)
    collector = create_skill_trace_collector("jsonl")
    session.add_extension(collector)

    # 2. Run offline analysis periodically (e.g., daily cron job)
    agent = create_offline_evolution_agent("jsonl")
    result = await agent.run_evolution_cycle(
        skill_name="dev-process-backend",
        min_traces=50,
    )

    # 3. Validate and apply accepted proposals
    gate = create_validation_gate()
    for proposal in result["final_proposals"]:
        validation_result = await gate.validate(proposal)
        if validation_result.passed:
            await gate.apply_proposal(proposal)

Key Concepts:
- Trace: Single record of skill usage (query → rules → outcome)
- Proposal: Suggested change to a skill rule
- Validation: Before/after comparison to ensure improvement
- Batch Processing: Analyze many traces together to avoid overfitting

References:
- Trace2Skill: https://arxiv.org/abs/xxxx.xxxxx (aggregate patterns from traces)
- EvoSkill: https://arxiv.org/abs/xxxx.xxxxx (validation-gated evolution)
"""

from .types import (
    ExecutionOutcome,
    EvolutionSummary,
    MergedProposal,
    PatchProposal,
    PathStep,
    RuleReference,
    SkillEvolutionTrace,
    TestCase,
    ValidationResult,
)
from .store import (
    SkillEvolutionStore,
    InMemorySkillEvolutionStore,
    JsonlSkillEvolutionStore,
    create_skill_evolution_store,
)
from .collector import (
    SkillTraceCollector,
    create_skill_trace_collector,
)
from .agent import (
    OfflineEvolutionAgent,
    create_offline_evolution_agent,
)
from .validation import (
    SkillValidationGate,
    create_validation_gate,
    evaluate_acceptance_gates,
)
from .audit import (
    write_audit_entry,
    read_audit_log,
)
from .reward import HybridReward, heuristic_reward
from .grouping import build_groups, normalize_task_key
from .relative_score import assign_advantages, score_group
from .distiller import distill_group
from .group_rollout import GroupRollout, GroupRolloutResult, should_trigger_group_rollout
from .cases import PathCase, append_case, load_cases, select_top_k_cases, format_cases_for_prompt
from .case_recall import SkillCaseRecallExtension

__all__ = [
    # Types
    "ExecutionOutcome",
    "EvolutionSummary",
    "MergedProposal",
    "PatchProposal",
    "PathStep",
    "RuleReference",
    "SkillEvolutionTrace",
    "TestCase",
    "ValidationResult",
    
    # Store
    "SkillEvolutionStore",
    "InMemorySkillEvolutionStore",
    "JsonlSkillEvolutionStore",
    "create_skill_evolution_store",
    
    # Collector
    "SkillTraceCollector",
    "create_skill_trace_collector",
    
    # Agent
    "OfflineEvolutionAgent",
    "create_offline_evolution_agent",
    
    # Validation
    "SkillValidationGate",
    "create_validation_gate",
    "evaluate_acceptance_gates",

    # Audit
    "write_audit_entry",
    "read_audit_log",

    # GRPO-style path evolution
    "HybridReward",
    "heuristic_reward",
    "build_groups",
    "normalize_task_key",
    "assign_advantages",
    "score_group",
    "distill_group",
    "GroupRollout",
    "GroupRolloutResult",
    "should_trigger_group_rollout",
    "PathCase",
    "append_case",
    "load_cases",
    "select_top_k_cases",
    "format_cases_for_prompt",
    "SkillCaseRecallExtension",
]

__version__ = "0.1.0"
