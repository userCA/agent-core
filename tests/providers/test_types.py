from pydantic import TypeAdapter

from agent_core.providers.types import (
    Model,
    ModelCost,
    StreamEvent,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
    StreamMessageEnd,
)


def test_model_defaults():
    m = Model(
        provider="openai",
        id="gpt-4o",
        context_window=128_000,
        max_output_tokens=4096,
    )
    assert m.supports_reasoning is False
    assert m.cost.input == 0.0


def test_model_cost():
    m = Model(
        provider="openai",
        id="gpt-4o",
        context_window=1,
        max_output_tokens=1,
        cost=ModelCost(input=2.5, output=10.0),
    )
    assert m.cost.input == 2.5
    assert m.cost.output == 10.0


def test_stream_event_union():
    adapter = TypeAdapter(StreamEvent)
    evt = adapter.validate_python({"type": "text_delta", "text": "hi"})
    assert isinstance(evt, StreamTextDelta)
    evt2 = adapter.validate_python(
        {"type": "tool_call_start", "id": "c1", "name": "echo"}
    )
    assert isinstance(evt2, StreamToolCallStart)
    evt3 = adapter.validate_python(
        {"type": "tool_call_end", "id": "c1", "arguments": {"x": 1}}
    )
    assert isinstance(evt3, StreamToolCallEnd)
    evt4 = adapter.validate_python(
        {"type": "message_end", "stop_reason": "stop"}
    )
    assert isinstance(evt4, StreamMessageEnd)
