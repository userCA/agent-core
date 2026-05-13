"""Tool execution logic extracted from loop.py to avoid circular imports."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

from agent_core.core.content import TextContent
from agent_core.core.events import ToolExecutionEnd, ToolExecutionStart
from agent_core.core.messages import AssistantMessage, ToolResultMessage
from agent_core.tools.base import ToolContext, ToolRegistry, ToolResult


async def execute_tools(
    *,
    assistant: AssistantMessage,
    config: Any,
    context: Any,
    signal: asyncio.Event | None,
    tool_results_out: list[Any],
) -> AsyncIterator[Any]:
    registry: ToolRegistry | None = getattr(config, "tool_registry", None)
    if registry is None:
        return

    calls = assistant.tool_calls()
    if not calls:
        return

    mode = getattr(config, "tool_execution", "parallel")
    before = getattr(config, "before_tool_call", None)
    after = getattr(config, "after_tool_call", None)

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
                tc, registry, before, after, signal
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
