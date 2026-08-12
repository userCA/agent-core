"""Generic chat assistant built on agent_core with tool and skill support."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

from agent_core.core.content import ImageContent
from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    MessageUpdate,
    TextDelta,
    ToolCallDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
)
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.store import CustomEntry, SessionStore
from agent_core.prompts.builder import SystemPromptBuilder
from agent_core.resources.loader import ResourceLoader
from agent_core.resources.personas import Persona
from agent_core.resources.types import Skill
from agent_core.resources.skill_activation import skill_progressive_enabled
from agent_core.tools.base import Tool, ToolRegistry
from agent_core.tools.aigc_creation import create_nolo_video_tool
from agent_core.tools.local import create_all_tools
from agent_core.tools.music import create_text_to_music_tool
from agent_core.tools.widgets import ShowWidgetTool

from scene.h5.request_context import current_request_headers
from scene.skill_runtime import SkillRuntime


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
        workflow_handle: Any | None = None,
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
        self._workflow_handle = workflow_handle
        self._skill_trace_collector = skill_trace_collector
        self._artifact_store = artifact_store
        self._state_store = state_store
        self._skill_runtime = SkillRuntime(self._skills, harness)
        self._skill_runtime.register_tools(self._tool_registry)

        # Legacy mapping for frontend display / history restoration (not primary attribution)
        self._tool_to_skill: dict[str, Skill] = {}
        for skill in self._skills:
            for tool_name in skill.tools:
                self._tool_to_skill[tool_name] = skill
        self._skill_mapping_persisted = False

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
                async def execute(self, params: dict, **kwargs: Any) -> ToolResult:
                    return await _kb_rt.execute("", params, kwargs.get("ctx"))

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
            elif provider_name == "deepseek":
                auth_source = AuthSource.env("DEEPSEEK_API_KEY")
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
        elif provider_name == "deepseek":
            from agent_core.providers.types import Model

            provider = OpenAIProvider(
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                provider_name="deepseek",
                models=[
                    Model(
                        provider="deepseek",
                        id="deepseek-v4-flash",
                        context_window=128_000,
                        max_output_tokens=8192,
                        supports_vision=False,
                    ),
                    Model(
                        provider="deepseek",
                        id="deepseek-chat",
                        context_window=64_000,
                        max_output_tokens=8192,
                        supports_vision=False,
                    ),
                    Model(
                        provider="deepseek",
                        id="deepseek-reasoner",
                        context_window=64_000,
                        max_output_tokens=8192,
                        supports_vision=False,
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
            skill_progressive=skill_progressive_enabled(),
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
        from scene.h5.memory_config import (
            build_memory_extensions,
            resolve_memory_backend,
        )
        from scene.h5.evolution_config import (
            build_skill_case_recall_extension,
            build_skill_trace_collector,
        )
        from scene.h5.artifacts_config import (
            build_artifact_extension,
            install_scene_databus,
        )
        from scene.h5.state_kv_config import build_state_kv_extension

        extensions = build_memory_extensions(
            resolve_memory_backend(memory_backend),
            memory_config or {},
            resolved_session_id,
        )
        skill_trace_collector = build_skill_trace_collector(skills=skills)
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
        resolved_owner = owner or companion_uid or ""
        if resolved_owner:
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
                        owner=resolved_owner,
                    ),
                )

        from scene.h5.multi_agent_profiles import (
            default_multi_agent_options,
            multi_agent_enabled,
        )
        from scene.h5.planning_config import planning_enabled
        from scene.h5.compaction_config import compaction_enabled
        from scene.h5.workflows_config import workflows_enabled

        system_prompt_text = prompt.text
        if planning_enabled():
            from agent_core.planning import install_planning, planning_prompt_snippet
            from agent_core.tools.short_drama_pipeline import create_short_drama_tool
            from agent_core.tools.video_concat_tool import concat_videos_tool

            plan_store, _, extensions = await install_planning(
                tool_registry,
                store=store,
                session_id=resolved_session_id,
                owner=resolved_owner,
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

        from scene.h5.working_memory_config import install_scene_working_memory

        _, extensions = install_scene_working_memory(
            tool_registry, extensions=extensions
        )

        use_multi = (
            multi_agent_enabled() if enable_multi_agent is None else enable_multi_agent
        )
        if use_multi and workflows_enabled():
            from agent_core.workflows import workflow_prompt_snippet

            system_prompt_text = system_prompt_text.rstrip() + "\n\n" + workflow_prompt_snippet()
        multi_handle = None
        workflow_handle = None
        harness_kwargs: dict[str, Any] = {
            "extensions": extensions or None,
            "tool_execution": "sequential",
            "before_tool_call": _auth_before_tool_call,
            "transform_context": _transform_context,
            "max_turns": 20,
        }

        # Phase 1/2 tool & skill routing — controlled via env vars
        _catalog_threshold = os.environ.get("TOOL_CATALOG_THRESHOLD")
        if _catalog_threshold:
            harness_kwargs["tool_catalog_threshold"] = int(_catalog_threshold)
        if os.environ.get("DISABLE_TOOL_ROUTING", "0").strip().lower() in ("1", "true", "yes"):
            harness_kwargs["disable_tool_routing"] = True
        if os.environ.get("ENABLE_SKILL_ROUTING", "0").strip().lower() in ("1", "true", "yes"):
            harness_kwargs["skill_routing"] = True
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
                owner=resolved_owner,
                tool_registry=tool_registry,
                **harness_kwargs,
            )
            if workflows_enabled():
                from agent_core.workflows import WorkflowOptions, install_workflows, workflow_prompt_snippet

                workflow_handle = install_workflows(
                    tool_registry=tool_registry,
                    sub_agent_runner=multi_handle.runner,
                    profile_registry=multi_handle.registry,
                    parent_harness=harness,
                    session_store=store,
                    session_id=resolved_session_id,
                    owner=resolved_owner,
                    options=WorkflowOptions(
                        search_paths=[os.path.join(cwd, ".pi", "workflows")],
                    ),
                )
                harness.state.system_prompt = (
                    harness.state.system_prompt.rstrip()
                    + "\n\n"
                    + workflow_prompt_snippet(workflows=workflow_handle.list_workflows())
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
            workflow_handle=workflow_handle,
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
        self._skill_runtime.bind_handlers(self._handlers)
        self._session_unsub = self._harness.subscribe(self._on_agent_event)

        # Persist tool_to_skill mapping for history restoration (once per session)
        if self._tool_to_skill and not self._skill_mapping_persisted:
            mapping = {tool: skill.name for tool, skill in self._tool_to_skill.items()}
            # Also include descriptions for frontend display
            descriptions = {skill.name: skill.description for skill in self._tool_to_skill.values()}
            entry = CustomEntry(
                custom_type="skill_mapping",
                data={"tool_to_skill": mapping, "descriptions": descriptions},
                id=f"skill-map-{int(time.time() * 1000)}",
            )
            try:
                await self._harness._persistence.append_entry(entry)
                self._skill_mapping_persisted = True
            except Exception as exc:
                logger.warning(
                    "Failed to persist skill_mapping for %s: %s",
                    self._harness.session_id,
                    exc,
                )

    def on_event(self, handler: EventHandler) -> Callable[[], None]:
        """Subscribe to agent events. Returns an unsubscribe function."""
        self._handlers.append(handler)

        def _unsub() -> None:
            try:
                self._handlers.remove(handler)
            except ValueError:
                pass

        return _unsub

    async def send_message(
        self,
        text: str,
        images: list[ImageContent] | None = None,
    ) -> None:
        """Send a user message to the assistant.

        Supports /skill:name commands which inject skill content into the prompt.
        When *images* is provided, they are attached as multimodal content blocks.
        """
        expanded = await self._skill_runtime.expand_user_message(text)
        await self._harness.prompt(expanded, images=images)

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
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(runner.abort_all())
                except RuntimeError:
                    pass
        wf_handle = self._workflow_handle
        if wf_handle is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(wf_handle.abort())
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

    async def _on_agent_event(self, evt: AgentEvent) -> None:
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
