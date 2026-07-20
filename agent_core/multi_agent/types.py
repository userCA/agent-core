"""Multi-agent types: profiles, options, results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

if TYPE_CHECKING:
    from agent_core.multi_agent.profile_registry import AgentProfileRegistry
    from agent_core.multi_agent.sub_agent_runner import SubAgentRunner

IsolationMode = Literal["isolated", "forked"]
DelegationMode = Literal["single", "parallel", "chain"]
SubAgentStatus = Literal["completed", "failed", "aborted"]

SystemPromptValue = str | Callable[..., Awaitable[str] | str]


@dataclass
class AgentProfile:
    name: str
    description: str
    system_prompt: SystemPromptValue
    model: Any | None = None
    thinking_level: str | None = None
    tools: list[str] | None = None
    isolation: IsolationMode = "isolated"
    max_concurrency: int = 1
    allow_nested_delegate: bool = False


@dataclass
class MultiAgentHarnessOptions:
    profiles: list[AgentProfile]
    max_concurrent_agents: int = 4
    delegate_tool_name: str = "delegate_task"
    routing_prompt: str | None = None
    cleanup_sub_sessions: bool = False


@dataclass
class SubAgentResult:
    agent_name: str
    task: str
    status: SubAgentStatus
    response_text: str
    usage: dict[str, int | float] = field(default_factory=dict)
    duration_ms: int = 0
    error_message: str | None = None
    session_id: str | None = None


@dataclass
class MultiAgentHandle:
    registry: AgentProfileRegistry
    runner: SubAgentRunner
