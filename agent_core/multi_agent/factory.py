"""create_multi_agent_harness — assemble orchestrator + delegate_task."""

from __future__ import annotations

from typing import Any

from agent_core.core.state import AgentState
from agent_core.multi_agent.delegate_tool import DEFAULT_ROUTING_HINT, DelegateTaskTool
from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.sub_agent_factory import SubAgentFactory
from agent_core.multi_agent.sub_agent_runner import SubAgentRunner
from agent_core.multi_agent.types import MultiAgentHandle, MultiAgentHarnessOptions
from agent_core.providers.auth import AuthSource
from agent_core.providers.base import ModelProvider
from agent_core.providers.types import Model
from agent_core.session.harness import AgentHarness
from agent_core.session.store import SessionStore
from agent_core.session.tool_utils import resolve_tool_name
from agent_core.tools.base import Tool, ToolRegistry


def _tools_from_arg(
    tools: list[Tool] | ToolRegistry | None,
) -> tuple[list[Tool], ToolRegistry | None]:
    if tools is None:
        return [], None
    if isinstance(tools, ToolRegistry):
        reg = tools
        tool_list: list[Tool] = []
        for info in reg.list():
            t = reg.get(info.name)
            if t is not None:
                tool_list.append(t)
        return tool_list, reg
    return list(tools), None


def build_orchestrator_system_prompt(
    base: str | None,
    registry: AgentProfileRegistry,
    routing_prompt: str | None,
) -> str:
    parts: list[str] = []
    if base:
        parts.append(base.strip())
    parts.append((routing_prompt or DEFAULT_ROUTING_HINT).strip())
    parts.append(registry.format_for_system_prompt())
    return "\n\n".join(parts)


def create_multi_agent_harness(
    *,
    options: MultiAgentHarnessOptions,
    provider: ModelProvider,
    auth_source: AuthSource,
    store: SessionStore,
    session_id: str,
    model: Model | None = None,
    tools: list[Tool] | ToolRegistry | None = None,
    system_prompt: str | None = None,
    initial_state: AgentState | None = None,
    owner: str = "",
    tool_registry: ToolRegistry | None = None,
    **harness_kwargs: Any,
) -> tuple[AgentHarness, MultiAgentHandle]:
    """Create an orchestrator AgentHarness with delegate_task injected."""
    resolved_model = model or (initial_state.model if initial_state else None)
    if resolved_model is None:
        raise ValueError("create_multi_agent_harness requires model or initial_state.model")

    registry = AgentProfileRegistry()
    for p in options.profiles:
        registry.register(p)

    user_tools, tools_as_registry = _tools_from_arg(tools)
    registry_for_exec = tool_registry or tools_as_registry or ToolRegistry()
    for t in user_tools:
        name = resolve_tool_name(t)
        if registry_for_exec.get(name) is None:
            registry_for_exec.register(t)

    factory = SubAgentFactory(
        provider=provider,
        auth_source=auth_source,
        store=store,
        parent_session_id=session_id,
        default_model=resolved_model,
        all_tools=user_tools,
        tool_registry=registry_for_exec,
        delegate_tool_name=options.delegate_tool_name,
        owner=owner,
        harness_kwargs=harness_kwargs,
    )
    runner = SubAgentRunner(
        factory=factory,
        registry=registry,
        store=store,
        max_concurrent_agents=options.max_concurrent_agents,
        cleanup_sub_sessions=options.cleanup_sub_sessions,
    )

    # Sub-agents share the user tool pool (without delegate). After registering
    # delegate on orchestrator registry, rebuild factory all_tools from user_tools only.
    delegate = DelegateTaskTool(
        registry=registry,
        runner=runner,
        name=options.delegate_tool_name,
    )
    registry_for_exec.register(delegate)

    orch_prompt = build_orchestrator_system_prompt(
        system_prompt or (initial_state.system_prompt if initial_state else None),
        registry,
        options.routing_prompt,
    )
    state = initial_state or AgentState()
    state.model = resolved_model
    state.system_prompt = orch_prompt
    orch_tools: list[Tool] = []
    seen: set[str] = set()
    for t in [*user_tools, delegate]:
        n = resolve_tool_name(t)
        if n in seen:
            continue
        seen.add(n)
        orch_tools.append(t)
    state.tools = orch_tools

    harness = AgentHarness(
        provider=provider,
        auth_source=auth_source,
        store=store,
        session_id=session_id,
        initial_state=state,
        tool_registry=registry_for_exec,
        **harness_kwargs,
    )
    return harness, MultiAgentHandle(registry=registry, runner=runner)
