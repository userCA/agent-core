"""Plan context formatting and Extension injection."""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_core.core.messages import CustomMessage
from agent_core.extensions.base import ExtensionContext
from agent_core.planning.store import PlanStore
from agent_core.planning.types import Plan, PlanStep
from agent_core.session.tool_utils import resolve_tool_name

logger = logging.getLogger(__name__)

# Always keep plan + working-memory tools when filtering by suggested_tools.
_DEFAULT_ALWAYS_TOOLS = ("manage_plan", "working_memory")


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
        tools = (
            f" (tools: {', '.join(s.suggested_tools)})" if s.suggested_tools else ""
        )
        lines.append(f"  {mark} {s.id}: {s.title}{extra}{tools}")
    return "\n".join(lines)


def current_plan_step(plan: Plan | None) -> PlanStep | None:
    """Prefer in_progress; else first pending; else None."""
    if plan is None or plan.status != "active":
        return None
    for s in plan.steps:
        if s.status == "in_progress":
            return s
    for s in plan.steps:
        if s.status == "pending":
            return s
    return None


class PlanningContextExtension:
    """Inject plan summary; optionally shrink tool schema to current step."""

    name = "planning_context"

    def __init__(
        self,
        plan_store: PlanStore,
        *,
        always_tools: tuple[str, ...] | list[str] = _DEFAULT_ALWAYS_TOOLS,
        enable_step_action_space: bool = True,
    ) -> None:
        self._store = plan_store
        self._tool_calls_in_step: int = 0
        self._always_tools = tuple(always_tools)
        self._enable_step_action_space = enable_step_action_space
        self._last_action_space_key: str | None = None

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

        await self._sync_action_space(ctx)

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
        if name in ("manage_plan", "working_memory", ""):
            return None
        plan = self._store.plan
        if plan is None or plan.status != "active":
            return None

        in_progress_step = next((s for s in plan.steps if s.status == "in_progress"), None)

        if in_progress_step is not None:
            self._tool_calls_in_step += 1
        else:
            for step in plan.steps:
                if step.status == "pending":
                    try:
                        self._store.set_status(step_id=step.id, status="in_progress")
                        await self._store.persist()
                        self._tool_calls_in_step = 1
                        logger.debug("Auto-advanced plan step '%s' to in_progress", step.id)
                        await self._sync_action_space(ctx)
                    except Exception as exc:
                        logger.warning("Failed to auto-advance step %s: %s", step.id, exc)
                    break
        return None

    async def on_after_tool_call(
        self, ctx: ExtensionContext, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        name = getattr(tool_call, "name", "")
        if name == "manage_plan" and not is_error:
            await self._sync_action_space(ctx)
        return None

    async def _sync_action_space(self, ctx: ExtensionContext) -> None:
        if not self._enable_step_action_space:
            return
        set_fn = getattr(ctx.harness, "set_active_tools", None)
        if not callable(set_fn):
            return

        all_tools = list(getattr(ctx.harness.state, "tools", None) or [])
        all_names = [resolve_tool_name(t, i) for i, t in enumerate(all_tools)]
        if not all_names:
            return

        plan = self._store.plan
        step = current_plan_step(plan)
        if step is None or not step.suggested_tools:
            # No step filter → restore full tool schema.
            key = "__all__"
            if key == self._last_action_space_key:
                return
            try:
                await set_fn(all_names)
                self._last_action_space_key = key
            except Exception as exc:
                logger.warning("Failed to restore full tool schema: %s", exc)
            return

        known = set(all_names)
        selected: list[str] = []
        for name in [*step.suggested_tools, *self._always_tools]:
            if name in known and name not in selected:
                selected.append(name)
        # No overlap with registered tools → do not trap the agent; restore all.
        suggested_known = [n for n in step.suggested_tools if n in known]
        if not suggested_known:
            logger.warning(
                "Plan step '%s' suggested_tools=%r match no registered tools; "
                "keeping full tool schema",
                step.id,
                step.suggested_tools,
            )
            key = "__all__"
            if key != self._last_action_space_key:
                try:
                    await set_fn(all_names)
                    self._last_action_space_key = key
                except Exception as exc:
                    logger.warning("Failed to restore full tool schema: %s", exc)
            return
        if not selected:
            return
        key = f"{step.id}:{','.join(selected)}"
        if key == self._last_action_space_key:
            return
        try:
            await set_fn(selected)
            self._last_action_space_key = key
            logger.debug(
                "Plan step '%s' action space → %s",
                step.id,
                selected,
            )
        except Exception as exc:
            logger.warning("Failed to set step action space: %s", exc)
