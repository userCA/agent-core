"""Pure async-generator agent loop."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.content import TextContent, ToolCallContent
from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    TextDelta,
    ToolCallDelta,
    ThinkingDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)
from agent_core.core.messages import AssistantMessage, ToolResultMessage, Usage
from agent_core.providers.types import (
    StreamError,
    StreamMessageEnd,
    StreamTextDelta,
    StreamThinkingDelta,
    StreamToolCallDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)
from agent_core.tools.base import ToolContext, ToolRegistry, ToolResult


async def agent_loop(
    new_messages: list[Any],
    context: AgentContext,
    config: AgentLoopConfig,
    signal: asyncio.Event | None = None,
) -> AsyncIterator[AgentEvent]:
    """Drive an agent run: yield user messages → stream LLM → execute tools → repeat."""

    yield AgentStart()

    context.messages.extend(new_messages)
    for msg in new_messages:
        yield MessageStart(message=msg)
        yield MessageEnd(message=msg)

    new_assistant_messages: list[Any] = []

    while True:
        if signal is not None and signal.is_set():
            break

        yield TurnStart()

        llm_messages = await config.convert_to_llm(context.messages)
        if config.transform_context is not None:
            llm_messages = await config.transform_context(llm_messages, signal)

        auth = await config.auth_resolver(config.model.provider)

        tool_defs = _tools_to_provider_format(context.tools)

        assistant, updates = await _stream_assistant(
            config=config,
            llm_messages=llm_messages,
            tool_defs=tool_defs,
            auth=auth,
            signal=signal,
        )

        yield MessageStart(message=assistant)
        for upd in updates:
            yield upd
        yield MessageEnd(message=assistant)
        context.messages.append(assistant)
        new_assistant_messages.append(assistant)

        tool_result_messages: list[Any] = []
        if assistant.has_tool_calls() and config.tool_registry is not None:
            async for evt in _execute_tools(
                assistant=assistant,
                config=config,
                context=context,
                signal=signal,
                tool_results_out=tool_result_messages,
            ):
                yield evt

        yield TurnEnd(message=assistant, tool_results=tool_result_messages)

        if assistant.stop_reason in ("error", "aborted"):
            break
        if tool_result_messages:
            continue

        steering: list[Any] = []
        if config.get_steering_messages is not None:
            steering = await config.get_steering_messages()
        if steering:
            for msg in steering:
                context.messages.append(msg)
                yield MessageStart(message=msg)
                yield MessageEnd(message=msg)
            continue

        follow_ups: list[Any] = []
        if config.get_follow_up_messages is not None:
            follow_ups = await config.get_follow_up_messages()
        if follow_ups:
            for msg in follow_ups:
                context.messages.append(msg)
                yield MessageStart(message=msg)
                yield MessageEnd(message=msg)
            continue

        break

    yield AgentEnd(messages=new_assistant_messages)


async def agent_loop_continue(
    context: AgentContext,
    config: AgentLoopConfig,
    signal: asyncio.Event | None = None,
) -> AsyncIterator[AgentEvent]:
    """Continue an agent run from the existing transcript (no new user message)."""

    async for evt in agent_loop([], context, config, signal):
        yield evt


def _tools_to_provider_format(tools: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in tools:
        if isinstance(t, dict):
            out.append(_definition_to_openai(t))
        elif hasattr(t, "model_dump"):
            out.append(_definition_to_openai(t.model_dump()))
    return out


def _definition_to_openai(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": d["name"],
            "description": d.get("description", ""),
            "parameters": d.get("parameters", {"type": "object", "properties": {}}),
        },
    }


async def _stream_assistant(
    *,
    config: AgentLoopConfig,
    llm_messages: list[dict[str, Any]],
    tool_defs: list[dict[str, Any]],
    auth: Any,
    signal: asyncio.Event | None,
) -> tuple[AssistantMessage, list[MessageUpdate]]:
    assistant = AssistantMessage(
        content=[],
        usage=Usage(),
        stop_reason="stop",
        provider=config.model.provider,
        model=config.model.id,
        timestamp=time.time(),
    )

    updates: list[MessageUpdate] = []
    text_buf = ""
    tool_buffers: dict[str, dict[str, Any]] = {}
    error_message: str | None = None

    stream = config.provider.stream(
        model=config.model,
        messages=llm_messages,
        tools=tool_defs,
        system_prompt=config.model.provider and config.model.provider or "",
        thinking_level=config.thinking_level,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        signal=signal,
        auth=auth,
    )
    # provider.stream may be coroutine returning AsyncIterator or AsyncIterator itself
    if hasattr(stream, "__aiter__"):
        iterator = stream
    else:
        iterator = await stream  # type: ignore[assignment]

    async for evt in iterator:
        if isinstance(evt, StreamTextDelta):
            text_buf += evt.text
            updates.append(MessageUpdate(message=assistant, delta=TextDelta(text=evt.text)))
        elif isinstance(evt, StreamThinkingDelta):
            updates.append(MessageUpdate(message=assistant, delta=ThinkingDelta(text=evt.text)))
        elif isinstance(evt, StreamToolCallStart):
            tool_buffers[evt.id] = {"id": evt.id, "name": evt.name, "args": {}}
            updates.append(
                MessageUpdate(
                    message=assistant,
                    delta=ToolCallDelta(id=evt.id, name=evt.name),
                )
            )
        elif isinstance(evt, StreamToolCallDelta):
            updates.append(
                MessageUpdate(
                    message=assistant,
                    delta=ToolCallDelta(id=evt.id, arguments_delta=evt.arguments_delta),
                )
            )
        elif isinstance(evt, StreamToolCallEnd):
            slot = tool_buffers.setdefault(evt.id, {"id": evt.id, "name": "", "args": {}})
            slot["args"] = evt.arguments
        elif isinstance(evt, StreamMessageEnd):
            assistant.usage = Usage(
                input_tokens=evt.input_tokens,
                output_tokens=evt.output_tokens,
            )
            stop = evt.stop_reason
            if stop in ("tool_calls", "tool_use"):
                assistant.stop_reason = "tool_use"
            elif stop in ("stop", "end_turn"):
                assistant.stop_reason = "stop"
            elif stop == "length":
                assistant.stop_reason = "length"
            else:
                assistant.stop_reason = "stop"
        elif isinstance(evt, StreamError):
            error_message = evt.message
            assistant.stop_reason = "error"

    if text_buf:
        assistant.content.append(TextContent(text=text_buf))
    for slot in tool_buffers.values():
        assistant.content.append(
            ToolCallContent(id=slot["id"], name=slot["name"] or "", arguments=slot["args"])
        )
    if error_message:
        assistant.error_message = error_message

    return assistant, updates


async def _execute_tools(
    *,
    assistant: AssistantMessage,
    config: AgentLoopConfig,
    context: AgentContext,
    signal: asyncio.Event | None,
    tool_results_out: list[Any],
) -> AsyncIterator[AgentEvent]:
    registry = config.tool_registry
    if registry is None:
        return

    calls = assistant.tool_calls()
    if not calls:
        return

    if config.tool_execution == "parallel":
        for tc in calls:
            yield ToolExecutionStart(
                tool_call_id=tc.id, tool_name=tc.name, args=tc.arguments
            )
        results = await _run_tools_parallel(
            calls=calls,
            registry=registry,
            before=config.before_tool_call,
            after=config.after_tool_call,
            signal=signal,
        )
        for tool_call, result, is_error in results:
            yield ToolExecutionEnd(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result=result,
                is_error=is_error,
            )
            tool_result_msg = ToolResultMessage(
                tool_call_id=tool_call.id,
                content=result.content,
                is_error=is_error,
                timestamp=time.time(),
            )
            context.messages.append(tool_result_msg)
            tool_results_out.append(tool_result_msg)
    else:
        for tc in calls:
            yield ToolExecutionStart(
                tool_call_id=tc.id, tool_name=tc.name, args=tc.arguments
            )
            _, result, is_error = await _run_single_tool(
                tc, registry, config.before_tool_call, config.after_tool_call, signal
            )
            yield ToolExecutionEnd(
                tool_call_id=tc.id,
                tool_name=tc.name,
                result=result,
                is_error=is_error,
            )
            tool_result_msg = ToolResultMessage(
                tool_call_id=tc.id,
                content=result.content,
                is_error=is_error,
                timestamp=time.time(),
            )
            context.messages.append(tool_result_msg)
            tool_results_out.append(tool_result_msg)


async def _run_single_tool(
    tool_call: Any,
    registry: ToolRegistry,
    before: Any,
    after: Any,
    signal: asyncio.Event | None,
) -> tuple[Any, ToolResult, bool]:
    abort_event = signal or asyncio.Event()
    tool = registry.get(tool_call.name)

    if tool is None:
        result = ToolResult(
            content=[TextContent(text=f"Tool '{tool_call.name}' not found.")]
        )
        return tool_call, result, True

    # before hook
    if before is not None:
        try:
            hook_result = await before(
                {"tool_call": tool_call, "args": tool_call.arguments}
            )
            if hook_result and hook_result.get("block"):
                result = ToolResult(
                    content=[
                        TextContent(
                            text=hook_result.get("reason", "Blocked by before_tool_call hook.")
                        )
                    ]
                )
                return tool_call, result, True
        except Exception:
            pass

    ctx = ToolContext(signal=abort_event)
    try:
        result = await tool.execute(
            tool_call_id=tool_call.id,
            params=tool_call.arguments,
            ctx=ctx,
        )
        is_error = False
    except Exception as exc:
        result = ToolResult(content=[TextContent(text=str(exc))])
        is_error = True

    # after hook
    if after is not None:
        try:
            hook_result = await after(
                {
                    "tool_call": tool_call,
                    "args": tool_call.arguments,
                    "result": result,
                    "is_error": is_error,
                }
            )
            if hook_result and hook_result.get("result"):
                result = ToolResult(
                    content=hook_result["result"].get("content", result.content),
                    details=hook_result["result"].get("details", result.details),
                )
        except Exception:
            pass

    return tool_call, result, is_error


async def _run_tools_parallel(
    *,
    calls: list[Any],
    registry: ToolRegistry,
    before: Any,
    after: Any,
    signal: asyncio.Event | None,
) -> list[tuple[Any, ToolResult, bool]]:
    tasks = [
        _run_single_tool(c, registry, before, after, signal) for c in calls
    ]
    return await asyncio.gather(*tasks)


async def _run_tools_sequential(
    *,
    calls: list[Any],
    registry: ToolRegistry,
    before: Any,
    after: Any,
    signal: asyncio.Event | None,
) -> list[tuple[Any, ToolResult, bool]]:
    results: list[tuple[Any, ToolResult, bool]] = []
    for c in calls:
        results.append(await _run_single_tool(c, registry, before, after, signal))
    return results
