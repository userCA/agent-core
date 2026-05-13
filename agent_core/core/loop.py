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
    """Delegate to tool_runner to avoid circular imports at module level."""
    from agent_core.core.tool_runner import execute_tools

    async for evt in execute_tools(
        assistant=assistant,
        config=config,
        context=context,
        signal=signal,
        tool_results_out=tool_results_out,
    ):
        yield evt
