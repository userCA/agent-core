"""Unified hook system — typed events + reducer semantics.

Replaces scattered ``_chain_*`` methods on Agent with a single
``AgentHooks`` class that owns registration, dispatch, and reduction.

Event types and their reducer semantics:

* ``context`` — chain transform: each handler may update ``messages``.
* ``before_agent_start`` — accumulate: chain ``system_prompt``, collect ``messages``.
* ``tool_call`` — sequential, early exit on ``block=True``.
* ``tool_result`` — sequential patch accumulation.
* Observational events (``message_end``, ``agent_end``, etc.) — fire-and-forget.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Union

_log = logging.getLogger(__name__)

# -- Handler signatures --

HookHandler = Callable[..., Union[Any, Awaitable[Any], None]]
HookObserver = Callable[[Any], Union[None, Awaitable[None]]]


# -- Typed hook events --

@dataclass
class HookEvent:
    """Base class for all hook events."""
    type: str = ""


@dataclass
class ContextHookEvent(HookEvent):
    """Context transform — handler may return updated messages.

    Reducer: chain transform.  Each handler sees current messages,
    may return ``{"messages": [...]}`` to update.
    """
    type: str = "context"
    messages: list[Any] = field(default_factory=list)


@dataclass
class BeforeAgentStartHookEvent(HookEvent):
    """Before agent start — handler may inject system_prompt / messages.

    Reducer: accumulate.  system_prompt is chained, messages are collected.
    """
    type: str = "before_agent_start"
    prompt: str = ""
    system_prompt: str = ""


@dataclass
class ToolCallHookEvent(HookEvent):
    """Before tool execution — handler may block or inject metadata.

    Reducer: sequential, early exit on ``block=True``.
    """
    type: str = "tool_call"
    tool_call_id: str = ""
    tool_name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    call_ctx: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResultHookEvent(HookEvent):
    """After tool execution — handler may patch the result.

    Reducer: sequential patch accumulation.  Each handler sees the
    current patched result.
    """
    type: str = "tool_result"
    tool_call_id: str = ""
    tool_name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    is_error: bool = False
    call_ctx: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionBeforeCompactHookEvent(HookEvent):
    """Before session compaction — handler may cancel or provide custom compaction.

    Reducer: cancel if any handler returns ``{"cancel": True}``.
    """
    type: str = "session_before_compact"
    messages: list[Any] = field(default_factory=list)
    instructions: str | None = None


@dataclass
class BeforeProviderRequestHookEvent(HookEvent):
    """Before provider request — handler may patch stream options."""
    type: str = "before_provider_request"
    model: Any = None
    session_id: str = ""
    stream_options: dict[str, Any] = field(default_factory=dict)


@dataclass
class BeforeProviderPayloadHookEvent(HookEvent):
    """Before provider payload is sent — handler may transform payload."""
    type: str = "before_provider_payload"
    model: Any = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class AfterProviderResponseHookEvent(HookEvent):
    """After provider response — observational only."""
    type: str = "after_provider_response"
    model: Any = None
    status: int = 0
    headers: dict[str, str] = field(default_factory=dict)


# -- AgentHooks class --

class AgentHooks:
    """Unified hook registration, dispatch, and reduction.

    Three API surfaces:

    * ``observe(handler)`` — read-only, sees all events, return ignored.
    * ``on(type, handler)`` — participates in that event's reducer semantics.
    * ``emit(event)`` — the single dispatch entry; runs observers then handlers.
    """

    def __init__(self) -> None:
        self._observers: list[HookObserver] = []
        self._handlers: dict[str, list[HookHandler]] = {}

    # -- registration --

    def observe(self, handler: HookObserver) -> Callable[[], None]:
        """Register a read-only observer for all events."""
        self._observers.append(handler)

        def _unsub() -> None:
            try:
                self._observers.remove(handler)
            except ValueError:
                pass

        return _unsub

    def on(self, event_type: str, handler: HookHandler) -> Callable[[], None]:
        """Register a handler for a specific event type."""
        handlers = self._handlers.setdefault(event_type, [])
        handlers.append(handler)

        def _unsub() -> None:
            try:
                self._handlers[event_type].remove(handler)
            except (ValueError, KeyError):
                pass

        return _unsub

    # -- dispatch --

    async def emit(self, event: HookEvent) -> Any:
        """Dispatch a hook event through observers then typed handlers.

        Returns the reduced result, or ``None`` if no handlers matched.
        """
        # Observers always run, return ignored
        for observer in list(self._observers):
            try:
                result = observer(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                _log.warning("Hook observer failed for %s", event.type, exc_info=True)

        handlers = self._handlers.get(event.type, [])
        if not handlers:
            return None

        # Dispatch to typed reducer
        reducer = _REDUCERS.get(event.type)
        if reducer is not None:
            return await reducer(event, handlers)

        # No reducer → fire-and-forget
        for handler in list(handlers):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                _log.warning("Hook handler failed for %s", event.type, exc_info=True)
        return None


# -- Reducer implementations --

async def _await_result(handler: HookHandler, *args: Any) -> Any:
    result = handler(*args)
    if inspect.isawaitable(result):
        return await result
    return result


async def _reduce_context(event: ContextHookEvent, handlers: list[HookHandler]) -> dict[str, Any] | None:
    """Chain transform: each handler may return updated messages."""
    current_messages = list(event.messages)
    changed = False

    for handler in list(handlers):
        try:
            result = await _await_result(handler, event)
        except Exception:
            _log.warning("Context hook handler failed", exc_info=True)
            continue
        if result and isinstance(result, dict) and "messages" in result:
            current_messages = result["messages"]
            event.messages = list(current_messages)
            changed = True

    return {"messages": current_messages} if changed else None


async def _reduce_before_agent_start(
    event: BeforeAgentStartHookEvent, handlers: list[HookHandler]
) -> dict[str, Any] | None:
    """Accumulate: chain system_prompt, collect messages."""
    system_prompt = event.system_prompt
    messages: list[Any] = []

    for handler in list(handlers):
        try:
            result = await _await_result(handler, event)
        except Exception:
            _log.warning("Before agent start hook handler failed", exc_info=True)
            continue
        if result and isinstance(result, dict):
            if result.get("system_prompt"):
                system_prompt = result["system_prompt"]
                # Update event so next handler sees chained prompt
                event.system_prompt = system_prompt
            if result.get("message"):
                messages.append(result["message"])

    if messages or system_prompt != event.system_prompt:
        return {"messages": messages, "system_prompt": system_prompt} if messages else {"system_prompt": system_prompt}
    return None


async def _reduce_tool_call(
    event: ToolCallHookEvent, handlers: list[HookHandler]
) -> dict[str, Any] | None:
    """Sequential, early exit on block."""
    for handler in list(handlers):
        try:
            result = await _await_result(handler, event)
        except Exception:
            _log.warning("Tool call hook handler failed", exc_info=True)
            continue
        if result and isinstance(result, dict) and result.get("block"):
            return result
    return None


async def _reduce_tool_result(
    event: ToolResultHookEvent, handlers: list[HookHandler]
) -> dict[str, Any] | None:
    """Sequential patch accumulation."""
    modified = False
    current_result = event.result
    current_is_error = event.is_error

    for handler in list(handlers):
        try:
            result = await _await_result(handler, event)
        except Exception:
            _log.warning("Tool result hook handler failed", exc_info=True)
            continue
        if result and isinstance(result, dict):
            if result.get("result") is not None:
                hr = result["result"]
                if hasattr(current_result, "content"):
                    current_result = type(current_result)(
                        content=hr.get("content", current_result.content) if hasattr(hr, "get") else getattr(hr, "content", current_result.content),
                        details=hr.get("details", current_result.details) if hasattr(hr, "get") else getattr(hr, "details", current_result.details),
                        display=hr.get("display", current_result.display) if hasattr(hr, "get") else getattr(hr, "display", current_result.display),
                    )
                    event.result = current_result
                    modified = True
            if "is_error" in result:
                current_is_error = result["is_error"]
                event.is_error = current_is_error
                modified = True

    return {"result": current_result, "is_error": current_is_error} if modified else None


async def _reduce_session_before_compact(
    event: SessionBeforeCompactHookEvent, handlers: list[HookHandler]
) -> dict[str, Any] | None:
    """Any handler may cancel compaction."""
    for handler in list(handlers):
        try:
            result = await _await_result(handler, event)
        except Exception:
            _log.warning("Session before compact hook handler failed", exc_info=True)
            continue
        if result and isinstance(result, dict) and result.get("cancel"):
            return {"cancel": True}
    return None


async def _reduce_before_provider_request(
    event: BeforeProviderRequestHookEvent, handlers: list[HookHandler]
) -> dict[str, Any] | None:
    """Chain patch stream_options."""
    from agent_core.core.stream_options import apply_stream_options_patch, clone_stream_options

    current = clone_stream_options(event.stream_options)
    changed = False
    for handler in list(handlers):
        try:
            event.stream_options = clone_stream_options(current)
            result = await _await_result(handler, event)
        except Exception:
            _log.warning("Before provider request hook handler failed", exc_info=True)
            continue
        if result and isinstance(result, dict) and "stream_options" in result:
            patch = result["stream_options"]
            if isinstance(patch, dict):
                current = apply_stream_options_patch(current, patch)
                changed = True
    return {"stream_options": current} if changed else None


async def _reduce_before_provider_payload(
    event: BeforeProviderPayloadHookEvent, handlers: list[HookHandler]
) -> dict[str, Any] | None:
    """Chain transform payload."""
    current = dict(event.payload)
    changed = False
    for handler in list(handlers):
        try:
            event.payload = dict(current)
            result = await _await_result(handler, event)
        except Exception:
            _log.warning("Before provider payload hook handler failed", exc_info=True)
            continue
        if result is not None and isinstance(result, dict) and "payload" in result:
            current = dict(result["payload"])
            changed = True
    return {"payload": current} if changed else None


# -- Reducer dispatch table --

_REDUCERS: dict[str, Callable[..., Awaitable[Any]]] = {
    "context": _reduce_context,
    "before_agent_start": _reduce_before_agent_start,
    "tool_call": _reduce_tool_call,
    "tool_result": _reduce_tool_result,
    "session_before_compact": _reduce_session_before_compact,
    "before_provider_request": _reduce_before_provider_request,
    "before_provider_payload": _reduce_before_provider_payload,
}
