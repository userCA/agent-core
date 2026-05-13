import asyncio

import httpx
import pytest
import respx

from agent_core.providers.auth import ProviderAuth
from agent_core.providers.openai_provider import OpenAIProvider
from agent_core.providers.types import (
    Model,
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)


def _sse(*chunks: str) -> str:
    body = ""
    for c in chunks:
        body += f"data: {c}\n\n"
    body += "data: [DONE]\n\n"
    return body


@respx.mock
def test_openai_provider_streams_text():
    provider = OpenAIProvider(base_url="https://api.openai.com/v1")
    model = Model(
        provider="openai", id="gpt-4o", context_window=128_000, max_output_tokens=4096
    )
    body = _sse(
        '{"choices":[{"delta":{"content":"Hello"}}]}',
        '{"choices":[{"delta":{"content":" world"}}]}',
        '{"choices":[{"delta":{},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":5,"completion_tokens":2}}',
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    )

    async def run() -> list:
        events = []
        async for evt in provider.stream(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            system_prompt="be brief",
            auth=ProviderAuth(api_key="sk-test"),
        ):
            events.append(evt)
        return events

    events = asyncio.run(run())
    text_deltas = [e for e in events if isinstance(e, StreamTextDelta)]
    assert "".join(e.text for e in text_deltas) == "Hello world"
    ends = [e for e in events if isinstance(e, StreamMessageEnd)]
    assert len(ends) == 1
    assert ends[0].stop_reason == "stop"
    assert ends[0].input_tokens == 5


@respx.mock
def test_openai_provider_streams_tool_call():
    provider = OpenAIProvider(base_url="https://api.openai.com/v1")
    model = Model(
        provider="openai", id="gpt-4o", context_window=128_000, max_output_tokens=4096
    )
    body = _sse(
        '{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"echo","arguments":""}}]}}]}',
        '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"x\\":"}}]}}]}',
        '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"1}"}}]}}]}',
        '{"choices":[{"delta":{},"finish_reason":"tool_calls"}],'
        '"usage":{"prompt_tokens":3,"completion_tokens":4}}',
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    )

    async def run():
        events = []
        async for evt in provider.stream(
            model=model,
            messages=[{"role": "user", "content": "do it"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "description": "echo",
                        "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
                    },
                }
            ],
            system_prompt="",
            auth=ProviderAuth(api_key="sk-test"),
        ):
            events.append(evt)
        return events

    events = asyncio.run(run())
    starts = [e for e in events if isinstance(e, StreamToolCallStart)]
    ends = [e for e in events if isinstance(e, StreamToolCallEnd)]
    assert len(starts) == 1
    assert starts[0].name == "echo"
    assert len(ends) == 1
    assert ends[0].arguments == {"x": 1}
