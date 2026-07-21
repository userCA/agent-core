"""manage_plan tool — explicit plan/todo updates for Plan-Execute."""

from __future__ import annotations

from typing import Any

from agent_core.core.content import TextContent
from agent_core.planning.store import PlanStore
from agent_core.planning.types import DEFAULT_PLANNING_HINT
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult


class ManagePlanTool:
    def __init__(
        self,
        *,
        plan_store: PlanStore,
        name: str = "manage_plan",
    ) -> None:
        self._store = plan_store
        self.definition = ToolDefinition(
            name=name,
            description=(
                "Create or update the task plan/checklist for the current conversation. "
                "action=replace: create/replace full plan with title + "
                "steps[{id?,title,status?,detail?,suggested_tools?}]. "
                "action=set_status: update one step (step_id+status+detail?) or updates=[{id,status,detail?}]. "
                "action=revise: merge step list / title. "
                "action=complete_plan | cancel_plan: finish the plan."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "replace",
                            "set_status",
                            "revise",
                            "complete_plan",
                            "cancel_plan",
                        ],
                    },
                    "title": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "status": {"type": "string"},
                                "detail": {"type": "string"},
                                "suggested_tools": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "Optional tool names allowed while this step is current"
                                    ),
                                },
                            },
                        },
                    },
                    "step_id": {"type": "string"},
                    "status": {"type": "string"},
                    "detail": {"type": "string"},
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "status": {"type": "string"},
                                "detail": {"type": "string"},
                            },
                            "required": ["id", "status"],
                        },
                    },
                },
                "required": ["action"],
            },
            prompt_snippet=DEFAULT_PLANNING_HINT,
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        action = str(params.get("action") or "").strip()
        phase = "updated"
        try:
            if action == "replace":
                steps = params.get("steps") or []
                if not isinstance(steps, list) or not steps:
                    return self._error("replace requires non-empty steps")
                plan = self._store.replace(
                    title=str(params.get("title") or "Plan"),
                    steps=steps,
                )
                phase = "replaced"
            elif action == "set_status":
                plan = self._store.set_status(
                    step_id=params.get("step_id"),
                    status=params.get("status"),
                    detail=params.get("detail"),
                    updates=params.get("updates"),
                )
            elif action == "revise":
                plan = self._store.revise(
                    steps=params.get("steps"),
                    title=params.get("title"),
                )
            elif action == "complete_plan":
                plan = self._store.complete_plan()
                phase = "completed"
            elif action == "cancel_plan":
                plan = self._store.cancel_plan()
                phase = "cancelled"
            else:
                return self._error(f"unknown action: {action}")
        except ValueError as exc:
            return self._error(str(exc))

        await self._store.persist()
        payload = self._store.snapshot_payload(phase=phase)
        if ctx.on_update is not None:
            ctx.on_update(
                ToolResult(
                    content=[TextContent(text="")],
                    details={"plan": payload},
                )
            )

        done, total = plan.progress()
        summary = f"plan={plan.title} status={plan.status} progress={done}/{total} v{plan.version}"
        return ToolResult(
            content=[TextContent(text=summary)],
            details={"plan": payload},
            display={"type": "plan", "title": plan.title, "status": plan.status, "done": done, "total": total},
        )

    def _error(self, message: str) -> ToolResult:
        return ToolResult(
            content=[TextContent(text=message)],
            details={
                "plan": {
                    "type": "plan",
                    "phase": "error",
                    "error_message": message,
                    "plan": self._store.plan.to_dict() if self._store.plan else None,
                }
            },
            display={"type": "plan_error", "error": message},
        )
