"""Skill Execution Trace Collector.

This extension automatically captures traces whenever skills are loaded and applied,
storing them for later offline analysis by the SkillEvolutionAgent.

Usage:
    from agent_core.skill_evolution.collector import SkillTraceCollector
    from agent_core.skill_evolution.store import create_skill_evolution_store

    store = create_skill_evolution_store("jsonl")
    collector = SkillTraceCollector(store)

    # Register with your agent/session
    session.add_extension(collector)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from agent_core.extensions.base import Extension, ExtensionContext
from agent_core.core.events import AgentEvent, TurnEnd

from .store import SkillEvolutionStore
from .types import ExecutionOutcome, SkillEvolutionTrace


_log = logging.getLogger(__name__)


class SkillTraceCollector(Extension):
    """Extension that collects skill execution traces for self-evolution.

    This extension hooks into the agent lifecycle to capture:
    1. When a skill is loaded (which rules were activated)
    2. How the guided task performed (success/failure)
    3. Any new rules discovered during execution

    Traces are persisted to a SkillEvolutionStore for batch offline analysis.
    """

    def __init__(
        self,
        store: SkillEvolutionStore,
        enabled: bool = True,
    ):
        """Initialize the trace collector.

        Args:
            store: Backend for persisting traces
            enabled: Whether to actively collect traces (can disable for debugging)
        """
        self.store = store
        self.enabled = enabled
        self._current_trace: SkillEvolutionTrace | None = None
        self._loaded_skills: dict[str, list[str]] = {}  # skill_name → rule_ids

    @property
    def name(self) -> str:
        return "skill_trace_collector"

    async def on_before_agent_start(self, ctx: ExtensionContext) -> dict | None:
        """Called when agent starts processing a new user query.

        We capture the initial query here to start a new trace.
        """
        if not self.enabled:
            return None

        # Reset state for new turn
        self._current_trace = None
        self._loaded_skills.clear()

        # Extract user query from context
        user_query = ""
        if ctx and hasattr(ctx, 'context') and ctx.context:
            if hasattr(ctx.context, 'messages') and ctx.context.messages:
                # Get last user message
                for msg in reversed(ctx.context.messages):
                    if hasattr(msg, 'role') and msg.role == "user":
                        if hasattr(msg, 'content'):
                            user_query = str(msg.content)[:500]  # Truncate long queries
                        break

        _log.debug(f"[SkillTraceCollector] Starting new trace for query: {user_query[:50]}...")

        return None

    async def on_skill_loaded(
        self,
        skill_name: str,
        rule_ids: list[str],
        ctx: ExtensionContext | None = None,
    ) -> None:
        """Called when a skill is loaded during prompt building.

        This should be invoked by SystemPromptBuilder or whoever loads skills.

        Args:
            skill_name: Name of the loaded skill (e.g., "dev-process-backend")
            rule_ids: List of rule IDs that were activated
            ctx: Optional extension context for session info
        """
        if not self.enabled:
            return

        self._loaded_skills[skill_name] = rule_ids
        _log.debug(f"[SkillTraceCollector] Skill loaded: {skill_name} with {len(rule_ids)} rules")

        # If we don't have a trace yet, create one now
        if self._current_trace is None:
            session_id = None
            if ctx and hasattr(ctx, 'session_id'):
                session_id = ctx.session_id
            
            self._current_trace = SkillEvolutionTrace(
                trace_id=str(uuid.uuid4()),
                session_id=session_id,
                skill_name=skill_name,
                loaded_rules=rule_ids,
            )

    async def on_turn_end(self, ctx: ExtensionContext, evt: TurnEnd) -> dict | None:
        """Called at the end of each agent turn.

        We finalize the trace here based on whether the turn succeeded or failed.
        """
        if not self.enabled or not self._current_trace:
            return None

        # Determine outcome based on event state
        if evt.state and evt.state.error_message:
            self._current_trace.mark_failure(
                error=evt.state.error_message,
                details={"turn_index": evt.turn_index},
            )
        else:
            self._current_trace.mark_success(
                details={
                    "turn_index": evt.turn_index,
                    "messages_count": len(evt.state.messages) if evt.state else 0,
                }
            )

        # Fill in missing fields from context
        if not self._current_trace.user_query and ctx:
            if hasattr(ctx, 'context') and ctx.context:
                if hasattr(ctx.context, 'messages') and ctx.context.messages:
                    for msg in reversed(ctx.context.messages):
                        if hasattr(msg, 'role') and msg.role == "user":
                            if hasattr(msg, 'content'):
                                self._current_trace.user_query = str(msg.content)[:500]
                            break

        if not self._current_trace.session_id:
            if ctx and hasattr(ctx, 'session_id'):
                self._current_trace.session_id = ctx.session_id

        # Persist the trace
        try:
            await self.store.save_trace(self._current_trace)
            _log.info(
                f"[SkillTraceCollector] Saved trace: {self._current_trace.trace_id} "
                f"(skill={self._current_trace.skill_name}, outcome={self._current_trace.execution_outcome.value})"
            )
        except Exception as e:
            _log.error(f"[SkillTraceCollector] Failed to save trace: {e}", exc_info=True)

        # Reset for next turn
        self._current_trace = None
        self._loaded_skills.clear()

        return None

    async def on_error(self, ctx: ExtensionContext, error: Exception) -> dict | None:
        """Called when an unhandled error occurs.

        We mark the current trace as failed and save it.
        """
        if not self.enabled or not self._current_trace:
            return None

        self._current_trace.mark_failure(
            error=str(error),
            details={"exception_type": type(error).__name__},
        )

        try:
            await self.store.save_trace(self._current_trace)
            _log.warning(
                f"[SkillTraceCollector] Saved failed trace: {self._current_trace.trace_id}"
            )
        except Exception as e:
            _log.error(f"[SkillTraceCollector] Failed to save error trace: {e}", exc_info=True)

        self._current_trace = None
        self._loaded_skills.clear()

        return None

    async def record_user_feedback(
        self,
        trace_id: str,
        feedback: str,
        was_helpful: bool | None = None,
    ) -> None:
        """Manually attach user feedback to a trace.

        This can be called by UI components when user explicitly rates
        the assistant's response.

        Args:
            trace_id: ID of the trace to update
            feedback: User's comment or rating
            was_helpful: Binary helpful/not-helpful flag
        """
        # Note: Since traces are append-only, we can't update existing records.
        # Instead, we create a new "feedback" trace that references the original.
        # The offline analyzer will join related traces.

        feedback_trace = SkillEvolutionTrace(
            trace_id=f"{trace_id}-feedback",
            user_query="",
            skill_name="",
            execution_outcome=ExecutionOutcome.SUCCESS if was_helpful else ExecutionOutcome.FAILURE,
            user_feedback=feedback,
            execution_details={"original_trace_id": trace_id, "type": "feedback"},
        )

        await self.store.save_trace(feedback_trace)
        _log.debug(f"[SkillTraceCollector] Recorded feedback for trace {trace_id}")


def create_skill_trace_collector(
    store_type: str = "jsonl",
    storage_path: str | None = None,
    enabled: bool = True,
) -> SkillTraceCollector:
    """Factory function to create and configure a trace collector.

    Args:
        store_type: "memory" for testing, "jsonl" for production
        storage_path: Custom path for jsonl store
        enabled: Whether to actively collect traces

    Returns:
        Configured SkillTraceCollector instance
    """
    from .store import create_skill_evolution_store

    store = create_skill_evolution_store(store_type, storage_path)
    return SkillTraceCollector(store, enabled=enabled)
