"""LoadSkill tool — progressive disclosure activation for skills."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_core.core.content import TextContent
from agent_core.resources.skill_activation import (
    SkillActivationTracker,
    find_skill,
    format_skill_block,
)
from agent_core.resources.types import Skill
from agent_core.tools.base import Tool, ToolContext, ToolDefinition, ToolResult

SkillActivateHook = Callable[[Skill, str], Awaitable[None] | None]


class LoadSkillTool(Tool):
    def __init__(
        self,
        skills: list[Skill],
        tracker: SkillActivationTracker,
        on_activate: SkillActivateHook | None = None,
    ) -> None:
        self._skills = skills
        self._tracker = tracker
        self._on_activate = on_activate
        self.definition = ToolDefinition(
            name="load_skill",
            description=(
                "Load the full instructions for a skill by name before following it. "
                "Call this when an available skill matches the user task. "
                "Do not claim to follow a skill you have not loaded."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact skill name from <available_skills>",
                    },
                },
                "required": ["name"],
            },
        )

    async def execute(
        self,
        tool_call_id: str,
        params: dict[str, Any],
        ctx: ToolContext | None,
    ) -> ToolResult:
        del tool_call_id, ctx
        name = str(params.get("name", "")).strip()
        if not name:
            return ToolResult(
                content=[TextContent(text="Missing required parameter: name")],
                details={"error": "missing_name"},
            )

        skill = find_skill(self._skills, name)
        if skill is None:
            return ToolResult(
                content=[TextContent(text=f"Unknown skill: {name}")],
                details={"error": "unknown_skill", "skill_name": name},
            )

        if skill.disable_model_invocation:
            return ToolResult(
                content=[
                    TextContent(
                        text=(
                            f"Skill '{name}' cannot be loaded by the model. "
                            "Ask the user to invoke it with /skill:" + name
                        )
                    )
                ],
                details={"error": "model_invocation_disabled", "skill_name": name},
            )

        first_activation = self._tracker.activate(skill.name, source="load_skill")
        if self._on_activate is not None and first_activation:
            result = self._on_activate(skill, "load_skill")
            if hasattr(result, "__await__"):
                await result

        block = format_skill_block(skill)
        return ToolResult(
            content=[TextContent(text=block)],
            details={"skill_name": skill.name, "first_activation": first_activation},
        )


def create_load_skill_tool(
    skills: list[Skill],
    tracker: SkillActivationTracker,
    on_activate: SkillActivateHook | None = None,
) -> LoadSkillTool:
    return LoadSkillTool(skills=skills, tracker=tracker, on_activate=on_activate)
