"""Agent loop with emit-sink callback (primary) and async-generator (compat)."""

from __future__ import annotations

import asyncio
import logging
import random as _random
import time
from typing import Any, AsyncIterator, Awaitable, Callable

from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.content import TextContent, ToolCallContent
from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    SavePoint,
    TextDelta,
    ToolCallDelta,
    ThinkingDelta,
    TurnEnd,
    TurnStart,
)
from agent_core.core.messages import AssistantMessage, Usage
from agent_core.core.stream_options import clone_stream_options
from agent_core.core.tool_runner import execute_tools
from agent_core.providers.base import tools_to_provider_format
from agent_core.providers.types import (
    StreamError,
    StreamMessageEnd,
    StreamTextDelta,
    StreamThinkingDelta,
    StreamToolCallDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)

_log = logging.getLogger(__name__)

# -- Type alias for the emit-sink callback --
EventSink = Callable[[AgentEvent], Awaitable[None]]


async def _save_point(
    config: AgentLoopConfig,
    context: AgentContext,
    emit: EventSink,
    turn_count: int,
) -> None:
    """Refresh the turn snapshot at the save point.

    Flushes any pending session writes first, then calls
    ``config.prepare_next_turn`` to obtain a fresh snapshot from the
    latest harness state.  If a snapshot is returned the context and
    relevant config fields are updated so the next iteration uses the
    latest values.  A ``SavePoint`` event is emitted afterward.
    """
    if config.flush_pending_writes is not None:
        await config.flush_pending_writes()
    if config.prepare_next_turn is not None:
        snapshot = await config.prepare_next_turn()
        if snapshot is not None:
            context.system_prompt = snapshot.system_prompt
            context.messages = list(snapshot.messages)
            context.tools = list(snapshot.tools)
            if snapshot.model is not None:
                config.model = snapshot.model
            config.thinking_level = snapshot.thinking_level  # type: ignore[assignment]
            config.stream_options = clone_stream_options(snapshot.stream_options)
    await emit(SavePoint(turn_count=turn_count))


async def run_agent_loop(
    new_messages: list[Any],
    context: AgentContext,
    config: AgentLoopConfig,
    emit: EventSink,
    signal: asyncio.Event | None = None,
) -> list[Any]:
    """Drive an agent run via emit-sink callback.

    Events are pushed to *emit* as they occur.  Returns the list of new
    assistant messages produced during the run.
    """

    await emit(AgentStart())

    context.messages.extend(new_messages)
    for msg in new_messages:
        await emit(MessageStart(message=msg))
        await emit(MessageEnd(message=msg))

    new_assistant_messages: list[Any] = []
    turn_count = 0

    while True:
        if signal is not None and signal.is_set():
            break
        if config.max_turns is not None and turn_count >= config.max_turns:
            break

        await emit(TurnStart())
        turn_count += 1

        llm_messages = await config.convert_to_llm(context.messages)
        if config.transform_context is not None:
            llm_messages = await config.transform_context(llm_messages, signal)

        auth = await config.auth_resolver(config.model.provider)
        tool_defs = tools_to_provider_format(context.tools)

        max_retries = config.max_retries
        retry_base_delay = config.retry_base_delay
        retry_max_delay = config.retry_max_delay

        assistant: AssistantMessage | None = None
        retry_count = 0
        while True:
            assistant = AssistantMessage(
                content=[],
                usage=Usage(),
                stop_reason="stop",
                provider=config.model.provider,
                model=config.model.id,
                timestamp=time.time(),
            )

            if retry_count == 0:
                # First attempt: stream in real-time for responsiveness.
                await emit(MessageStart(message=assistant))
                async for upd in _stream_assistant(
                    config=config,
                    llm_messages=llm_messages,
                    tool_defs=tool_defs,
                    auth=auth,
                    signal=signal,
                    system_prompt=context.system_prompt,
                    assistant=assistant,
                ):
                    await emit(upd)
            else:
                # Retry attempts: buffer to avoid emitting partial failed output.
                buffered: list[Any] = []
                async for upd in _stream_assistant(
                    config=config,
                    llm_messages=llm_messages,
                    tool_defs=tool_defs,
                    auth=auth,
                    signal=signal,
                    system_prompt=context.system_prompt,
                    assistant=assistant,
                ):
                    buffered.append(upd)
                await emit(MessageStart(message=assistant))
                for upd in buffered:
                    await emit(upd)

            should_retry = False
            if (assistant.stop_reason == "error"
                    and assistant.retryable_error
                    and retry_count < max_retries):
                should_retry = True
                retry_count += 1
                delay = min(retry_base_delay * (2 ** (retry_count - 1)), retry_max_delay)
                delay = delay * (0.5 + _random.random())
                _log.warning(
                    "Retryable error in agent loop (attempt %s/%s), retrying in %.1fs: %s",
                    retry_count, max_retries, delay, assistant.error_message,
                )
                await asyncio.sleep(delay)

            elif (assistant.overflow_error
                    and config.compact_callback is not None
                    and retry_count < max_retries):
                _log.warning(
                    "Context overflow detected (attempt %s/%s), triggering compaction",
                    retry_count + 1, max_retries,
                )
                compacted = await config.compact_callback(context.messages)
                if compacted:
                    retry_count += 1
                    llm_messages = await config.convert_to_llm(context.messages)
                    if config.transform_context is not None:
                        llm_messages = await config.transform_context(llm_messages, signal)
                    should_retry = True
                else:
                    _log.warning("Compaction callback returned False, cannot retry overflow")

            if should_retry:
                continue

            break

        await emit(MessageEnd(message=assistant))

        context.messages.append(assistant)
        new_assistant_messages.append(assistant)

        tool_result_messages: list[Any] = []
        if assistant.has_tool_calls() and config.tool_registry is not None:
            async for evt in execute_tools(
                assistant=assistant,
                config=config,
                context=context,
                signal=signal,
                tool_results_out=tool_result_messages,
                human_input_gate=config.human_input_gate,
                mutation_queue=config.mutation_queue,
            ):
                await emit(evt)

        await emit(TurnEnd(message=assistant, tool_results=tool_result_messages))

        if assistant.stop_reason in ("error", "aborted"):
            break
        if tool_result_messages:
            await _save_point(config, context, emit, turn_count)
            continue

        steering: list[Any] = []
        if config.get_steering_messages is not None:
            steering = await config.get_steering_messages()
        if steering:
            for msg in steering:
                context.messages.append(msg)
                await emit(MessageStart(message=msg))
                await emit(MessageEnd(message=msg))
            await _save_point(config, context, emit, turn_count)
            continue

        follow_ups: list[Any] = []
        if config.get_follow_up_messages is not None:
            follow_ups = await config.get_follow_up_messages()
        if follow_ups:
            for msg in follow_ups:
                context.messages.append(msg)
                await emit(MessageStart(message=msg))
                await emit(MessageEnd(message=msg))
            await _save_point(config, context, emit, turn_count)
            continue

        break

    await emit(AgentEnd(messages=new_assistant_messages))
    return new_assistant_messages


