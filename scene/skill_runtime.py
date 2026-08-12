"""Shared skill progressive-disclosure helpers for scene chat assistants."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from agent_core.core.events import SkillStart
from agent_core.resources.skill_activation import (
    SkillActivationTracker,
    expand_skill_command,
    find_skill,
    find_skill_by_read_path,
    skill_path_read_activation_enabled,
    skill_progressive_enabled,
)
from agent_core.resources.types import Skill
from agent_core.session.harness import AgentHarness
from agent_core.tools.load_skill import create_load_skill_tool
from agent_core.tools.base import ToolRegistry

EventHandler = Callable[[Any], Awaitable[None] | None]


class SkillRuntime:
    """Skill activation state and helpers shared by scene ChatAssistants."""

    def __init__(self, skills: list[Skill], harness: AgentHarness, *, cwd: str = "") -> None:
        self.skills = skills
        self.harness = harness
        self.cwd = cwd
        self.tracker = SkillActivationTracker()
        self._active_skills: set[str] = set()
        self._handlers: list[EventHandler] = []
        harness.add_before_tool_call_hook(self.before_tool_call)

    def bind_handlers(self, handlers: list[EventHandler]) -> None:
        self._handlers = handlers

    def register_tools(self, tool_registry: ToolRegistry) -> None:
        if not skill_progressive_enabled():
            return
        tool_registry.register(
            create_load_skill_tool(
                self.skills,
                self.tracker,
                on_activate=self._on_load_skill_activate,
            )
        )

    async def _on_load_skill_activate(self, skill: Skill, source: str) -> None:
        await self._emit_skill_start(skill, source=source)

    async def before_tool_call(self, call_ctx: dict[str, Any]) -> dict[str, Any] | None:
        if not skill_path_read_activation_enabled():
            return None
        tool_call = call_ctx.get("tool_call")
        if tool_call is None or getattr(tool_call, "name", "") != "read":
            return None
        raw_path = (call_ctx.get("input") or {}).get("path", "")
        skill = find_skill_by_read_path(str(raw_path), self.skills, cwd=self.cwd)
        if skill is None:
            return None
        if self.tracker.activate(skill.name, source="path_read"):
            await self._emit_skill_start(skill, source="path_read")
        return None

    async def expand_user_message(self, text: str) -> str:
        expanded, should_emit = expand_skill_command(text, self.skills, self.tracker)
        if should_emit:
            space_idx = text.find(" ")
            skill_name = text[7:space_idx] if space_idx != -1 else text[7:]
            skill = find_skill(self.skills, skill_name)
            if skill is not None:
                await self._emit_skill_start(skill, source="injected")
        return expanded

    async def _emit_skill_start(self, skill: Skill, *, source: str) -> None:
        self._active_skills.add(skill.name)
        self.harness.record_skill_activation(skill.name, source)
        skill_start = SkillStart(
            skill_name=skill.name,
            skill_description=skill.description,
        )
        for handler in list(self._handlers):
            result = handler(skill_start)
            if asyncio.iscoroutine(result):
                await result

    async def handle_turn_end(self, handlers: list[EventHandler]) -> None:
        from agent_core.core.events import SkillEnd

        if not self._active_skills:
            return
        for skill_name in list(self._active_skills):
            skill_end = SkillEnd(skill_name=skill_name)
            for handler in list(handlers):
                result = handler(skill_end)
                if asyncio.iscoroutine(result):
                    await result
        self._active_skills.clear()

    def clear_on_agent_end(self) -> None:
        self._active_skills.clear()
