import time

from pydantic import TypeAdapter

from agent_core.core.content import TextContent, ToolCallContent
from agent_core.core.messages import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    ToolResultMessage,
    Usage,
    UserMessage,
)


def test_user_message():
    msg = UserMessage(content=[TextContent(text="hi")], timestamp=time.time())
    assert msg.role == "user"


def test_assistant_message_with_tool_call():
    msg = AssistantMessage(
        content=[
            TextContent(text="calling tool"),
            ToolCallContent(id="c1", name="echo", arguments={"x": 1}),
        ],
        usage=Usage(input_tokens=10, output_tokens=5),
        stop_reason="tool_use",
        provider="openai",
        model="gpt-4o",
        timestamp=time.time(),
    )
    assert msg.role == "assistant"
    assert msg.has_tool_calls()
    calls = msg.tool_calls()
    assert len(calls) == 1
    assert calls[0].name == "echo"


def test_tool_result_message():
    msg = ToolResultMessage(
        tool_call_id="c1",
        content=[TextContent(text="ok")],
        is_error=False,
        timestamp=time.time(),
    )
    assert msg.role == "tool_result"


def test_custom_message():
    msg = CustomMessage(
        custom_type="notification",
        content={"text": "hi"},
        timestamp=time.time(),
    )
    assert msg.role == "custom"


def test_discriminated_union_dispatch():
    adapter = TypeAdapter(AgentMessage)
    payload = {
        "role": "user",
        "content": [{"type": "text", "text": "hi"}],
        "timestamp": 1.0,
    }
    msg = adapter.validate_python(payload)
    assert isinstance(msg, UserMessage)
