"""AgentEvent discriminated union emitted by the agent loop."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ThinkingDelta(BaseModel):
    type: Literal["thinking_delta"] = "thinking_delta"
    text: str


class ToolCallDelta(BaseModel):
    type: Literal["tool_call_delta"] = "tool_call_delta"
    id: str
    name: str | None = None
    arguments_delta: str | None = None


MessageDelta = Annotated[
    Union[TextDelta, ThinkingDelta, ToolCallDelta],
    Field(discriminator="type"),
]


class _EventBase(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)


class AgentStart(_EventBase):
    type: Literal["agent_start"] = "agent_start"


class AgentEnd(_EventBase):
    type: Literal["agent_end"] = "agent_end"
    messages: list[Any]


class TurnStart(_EventBase):
    type: Literal["turn_start"] = "turn_start"


class TurnEnd(_EventBase):
    type: Literal["turn_end"] = "turn_end"
    message: Any
    tool_results: list[Any]


class MessageStart(_EventBase):
    type: Literal["message_start"] = "message_start"
    message: Any


class MessageUpdate(_EventBase):
    type: Literal["message_update"] = "message_update"
    message: Any
    delta: MessageDelta


class MessageEnd(_EventBase):
    type: Literal["message_end"] = "message_end"
    message: Any


class ToolExecutionStart(_EventBase):
    type: Literal["tool_execution_start"] = "tool_execution_start"
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]


class ToolExecutionUpdate(_EventBase):
    type: Literal["tool_execution_update"] = "tool_execution_update"
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    partial_result: Any


class ToolExecutionEnd(_EventBase):
    type: Literal["tool_execution_end"] = "tool_execution_end"
    tool_call_id: str
    tool_name: str
    result: Any
    is_error: bool


class HumanInputRequired(_EventBase):
    type: Literal["human_input_required"] = "human_input_required"
    tool_call_id: str
    prompt: str
    input_schema: dict[str, Any]


AgentEvent = Annotated[
    Union[
        AgentStart,
        AgentEnd,
        TurnStart,
        TurnEnd,
        MessageStart,
        MessageUpdate,
        MessageEnd,
        ToolExecutionStart,
        ToolExecutionUpdate,
        ToolExecutionEnd,
        HumanInputRequired,
    ],
    Field(discriminator="type"),
]
