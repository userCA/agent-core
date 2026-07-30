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
    """Inject scene metadata into ToolContext for selected tools."""
    tool_call = info.get("tool_call")
    if tool_call is None:
        return None
    name = getattr(tool_call, "name", "")
    inject: dict[str, Any] = {}

    if name.startswith("create_"):
        headers = current_request_headers.get({})
        inject["aigc_auth"] = {
            "uid": headers.get("uid"),
            "deviceid": headers.get("deviceid"),
            "channel": headers.get("channel"),
            "pacmtoken": headers.get("pacmtoken"),
        }

    if name in ("create_short_drama", "concat_videos"):
        inject["cwd"] = os.getcwd()
        inject["public_base_url"] = os.environ.get(
            "PUBLIC_BASE_URL", "http://127.0.0.1:8001"
        ).rstrip("/")

    if not inject:
        return None
    return {"inject_metadata": inject}

EventHandler = Callable[[AgentEvent], Awaitable[None] | None]


class ChatAssistant:
    """High-level chat assistant combining AgentHarness, tools, and skills."""

    def __init__(
        self,
        *,
        harness: AgentHarness,
        skills: list[Skill] | None = None,
        tool_registry: ToolRegistry | None = None,
        cwd: str = "",
        multi_agent_handle: Any | None = None,
        skill_trace_collector: Any | None = None,
        artifact_store: Any | None = None,
        state_store: Any | None = None,
    ) -> None:
        self._harness = harness
        self._tool_registry = tool_registry or ToolRegistry()
        self._skills = skills or []
        self._cwd = cwd or os.getcwd()
        self._session_unsub: Callable[[], None] | None = None
        self._handlers: list[EventHandler] = []
        self._multi_agent_handle = multi_agent_handle
        self._skill_trace_collector = skill_trace_collector
        self._artifact_store = artifact_store
        self._state_store = state_store

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
        memory_backend: str = "",
        memory_config: dict[str, Any] | None = None,
        companion_queue: "asyncio.Queue[Any] | None" = None,
        companion_uid: str = "",
        owner: str = "",
        enable_multi_agent: bool | None = None,
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
            from agent_core.tools.agnes_video_tool import agnes_video_tool, check_video_tool
            tool_registry.register(agnes_video_tool)
            tool_registry.register(check_video_tool)
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
                for name, tool in tool_registry._tools.items():
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

        resolved_session_id = session_id or _generate_session_id()
        from scene.http_sse.memory_config import (
            build_memory_extensions,
            resolve_memory_backend,
        )
        from scene.http_sse.evolution_config import (
            build_skill_case_recall_extension,
            build_skill_trace_collector,
        )
        from scene.http_sse.artifacts_config import (
            build_artifact_extension,
            install_scene_databus,
        )
        from scene.http_sse.state_kv_config import build_state_kv_extension

        extensions = build_memory_extensions(
            resolve_memory_backend(memory_backend),
            memory_config or {},
            resolved_session_id,
        )
        skill_trace_collector = build_skill_trace_collector()
        if skill_trace_collector is not None:
            extensions.append(skill_trace_collector)
        case_recall = build_skill_case_recall_extension(
            skill_dir=skills_dir or os.path.join(cwd, ".pi", "skills"),
            skill_names=[s.name for s in skills],
        )
        if case_recall is not None:
            extensions.append(case_recall)
        artifact_store, artifact_ext = build_artifact_extension()
        if artifact_ext is not None:
            extensions.append(artifact_ext)
        extensions = install_scene_databus(
            tool_registry,
            store=artifact_store,
            session_id=resolved_session_id,
            extensions=extensions,
        )
        state_store, state_ext = build_state_kv_extension()
        if state_ext is not None:
            extensions.append(state_ext)

        # Companion extension — optional, wired when a companion queue is provided
        if companion_queue is not None and companion_uid:
            from agent_core.extensions.companion import CompanionExtension
            extensions.append(CompanionExtension(
                uid=companion_uid,
                send_event=companion_queue.put_nowait,
            ))

        store = session_store or InMemoryStore()
        # Ensure session header carries owner before harness.start().
        if owner:
            from datetime import datetime, timezone

            from agent_core.session.store import SessionHeader

            try:
                await store.load_session(resolved_session_id)
            except KeyError:
                await store.create_session(
                    resolved_session_id,
                    SessionHeader(
                        id=resolved_session_id,
                        timestamp=datetime.now(tz=timezone.utc).isoformat(),
                        cwd=cwd,
                        owner=owner,
                    ),
                )

        from scene.http_sse.multi_agent_profiles import (
            default_multi_agent_options,
            multi_agent_enabled,
        )
        from scene.http_sse.planning_config import planning_enabled
        from scene.http_sse.compaction_config import compaction_enabled

        system_prompt_text = prompt.text
        if planning_enabled():
            from agent_core.planning import install_planning, planning_prompt_snippet
            from agent_core.tools.short_drama_pipeline import create_short_drama_tool
            from agent_core.tools.video_concat_tool import concat_videos_tool

            plan_store, _, extensions = await install_planning(
                tool_registry,
                store=store,
                session_id=resolved_session_id,
                owner=owner,
                extensions=extensions,
            )
            if tool_registry.get("concat_videos") is None:
                tool_registry.register(concat_videos_tool)
            if tool_registry.get("create_short_drama") is None:
                tool_registry.register(create_short_drama_tool(plan_store=plan_store))
            system_prompt_text = system_prompt_text.rstrip() + "\n\n" + planning_prompt_snippet()
        else:
            from agent_core.tools.short_drama_pipeline import create_short_drama_tool
            from agent_core.tools.video_concat_tool import concat_videos_tool

            if tool_registry.get("concat_videos") is None:
                tool_registry.register(concat_videos_tool)
            if tool_registry.get("create_short_drama") is None:
                tool_registry.register(create_short_drama_tool(plan_store=None))

        from scene.http_sse.working_memory_config import install_scene_working_memory

        _, extensions = install_scene_working_memory(
            tool_registry, extensions=extensions
        )

        use_multi = (
            multi_agent_enabled() if enable_multi_agent is None else enable_multi_agent
        )
        multi_handle = None
        harness_kwargs: dict[str, Any] = {
            "extensions": extensions or None,
            "tool_execution": "sequential",
            "before_tool_call": _auth_before_tool_call,
            "transform_context": _transform_context,
            "max_turns": 10,
        }
        if compaction_enabled():
            from agent_core.compaction import create_default_compactor

            harness_kwargs["compactor"] = create_default_compactor()

        if use_multi:
            from agent_core.multi_agent import create_multi_agent_harness

            tool_list = [
                t for info in tool_registry.list() if (t := tool_registry.get(info.name))
            ]
            options = default_multi_agent_options()
            if persona is not None and persona.name:
                options.routing_prompt = (
                    (options.routing_prompt or "")
                    + f"\n当前接待风格参考 persona: {persona.name}."
                )
            harness, multi_handle = create_multi_agent_harness(
                options=options,
                provider=provider,
                auth_source=auth_source,
                store=store,
                session_id=resolved_session_id,
                model=model,
                tools=tool_list,
                system_prompt=system_prompt_text,
                owner=owner,
                tool_registry=tool_registry,
                **harness_kwargs,
            )
        else:
            harness = AgentHarness(
                provider=provider,
                auth_source=auth_source,
                store=store,
                session_id=resolved_session_id,
                initial_state=AgentState(
                    system_prompt=system_prompt_text,
                    model=model,
                    tools=tool_registry.to_definitions(),
                ),
                tool_registry=tool_registry,
                **harness_kwargs,
            )

        assistant = cls(
            harness=harness,
            skills=skills,
            tool_registry=tool_registry,
            cwd=cwd,
            multi_agent_handle=multi_handle,
            skill_trace_collector=skill_trace_collector,
            artifact_store=artifact_store,
            state_store=state_store,
        )
        await assistant.start()

        # Debug replay recorder — optional, enabled via ENABLE_RUN_REPLAY=1
        from scene.http_sse.replay import replay_enabled, RunReplayRecorder
        if replay_enabled():
            recorder = RunReplayRecorder(session_id=resolved_session_id)
            assistant.on_event(recorder.handle_event)

        return assistant

    @property
    def harness(self) -> AgentHarness:
        return self._harness

    @property
    def skill_trace_collector(self) -> Any | None:
        return self._skill_trace_collector

    @property
    def artifact_store(self) -> Any | None:
        return self._artifact_store

    @property
    def state_store(self) -> Any | None:
        return self._state_store

    async def start(self) -> None:
        """Start the harness and subscribe to agent events."""
        await self._harness.start()
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
        """Send a user message to the assistant.

        Supports /skill:name commands which inject skill content into the prompt.
        """
        expanded = self._expand_skill_command(text)
        await self._harness.prompt(expanded)

    async def continue_(self) -> None:
        """Continue the conversation from the current state."""
        await self._harness.continue_()

    def abort(self) -> None:
        """Abort the current operation (and any running sub-agents)."""
        self._harness.abort()
        handle = self._multi_agent_handle
        if handle is not None:
            runner = getattr(handle, "runner", None)
            if runner is not None:
                # Fire-and-forget abort of active sub-agents.
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(runner.abort_all())
                except RuntimeError:
                    pass

    def provide_human_input(self, tool_call_id: str, values: dict[str, Any]) -> bool:
        """Resume a tool that is waiting for human input."""
        return self._harness.provide_human_input(tool_call_id, values)

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
        await self._harness.dispose()
