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
    run_id: str = ""


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


class SkillStart(_EventBase):
    """Emitted when a skill is activated (tool associated with a skill is called)."""
    type: Literal["skill_start"] = "skill_start"
    skill_name: str
    skill_description: str = ""


class SkillEnd(_EventBase):
    """Emitted when a skill's lifecycle completes (at turn end)."""
    type: Literal["skill_end"] = "skill_end"
    skill_name: str


class SavePoint(_EventBase):
    """Emitted at the save point between turns (after turn_end, before next provider request)."""
    type: Literal["save_point"] = "save_point"
    turn_count: int = 0


# -- Harness own events (config / lifecycle) ---------------------------------


class ModelUpdate(_EventBase):
    """Runtime model changed via set_model()."""
    type: Literal["model_update"] = "model_update"
    model: Any = None
    previous_model: Any = None
    source: str = "set"


class ThinkingLevelUpdate(_EventBase):
    """Runtime thinking level changed via set_thinking_level()."""
    type: Literal["thinking_level_update"] = "thinking_level_update"
    level: str = "off"
    previous_level: str = "off"


class ToolsUpdate(_EventBase):
    """Runtime tool set or active tools changed."""
    type: Literal["tools_update"] = "tools_update"
    tool_names: list[str] = []
    previous_tool_names: list[str] = []
    active_tool_names: list[str] = []
    previous_active_tool_names: list[str] = []
    source: str = "set"


class QueueUpdate(_EventBase):
    """Steering / follow-up / next-turn queue changed (enqueue, drain, clear)."""
    type: Literal["queue_update"] = "queue_update"
    steer_count: int = 0
    follow_up_count: int = 0
    next_turn_count: int = 0


class Settled(_EventBase):
    """Agent finished a run and all pending writes are flushed."""
    type: Literal["settled"] = "settled"
    next_turn_count: int = 0


class AbortEvent(_EventBase):
    """Abort completed — queues cleared, run stopped."""
    type: Literal["abort"] = "abort"
    cleared_steer: list[Any] = []
    cleared_follow_up: list[Any] = []


class ResourcesUpdate(_EventBase):
    """Runtime resources changed via set_resources()."""
    type: Literal["resources_update"] = "resources_update"
    resources: Any = None
    previous_resources: Any = None


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
        SkillStart,
        SkillEnd,
        SavePoint,
        ModelUpdate,
        ThinkingLevelUpdate,
        ToolsUpdate,
        QueueUpdate,
        Settled,
        AbortEvent,
        ResourcesUpdate,
    ],
    Field(discriminator="type"),
]
