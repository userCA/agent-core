"""Mutable runtime state shared across an Agent run."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_core.core.messages import AgentMessage

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    system_prompt: str = ""
    model: Any | None = None
    thinking_level: ThinkingLevel = "off"
    tools: list[Any] = Field(default_factory=list)
    messages: list[AgentMessage] = Field(default_factory=list)

    is_streaming: bool = False
    streaming_message: Any | None = None
    error_message: str | None = None

    @field_validator("tools", "messages", mode="before")
    @classmethod
    def _copy_list(cls, v: Any) -> Any:
        if isinstance(v, list):
            return list(v)
        return v
