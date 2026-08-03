"""Skill Evolution Memory Store.

This module provides persistent storage for skill evolution traces,
enabling offline analysis and batch processing.

The store is intentionally simple - it's a write-optimized append-only
log that can be queried by various criteria. Actual analysis happens
in the OfflineEvolutionAgent.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from .types import ExecutionOutcome, PathStep, SkillEvolutionTrace


def _trace_to_dict(trace: SkillEvolutionTrace) -> dict:
    outcome = trace.execution_outcome
    outcome_val = outcome.value if isinstance(outcome, ExecutionOutcome) else str(outcome)
    return {
        "trace_id": trace.trace_id,
        "timestamp": trace.timestamp,
        "session_id": trace.session_id,
        "user_query": trace.user_query,
        "skill_name": trace.skill_name,
        "loaded_rules": trace.loaded_rules,
        "execution_outcome": outcome_val,
        "execution_details": trace.execution_details,
        "new_rules_discovered": trace.new_rules_discovered,
        "user_feedback": trace.user_feedback,
        "regression_info": trace.regression_info,
        "steps": [s.to_dict() for s in (trace.steps or [])],
        "group_id": trace.group_id,
        "task_key": trace.task_key,
        "reward": trace.reward,
        "advantage": trace.advantage,
        "human_signal": trace.human_signal,
    }


def _trace_from_dict(data: dict) -> SkillEvolutionTrace:
    raw_outcome = data.get("execution_outcome", "success")
    if isinstance(raw_outcome, ExecutionOutcome):
        outcome = raw_outcome
    else:
        try:
            outcome = ExecutionOutcome(raw_outcome)
        except ValueError:
            outcome = ExecutionOutcome.SUCCESS

    steps_data = data.get("steps") or []
    steps = [
        PathStep.from_dict(s) if isinstance(s, dict) else s
        for s in steps_data
    ]

    return SkillEvolutionTrace(
        trace_id=data["trace_id"],
        timestamp=data.get("timestamp", 0.0),
        session_id=data.get("session_id"),
        user_query=data.get("user_query", ""),
        skill_name=data.get("skill_name", ""),
        loaded_rules=data.get("loaded_rules", []),
        execution_outcome=outcome,
        execution_details=data.get("execution_details", {}),
        new_rules_discovered=data.get("new_rules_discovered", []),
        user_feedback=data.get("user_feedback"),
        regression_info=data.get("regression_info"),
        steps=steps,
        group_id=data.get("group_id"),
        task_key=data.get("task_key", ""),
        reward=data.get("reward"),
        advantage=data.get("advantage"),
        human_signal=data.get("human_signal"),
    )


class SkillEvolutionStore(ABC):
    """Abstract interface for storing skill evolution traces.

    Implementations:
    - InMemorySkillEvolutionStore: For testing
    - JsonlSkillEvolutionStore: For production (append-only JSONL)
    - MongoSkillEvolutionStore: For distributed deployments (optional)
    """

    @abstractmethod
    async def save_trace(self, trace: SkillEvolutionTrace) -> None:
        """Persist a single trace."""
        pass

    @abstractmethod
    async def get_traces(
        self,
        skill_name: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkillEvolutionTrace]:
        """Query traces with optional filters.

        Args:
            skill_name: Filter by skill name
            outcome: Filter by execution outcome ("success", "failure", etc.)
            limit: Max number of traces to return
            offset: Skip N traces (for pagination)

        Returns:
            List of matching traces, ordered by timestamp descending
        """
        pass

    @abstractmethod
    async def get_trace_count(
        self,
        skill_name: str | None = None,
        outcome: str | None = None,
    ) -> int:
        """Count traces matching criteria."""
        pass

    @abstractmethod
    async def delete_old_traces(self, older_than_days: int = 30) -> int:
        """Clean up old traces to prevent unbounded growth.

        Args:
            older_than_days: Delete traces older than N days

        Returns:
            Number of traces deleted
        """
        pass

    async def get_analyzed_trace_ids(self, skill_name: str) -> set[str]:
        """Return trace IDs already processed by offline analysis for a skill."""
        return set()

    async def mark_traces_analyzed(self, skill_name: str, trace_ids: list[str]) -> None:
        """Persist trace IDs as analyzed for a skill."""
        return None


class InMemorySkillEvolutionStore(SkillEvolutionStore):
    """In-memory implementation for testing."""

    def __init__(self):
        self._traces: list[SkillEvolutionTrace] = []
        self._analyzed: dict[str, set[str]] = {}

    async def save_trace(self, trace: SkillEvolutionTrace) -> None:
        self._traces.append(trace)

    async def get_analyzed_trace_ids(self, skill_name: str) -> set[str]:
        return set(self._analyzed.get(skill_name, set()))

    async def mark_traces_analyzed(self, skill_name: str, trace_ids: list[str]) -> None:
        bucket = self._analyzed.setdefault(skill_name, set())
        bucket.update(trace_ids)

    async def get_traces(
        self,
        skill_name: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkillEvolutionTrace]:
        filtered = self._traces

        if skill_name:
            filtered = [t for t in filtered if t.skill_name == skill_name]
        if outcome:
            filtered = [t for t in filtered if t.execution_outcome.value == outcome]

        # Sort by timestamp descending (newest first)
        filtered.sort(key=lambda t: t.timestamp, reverse=True)

        return filtered[offset : offset + limit]

    async def get_trace_count(
        self,
        skill_name: str | None = None,
        outcome: str | None = None,
    ) -> int:
        filtered = self._traces
        if skill_name:
            filtered = [t for t in filtered if t.skill_name == skill_name]
        if outcome:
            filtered = [t for t in filtered if t.execution_outcome.value == outcome]
        return len(filtered)

    async def delete_old_traces(self, older_than_days: int = 30) -> int:
        import time

        cutoff = time.time() - (older_than_days * 86400)
        before = len(self._traces)
        self._traces = [t for t in self._traces if t.timestamp >= cutoff]
        return before - len(self._traces)


class JsonlSkillEvolutionStore(SkillEvolutionStore):
    """JSONL-based persistent store for production use.

    Each trace is appended as a single JSON line to a log file.
    This format is:
    - Write-optimized (append-only, no random access needed)
    - Human-readable (can inspect with `tail -f`)
    - Easy to process with standard tools (jq, awk, etc.)
    """

    def __init__(
        self,
        storage_path: str | Path = "~/.agent-core/skill-evolution-traces.jsonl",
        analyzed_path: str | Path | None = None,
    ):
        self.storage_path = Path(storage_path).expanduser()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if analyzed_path is None:
            analyzed_path = self.storage_path.with_name("skill-evolution-analyzed.json")
        self.analyzed_path = Path(analyzed_path).expanduser()
        self._analyzed_cache: dict[str, set[str]] | None = None

    def _load_analyzed(self) -> dict[str, set[str]]:
        if self._analyzed_cache is not None:
            return self._analyzed_cache
        if not self.analyzed_path.exists():
            self._analyzed_cache = {}
            return self._analyzed_cache
        with open(self.analyzed_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._analyzed_cache = {
            skill: set(ids) for skill, ids in raw.items() if isinstance(ids, list)
        }
        return self._analyzed_cache

    def _save_analyzed(self) -> None:
        if self._analyzed_cache is None:
            return
        self.analyzed_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {skill: sorted(ids) for skill, ids in self._analyzed_cache.items()}
        with open(self.analyzed_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    async def get_analyzed_trace_ids(self, skill_name: str) -> set[str]:
        return set(self._load_analyzed().get(skill_name, set()))

    async def mark_traces_analyzed(self, skill_name: str, trace_ids: list[str]) -> None:
        analyzed = self._load_analyzed()
        bucket = analyzed.setdefault(skill_name, set())
        bucket.update(trace_ids)
        self._save_analyzed()

    async def save_trace(self, trace: SkillEvolutionTrace) -> None:
        """Append trace as a single JSON line."""
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(_trace_to_dict(trace)) + "\n")

    async def get_traces(
        self,
        skill_name: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkillEvolutionTrace]:
        """Read and filter traces from JSONL file.

        Note: This reads the entire file into memory. For large datasets,
        consider using indexed storage or database backend.
        """
        if not self.storage_path.exists():
            return []

        traces = []
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                data = json.loads(line)
                trace = _trace_from_dict(data)

                # Apply filters
                if skill_name and trace.skill_name != skill_name:
                    continue
                if outcome:
                    # Handle both enum and string comparison
                    trace_outcome = trace.execution_outcome.value if hasattr(trace.execution_outcome, 'value') else trace.execution_outcome
                    if trace_outcome != outcome:
                        continue

                traces.append(trace)

        # Sort by timestamp descending
        traces.sort(key=lambda t: t.timestamp, reverse=True)
        return traces[offset : offset + limit]

    async def get_trace_count(
        self,
        skill_name: str | None = None,
        outcome: str | None = None,
    ) -> int:
        """Count traces without loading all into memory."""
        if not self.storage_path.exists():
            return 0

        count = 0
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                data = json.loads(line)

                if skill_name and data.get("skill_name") != skill_name:
                    continue
                if outcome and data.get("execution_outcome") != outcome:
                    continue

                count += 1

        return count

    async def delete_old_traces(self, older_than_days: int = 30) -> int:
        """Rewrite file excluding old traces.

        Since this is append-only, we can't truly "delete" lines. Instead,
        we rewrite the file with only recent traces.
        """
        import time

        if not self.storage_path.exists():
            return 0

        cutoff = time.time() - (older_than_days * 86400)

        # Read all traces
        recent_traces = []
        deleted_count = 0

        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                data = json.loads(line)
                if data["timestamp"] >= cutoff:
                    recent_traces.append(line)
                else:
                    deleted_count += 1

        # Rewrite file with only recent traces
        with open(self.storage_path, "w", encoding="utf-8") as f:
            for line in recent_traces:
                f.write(line + "\n")

        return deleted_count


def create_skill_evolution_store(
    store_type: str = "jsonl",
    storage_path: str | None = None,
) -> SkillEvolutionStore:
    """Factory function to create appropriate store implementation.

    Args:
        store_type: "memory" for testing, "jsonl" for production
        storage_path: Custom path for jsonl store (optional)

    Returns:
        Configured SkillEvolutionStore instance
    """
    if store_type == "memory":
        return InMemorySkillEvolutionStore()
    elif store_type == "jsonl":
        path = storage_path or "~/.agent-core/skill-evolution-traces.jsonl"
        return JsonlSkillEvolutionStore(path)
    else:
        raise ValueError(f"Unknown store type: {store_type}")
