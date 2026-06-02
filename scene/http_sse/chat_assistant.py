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
from agent_core.prompts.builder import SystemPromptBuilder
from agent_core.resources.loader import ResourceLoader
from agent_core.resources.personas import Persona
from agent_core.resources.types import Skill
from agent_core.tools.base import Tool, ToolRegistry
from agent_core.tools.aigc_creation import create_nolo_video_tool
from agent_core.tools.local import create_all_tools
from agent_core.tools.music import create_text_to_music_tool
from agent_core.tools.widgets import ShowWidgetTool

from scene.http_sse.request_context import current_request_headers


def _generate_session_id() -> str:
    import time
    return f"scene-{int(time.time() * 1000)}"


async def _auth_before_tool_call(info: dict[str, Any]) -> dict[str, Any] | None:
    """Inject AIGC auth headers into ToolContext.metadata."""
    tool_call = info.get("tool_call")
    if tool_call is None:
        return None
    name = getattr(tool_call, "name", "")
    if not name.startswith("create_"):
        return None

    headers = current_request_headers.get({})
    return {
        "inject_metadata": {
            "aigc_auth": {
                "uid": headers.get("uid"),
                "deviceid": headers.get("deviceid"),
                "channel": headers.get("channel"),
                "pacmtoken": headers.get("pacmtoken"),
            }
        }
    }

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
        persona: Persona | None = None,
        mcp_manager: Any | None = None,
        cwd: str = "",
    ) -> "ChatAssistant":
        """Factory method to create a ChatAssistant with minimal configuration."""
        from agent_core.providers.openai_provider import OpenAIProvider
        from agent_core.providers.anthropic_provider import AnthropicProvider

        cwd = cwd or os.getcwd()

        # Load skills and context files
        loader = ResourceLoader(
            cwd=cwd,
            extra_skill_paths=[skills_dir] if skills_dir else None,
        )
        skills, _ = loader.load_skills()
        context_files = loader.load_context_files()

        # Build tool registry
        tool_registry = ToolRegistry()
        local_tools = create_all_tools(cwd)
        for tool in local_tools.values():
            tool_registry.register(tool)
        tool_registry.register(create_text_to_music_tool())
        tool_registry.register(create_nolo_video_tool())
        # Register local knowledge base via existing RetrieverTool
        # Only if no persona filtering, or persona explicitly enables "local" knowledge base
        _kb_allowed = True
        if persona is not None and persona.knowledge_bases is not None:
            _kb_allowed = "local" in persona.knowledge_bases
        elif persona is not None and persona.enabled_tools is not None:
            _kb_allowed = False  # persona has tool filtering but didn't opt into local KB

        if _kb_allowed:
            from agent_core.knowledge.local_kb import LocalKnowledgeBase
            from agent_core.retrieval.tool import RetrieverTool
            from agent_core.tools.base import ToolContext, ToolResult

            kb_dir = os.path.join(cwd, ".pi", "knowledge")
            kb_retriever = LocalKnowledgeBase(kb_dir)
            _kb_rt = RetrieverTool(
                retriever=kb_retriever,
                name="search_knowledge",
                description="搜索本地知识库中的文档。传入自然语言查询，返回语义相关的文档片段及其来源。",
            )

            class _KBAdapter:
                definition = _kb_rt.definition
                async def execute(self, params: dict, context: ToolContext | None = None) -> ToolResult:
                    return await _kb_rt.execute("", params, context)

            tool_registry.register(_KBAdapter())
        tool_registry.register(ShowWidgetTool())

        # Register Feishu CLI tool — agent can use lark-cli for Feishu operations
        try:
            from agent_core.tools.feishu_cli_tool import feishu_cli_tool
            tool_registry.register(feishu_cli_tool)
        except ImportError:
            pass

        # Register Agnes Image tool — text-to-image and image editing
        try:
            from agent_core.tools.agnes_image_tool import agnes_image_tool
            tool_registry.register(agnes_image_tool)
        except ImportError:
            pass

        # Register Agnes Video tool — text-to-video, image-to-video, keyframes
        try:
            from agent_core.tools.agnes_video_tool import agnes_video_tool
            tool_registry.register(agnes_video_tool)
        except ImportError:
            pass

        if tools:
            for tool in tools:
                tool_registry.register(tool)

        # Register MCP tools (pre-loaded at server startup by manager)
        if mcp_manager is not None:
            mcp_manager.register_tools(tool_registry)

        # Apply persona tool filtering
        if persona is not None:
            allowed: set[str] | None = None
            if persona.enabled_tools is not None:
                allowed = set(persona.enabled_tools)
            # Auto-include knowledge base tools
            if persona.knowledge_bases:
                kb_names = set(persona.knowledge_bases)
                # Local KB
                if "local" in kb_names and allowed is not None:
                    allowed.add("search_knowledge")
                # MCP KB connectors
                if mcp_manager is not None:
                    for adapter in mcp_manager.adapters:
                        if adapter.server_name in kb_names and allowed is not None:
                            allowed.add(adapter.definition.name)
            if allowed is not None:
                filtered = ToolRegistry()
                for name, tool in tool_registry:
                    if name in allowed:
                        filtered.register(tool)
                tool_registry = filtered

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
            elif provider_name == "agnes":
                auth_source = AuthSource.env("AGNES_API_KEY")
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
        elif provider_name == "agnes":
            from agent_core.providers.types import Model

            provider = OpenAIProvider(
                base_url="https://apihub.agnes-ai.com/v1",
                provider_name="agnes",
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

        # Build system prompt — persona overrides base_prompt
        effective_prompt = persona.system_prompt if persona is not None else system_prompt
        prompt = SystemPromptBuilder(base_prompt=effective_prompt).build(
            cwd=cwd,
            active_tools=tool_registry.to_definitions(),
            skills=skills,
            context_files=context_files,
        )

        # Auto-retrieval: inject knowledge base context before each LLM call
        from agent_core.knowledge.local_kb import LocalKnowledgeBase
        from agent_core.retrieval.extension import AutoRetrievalExtension

        kb_dir = os.path.join(cwd, ".pi", "knowledge")
        _kb_retriever = LocalKnowledgeBase(kb_dir)
        _auto_retrieval = AutoRetrievalExtension(retriever=_kb_retriever, top_k=3)

        async def _transform_context(llm_messages, signal=None):
            return await _auto_retrieval.transform_context(llm_messages, signal)

        agent = Agent(
            initial_state=AgentState(
                system_prompt=prompt.text,
                model=model,
                tools=tool_registry.to_definitions(),
            ),
            provider=provider,
            auth_source=auth_source,
            tool_registry=tool_registry,
            tool_execution="sequential",
            before_tool_call=_auth_before_tool_call,
            transform_context=_transform_context,
            max_turns=10,
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

    @property
    def tool_infos(self) -> list[dict[str, str]]:
        """Return tool name + description for each registered tool."""
        result: list[dict[str, str]] = []
        for name, tool in self._tool_registry._tools.items():
            result.append({
                "name": name,
                "description": tool.definition.description,
            })
        result.sort(key=lambda t: t["name"])
        return result

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
            with open(skill.source.origin, "r", encoding="utf-8") as f:
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
            f'<skill name="{skill.name}" location="{skill.source.origin}">\n'
            f"References are relative to {skill.source.base_dir}.\n\n"
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
