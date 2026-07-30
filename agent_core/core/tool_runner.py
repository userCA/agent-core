"""Tool execution: parallel/sequential dispatch, hook invocation, HITL integration."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, AsyncIterator

from agent_core.core.content import TextContent
from agent_core.core.context import AgentLoopConfig
from agent_core.core.events import HumanInputRequired, ToolExecutionEnd, ToolExecutionStart, ToolExecutionUpdate
from agent_core.core.human_input import HumanInputGate, RequiresHumanInput
from agent_core.core.messages import AssistantMessage, ToolResultMessage

if TYPE_CHECKING:
    from agent_core.core.tool_guard import DuplicateToolCallGuard
    from agent_core.tools.base import ToolContext, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


async def execute_tools(
    *,
    assistant: AssistantMessage,
    config: AgentLoopConfig,
    context: Any,
    signal: asyncio.Event | None,
    tool_results_out: list[Any],
    human_input_gate: HumanInputGate | None = None,
    mutation_queue: Any = None,
    duplicate_guard: DuplicateToolCallGuard | None = None,
) -> AsyncIterator[Any]:
    # Lazy import to break circular dependency: core → tools → core
    from agent_core.tools.base import ToolResult  # noqa: F811

    registry = config.tool_registry
    if registry is None:
        return

    calls = assistant.tool_calls()
    if not calls:
        return

    mode = config.tool_execution
    before = config.before_tool_call
    after = config.after_tool_call
    tool_timeout = config.tool_timeout

    if mode == "parallel":
        for tc in calls:
            yield ToolExecutionStart(
                tool_call_id=tc.id, tool_name=tc.name, args=tc.arguments
            )
        results = await _run_tools_parallel(
            calls=calls,
            registry=registry,
            before=before,
            after=after,
            signal=signal,
            mutation_queue=mutation_queue,
            tool_timeout=tool_timeout,
            duplicate_guard=duplicate_guard,
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
                tool_name=tool_call.name,
                content=result.content,
                is_error=is_error,
                details=getattr(result, "details", None),
                timestamp=time.time(),
            )
            context.messages.append(tool_result_msg)
            tool_results_out.append(tool_result_msg)
    else:
        for tc in calls:
            yield ToolExecutionStart(
                tool_call_id=tc.id, tool_name=tc.name, args=tc.arguments
            )

            update_queue: asyncio.Queue[ToolResult] = asyncio.Queue()

            def _on_update(partial: ToolResult) -> None:
                update_queue.put_nowait(partial)

            tool_task = asyncio.create_task(
                _run_single_tool(
                    tc,
                    registry,
                    before,
                    after,
                    signal,
                    mutation_queue,
                    _on_update,
                    tool_timeout=tool_timeout,
                    duplicate_guard=duplicate_guard,
                )
            )

            # Stream intermediate updates while the tool runs
            while not tool_task.done():
                try:
                    partial = update_queue.get_nowait()
                    yield ToolExecutionUpdate(
                        tool_call_id=tc.id,
                        tool_name=tc.name,
                        args=tc.arguments,
                        partial_result=partial,
                    )
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.5)

            # Drain remaining updates
            while not update_queue.empty():
                partial = update_queue.get_nowait()
                yield ToolExecutionUpdate(
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                    args=tc.arguments,
                    partial_result=partial,
                )

            try:
                _, result, is_error = tool_task.result()
            except RequiresHumanInput as exc:
                if human_input_gate is None:
                    result = ToolResult(
                        content=[TextContent(text="Human input required but HITL is not configured.")]
                    )
                    is_error = True
                else:
                    future = human_input_gate.require_input(tc.id)
                    yield HumanInputRequired(
                        tool_call_id=tc.id,
                        prompt=exc.prompt,
                        input_schema=exc.input_schema,
                    )
                    values = await future
                    if isinstance(tc.arguments, dict):
                        tc.arguments.update(values)
                    _, result, is_error = await _run_single_tool(
                        tc,
                        registry,
                        before,
                        after,
                        signal,
                        mutation_queue,
                        _on_update,
                        tool_timeout=tool_timeout,
                        duplicate_guard=duplicate_guard,
                    )
            yield ToolExecutionEnd(
                tool_call_id=tc.id,
                tool_name=tc.name,
                result=result,
                is_error=is_error,
            )
            tool_result_msg = ToolResultMessage(
                tool_call_id=tc.id,
                tool_name=tc.name,
                content=result.content,
                is_error=is_error,
                details=getattr(result, "details", None),
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
    mutation_queue: Any | None = None,
    on_update: Any = None,
    tool_timeout: float | None = None,
    duplicate_guard: DuplicateToolCallGuard | None = None,
) -> tuple[Any, Any, bool]:
    from agent_core.tools.base import ToolResult, ToolContext  # noqa: F811

    abort_event = signal or asyncio.Event()
    tool = registry.get(tool_call.name)

    if tool is None:
        result = ToolResult(
            content=[TextContent(text=f"Tool '{tool_call.name}' not found.")]
        )
        return tool_call, result, True

    if duplicate_guard is not None:
        blocked = duplicate_guard.check(
            getattr(tool_call, "name", ""),
            getattr(tool_call, "arguments", None),
        )
        if blocked:
            result = ToolResult(
                content=[TextContent(text=blocked)],
                details={"__duplicate_blocked": True},
            )
            return tool_call, result, True

    _extra_metadata: dict[str, Any] = {}

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
            if hook_result and hook_result.get("inject_metadata"):
                _extra_metadata.update(hook_result["inject_metadata"])
            if hook_result and hook_result.get("mutated_args"):
                tool_call.arguments.update(hook_result["mutated_args"])
        except Exception as exc:
            logger.warning("before_tool_call hook failed: %s", exc)

    # Validate args if tool defines an args_model
    args_model = getattr(tool.definition, "args_model", None)
    if args_model is not None:
        try:
            tool_call.arguments = args_model(**tool_call.arguments).model_dump()
        except Exception as exc:
            logger.warning("Args validation failed for tool '%s': %s", tool_call.name, exc)
            result = ToolResult(
                content=[TextContent(text=f"Invalid arguments for '{tool_call.name}': {exc}")]
            )
            return tool_call, result, True

    ctx = ToolContext(
        signal=abort_event,
        mutation_queue=mutation_queue,
        on_update=on_update,
        metadata=_extra_metadata,
    )

    effective_timeout = tool.definition.timeout_seconds
    if effective_timeout is None:
        effective_timeout = tool_timeout

    try:
        if effective_timeout is not None:
            result = await asyncio.wait_for(
                tool.execute(
                    tool_call_id=tool_call.id,
                    params=tool_call.arguments,
                    ctx=ctx,
                ),
                timeout=effective_timeout,
            )
        else:
            result = await tool.execute(
                tool_call_id=tool_call.id,
                params=tool_call.arguments,
                ctx=ctx,
            )
        is_error = False
    except asyncio.TimeoutError:
        result = ToolResult(
            content=[TextContent(
                text=f"Tool '{tool_call.name}' timed out after {effective_timeout:.0f}s"
            )]
        )
        is_error = True
    except RequiresHumanInput:
        raise
    except Exception as exc:
        logger.warning("Tool '%s' execution failed: %s", tool_call.name, exc)
        result = ToolResult(content=[TextContent(text=str(exc))])
        is_error = True

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
            if hook_result and hook_result.get("result") is not None:
                hr = hook_result["result"]
                # Reducer may return a ToolResult instance; legacy hooks return a dict.
                if hasattr(hr, "content") and not isinstance(hr, dict):
                    result = hr
                else:
                    result = ToolResult(
                        content=hr.get("content", result.content),
                        details=hr.get("details", result.details),
                        display=hr.get("display", result.display),
                    )
                if "is_error" in hook_result:
                    is_error = bool(hook_result["is_error"])
        except Exception as exc:
            logger.warning("after_tool_call hook failed: %s", exc)

    return tool_call, result, is_error


async def _run_tools_parallel(
    *,
    calls: list[Any],
    registry: ToolRegistry,
    before: Any,
    after: Any,
    signal: asyncio.Event | None,
    mutation_queue: Any | None = None,
    tool_timeout: float | None = None,
    max_concurrent: int = 8,
    duplicate_guard: DuplicateToolCallGuard | None = None,
) -> list[tuple[Any, ToolResult, bool]]:
    _sem = asyncio.Semaphore(max_concurrent)

    async def _bounded(c):
        async with _sem:
            return await _run_single_tool(
                c,
                registry,
                before,
                after,
                signal,
                mutation_queue,
                tool_timeout=tool_timeout,
                duplicate_guard=duplicate_guard,
            )

    tasks = [_bounded(c) for c in calls]
    return await asyncio.gather(*tasks)
