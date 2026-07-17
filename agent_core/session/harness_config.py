"""Runtime config setters and pending writes for AgentHarness."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from agent_core.core.errors import AgentHarnessError
from agent_core.core.events import ModelUpdate, ResourcesUpdate, ThinkingLevelUpdate, ToolsUpdate
from agent_core.core.hooks import ContextHookEvent
from agent_core.core.pending_writes import PendingSessionWrite
from agent_core.core.state import AgentHarnessPhase
from agent_core.core.stream_options import clone_stream_options
from agent_core.session.tool_utils import resolve_tool_name
from agent_core.session.turn_runtime import (
    register_legacy_context,
    register_legacy_tool_call,
    register_legacy_tool_result,
)

if TYPE_CHECKING:
    from agent_core.session.harness import AgentHarness


class HarnessConfigMixin:
    """Mixin: pending writes and runtime config setters."""

    async def flush_pending_writes(self: AgentHarness) -> None:
        while self._pending_writes:
            write = self._pending_writes[0]
            await self._persistence.persist_pending_write(write)
            self._pending_writes.pop(0)

    async def _apply_config_write(self: AgentHarness, write: PendingSessionWrite) -> None:
        if self.phase == AgentHarnessPhase.IDLE:
            await self._persistence.persist_pending_write(write)
        else:
            self._pending_writes.append(write)

    def get_model(self: AgentHarness) -> Any:
        return self.state.model

    async def set_model(self: AgentHarness, model: Any) -> None:
        previous_model = self.state.model
        write = PendingSessionWrite(
            type="model_change",
            data={"provider": getattr(model, "provider", ""), "model_id": getattr(model, "id", "")},
        )
        await self._apply_config_write(write)
        self.state.model = model
        await self._notify_listeners(ModelUpdate(
            model=model, previous_model=previous_model, source="set",
        ))

    def get_thinking_level(self: AgentHarness) -> str:
        return self.state.thinking_level

    async def set_thinking_level(self: AgentHarness, level: str) -> None:
        previous_level = self.state.thinking_level
        write = PendingSessionWrite(
            type="thinking_level_change",
            data={"thinking_level": level},
        )
        await self._apply_config_write(write)
        self.state.thinking_level = level
        await self._notify_listeners(ThinkingLevelUpdate(
            level=level, previous_level=previous_level,
        ))

    def get_tools(self: AgentHarness) -> list[Any]:
        return list(self.state.tools)

    async def set_tools(
        self: AgentHarness, tools: list[Any], active_tool_names: list[str] | None = None,
    ) -> None:
        names = [resolve_tool_name(t, i) for i, t in enumerate(tools)]
        if len(names) != len(set(names)):
            raise AgentHarnessError("invalid_argument", "Duplicate tool name(s)")
        previous_tool_names = [
            resolve_tool_name(t, i) for i, t in enumerate(self.state.tools)
        ]
        if active_tool_names is None:
            active_tool_names = list(names)
        unknown = [n for n in active_tool_names if n not in names]
        if unknown:
            raise AgentHarnessError("invalid_argument", f"Unknown tool(s): {', '.join(unknown)}")
        write = PendingSessionWrite(
            type="active_tools_change",
            data={"active_tool_names": list(active_tool_names)},
        )
        await self._apply_config_write(write)
        self.state.tools = list(tools)
        self._active_tool_names = list(active_tool_names)
        await self._notify_listeners(ToolsUpdate(
            tool_names=names, previous_tool_names=previous_tool_names,
            active_tool_names=list(active_tool_names),
            previous_active_tool_names=previous_tool_names, source="set",
        ))

    async def set_active_tools(self: AgentHarness, tool_names: list[str]) -> None:
        all_names = {
            resolve_tool_name(t, i) for i, t in enumerate(self.state.tools)
        }
        unknown = [n for n in tool_names if n not in all_names]
        if unknown:
            raise AgentHarnessError("invalid_argument", f"Unknown tool(s): {', '.join(unknown)}")
        previous_tool_names = [
            resolve_tool_name(t, i) for i, t in enumerate(self.state.tools)
        ]
        write = PendingSessionWrite(
            type="active_tools_change",
            data={"active_tool_names": list(tool_names)},
        )
        await self._apply_config_write(write)
        self._active_tool_names = list(tool_names)
        await self._notify_listeners(ToolsUpdate(
            tool_names=previous_tool_names, previous_tool_names=previous_tool_names,
            active_tool_names=list(tool_names),
            previous_active_tool_names=previous_tool_names, source="set",
        ))

    def get_stream_options(self: AgentHarness) -> dict[str, Any]:
        return clone_stream_options(self._stream_options)

    def set_stream_options(self: AgentHarness, options: dict[str, Any]) -> None:
        self._stream_options = clone_stream_options(options)

    def get_resources(self: AgentHarness) -> dict[str, Any]:
        return {
            "skills": list(self._resources.get("skills", [])),
            "prompt_templates": list(self._resources.get("prompt_templates", [])),
        }

    async def set_resources(self: AgentHarness, resources: dict[str, Any]) -> None:
        previous = self.get_resources()
        self._resources = {
            "skills": list(resources.get("skills", [])),
            "prompt_templates": list(resources.get("prompt_templates", [])),
        }
        await self._notify_listeners(ResourcesUpdate(
            resources=self.get_resources(), previous_resources=previous,
        ))

    def _register_context_transform(self: AgentHarness, handler: Any) -> None:
        async def _adapter(event: ContextHookEvent) -> Any:
            result = handler(event.messages, None)
            if inspect.isawaitable(result):
                result = await result
            if result is not None and result is not event.messages:
                return {"messages": result}
            return None
        self.hooks.on("context", _adapter)

    def add_before_agent_start_hook(self: AgentHarness, hook: Any) -> None:
        self.hooks.on("before_agent_start", hook)

    def add_before_tool_call_hook(self: AgentHarness, hook: Any) -> None:
        register_legacy_tool_call(self.hooks, hook)

    def remove_before_tool_call_hook(self: AgentHarness, hook: Any) -> None:
        pass

    def add_after_tool_call_hook(self: AgentHarness, hook: Any) -> None:
        register_legacy_tool_result(self.hooks, hook)

    def remove_after_tool_call_hook(self: AgentHarness, hook: Any) -> None:
        pass

    def add_transform_context_hook(self: AgentHarness, hook: Any) -> None:
        register_legacy_context(self.hooks, hook)
