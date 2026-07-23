"""Skill Execution Trace Collector.

This extension automatically captures traces whenever skills are loaded and applied,
storing them for later offline analysis by the SkillEvolutionAgent.

Trace collection works through the standard Extension.on_event hook, which is
already dispatched by AgentHarness. No additional wiring needed — just register
the collector as an extension and it self-drives from TurnEnd events.

Usage:
    from agent_core.skill_evolution.collector import SkillTraceCollector
    from agent_core.skill_evolution.store import create_skill_evolution_store
    from agent_core.session.harness import AgentHarness

    store = create_skill_evolution_store("jsonl")
    collector = SkillTraceCollector(store)

    harness = AgentHarness(..., extensions=[collector])
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from agent_core.extensions.base import Extension, ExtensionContext
from agent_core.core.events import (
    AgentEvent,
    AgentStart,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
)

from .store import SkillEvolutionStore
from .types import ExecutionOutcome, PathStep, SkillEvolutionTrace


_log = logging.getLogger(__name__)

# Regex to extract skill names from <skill name="..."> tags in system prompt
_SKILL_TAG_RE = re.compile(r'<skill\s+name="([^"]+)"')


class SkillTraceCollector(Extension):
    """Extension that collects skill execution traces for self-evolution.

    Primary mechanism: on_event(ctx, evt) — fires on every agent event.
    On AgentStart: resets turn counter and pending path steps.
    On ToolExecutionStart/End: accumulates PathStep for the current run.
    On TurnEnd:   extracts skill names from system_prompt (via ctx.harness.state),
                  determines outcome from message/tool results, persists trace.

    Also provides on_skill_loaded() as an optional explicit API for callers
    that want to provide precise rule IDs rather than relying on auto-detection.
    """

    def __init__(
        self,
        store: SkillEvolutionStore,
        enabled: bool = True,
    ):
        self.store = store
        self.enabled = enabled
        self._turn_count = 0
        self._loaded_skills: dict[str, list[str]] = {}
        self._pending_steps: list[PathStep] = []
        self._pending_args: dict[str, dict[str, Any]] = {}

    @property
    def name(self) -> str:
        return "skill_trace_collector"

    # ── primary entry point (dispatched by AgentHarness) ──────────────

    async def on_event(self, ctx: ExtensionContext, evt: AgentEvent) -> None:
        """Receive every agent event. We handle AgentStart and TurnEnd."""
        if not self.enabled:
            return

        if isinstance(evt, AgentStart):
            self._turn_count = 0
            self._pending_steps.clear()
            self._pending_args.clear()

        elif isinstance(evt, ToolExecutionStart):
            self._pending_args[evt.tool_call_id] = dict(evt.args or {})

        elif isinstance(evt, ToolExecutionEnd):
            args = self._pending_args.pop(evt.tool_call_id, {})
            error_summary = ""
            if evt.is_error:
                error_summary = self._summarize_result(evt.result, max_len=120)
            self._pending_steps.append(
                PathStep(
                    tool_name=evt.tool_name,
                    args_summary=self._summarize_args(args),
                    is_error=bool(evt.is_error),
                    error_summary=error_summary,
                    tool_call_id=evt.tool_call_id or "",
                )
            )

        elif isinstance(evt, TurnEnd):
            self._turn_count += 1
            await self._handle_turn_end(ctx, evt)

    # ── turn-end handling ─────────────────────────────────────────────

    async def _handle_turn_end(self, ctx: ExtensionContext, evt: TurnEnd) -> None:
        skill_names = self._extract_skill_names(ctx)
        if not skill_names:
            return

        user_query = self._extract_user_query(ctx)
        outcome, error = self._determine_outcome(evt)
        steps = list(self._pending_steps)
        task_key = self._normalize_task_key(user_query)

        for skill_name in skill_names:
            rule_ids = self._loaded_skills.get(skill_name, [])
            trace = SkillEvolutionTrace(
                trace_id=str(uuid.uuid4()),
                session_id=ctx.session_id,
                user_query=user_query,
                skill_name=skill_name,
                loaded_rules=rule_ids,
                execution_outcome=outcome,
                execution_details={
                    "turn_index": self._turn_count,
                    **({"error": error} if error else {}),
                },
                steps=steps,
                task_key=task_key,
            )
            try:
                await self.store.save_trace(trace)
                _log.debug(
                    "Saved trace %s skill=%s outcome=%s steps=%d",
                    trace.trace_id, skill_name, outcome.value, len(steps),
                )
            except Exception:
                _log.exception("Failed to save trace for skill=%s", skill_name)

    @staticmethod
    def _normalize_task_key(query: str) -> str:
        from .grouping import normalize_task_key

        return normalize_task_key(query)

    @staticmethod
    def _summarize_args(args: dict[str, Any], max_len: int = 200) -> str:
        if not args:
            return ""
        # Prefer short values first so key names survive truncation.
        parts: list[str] = []
        for key in sorted(args.keys(), key=lambda k: (len(str(args[k])), k)):
            val = args[key]
            text = str(val)
            if len(text) > 60:
                text = text[:57] + "..."
            parts.append(f"{key}={text}")
        joined = ", ".join(parts)
        if len(joined) > max_len:
            return joined[: max_len - 3] + "..."
        return joined

    @staticmethod
    def _summarize_result(result: Any, max_len: int = 120) -> str:
        text = str(result) if result is not None else ""
        if len(text) > max_len:
            return text[: max_len - 3] + "..."
        return text

    @staticmethod
    def _extract_skill_names(ctx: ExtensionContext) -> list[str]:
        """Parse <skill name="..."> tags from the agent's system prompt."""
        if not ctx.harness or not hasattr(ctx.harness, 'state'):
            return []
        sp = getattr(ctx.harness.state, 'system_prompt', '') or ''
        return _SKILL_TAG_RE.findall(sp)

    @staticmethod
    def _extract_user_query(ctx: ExtensionContext) -> str:
        """Extract the last user message from agent state."""
        if not ctx.harness or not hasattr(ctx.harness, 'state'):
            return ""
        messages = getattr(ctx.harness.state, 'messages', []) or []
        for msg in reversed(messages):
            if hasattr(msg, 'role') and msg.role == "user":
                if hasattr(msg, 'content'):
                    return str(msg.content)[:500]
        return ""

    @staticmethod
    def _determine_outcome(evt: TurnEnd) -> tuple[ExecutionOutcome, str]:
        """Determine execution outcome from a TurnEnd event."""
        msg = evt.message
        # Check for explicit error on the assistant message
        if hasattr(msg, 'error_message') and msg.error_message:
            return ExecutionOutcome.FAILURE, str(msg.error_message)
        if hasattr(msg, 'stop_reason') and msg.stop_reason in ("error", "aborted"):
            return ExecutionOutcome.FAILURE, f"stop_reason={msg.stop_reason}"
        # Check tool results for errors
        for tr in (evt.tool_results or []):
            if hasattr(tr, 'is_error') and tr.is_error:
                return ExecutionOutcome.FAILURE, "tool execution error"
        return ExecutionOutcome.SUCCESS, ""

    # ── optional explicit API ─────────────────────────────────────────
    # These are not dispatched automatically; callers may invoke them
    # directly when they have more precise data than on_event provides.

    async def on_before_agent_start(
        self, ctx: ExtensionContext, prompt: str = "", system_prompt: str = ""
    ) -> dict | None:
        """Reset state for a new agent run. Kept for API compatibility."""
        if not self.enabled:
            return None
        self._turn_count = 0
        self._loaded_skills.clear()
        self._pending_steps.clear()
        self._pending_args.clear()
        return None

    async def on_skill_loaded(
        self,
        skill_name: str,
        rule_ids: list[str],
        ctx: ExtensionContext | None = None,
    ) -> None:
        """Register skill→rule mapping for more precise trace data.

        Call this after skill discovery if you want rule_ids populated in
        traces. If not called, traces will have empty loaded_rules.
        """
        if not self.enabled:
            return
        self._loaded_skills[skill_name] = rule_ids
        _log.debug("Skill loaded: %s with %d rules", skill_name, len(rule_ids))

    async def on_turn_end(self, ctx: ExtensionContext, evt: TurnEnd) -> dict | None:
        """Kept for API compatibility; on_event handles this now."""
        return None

    async def on_error(self, ctx: ExtensionContext, error: Exception) -> dict | None:
        """Kept for API compatibility."""
        return None

    async def record_user_feedback(
        self,
        trace_id: str,
        feedback: str,
        was_helpful: bool | None = None,
    ) -> None:
        """Manually attach user feedback to a trace.

        Since traces are append-only, this creates a new feedback trace
        that references the original. The offline analyzer joins related traces.
        """
        if was_helpful is True:
            outcome = ExecutionOutcome.SUCCESS
        elif was_helpful is False:
            outcome = ExecutionOutcome.FAILURE
        else:
            outcome = ExecutionOutcome.PARTIAL

        feedback_trace = SkillEvolutionTrace(
            trace_id=f"{trace_id}-feedback",
            user_query="",
            skill_name="",
            execution_outcome=outcome,
            user_feedback=feedback,
            execution_details={"original_trace_id": trace_id, "type": "feedback"},
        )
        await self.store.save_trace(feedback_trace)
        _log.debug("Recorded feedback for trace %s", trace_id)


def create_skill_trace_collector(
    store_type: str = "jsonl",
    storage_path: str | None = None,
    enabled: bool = True,
) -> SkillTraceCollector:
    """Factory function to create and configure a trace collector."""
    from .store import create_skill_evolution_store

    store = create_skill_evolution_store(store_type, storage_path)
    return SkillTraceCollector(store, enabled=enabled)
