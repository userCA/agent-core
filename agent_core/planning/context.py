"""Plan context formatting and Extension injection."""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_core.core.messages import CustomMessage
from agent_core.extensions.base import ExtensionContext
from agent_core.planning.store import PlanStore
from agent_core.planning.types import Plan

logger = logging.getLogger(__name__)


def format_plan_for_prompt(plan: Plan | None) -> str:
    if plan is None:
        return ""
    lines = [f"Current plan: {plan.title} [{plan.status}] v{plan.version}"]
    for s in plan.steps:
        mark = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
            "failed": "[!]",
            "cancelled": "[-]",
            "skipped": "[~]",
        }.get(s.status, "[ ]")
        extra = f" — {s.detail}" if s.detail else ""
        lines.append(f"  {mark} {s.id}: {s.title}{extra}")
    return "\n".join(lines)


class PlanningContextExtension:
    """Inject current plan summary before each agent start and auto-advance steps."""

    name = "planning_context"

    def __init__(self, plan_store: PlanStore) -> None:
        self._store = plan_store
        self._tool_calls_in_step: int = 0  # track tool calls while a step is in_progress

    async def on_event(self, ctx: ExtensionContext, evt: Any) -> None:
        return None

    async def on_before_agent_start(
        self, ctx: ExtensionContext, prompt: str, system_prompt: str
    ) -> dict[str, Any] | None:
        # Auto-complete: if a step was in_progress and had tool calls in the previous turn,
        # mark it as completed (the LLM has moved on to a new turn).
        plan = self._store.plan
        if plan is not None and plan.status == "active" and self._tool_calls_in_step > 0:
            in_progress_step = next(
                (s for s in plan.steps if s.status == "in_progress"), None
            )
            if in_progress_step is not None:
                try:
                    self._store.set_status(
                        step_id=in_progress_step.id, status="completed"
                    )
                    await self._store.persist()
                    logger.debug(
                        "Auto-completed plan step '%s' (had %d tool calls)",
                        in_progress_step.id,
                        self._tool_calls_in_step,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to auto-complete step %s: %s",
                        in_progress_step.id,
                        exc,
                    )
        self._tool_calls_in_step = 0

        text = format_plan_for_prompt(self._store.plan)
        if not text:
            return None
        return {
            "message": CustomMessage(
                custom_type="plan_context",
                content=text,
                display=False,
                timestamp=time.time(),
            )
        }

    async def on_before_tool_call(
        self, ctx: ExtensionContext, tool_call: Any
    ) -> dict[str, Any] | None:
        """Auto-advance: manage step lifecycle around non-plan tool calls."""
        name = getattr(tool_call, "name", "")
        if name in ("manage_plan", ""):
            return None
        plan = self._store.plan
        if plan is None or plan.status != "active":
            return None

        # Find current in_progress step
        in_progress_step = next((s for s in plan.steps if s.status == "in_progress"), None)

        if in_progress_step is not None:
            # Step already in_progress — count tool calls
            self._tool_calls_in_step += 1
        else:
            # No step in_progress — auto-advance the next pending step
            for step in plan.steps:
                if step.status == "pending":
                    try:
                        self._store.set_status(step_id=step.id, status="in_progress")
                        await self._store.persist()
                        self._tool_calls_in_step = 1
                        logger.debug("Auto-advanced plan step '%s' to in_progress", step.id)
                    except Exception as exc:
                        logger.warning("Failed to auto-advance step %s: %s", step.id, exc)
                    break
        return None

    async def on_after_tool_call(
        self, ctx: ExtensionContext, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        """Auto-complete: mark in_progress step as done when enough evidence."""
        name = getattr(tool_call, "name", "")
        if name in ("manage_plan", ""):
            return None
        plan = self._store.plan
        if plan is None or plan.status != "active":
            return None

        in_progress_step = next((s for s in plan.steps if s.status == "in_progress"), None)
        if in_progress_step is None:
            return None

        # Heuristic: if LLM already called manage_plan to update this step, don't interfere.
        # Otherwise, auto-complete after the step has had tool calls and the LLM moves on
        # (detected by the next before_tool_call advancing a new step).
        # We don't auto-complete here because a step might need multiple tool calls.
        # The LLM should explicitly call manage_plan(set_status=completed) for best results.
        return None
