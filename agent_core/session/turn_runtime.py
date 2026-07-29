"""Stateless turn assembly helpers — build loop config and stream wrappers."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Protocol

from agent_core.core.context import AgentLoopConfig, TurnSnapshot
from agent_core.core.hooks import (
    AgentHooks,
    BeforeAgentStartHookEvent,
    BeforeProviderPayloadHookEvent,
    BeforeProviderRequestHookEvent,
    AfterProviderResponseHookEvent,
    ContextHookEvent,
    ToolCallHookEvent,
    ToolResultHookEvent,
)
from agent_core.core.stream_options import clone_stream_options
from agent_core.providers.auth import AuthSource
from agent_core.providers.base import ModelProvider
from agent_core.tools.mutation_queue import FileMutationQueue


class TurnRuntimeHost(Protocol):
    """Minimal harness surface required by turn runtime helpers."""

    state: Any
    hooks: AgentHooks
    session_id: str
    active_tool_names: list[str] | None
    stream_options: dict[str, Any]
    resources: dict[str, Any]

    def get_resources(self) -> dict[str, Any]: ...

    async def drain_steering(self) -> list[Any]: ...
    async def drain_follow_up(self) -> list[Any]: ...
    async def prepare_next_turn(self) -> TurnSnapshot | None: ...
    async def flush_pending_writes(self) -> None: ...


async def maybe_await(fn: Any, *args: Any) -> Any:
    result = fn(*args)
    if inspect.isawaitable(result):
        return await result
    return result


def register_legacy_tool_call(hooks: AgentHooks, handler: Any) -> None:
    async def _adapter(event: ToolCallHookEvent) -> Any:
        return await maybe_await(handler, event.call_ctx)
    hooks.on("tool_call", _adapter)


def register_legacy_tool_result(hooks: AgentHooks, handler: Any) -> None:
    async def _adapter(event: ToolResultHookEvent) -> Any:
        return await maybe_await(handler, event.call_ctx)
    hooks.on("tool_result", _adapter)


def register_legacy_context(hooks: AgentHooks, handler: Any) -> None:
    async def _adapter(event: ContextHookEvent) -> Any:
        result = handler(event.messages, None)
        if inspect.isawaitable(result):
            result = await result
        if result is not None and result is not event.messages:
            return {"messages": result}
        return None
    hooks.on("context", _adapter)


def create_turn_snapshot(host: TurnRuntimeHost) -> TurnSnapshot:
    from agent_core.session.tool_utils import filter_active_tools

    all_tools = list(host.state.tools)
    active_tools = filter_active_tools(all_tools, host.active_tool_names)
    resources = host.get_resources()
    return TurnSnapshot(
        messages=list(host.state.messages),
        system_prompt=host.state.system_prompt,
        tools=active_tools,
        model=host.state.model,
        thinking_level=host.state.thinking_level,
        stream_options=clone_stream_options(host.stream_options),
        resources={
            "skills": list(resources.get("skills", [])),
            "prompt_templates": list(resources.get("prompt_templates", [])),
        },
        session_id=host.session_id,
    )


def chain_before_agent_start_hooks(hooks: AgentHooks) -> Callable[..., Awaitable[Any]] | None:
    if not hooks._handlers.get("before_agent_start"):
        return None

    async def _chained(prompt: str, system_prompt: str) -> dict[str, Any] | None:
        evt = BeforeAgentStartHookEvent(prompt=prompt, system_prompt=system_prompt)
        return await hooks.emit(evt)

    return _chained


def chain_before_hooks(hooks: AgentHooks) -> Callable[..., Awaitable[Any]] | None:
    if not hooks._handlers.get("tool_call"):
        return None

    async def _chained(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
        evt = ToolCallHookEvent(
            tool_call_id=call_ctx.get("tool_call_id", ""),
            tool_name=call_ctx.get("tool_name", ""),
            input=call_ctx.get("input", {}),
            call_ctx=call_ctx,
        )
        return await hooks.emit(evt)

    return _chained


def chain_after_hooks(hooks: AgentHooks) -> Callable[..., Awaitable[Any]] | None:
    if not hooks._handlers.get("tool_result"):
        return None

    async def _chained(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
        evt = ToolResultHookEvent(
            tool_call_id=call_ctx.get("tool_call_id", ""),
            tool_name=call_ctx.get("tool_name", ""),
            input=call_ctx.get("input", {}),
            result=call_ctx.get("result"),
            is_error=call_ctx.get("is_error", False),
            call_ctx=call_ctx,
        )
        return await hooks.emit(evt)

    return _chained


def chain_transform_hooks(hooks: AgentHooks) -> Callable[..., Awaitable[Any]] | None:
    if not hooks._handlers.get("context"):
        return None

    async def _chained(llm_messages: list[Any], signal: Any) -> list[Any]:
        evt = ContextHookEvent(messages=list(llm_messages))
        result = await hooks.emit(evt)
        if result and isinstance(result, dict) and "messages" in result:
            return result["messages"]
        return llm_messages

    return _chained


def _filter_stream_kwargs(base_stream: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Pass through kwargs accepted by the provider stream() signature."""
    try:
        sig = inspect.signature(base_stream)
    except (TypeError, ValueError):
        return kwargs
    params = sig.parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    allowed = set(params)
    return {k: v for k, v in kwargs.items() if k in allowed}


