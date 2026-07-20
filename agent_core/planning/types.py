"""Plan-Execute types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PlanStepStatus = Literal[
    "pending", "in_progress", "completed", "failed", "cancelled", "skipped"
]
PlanStatus = Literal["active", "completed", "cancelled"]


@dataclass
class PlanStep:
    id: str
    title: str
    status: PlanStepStatus = "pending"
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or ""),
            status=data.get("status") or "pending",  # type: ignore[arg-type]
            detail=data.get("detail"),
        )


@dataclass
class Plan:
    id: str
    title: str
    status: PlanStatus = "active"
    steps: list[PlanStep] = field(default_factory=list)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        steps_raw = data.get("steps") or []
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or ""),
            status=data.get("status") or "active",  # type: ignore[arg-type]
            steps=[PlanStep.from_dict(s) for s in steps_raw if isinstance(s, dict)],
            version=int(data.get("version") or 1),
        )

    def progress(self) -> tuple[int, int]:
        done = sum(1 for s in self.steps if s.status in ("completed", "skipped", "cancelled"))
        return done, len(self.steps)


@dataclass
class PlanningOptions:
    tool_name: str = "manage_plan"
    prompt_snippet: str | None = None
    persist: bool = True


DEFAULT_PLANNING_HINT = (
    "## Planning Mode\n"
    "When the user asks you to plan, organize, or arrange anything "
    "(e.g., travel itineraries, birthday parties, event planning, project schedules, "
    "meal plans, shopping lists, renovation plans, study plans, etc.), "
    "you MUST call manage_plan(action=replace) to create a structured plan FIRST.\n"
    "Even if the task seems simple, if it involves multiple aspects to consider, "
    "create a plan — the user benefits from seeing the structured breakdown.\n\n"
    "### Execution Rhythm\n"
    "After creating the plan, execute each step one by one:\n"
    "1. Call manage_plan(action=set_status, step_id=X, status=in_progress) BEFORE executing\n"
    "2. Execute the step (call relevant tools or generate content)\n"
    "3. Call manage_plan(action=set_status, step_id=X, status=completed) AFTER the step finishes\n"
    "4. Move to the next step\n"
    "Never batch-execute all steps and update statuses at the end. "
    "Call complete_plan when all steps are done."
)
