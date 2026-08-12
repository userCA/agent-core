"""Generic chat assistant built on agent_core with tool and skill support."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable

from agent_core.core.content import ImageContent
from agent_core.core.events import (
    AgentEvent,
    MessageEnd,
    MessageUpdate,
    TextDelta,
    ToolCallDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.jsonl_store import JsonlStore
from agent_core.session.store import SessionStore
from agent_core.prompts.builder import SystemPromptBuilder
from agent_core.resources.agents import AgentDefinition
from agent_core.resources.loader import ResourceLoader
from agent_core.resources.types import Skill
from agent_core.resources.skill_activation import skill_progressive_enabled
from agent_core.tools.base import Tool, ToolRegistry
from agent_core.tools.local import create_all_tools

from scene.skill_runtime import SkillRuntime


def _generate_session_id() -> str:
    import time
    return f"scene-{int(time.time() * 1000)}"


EventHandler = Callable[[AgentEvent], Awaitable[None] | None]


class ChatAssistant:
    """High-level chat assistant combining AgentHarness, tools, and skills."""

    def __init__(
        self,
        *,
        harness: AgentHarness | None = None,
        skills: list[Skill] | None = None,
        tool_registry: ToolRegistry | None = None,
        cwd: str = "",
        agent: AgentDefinition | None = None,
    ) -> None:
        self._harness = harness
        self._agent = agent
        self._tool_registry = tool_registry or ToolRegistry()
        self._skills = skills or []
        self._cwd = cwd or os.getcwd()
        self._session_unsub: Callable[[], None] | None = None
        self._handlers: list[EventHandler] = []
        if harness is not None:
            self._skill_runtime = SkillRuntime(self._skills, harness)
            self._skill_runtime.register_tools(self._tool_registry)
        else:
            self._skill_runtime = None

    @classmethod
    async def create(
        cls,
        *,
        provider_name: str = "openai",
        model_id: str = "gpt-4o",
        api_key: str | None = None,
        api_key_env: str | None = None,
        tools: list[Tool] | None = None,
        skills_dir: str | None = None,
        session_store: SessionStore | None = None,
        session_id: str | None = None,
        system_prompt: str | None = None,
        cwd: str = "",
    ) -> "ChatAssistant":
        """Factory method to create a ChatAssistant with minimal configuration."""
        from agent_core.providers.openai_provider import OpenAIProvider
        from agent_core.providers.anthropic_provider import AnthropicProvider

        cwd = cwd or os.getcwd()

        loader = ResourceLoader(
            cwd=cwd,
            extra_skill_paths=[skills_dir] if skills_dir else None,
        )
        skills, _ = loader.load_skills()
        context_files = loader.load_context_files()

        tool_registry = ToolRegistry()
        local_tools = create_all_tools(cwd)
        for tool in local_tools.values():
            tool_registry.register(tool)
        if tools:
            for tool in tools:
                tool_registry.register(tool)

        if api_key:
            auth_source = AuthSource.static(api_key=api_key)
        elif api_key_env:
            auth_source = AuthSource.env(api_key_env)
        else:
            if provider_name == "anthropic":
                auth_source = AuthSource.env("ANTHROPIC_API_KEY")
            elif provider_name == "minimax":
                auth_source = AuthSource.env("MINIMAX_API_KEY")
            elif provider_name == "agnes":
                auth_source = AuthSource.env("AGNES_API_KEY")
            else:
                auth_source = AuthSource.env("OPENAI_API_KEY")

        if provider_name == "openai":
            provider = OpenAIProvider()
        elif provider_name == "anthropic":
            provider = AnthropicProvider()
        elif provider_name == "minimax":
            from agent_core.providers.types import Model

            provider = OpenAIProvider(
                base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"),
                provider_name="minimax",
                models=[
                    Model(
                        provider="minimax",
                        id="minimax-m2.7",
                        context_window=256_000,
                        max_output_tokens=4096,
                    ),
                ],
            )
        elif provider_name == "agnes":
            from agent_core.providers.types import Model

            provider = OpenAIProvider(
                base_url=os.environ.get("AGNES_BASE_URL", "https://api.agnes-ai.cn/v1"),
                provider_name="agnes",
                timeout=300.0,  # agnes-2.0-flash is a reasoning model — first token can take >60s
                models=[
                    Model(
                        provider="agnes",
                        id="agnes-2.0-flash",
                        context_window=256_000,
                        max_output_tokens=65536,
                    ),
                ],
            )
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

        model = next((m for m in provider.list_models() if m.id == model_id), None)
        if model is None:
            model = provider.list_models()[0]

        prompt = SystemPromptBuilder(base_prompt=system_prompt).build(
            cwd=cwd,
            active_tools=tool_registry.to_definitions(),
            skills=skills,
            context_files=context_files,
            skill_progressive=skill_progressive_enabled(),
        )

        harness = AgentHarness(
            provider=provider,
            auth_source=auth_source,
            store=session_store or InMemoryStore(),
            session_id=session_id or _generate_session_id(),
            initial_state=AgentState(
                system_prompt=prompt.text,
                model=model,
                tools=tool_registry.to_definitions(),
            ),
            tool_registry=tool_registry,
        )

        assistant = cls(
            harness=harness,
            skills=skills,
            tool_registry=tool_registry,
            cwd=cwd,
        )
        await assistant.start()
        return assistant

    @property
    def harness(self) -> AgentHarness | None:
        return self._harness

    async def start(self) -> None:
        """Start the harness and subscribe to agent events."""
        await self._harness.start()
        if self._skill_runtime is not None:
            self._skill_runtime.bind_handlers(self._handlers)
        self._session_unsub = self._harness.subscribe(self._on_agent_event)

    def on_event(self, handler: EventHandler) -> Callable[[], None]:
        """Subscribe to agent events. Returns an unsubscribe function."""
        self._handlers.append(handler)

        def _unsub() -> None:
            try:
                self._handlers.remove(handler)
            except ValueError:
                pass

        return _unsub

    async def send_message(self, text: str) -> None:
        """Send a user message to the assistant."""
        if self._skill_runtime is not None:
            expanded = await self._skill_runtime.expand_user_message(text)
        else:
            expanded = text
        await self._harness.prompt(expanded)

    async def continue_(self) -> None:
        """Continue the conversation from the current state."""
        await self._harness.continue_()

    def abort(self) -> None:
        """Abort the current operation."""
        self._harness.abort()

    @property
    def messages(self) -> list[Any]:
        """Current conversation messages."""
        return self._harness.messages

    @property
    def skills(self) -> list[Skill]:
        return list(self._skills)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tool_registry)

    async def _on_agent_event(self, evt: AgentEvent) -> None:
        from agent_core.core.events import AgentEnd, TurnEnd

        if self._skill_runtime is not None:
            if isinstance(evt, TurnEnd):
                await self._skill_runtime.handle_turn_end(self._handlers)
            if isinstance(evt, AgentEnd):
                self._skill_runtime.clear_on_agent_end()

        for handler in list(self._handlers):
            result = handler(evt)
            if asyncio.iscoroutine(result):
                await result

    async def dispose(self) -> None:
        if self._session_unsub is not None:
            self._session_unsub()
            self._session_unsub = None
        await self._harness.dispose()
