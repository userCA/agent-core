"""Mutable runtime state shared across an Agent run."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_core.core.messages import AgentMessage

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]


class AgentHarnessPhase(str, Enum):
    """Explicit lifecycle phase of the AgentHarness.

    Structural operations (prompt, compact, navigateTree) require IDLE.
    Runtime config setters are allowed in any phase.
    """

    IDLE = "idle"
    TURN = "turn"
    COMPACTION = "compaction"
    BRANCH_SUMMARY = "branch_summary"
    RETRY = "retry"


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    system_prompt: str = ""
    model: Any | None = None
    thinking_level: ThinkingLevel = "off"
    tools: list[Any] = Field(default_factory=list)
    messages: list[AgentMessage] = Field(default_factory=list)

    phase: AgentHarnessPhase = AgentHarnessPhase.IDLE
    is_streaming: bool = False  # deprecated: use phase instead
    streaming_message: Any | None = None
    error_message: str | None = None

    @field_validator("tools", "messages", mode="before")
    @classmethod
    def _copy_list(cls, v: Any) -> Any:
        if isinstance(v, list):
            return list(v)
        return v