# ---------------------------------------------------------------------------
# Backward-compatible async-generator wrapper
# ---------------------------------------------------------------------------

async def agent_loop(
    new_messages: list[Any],
    context: AgentContext,
    config: AgentLoopConfig,
    signal: asyncio.Event | None = None,
) -> AsyncIterator[AgentEvent]:
    """Backward-compatible async-generator wrapper around :func:`run_agent_loop`.

    .. deprecated::
        Use :func:`run_agent_loop` with an emit-sink callback instead.
    """
    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

    async def _sink(evt: AgentEvent) -> None:
        await queue.put(evt)

    async def _run() -> None:
        try:
            await run_agent_loop(new_messages, context, config, _sink, signal)
        finally:
            await queue.put(None)  # sentinel

    task = asyncio.create_task(_run())
    while True:
        evt = await queue.get()
        if evt is None:
            break
        yield evt
    await task  # propagate exceptions


async def _stream_assistant(
    *,
    config: AgentLoopConfig,
    llm_messages: list[dict[str, Any]],
    tool_defs: list[dict[str, Any]],
    auth: Any,
    signal: asyncio.Event | None,
    system_prompt: str = "",
    assistant: AssistantMessage,
) -> AsyncIterator[MessageUpdate]:
    text_buf = ""
    tool_buffers: dict[str, dict[str, Any]] = {}
    error_message: str | None = None

    stream = config.stream_fn(
        model=config.model,
        messages=llm_messages,
        tools=tool_defs,
        system_prompt=system_prompt,
        thinking_level=config.thinking_level,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        signal=signal,
        auth=auth,
    )
    async for evt in stream:
        if isinstance(evt, StreamTextDelta):
            text_buf += evt.text
            yield MessageUpdate(message=assistant, delta=TextDelta(text=evt.text))
        elif isinstance(evt, StreamThinkingDelta):
            yield MessageUpdate(message=assistant, delta=ThinkingDelta(text=evt.text))
        elif isinstance(evt, StreamToolCallStart):
            tool_buffers[evt.id] = {"id": evt.id, "name": evt.name, "args": {}}
            yield MessageUpdate(
                message=assistant,
                delta=ToolCallDelta(id=evt.id, name=evt.name),
            )
        elif isinstance(evt, StreamToolCallDelta):
            yield MessageUpdate(
                message=assistant,
                delta=ToolCallDelta(id=evt.id, arguments_delta=evt.arguments_delta),
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
            if evt.retryable:
                assistant.retryable_error = True
            if evt.overflow:
                assistant.overflow_error = True

    if text_buf:
        assistant.content.append(TextContent(text=text_buf))
    for slot in tool_buffers.values():
        assistant.content.append(
            ToolCallContent(id=slot["id"], name=slot["name"] or "", arguments=slot["args"])
        )
    if error_message:
        assistant.error_message = error_message
