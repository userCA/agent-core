"""AgentContext / AgentLoopConfig — value snapshots passed into agent_loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from agent_core.providers.auth import ProviderAuth
from agent_core.providers.base import ModelProvider
from agent_core.providers.types import Model

if TYPE_CHECKING:
    from agent_core.tools.base import ToolRegistry

ConvertToLlm = Callable[[list[Any]], Awaitable[list[dict[str, Any]]]]
TransformContext = Callable[
    [list[Any], asyncio.Event | None], Awaitable[list[Any]]
]
AuthResolver = Callable[[str], Awaitable[ProviderAuth]]


@dataclass
class AgentContext:
    system_prompt: str = ""
    messages: list[Any] = field(default_factory=list)
    tools: list[Any] = field(default_factory=list)


@dataclass
class AgentLoopConfig:
    provider: ModelProvider
    model: Model
    convert_to_llm: ConvertToLlm
    auth_resolver: AuthResolver
    transform_context: TransformContext | None = None
    thinking_level: Literal["off", "minimal", "low", "medium", "high", "xhigh"] = "off"
    tool_execution: Literal["parallel", "sequential"] = "parallel"
    temperature: float | None = None
    max_tokens: int | None = None
    tool_registry: ToolRegistry | None = None
    before_tool_call: Any | None = None
    after_tool_call: Any | None = None
    get_steering_messages: Any | None = None
    get_follow_up_messages: Any | None = None
