"""Extension Protocol, ExtensionContext, and ExtensionRunner."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, Protocol

from agent_core.core.events import AgentEvent
from agent_core.core.hooks import AgentHooks
from agent_core.core.state import AgentState

logger = logging.getLogger(__name__)


class HarnessFacade(Protocol):
    """Minimal harness surface exposed to extensions."""

    state: AgentState
    hooks: AgentHooks
    session_id: str

    def abort(self) -> None: ...


@dataclass
class ExtensionContext:
    session_id: str
    harness: HarnessFacade
    store: Any | None = None
    signal: asyncio.Event | None = None
    abort: Callable[[], None] | None = None
    model: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Extension(Protocol):
    name: str

    async def on_event(self, ctx: ExtensionContext, evt: AgentEvent) -> None:
        """Receive every AgentEvent emitted during the session."""
        ...

    async def on_before_agent_start(
        self, ctx: ExtensionContext, prompt: str, system_prompt: str
    ) -> dict[str, Any] | None:
        """Return {'message': CustomMessage, 'system_prompt': '...'} to inject before agent loop."""
        ...

    async def on_before_tool_call(
        self, ctx: ExtensionContext, tool_call: Any
    ) -> dict[str, Any] | None:
        """Return {'block': True, 'reason': '...'} or {'mutated_args': {...}} or {'inject_metadata': {...}}."""
        ...

    async def on_after_tool_call(
        self, ctx: ExtensionContext, tool_call: Any, result: Any, is_error: bool
    ) -> dict[str, Any] | None:
        """Return {'result': {'content': [...], 'details': {...}}} to mutate result."""
        ...


class ExtensionRunner:
    """Runs extensions in order with error isolation."""

    def __init__(self, extensions: list[Extension], ctx: ExtensionContext) -> None:
        self._extensions = extensions
        self._ctx = ctx

    # ---------- agent lifecycle ----------

    async def on_before_agent_start(self, prompt: str, system_prompt: str) -> dict[str, Any] | None:
        merged: dict[str, Any] = {}
        for ext in self._extensions:
            if not hasattr(ext, "on_before_agent_start"):
                continue
            try:
                result = await ext.on_before_agent_start(self._ctx, prompt, system_prompt)
                if result:
                    if result.get("system_prompt"):
                        system_prompt = result["system_prompt"]
                        merged["system_prompt"] = system_prompt
                    if result.get("message"):
                        merged["message"] = result["message"]
            except Exception as exc:
                logger.warning("Extension on_before_agent_start failed: %s", exc)
        return merged if merged else None

    # ---------- tool call hooks ----------

    async def before_tool_call(self, call_ctx: dict[str, Any]) -> dict[str, Any] | None:
        tool_call = call_ctx.get("tool_call")
        merged_metadata: dict[str, Any] = {}
        merged_args: dict[str, Any] = {}
        for ext in self._extensions:
            try:
                result = await ext.on_before_tool_call(self._ctx, tool_call)
                if result and result.get("block"):
                    return result
                if result and result.get("inject_metadata"):
                    merged_metadata.update(result["inject_metadata"])
                if result and result.get("mutated_args"):
                    merged_args.update(result["mutated_args"])
            except Exception as exc:
                logger.warning("Extension before_tool_call failed: %s", exc)
        out: dict[str, Any] = {}
        if merged_metadata:
            out["inject_metadata"] = merged_metadata
        if merged_args:
            out["mutated_args"] = merged_args
        return out or None

    async def after_tool_call(self, call_ctx: dict[str, Any]) -> dict[str, Any] | None:
        tool_call = call_ctx.get("tool_call")
        result = call_ctx.get("result")
        is_error = call_ctx.get("is_error", False)
        mutated_result = None
        for ext in self._extensions:
            try:
                hook = await ext.on_after_tool_call(self._ctx, tool_call, result, is_error)
                if hook and hook.get("result"):
                    mutated_result = hook
                    hook_data = hook["result"]
                    existing_display = getattr(result, "display", None)
                    merged = {
                        "content": hook_data.get("content", getattr(result, "content", [])),
                        "details": hook_data.get("details", getattr(result, "details", None)),
                        "display": hook_data.get("display", existing_display),
                    }
                    result = type(result)(**merged)
            except Exception as exc:
                logger.warning("Extension after_tool_call failed: %s", exc)
        return mutated_result

    # ---------- event forwarding ----------

    async def on_event(self, evt: AgentEvent) -> None:
        for ext in self._extensions:
            try:
                await ext.on_event(self._ctx, evt)
            except Exception as exc:
                logger.warning("Extension on_event failed: %s", exc)
