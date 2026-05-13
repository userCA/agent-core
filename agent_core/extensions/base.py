"""Extension Protocol, ExtensionContext, and ExtensionRunner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from agent_core.core.events import AgentEvent


@dataclass
class ExtensionContext:
    session_id: str
    agent: Any
    store: Any | None = None


class Extension(Protocol):
    name: str

    async def on_event(self, ctx: ExtensionContext, evt: AgentEvent) -> None:
        """Receive every AgentEvent emitted during the session."""
        ...

    async def on_before_tool_call(
        self, ctx: ExtensionContext, tool_call: Any
    ) -> dict[str, Any] | None:
        """Return {'block': True, 'reason': '...'} to block the tool call."""
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

    # ---------- callbacks wired into Agent ----------

    async def before_tool_call(self, call_ctx: dict[str, Any]) -> dict[str, Any] | None:
        tool_call = call_ctx.get("tool_call")
        for ext in self._extensions:
            try:
                result = await ext.on_before_tool_call(self._ctx, tool_call)
                if result and result.get("block"):
                    return result
            except Exception:
                pass
        return None

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
                    result = type(result)(**hook["result"]) if type(result) else result
            except Exception:
                pass
        return mutated_result

    # ---------- event forwarding ----------

    async def on_event(self, evt: AgentEvent) -> None:
        for ext in self._extensions:
            try:
                await ext.on_event(self._ctx, evt)
            except Exception:
                pass
