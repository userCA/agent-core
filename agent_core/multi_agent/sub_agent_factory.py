"""Create isolated/forked sub-agent harnesses from profiles."""

from __future__ import annotations

import inspect
import secrets
from datetime import datetime, timezone
from typing import Any

from agent_core.core.state import AgentState
from agent_core.multi_agent.types import AgentProfile
from agent_core.providers.auth import AuthSource
from agent_core.providers.base import ModelProvider
from agent_core.providers.types import Model
from agent_core.session.harness import AgentHarness
from agent_core.session.store import SessionHeader, SessionStore
from agent_core.session.tool_utils import resolve_tool_name
from agent_core.tools.base import Tool, ToolRegistry


def make_sub_session_id(parent_session_id: str, profile_name: str) -> str:
    return f"{parent_session_id}__sub__{profile_name}__{secrets.token_hex(4)}"


async def resolve_system_prompt(value: Any) -> str:
    if callable(value):
        result = value()
        if inspect.isawaitable(result):
            result = await result
        return str(result)
    return str(value)


class SubAgentFactory:
    def __init__(
        self,
        *,
        provider: ModelProvider,
        auth_source: AuthSource,
        store: SessionStore,
        parent_session_id: str,
        default_model: Model,
        all_tools: list[Tool],
        tool_registry: ToolRegistry | None = None,
        delegate_tool_name: str = "delegate_task",
        owner: str = "",
        harness_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._provider = provider
        self._auth_source = auth_source
        self._store = store
        self._parent_session_id = parent_session_id
        self._default_model = default_model
        self._all_tools = list(all_tools)
        self._tool_registry = tool_registry
        self._delegate_tool_name = delegate_tool_name
        self._owner = owner
        self._harness_kwargs = dict(harness_kwargs or {})

    def _filter_tools(self, profile: AgentProfile) -> list[Tool]:
        tools = self._all_tools
        if profile.tools is not None:
            allow = set(profile.tools)
            tools = [
                t for i, t in enumerate(tools)
                if resolve_tool_name(t, i) in allow
            ]
        if not profile.allow_nested_delegate:
            tools = [
                t for i, t in enumerate(tools)
                if resolve_tool_name(t, i) != self._delegate_tool_name
            ]
        return tools

    async def create(self, profile: AgentProfile) -> tuple[AgentHarness, str]:
        session_id = make_sub_session_id(self._parent_session_id, profile.name)
        header = SessionHeader(
            id=session_id,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            cwd="",
            owner=self._owner,
        )
        if profile.isolation == "forked":
            await self._store.fork_session(
                self._parent_session_id, session_id, header=header
            )
        else:
            await self._store.create_session(session_id, header)

        tools = self._filter_tools(profile)
        system_prompt = await resolve_system_prompt(profile.system_prompt)
        model = profile.model or self._default_model
        thinking = profile.thinking_level or "off"

        initial = AgentState(
            model=model,
            system_prompt=system_prompt,
            thinking_level=thinking,
            tools=list(tools),
        )
        kw = {
            k: v
            for k, v in self._harness_kwargs.items()
            if k
            not in {
                "provider",
                "auth_source",
                "store",
                "session_id",
                "initial_state",
                "tool_registry",
            }
        }
        harness = AgentHarness(
            provider=self._provider,
            auth_source=self._auth_source,
            store=self._store,
            session_id=session_id,
            initial_state=initial,
            tool_registry=self._tool_registry,
            **kw,
        )
        await harness.start()
        harness.state.system_prompt = system_prompt
        if harness.state.model is None:
            harness.state.model = model
        return harness, session_id
