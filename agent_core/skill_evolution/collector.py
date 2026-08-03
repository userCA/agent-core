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
    collector.register_skills(skills)

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
    SkillStart,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
)

from .store import SkillEvolutionStore
from .types import ExecutionOutcome, PathStep, SkillEvolutionTrace


_log = logging.getLogger(__name__)

_SKILL_TAG_RE = re.compile(r'<skill\s+name="([^"]+)"')
_INJECTED_SKILL_RE = re.compile(r'<skill\s+name="([^"]+)"\s+location=')
_AVAILABLE_SKILLS_RE = re.compile(
    r"<available_skills>(.*?)</available_skills>",
    re.DOTALL | re.IGNORECASE,
)
_RULE_ID_RE = re.compile(r"## 规则 (\d+)：")


class SkillTraceCollector(Extension):
    """Extension that collects skill execution traces for self-evolution.

    Primary mechanism: on_event(ctx, evt) — fires on every agent event.
    On AgentStart: resets turn counter and pending path steps.
    On ToolExecutionStart/End: accumulates PathStep for the current run.
    On TurnEnd: attributes traces to activated skills only (tool mapping,
    SkillStart, injected /skill blocks, or a single routed available skill).

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
        self._skill_rule_ids: dict[str, list[str]] = {}
        self._tool_to_skill: dict[str, str] = {}
        self._turn_active_skills: set[str] = set()
        self._pending_steps: list[PathStep] = []
        self._pending_args: dict[str, dict[str, Any]] = {}
        self._active_group_id: str | None = None
        self._active_task_key: str | None = None
        self._consecutive_failures: int = 0

    @property
    def name(self) -> str:
        return "skill_trace_collector"

    def register_skills(self, skills: list[Any]) -> None:
        """Register skill→tool mappings and rule IDs from loaded Skill objects."""
        for skill in skills:
            name = getattr(skill, "name", None)
            if isinstance(skill, dict):
                name = skill.get("name")
            if not name:
                continue
            tools = getattr(skill, "tools", None)
            if tools is None and isinstance(skill, dict):
                tools = skill.get("tools")
            for tool_name in tools or []:
                self._tool_to_skill[str(tool_name)] = str(name)
            content = getattr(skill, "content", None)
            if content is None and isinstance(skill, dict):
                content = skill.get("content")
            rule_ids = self._extract_rule_ids(str(content or ""))
            if rule_ids:
                self._skill_rule_ids[str(name)] = rule_ids

    @staticmethod
    def _extract_rule_ids(content: str) -> list[str]:
        return [f"rule_{num}" for num in _RULE_ID_RE.findall(content)]

    def _activate_skill(self, skill_name: str) -> None:
        self._turn_active_skills.add(skill_name)
        if skill_name not in self._loaded_skills:
            self._loaded_skills[skill_name] = self._skill_rule_ids.get(
                skill_name,
                [f"skill:{skill_name}"],
            )

    # ── primary entry point (dispatched by AgentHarness) ──────────────

    async def on_event(self, ctx: ExtensionContext, evt: AgentEvent) -> None:
        """Receive every agent event. We handle AgentStart and TurnEnd."""
        if not self.enabled:
            return

        if isinstance(evt, AgentStart):
            self._turn_count = 0
            self._turn_active_skills.clear()
            self._pending_steps.clear()
            self._pending_args.clear()
            # Keep _active_group_id / _active_task_key across starts within a GroupRollout.

        elif isinstance(evt, SkillStart):
            self._activate_skill(evt.skill_name)

        elif isinstance(evt, ToolExecutionStart):
            self._pending_args[evt.tool_call_id] = dict(evt.args or {})
            skill_name = self._tool_to_skill.get(evt.tool_name)
            if skill_name:
                self._activate_skill(skill_name)

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
        skill_names = self._resolve_skill_names_for_turn(ctx)
        if not skill_names:
            return

        user_query = self._extract_user_query(ctx)
        steps = list(self._pending_steps)
        outcome, error = self._determine_outcome(evt, steps)
        task_key = self._active_task_key or self._normalize_task_key(user_query)

        if outcome == ExecutionOutcome.FAILURE:
            self._consecutive_failures += 1
        else:
            self._consecutive_failures = 0

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
                group_id=self._active_group_id,
            )
            try:
                await self.store.save_trace(trace)
                _log.debug(
                    "Saved trace %s skill=%s outcome=%s steps=%d",
                    trace.trace_id, skill_name, outcome.value, len(steps),
                )
            except Exception:
                _log.exception("Failed to save trace for skill=%s", skill_name)

        self._turn_active_skills.clear()

    def _resolve_skill_names_for_turn(self, ctx: ExtensionContext) -> list[str]:
        """Return skill names to trace for this turn (conservative attribution)."""
        if self._turn_active_skills:
            return sorted(self._turn_active_skills)

        injected = self._extract_injected_skill_names(ctx)
        if injected:
            for name in injected:
                self._activate_skill(name)
            return injected

        available = self._extract_available_skill_names(ctx)
        if len(available) == 1:
            self._activate_skill(available[0])
            return available

        return []

    @staticmethod
    def _normalize_task_key(query: str) -> str:
        from .grouping import normalize_task_key

        return normalize_task_key(query)

    @staticmethod
    def _summarize_args(args: dict[str, Any], max_len: int = 200) -> str:
        if not args:
            return ""
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
    def _system_prompt(ctx: ExtensionContext) -> str:
        if not ctx.harness or not hasattr(ctx.harness, "state"):
            return ""
        return getattr(ctx.harness.state, "system_prompt", "") or ""

    @classmethod
    def _extract_injected_skill_names(cls, ctx: ExtensionContext) -> list[str]:
        """Skills explicitly injected via /skill: (full blocks with location=)."""
        return _INJECTED_SKILL_RE.findall(cls._system_prompt(ctx))

    @classmethod
    def _extract_available_skill_names(cls, ctx: ExtensionContext) -> list[str]:
        """Skills listed in the <available_skills> routing section."""
        sp = cls._system_prompt(ctx)
        match = _AVAILABLE_SKILLS_RE.search(sp)
        if not match:
            return []
        return _SKILL_TAG_RE.findall(match.group(1))

    @staticmethod
    def _extract_text_from_content(content: Any) -> str:
        """Normalize user message content to plain text."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if hasattr(item, "text"):
                    parts.append(str(item.text))
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    parts.append(item)
            return " ".join(p for p in parts if p).strip()
        if hasattr(content, "text"):
            return str(content.text).strip()
        text = str(content).strip()
        # Fallback: parse TextContent repr like [TextContent(type='text', text='...')]
        m = re.search(r"text='([^']*)'", text)
        if m and text.startswith("[TextContent"):
            return m.group(1)
        m = re.search(r'text="([^"]*)"', text)
        if m and text.startswith("[TextContent"):
            return m.group(1)
        return text[:500]

    @classmethod
    def _extract_user_query(cls, ctx: ExtensionContext) -> str:
        """Extract the last user message from agent state."""
        if not ctx.harness or not hasattr(ctx.harness, "state"):
            return ""
        messages = getattr(ctx.harness.state, "messages", []) or []
        for msg in reversed(messages):
            if hasattr(msg, "role") and msg.role == "user":
                if hasattr(msg, "content"):
                    return cls._extract_text_from_content(msg.content)[:500]
        return ""

    @staticmethod
    def _determine_outcome(
        evt: TurnEnd,
        steps: list[PathStep] | None = None,
    ) -> tuple[ExecutionOutcome, str]:
        """Determine execution outcome from TurnEnd and accumulated tool steps."""
        msg = evt.message
        if hasattr(msg, "error_message") and msg.error_message:
            return ExecutionOutcome.FAILURE, str(msg.error_message)
        if hasattr(msg, "stop_reason") and msg.stop_reason in ("error", "aborted"):
            return ExecutionOutcome.FAILURE, f"stop_reason={msg.stop_reason}"
        for tr in (evt.tool_results or []):
            if hasattr(tr, "is_error") and tr.is_error:
                return ExecutionOutcome.FAILURE, "tool execution error"
        error_steps = [s for s in (steps or []) if s.is_error]
        if error_steps:
            summary = error_steps[0].error_summary or f"tool {error_steps[0].tool_name} failed"
            return ExecutionOutcome.FAILURE, summary
        return ExecutionOutcome.SUCCESS, ""

    def set_rollout_context(
        self,
        group_id: str,
        task_key: str | None = None,
    ) -> None:
        """Tag subsequent traces with a shared group_id (GroupRollout)."""
        self._active_group_id = group_id
        if task_key is not None:
            self._active_task_key = task_key

    def clear_rollout_context(self) -> None:
        """Clear GroupRollout tagging after a multi-sample batch finishes."""
        self._active_group_id = None
        self._active_task_key = None

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    # ── optional explicit API ─────────────────────────────────────────

    async def on_before_agent_start(
        self, ctx: ExtensionContext, prompt: str = "", system_prompt: str = ""
    ) -> dict | None:
        """Reset per-run step buffers. Kept for API compatibility."""
        if not self.enabled:
            return None
        self._turn_count = 0
        self._turn_active_skills.clear()
        self._pending_steps.clear()
        self._pending_args.clear()
        return None

    async def on_skill_loaded(
        self,
        skill_name: str,
        rule_ids: list[str],
        ctx: ExtensionContext | None = None,
    ) -> None:
        """Register skill→rule mapping for more precise trace data."""
        if not self.enabled:
            return
        self._loaded_skills[skill_name] = rule_ids
        self._activate_skill(skill_name)
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
        """Manually attach user feedback to a trace (append-only)."""
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
    skills: list[Any] | None = None,
) -> SkillTraceCollector:
    """Factory function to create and configure a trace collector."""
    from .store import create_skill_evolution_store

    store = create_skill_evolution_store(store_type, storage_path)
    collector = SkillTraceCollector(store, enabled=enabled)
    if skills:
        collector.register_skills(skills)
    return collector
