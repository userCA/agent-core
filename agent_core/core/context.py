"""AgentContext / AgentLoopConfig / TurnSnapshot — value snapshots passed into agent_loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Union

from agent_core.core.messages import AgentMessage
from agent_core.core.stream_options import clone_stream_options
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


@dataclass(frozen=True)
class TurnSnapshot:
    """Immutable snapshot of harness config taken at the start of each turn.

    Runtime config setters update the harness but do NOT mutate an in-flight
    snapshot.  At the save point the loop calls ``prepare_next_turn`` to
    create a fresh snapshot from the latest harness state.
    """

    messages: list[AgentMessage] = field(default_factory=list)
    system_prompt: str = ""
    tools: list[Any] = field(default_factory=list)
    model: Model | None = None
    thinking_level: str = "off"
    stream_options: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""


PrepareNextTurn = Callable[[], Awaitable[TurnSnapshot | None]]


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
    # Prompt budget pre-check: None disables; default 0.95 of context_window.
    prompt_budget_ratio: float | None = 0.95
    # C4 single-representation: off | warn (log) | raise (abort turn).
    single_representation_mode: Literal["off", "warn", "raise"] = "warn"
    # Consecutive identical tool+args allowed before hard block; None/0 disables.
    duplicate_tool_max_repeats: int | None = 3
    mutation_queue: Any | None = None
    get_steering_messages: MessageDrainer | None = None
    get_follow_up_messages: MessageDrainer | None = None
    human_input_gate: Any | None = None
    prepare_next_turn: PrepareNextTurn | None = None
    flush_pending_writes: Callable[[], Awaitable[None]] | None = None
    stream_options: dict[str, Any] | None = None
