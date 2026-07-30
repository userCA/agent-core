"""Provider-neutral Model and StreamEvent types."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class ModelCost(BaseModel):
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


class Model(BaseModel):
    provider: str
    id: str
    context_window: int
    max_output_tokens: int
    supports_reasoning: bool = False
    supports_xhigh_thinking: bool = False
    supports_vision: bool = True
    cost: ModelCost = ModelCost()


class StreamTextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class StreamThinkingDelta(BaseModel):
    type: Literal["thinking_delta"] = "thinking_delta"
    text: str


class StreamToolCallStart(BaseModel):
    type: Literal["tool_call_start"] = "tool_call_start"
    id: str
    name: str


class StreamToolCallDelta(BaseModel):
    type: Literal["tool_call_delta"] = "tool_call_delta"
    id: str
    arguments_delta: str


class StreamToolCallEnd(BaseModel):
    type: Literal["tool_call_end"] = "tool_call_end"
    id: str
    arguments: dict[str, Any]


class StreamMessageEnd(BaseModel):
    type: Literal["message_end"] = "message_end"
    stop_reason: str
    input_tokens: int = 0
    output_tokens: int = 0


class StreamError(BaseModel):
    type: Literal["error"] = "error"
    message: str
    retryable: bool = False
    overflow: bool = False


StreamEvent = Annotated[
    Union[
        StreamTextDelta,
        StreamThinkingDelta,
        StreamToolCallStart,
        StreamToolCallDelta,
        StreamToolCallEnd,
        StreamMessageEnd,
        StreamError,
    ],
    Field(discriminator="type"),
]
