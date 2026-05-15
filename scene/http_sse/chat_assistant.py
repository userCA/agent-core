"""Generic chat assistant built on agent_core with tool and skill support."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable

from agent_core.core.agent import Agent
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
from agent_core.providers.registry import ModelRegistry
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.jsonl_store import JsonlStore
from agent_core.session.session import AgentSession
from agent_core.session.store import SessionStore
from agent_core.skills import Skill, load_skills
from agent_core.tools.base import Tool, ToolRegistry
from agent_core.tools.local import create_all_tools


def _generate_session_id() -> str:
    import time
    return f"scene-{int(time.time() * 1000)}"

from scene.http_sse.system_prompt import build_system_prompt

EventHandler = Callable[[AgentEvent], Awaitable[None] | None]


class ChatAssistant:
    """High-level chat assistant combining Agent, Session, tools, and skills."""

    def __init__(
        self,
        *,
        agent: Agent,
        session_store: SessionStore | None = None,
        session_id: str | None = None,
        skills: list[Skill] | None = None,
        tool_registry: ToolRegistry | None = None,
        cwd: str = "",
    ) -> None:
        self._agent = agent
        self._tool_registry = tool_registry or ToolRegistry()
        self._skills = skills or []
        self._cwd = cwd or os.getcwd()
        self._session_store = session_store or InMemoryStore()
        self._session_id = session_id or _generate_session_id()
        self._session: AgentSession | None = None
        self._session_unsub: Callable[[], None] | None = None
        self._handlers: list[EventHandler] = []

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

        # Load skills
        skills_result = load_skills(cwd=cwd, include_defaults=True)
        skills = skills_result.skills
        if skills_dir:
            extra = load_skills(cwd=cwd, include_defaults=False, skill_paths=[skills_dir])
            skills.extend(extra.skills)

        # Build tool registry
        tool_registry = ToolRegistry()
        local_tools = create_all_tools(cwd)
        for tool in local_tools.values():
            tool_registry.register(tool)
        if tools:
            for tool in tools:
                tool_registry.register(tool)

        # Resolve auth
        if api_key:
            auth_source = AuthSource.static(api_key=api_key)
        elif api_key_env:
            auth_source = AuthSource.env(api_key_env)
        else:
            if provider_name == "anthropic":
                auth_source = AuthSource.env("ANTHROPIC_API_KEY")
            elif provider_name == "minimax":
                auth_source = AuthSource.env("MINIMAX_API_KEY")
            else:
                auth_source = AuthSource.env("OPENAI_API_KEY")

        # Resolve provider and model
        if provider_name == "openai":
            provider = OpenAIProvider()
        elif provider_name == "anthropic":
            provider = AnthropicProvider()
        elif provider_name == "minimax":
            from agent_core.providers.types import Model

            provider = OpenAIProvider(
                base_url="https://api.minimax.chat/v1",
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
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

        model = next((m for m in provider.list_models() if m.id == model_id), None)
        if model is None:
            model = provider.list_models()[0]

        # Build system prompt
        prompt = build_system_prompt(
            cwd=cwd,
            skills=skills,
            custom_prompt=system_prompt,
            tool_names=list(tool_registry),
        )

        agent = Agent(
            initial_state=AgentState(
                system_prompt=prompt,
                model=model,
                tools=tool_registry.to_definitions(),
            ),
            provider=provider,
            auth_source=auth_source,
            tool_registry=tool_registry,
            tool_execution="sequential",
        )

        assistant = cls(
            agent=agent,
            session_store=session_store,
            session_id=session_id,
            skills=skills,
            tool_registry=tool_registry,
            cwd=cwd,
        )
        await assistant.start()
        return assistant

    async def start(self) -> None:
        """Start the session and subscribe to agent events."""
        self._session = AgentSession(
            agent=self._agent,
            store=self._session_store,
            session_id=self._session_id,
        )
        await self._session.start()
        # Wire ChatAssistant handlers into the session event stream
        self._session_unsub = self._session.subscribe(self._on_agent_event)

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
        """Send a user message to the assistant.

        Supports /skill:name commands which inject skill content into the prompt.
        """
        expanded = self._expand_skill_command(text)
        if self._session is not None:
            await self._session.prompt(expanded)
        else:
            await self._agent.prompt(expanded)

    async def continue_(self) -> None:
        """Continue the conversation from the current state."""
        if self._session is not None:
            await self._session.continue_()
        else:
            await self._agent.continue_()

    def abort(self) -> None:
        """Abort the current operation."""
        self._agent.abort()

    def provide_human_input(self, tool_call_id: str, values: dict[str, Any]) -> bool:
        """Resume a tool that is waiting for human input."""
        return self._agent.provide_human_input(tool_call_id, values)

    @property
    def messages(self) -> list[Any]:
        """Current conversation messages."""
        if self._session is not None:
            return self._session.messages
        return list(self._agent.state.messages)

    @property
    def skills(self) -> list[Skill]:
        return list(self._skills)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tool_registry)

    def _expand_skill_command(self, text: str) -> str:
        """Expand /skill:name commands to inject skill content.

        Returns the expanded text, or the original if not a skill command.
        """
        if not text.startswith("/skill:"):
            return text

        space_idx = text.find(" ")
        skill_name = text[7:space_idx] if space_idx != -1 else text[7:]
        args = text[space_idx + 1:].strip() if space_idx != -1 else ""

        skill = next((s for s in self._skills if s.name == skill_name), None)
        if skill is None:
            return text

        try:
            with open(skill.file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return text

        # Strip frontmatter from skill content
        body = content
        if body.startswith("---"):
            parts = body.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].strip()

        skill_block = (
            f'<skill name="{skill.name}" location="{skill.file_path}">\n'
            f"References are relative to {skill.base_dir}.\n\n"
            f"{body}\n"
            f"</skill>"
        )
        return f"{skill_block}\n\n{args}" if args else skill_block

    async def _on_agent_event(self, evt: AgentEvent) -> None:
        for handler in list(self._handlers):
            result = handler(evt)
            if asyncio.iscoroutine(result):
                await result

    async def dispose(self) -> None:
        if self._session_unsub is not None:
            self._session_unsub()
            self._session_unsub = None
        if self._session is not None:
            await self._session.dispose()
