import json
import pytest
import httpx
import respx

from agent_core.providers.anthropic_provider import (
    AnthropicProvider,
    THINKING_BUDGETS,
    _convert_messages,
    _convert_tool_def,
)
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import Model


def test_list_models():
    provider = AnthropicProvider()
    models = provider.list_models()
    assert len(models) == 2
    assert models[0].provider == "anthropic"


def test_convert_tool_def():
    openai_tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
        },
    }
    anthropic = _convert_tool_def(openai_tool)
    assert anthropic["name"] == "get_weather"
    assert anthropic["description"] == "Get weather"
    assert anthropic["input_schema"] == {"type": "object", "properties": {"city": {"type": "string"}}}


def test_convert_messages_basic():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    anthropic_msgs, system = _convert_messages(msgs, "")
    assert system == ""
    assert len(anthropic_msgs) == 2
    assert anthropic_msgs[0]["role"] == "user"
    assert anthropic_msgs[0]["content"] == [{"type": "text", "text": "hello"}]


def test_convert_messages_with_system():
    msgs = [
        {"role": "system", "content": "You are a bot"},
        {"role": "user", "content": "hello"},
    ]
    anthropic_msgs, system = _convert_messages(msgs, "")
    assert system == "You are a bot"
    assert len(anthropic_msgs) == 1


def test_convert_messages_merges_same_role():
    msgs = [
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c"},
    ]
    anthropic_msgs, _ = _convert_messages(msgs, "")
    assert len(anthropic_msgs) == 2
    assert anthropic_msgs[0]["content"] == [
        {"type": "text", "text": "a"},
        {"type": "text", "text": "b"},
    ]


def test_convert_messages_tool_calls():
    msgs = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "tc1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city": "SF"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tc1", "content": "sunny"},
    ]
    anthropic_msgs, _ = _convert_messages(msgs, "")
    assert len(anthropic_msgs) == 2
    assistant = anthropic_msgs[0]
    assert assistant["content"][0]["type"] == "tool_use"
    assert assistant["content"][0]["name"] == "get_weather"
    user = anthropic_msgs[1]
    assert user["content"][0]["type"] == "tool_result"


@pytest.mark.asyncio
async def test_stream_parsing():
    provider = AnthropicProvider()
    sse_lines = [
        "data: " + json.dumps({"type": "message_start", "message": {"usage": {"input_tokens": 10}}}),
        "data: " + json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        "data: " + json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}),
        "data: " + json.dumps({"type": "content_block_stop", "index": 0}),
        "data: " + json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}}),
        "data: " + json.dumps({"type": "message_stop"}),
    ]

    async def _aiter_lines():
        for line in sse_lines:
            yield line

    class FakeResp:
        async def aiter_lines(self):
            async for line in _aiter_lines():
                yield line

    events = []
    async for evt in provider._parse_sse(FakeResp(), None):
        events.append(evt)

    assert events[0].type == "text_delta"
    assert events[0].text == "Hello"
    assert events[1].type == "message_end"


@pytest.mark.asyncio
async def test_build_payload_thinking():
    provider = AnthropicProvider()
    model = Model(
        provider="anthropic",
        id="claude-sonnet-4-6",
        context_window=200_000,
        max_output_tokens=8192,
        supports_reasoning=True,
    )
    payload = provider._build_payload(
        model=model,
        messages=[{"role": "user", "content": "hi"}],
        system="",
        tools=[],
        thinking_level="medium",
        temperature=None,
        max_tokens=None,
    )
    assert "thinking" in payload
    assert payload["thinking"]["type"] == "enabled"
    assert payload["thinking"]["budget_tokens"] == THINKING_BUDGETS["medium"]


@pytest.mark.asyncio
async def test_stream_http_error():
    provider = AnthropicProvider()
    with respx.mock:
        route = respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )
        events = []
        async for evt in provider.stream(
            model=Model(provider="anthropic", id="claude-sonnet-4-6", context_window=200_000, max_output_tokens=8192),
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            system_prompt="",
            auth=ProviderAuth(api_key="fake"),
        ):
            events.append(evt)
        assert len(events) == 1
        assert events[0].type == "error"
        assert "401" in events[0].message
