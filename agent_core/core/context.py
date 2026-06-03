"""AgentContext / AgentLoopConfig — value snapshots passed into agent_loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Union

from agent_core.core.messages import AgentMessage
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import Model

if TYPE_CHECKING:
    from agent_core.tools.base import ToolRegistry

ConvertToLlm = Callable[[list[AgentMessage]], Awaitable[list[dict[str, Any]]]]
TransformContext = Callable[
    [list[Any], asyncio.Event | None], Awaitable[list[Any]]
]
AuthResolver = Callable[[str], Awaitable[ProviderAuth]]

# Hook signatures
BeforeToolCallHook = Callable[
    [dict[str, Any]], Union[dict[str, Any], Awaitable[dict[str, Any] | None], None]
]
AfterToolCallHook = Callable[
    [dict[str, Any]], Union[dict[str, Any], Awaitable[dict[str, Any] | None], None]
]
MessageDrainer = Callable[[], Awaitable[list[Any]]]
CompactCallback = Callable[[list[Any]], Awaitable[bool]]


@dataclass
class AgentContext:
    system_prompt: str = ""
    messages: list[AgentMessage] = field(default_factory=list)
    tools: list[Any] = field(default_factory=list)


@dataclass
class AgentLoopConfig:
    model: Model
    stream_fn: Any  # Callable returning AsyncIterator[StreamEvent]
    convert_to_llm: ConvertToLlm
    auth_resolver: AuthResolver
    transform_context: TransformContext | None = None
    thinking_level: Literal["off", "minimal", "low", "medium", "high", "xhigh"] = "off"
    tool_execution: Literal["parallel", "sequential"] = "parallel"
    temperature: float | None = None
    max_tokens: int | None = None
    tool_registry: ToolRegistry | None = None
    before_tool_call: BeforeToolCallHook | None = None
    after_tool_call: AfterToolCallHook | None = None
    tool_timeout: float | None = 120.0
    max_turns: int | None = None
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    tool_result_max_chars: int = 4000
    compact_callback: CompactCallback | None = None
    mutation_queue: Any | None = None
    get_steering_messages: MessageDrainer | None = None
    get_follow_up_messages: MessageDrainer | None = None
    human_input_gate: Any | None = None
