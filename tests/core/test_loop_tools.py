import asyncio

import pytest

from agent_core.core.content import TextContent, ToolCallContent
from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.events import (
    ToolExecutionEnd,
    ToolExecutionStart,
)
from agent_core.core.loop import agent_loop
from agent_core.core.messages import UserMessage
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import StreamMessageEnd, StreamToolCallEnd, StreamToolCallStart
from agent_core.tools.base import ToolContext, ToolDefinition, ToolRegistry, ToolResult

from tests.conftest import FakeProvider, fake_model


class AddTool:
    definition = ToolDefinition(
        name="add",
        description="add two numbers",
        parameters={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}},
    )

    async def execute(self, tool_call_id, params, ctx):
        return ToolResult(content=[TextContent(text=str(params["a"] + params["b"]))])


async def _collect(gen):
    return [e async for e in gen]


def test_agent_loop_executes_tool_call():
    provider = FakeProvider()
    provider.queue_script(
        [
            StreamToolCallStart(id="c1", name="add"),
            StreamToolCallEnd(id="c1", arguments={"a": 1, "b": 2}),
            StreamMessageEnd(stop_reason="tool_calls", input_tokens=3, output_tokens=5),
        ]
    )
    # After tool execution, second LLM call returns final text
    provider.queue_script(
        [
            StreamMessageEnd(stop_reason="stop", input_tokens=3, output_tokens=1),
        ]
    )

    registry = ToolRegistry()
    registry.register(AddTool())

    user_msg = UserMessage(content=[{"type": "text", "text": "add 1 and 2"}], timestamp=0.0)

    async def llm_convert(msgs):
        return [{"role": "user", "content": "add 1 and 2"}]

    async def auth_resolver(_: str) -> ProviderAuth:
        return ProviderAuth(api_key="k")

    context = AgentContext(
        system_prompt="be brief",
        messages=[user_msg],
    )
    config = AgentLoopConfig(
        model=fake_model(),
        stream_fn=provider.stream,
        convert_to_llm=llm_convert,
        auth_resolver=auth_resolver,
        tool_registry=registry,
    )

    async def run():
        return await _collect(agent_loop([user_msg], context, config))

    events = asyncio.run(run())

    tool_starts = [e for e in events if isinstance(e, ToolExecutionStart)]
    tool_ends = [e for e in events if isinstance(e, ToolExecutionEnd)]
    assert len(tool_starts) == 1
    assert len(tool_ends) == 1
    assert tool_ends[0].tool_name == "add"
    assert tool_ends[0].is_error is False

    # Tool result message should be in context.messages
    tool_results = [m for m in context.messages if getattr(m, "role", None) == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0].content[0].text == "3"
    assert tool_results[0].tool_call_id == "c1"
    assert tool_results[0].tool_name == "add"
