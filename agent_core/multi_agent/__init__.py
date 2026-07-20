"""Multi-agent orchestration (Harness-in-Tool)."""

from agent_core.multi_agent.factory import create_multi_agent_harness
from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.types import (
    AgentProfile,
    DelegationMode,
    IsolationMode,
    MultiAgentHandle,
    MultiAgentHarnessOptions,
    SubAgentResult,
)

__all__ = [
    "AgentProfile",
    "AgentProfileRegistry",
    "DelegationMode",
    "IsolationMode",
    "MultiAgentHandle",
    "MultiAgentHarnessOptions",
    "SubAgentResult",
    "create_multi_agent_harness",
]