def make_stream_fn(
    *,
    provider: ModelProvider,
    hooks: AgentHooks,
    session_id: str,
    base_config: AgentLoopConfig,
) -> Any:
    base_stream = provider.stream

    async def stream_fn(**kwargs: Any) -> Any:
        options = clone_stream_options(base_config.stream_options)
        req_evt = BeforeProviderRequestHookEvent(
            model=kwargs.get("model"),
            session_id=session_id,
            stream_options=options,
        )
        req_result = await hooks.emit(req_evt)
        if req_result and isinstance(req_result, dict) and "stream_options" in req_result:
            options = req_result["stream_options"]

        payload = {
            "messages": list(kwargs.get("messages") or []),
            "tools": list(kwargs.get("tools") or []),
            "system_prompt": kwargs.get("system_prompt", ""),
        }
        payload_evt = BeforeProviderPayloadHookEvent(
            model=kwargs.get("model"),
            payload=payload,
        )
        payload_result = await hooks.emit(payload_evt)
        if payload_result and isinstance(payload_result, dict) and "payload" in payload_result:
            payload = payload_result["payload"]

        call_kwargs = dict(kwargs)
        call_kwargs["messages"] = payload.get("messages", call_kwargs.get("messages"))
        call_kwargs["tools"] = payload.get("tools", call_kwargs.get("tools"))
        call_kwargs["system_prompt"] = payload.get(
            "system_prompt", call_kwargs.get("system_prompt", ""),
        )
        call_kwargs["stream_options"] = options
        if options.get("headers"):
            call_kwargs["request_headers"] = dict(options["headers"])
        if options.get("metadata"):
            call_kwargs["request_metadata"] = dict(options["metadata"])
        if "temperature" in options:
            call_kwargs["temperature"] = options["temperature"]
        if "max_tokens" in options:
            call_kwargs["max_tokens"] = options["max_tokens"]

        async for evt in base_stream(**_filter_stream_kwargs(base_stream, call_kwargs)):
            yield evt

        resp_evt = AfterProviderResponseHookEvent(
            model=kwargs.get("model"),
            status=200,
            headers={},
        )
        await hooks.emit(resp_evt)

    return stream_fn


def build_loop_config(
    host: TurnRuntimeHost,
    *,
    provider: ModelProvider,
    auth_source: AuthSource,
    convert_to_llm: Any,
    tool_registry: Any | None,
    tool_execution: str,
    tool_timeout: float | None,
    max_turns: int | None,
    max_retries: int,
    retry_base_delay: float,
    retry_max_delay: float,
    compact_callback: Any | None,
    tool_result_max_chars: int,
    human_input_gate: Any,
    tool_catalog_threshold: int | None = None,
    disable_tool_routing: bool = False,
) -> AgentLoopConfig:
    async def auth_resolver(provider_name: str):
        return await auth_source.resolve(provider_name)

    snapshot = create_turn_snapshot(host)
    model = snapshot.model if snapshot.model is not None else host.state.model
    config = AgentLoopConfig(
        model=model,
        stream_fn=provider.stream,
        convert_to_llm=convert_to_llm,
        auth_resolver=auth_resolver,
        transform_context=chain_transform_hooks(host.hooks),
        thinking_level=snapshot.thinking_level,  # type: ignore[arg-type]
        tool_execution=tool_execution,
        tool_registry=tool_registry,
        before_tool_call=chain_before_hooks(host.hooks),
        after_tool_call=chain_after_hooks(host.hooks),
        tool_timeout=tool_timeout,
        max_turns=max_turns,
        max_retries=max_retries,
        retry_base_delay=retry_base_delay,
        retry_max_delay=retry_max_delay,
        compact_callback=compact_callback,
        mutation_queue=FileMutationQueue(),
        tool_result_max_chars=tool_result_max_chars,
        get_steering_messages=host.drain_steering,
        get_follow_up_messages=host.drain_follow_up,
        human_input_gate=human_input_gate,
        prepare_next_turn=host.prepare_next_turn,
        flush_pending_writes=host.flush_pending_writes,
        stream_options=clone_stream_options(snapshot.stream_options),
        tool_catalog_threshold=tool_catalog_threshold,
        disable_tool_routing=disable_tool_routing,
        session_id=host.session_id,
    )
    config.stream_fn = make_stream_fn(
        provider=provider,
        hooks=host.hooks,
        session_id=host.session_id,
        base_config=config,
    )
    return config
