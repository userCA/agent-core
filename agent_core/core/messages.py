"""Message types: user, assistant, tool_result, custom — discriminated union."""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

from agent_core.core.content import ImageContent, TextContent, ToolCallContent

StopReason = Literal[
    "stop", "tool_use", "length", "content_filter", "error", "aborted"
]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: list[TextContent | ImageContent]
    timestamp: float


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: list[TextContent | ToolCallContent]
    usage: Usage = Usage()
    stop_reason: StopReason = "stop"
    error_message: str | None = None
    retryable_error: bool = False
    overflow_error: bool = False
    provider: str | None = None
    model: str | None = None
    timestamp: float

    def tool_calls(self) -> list[ToolCallContent]:
        return [c for c in self.content if isinstance(c, ToolCallContent)]

    def has_tool_calls(self) -> bool:
        return any(isinstance(c, ToolCallContent) for c in self.content)


class ToolResultMessage(BaseModel):
    role: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    tool_name: str | None = None
    content: list[TextContent | ImageContent]
    is_error: bool = False
    timestamp: float = Field(default_factory=time.time)


class CustomMessage(BaseModel):
    role: Literal["custom"] = "custom"
    custom_type: str
    content: Any
    display: Any | None = None
    details: Any | None = None
    timestamp: float


AgentMessage = Annotated[
    Union[UserMessage, AssistantMessage, ToolResultMessage, CustomMessage],
    Field(discriminator="role"),
]

_agent_message_adapter: TypeAdapter[AgentMessage] = TypeAdapter(AgentMessage)


def deserialize_message(data: dict[str, Any]) -> AgentMessage:
    """Restore an AgentMessage from its JSON-serialized dict form."""
    return _agent_message_adapter.validate_python(data)
