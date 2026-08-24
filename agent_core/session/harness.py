"""AgentHarness — production orchestration API directly calling run_agent_loop."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from agent_core.compaction.compactor import Compactor
from agent_core.core.content import ImageContent, TextContent
from agent_core.core.context import AgentContext
from agent_core.core.errors import AgentHarnessError, normalize_harness_error, normalize_hook_error
from agent_core.core.events import (
    AbortEvent,
    AgentEnd,
    AgentEvent,
    MessageEnd,
    MessageStart,
    TurnEnd,
)
from agent_core.core.hooks import (
    AgentHooks,
    SessionBeforeCompactHookEvent,
    ToolCallHookEvent,
    ToolResultHookEvent,
)
from agent_core.core.human_input import HumanInputGate
from agent_core.core.loop import run_agent_loop
from agent_core.core.messages import AssistantMessage, ToolResultMessage, Usage, UserMessage
from agent_core.core.queue import PendingMessageQueue, QueueMode
from agent_core.core.state import AgentHarnessPhase, AgentState
from agent_core.extensions.base import ExtensionContext, ExtensionRunner, HarnessFacade
from agent_core.providers.auth import AuthSource
from agent_core.providers.base import ModelProvider
from agent_core.providers.message_converter import create_default_converter
from agent_core.providers.types import Model
from agent_core.session.persistence import HarnessPersistence
from agent_core.session.harness_config import HarnessConfigMixin
from agent_core.session.harness_events import HarnessEventsMixin
from agent_core.session.harness_queues import HarnessQueuesMixin
from agent_core.session.store import SessionHeader, SessionStore
from agent_core.session.turn_runtime import (
    build_loop_config,
    chain_before_agent_start_hooks,
    create_turn_snapshot,
    register_legacy_context,
    register_legacy_tool_call,
    register_legacy_tool_result,
)

logger = logging.getLogger(__name__)

Listener = Callable[[AgentEvent], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


class AgentHarness(HarnessEventsMixin, HarnessConfigMixin, HarnessQueuesMixin):
    """Unified production runtime: state, queues, persistence, hooks, loop execution."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        auth_source: AuthSource,
        store: SessionStore,
        session_id: str,
        initial_state: AgentState | None = None,
        convert_to_llm: Any | None = None,
        transform_context: Any | None = None,
        tool_registry: Any | None = None,
        before_tool_call: Any | None = None,
        after_tool_call: Any | None = None,
        tool_execution: str = "parallel",
        tool_timeout: float | None = 120.0,
        max_turns: int | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 60.0,
        compactor: Compactor | None = None,
        extensions: list[Any] | None = None,
        tool_result_max_chars: int = 4000,
        steering_mode: QueueMode = "one-at-a-time",
        followup_mode: QueueMode = "one-at-a-time",
        tool_catalog_threshold: int | None = None,
        disable_tool_routing: bool = False,
        skill_routing: bool = False,
    ) -> None:
        self.state: AgentState = initial_state or AgentState()
        self._provider = provider
        self._auth_source = auth_source
        self._store = store
        self._session_id = session_id
        self._persistence = HarnessPersistence(store, session_id)
        self._compactor = compactor
        self._extensions = extensions or []
        self._tool_registry = tool_registry
        self._tool_execution = tool_execution
        self._tool_timeout = tool_timeout
        self._max_turns = max_turns
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay
        self._tool_result_max_chars = tool_result_max_chars
        self._tool_catalog_threshold = tool_catalog_threshold
        self._disable_tool_routing = disable_tool_routing
        self._skill_routing = skill_routing
        if convert_to_llm is not None:
            self._convert_to_llm = convert_to_llm
        elif hasattr(provider, "create_message_converter"):
            self._convert_to_llm = provider.create_message_converter(tool_result_max_chars)
        else:
            self._convert_to_llm = create_default_converter(tool_result_max_chars)

        self.hooks = AgentHooks()
        if before_tool_call is not None:
            register_legacy_tool_call(self.hooks, before_tool_call)
        if after_tool_call is not None:
            register_legacy_tool_result(self.hooks, after_tool_call)
        if transform_context is not None:
            register_legacy_context(self.hooks, transform_context)

        self._steering = PendingMessageQueue(steering_mode)
        self._follow_up = PendingMessageQueue(followup_mode)
        self._next_turn = PendingMessageQueue("all")
        self._pending_writes: list[PendingSessionWrite] = []
        self._listeners: list[Listener] = []
        self._human_input_gate = HumanInputGate()
        self._active_run: asyncio.Task | None = None
        self._abort_event: asyncio.Event | None = None
        self._pending_tool_calls: set[str] = set()
        self._skill_activations: list[tuple[str, str]] = []
        self._phase = AgentHarnessPhase.IDLE
        self._active_tool_names: list[str] | None = None
        self._stream_options: dict[str, Any] = {}
        self._resources: dict[str, Any] = {"skills": [], "prompt_templates": []}
        self._started = False
        self._closed = False
        self._ext_runner: ExtensionRunner | None = None
        self._overflow_compact_callback: Any | None = None
        self._observability_user_id: str = ""

    # ── HarnessFacade / TurnRuntimeHost ─────────────────────────────

    @property
    def observability_user_id(self) -> str:
        return self._observability_user_id

    @observability_user_id.setter
    def observability_user_id(self, value: str) -> None:
        self._observability_user_id = value or ""

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def active_tool_names(self) -> list[str] | None:
        return self._active_tool_names

    @property
    def stream_options(self) -> dict[str, Any]:
        return self._stream_options

    @property
    def resources(self) -> dict[str, Any]:
        return self._resources

    @property
    def phase(self) -> AgentHarnessPhase:
        return self._phase

    @phase.setter
    def phase(self, value: AgentHarnessPhase) -> None:
        self._phase = value
        self.state.phase = value

    @property
    def signal(self) -> asyncio.Event | None:
        return self._abort_event

    @property
    def pending_tool_calls(self) -> set[str]:
        return self._pending_tool_calls

    @property
    def skill_activations(self) -> list[tuple[str, str]]:
        return list(self._skill_activations)

    def record_skill_activation(self, name: str, source: str) -> None:
        self._skill_activations.append((name, source))

    def clear_skill_activations(self) -> None:
        self._skill_activations.clear()

    @property
    def messages(self) -> list[Any]:
        return list(self.state.messages)

    # ── lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started or self._closed:
            return
        header = SessionHeader(
            id=self._session_id,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            cwd=os.getcwd(),
        )
        try:
            snapshot = await self._persistence.load_session()
            self._restore_from_snapshot(snapshot)
        except KeyError:
            await self._persistence.create_session(header)
        except Exception as exc:
            logger.warning("Failed to load session %s: %s", self._session_id, exc)

        if self._extensions:
            ext_ctx = ExtensionContext(
                session_id=self._session_id,
                harness=self,
                store=self._store,
            )
            self._ext_runner = ExtensionRunner(self._extensions, ext_ctx)

            async def _tool_call_adapter(event: ToolCallHookEvent) -> Any:
                return await self._ext_runner.before_tool_call(event.call_ctx)

            async def _tool_result_adapter(event: ToolResultHookEvent) -> Any:
                return await self._ext_runner.after_tool_call(event.call_ctx)

            self.hooks.on("tool_call", _tool_call_adapter)
            self.hooks.on("tool_result", _tool_result_adapter)

            async def _before_agent_start_adapter(event: Any) -> Any:
                from agent_core.core.hooks import BeforeAgentStartHookEvent
                if not isinstance(event, BeforeAgentStartHookEvent):
                    return None
                return await self._ext_runner.on_before_agent_start(
                    event.prompt, event.system_prompt,
                )

            self.hooks.on("before_agent_start", _before_agent_start_adapter)

            for ext in self._extensions:
                transform = getattr(ext, "transform_context", None)
                if callable(transform):
                    self._register_context_transform(transform)

        if self._compactor is not None:
            self._overflow_compact_callback = self._make_overflow_compact_callback()

        self._started = True

    async def dispose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._persistence.close()

    def _check_ready(self) -> None:
        if self._closed:
            raise AgentHarnessError("invalid_state", "AgentHarness is disposed")
        if not self._started:
            raise AgentHarnessError("invalid_state", "AgentHarness not started; call start() first")

    def _restore_from_snapshot(self, snapshot: Any) -> None:
        def apply_message(restored: list[Any]) -> None:
            self.state.messages = restored

        def apply_model(entry: Any) -> None:
            prev = self.state.model
            self.state.model = Model(
                provider=entry.provider,
                id=entry.model_id,
                context_window=getattr(prev, "context_window", 4096) if prev else 4096,
                max_output_tokens=getattr(prev, "max_output_tokens", 1024) if prev else 1024,
                supports_reasoning=getattr(prev, "supports_reasoning", False) if prev else False,
                supports_xhigh_thinking=getattr(prev, "supports_xhigh_thinking", False) if prev else False,
            )

        def apply_thinking(entry: Any) -> None:
            self.state.thinking_level = entry.level  # type: ignore[assignment]

        def apply_active_tools(entry: Any) -> None:
            self._active_tool_names = list(entry.active_tool_names)

        self._persistence.replay_entries(
            snapshot,
            apply_message=apply_message,
            apply_model_change=apply_model,
            apply_thinking_level=apply_thinking,
            apply_active_tools=apply_active_tools,
        )

    # ── listeners ───────────────────────────────────────────────────

    def subscribe(self, listener: Listener) -> Unsubscribe:
        self._listeners.append(listener)

        def _unsub() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _unsub

    async def emit_event(self, evt: AgentEvent) -> None:
        """Inject an event onto the same bus as the agent loop (extensions + subscribers)."""
        await self._handle_event(evt)

    async def _notify_listeners(self, evt: AgentEvent) -> None:
        for listener in list(self._listeners):
            try:
                result = listener(evt)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                raise normalize_hook_error(exc) from exc

    # ── public API ──────────────────────────────────────────────────

    async def prompt(
        self,
        text_or_message: Any,
        *,
        images: list[ImageContent] | None = None,
    ) -> AssistantMessage:
        self._check_ready()
        if self._phase != AgentHarnessPhase.IDLE:
            raise AgentHarnessError(
                "busy",
                f"AgentHarness is busy (phase={self._phase.value}); use steer/follow_up or wait_for_idle.",
            )
        message = self._normalize_input(text_or_message, images)
        prepended = self._drain_next_turn()
        return await self._execute_turn([*prepended, message], continuation=False)

    async def continue_(self) -> AssistantMessage:
        self._check_ready()
        if self._phase != AgentHarnessPhase.IDLE:
            raise AgentHarnessError("busy", f"AgentHarness is busy (phase={self._phase.value}).")
        if not self.state.messages:
            raise AgentHarnessError("invalid_state", "No messages in state to continue from.")
        last = self.state.messages[-1]
        if not isinstance(last, (UserMessage, ToolResultMessage)):
            raise AgentHarnessError(
                "invalid_state",
                f"Cannot continue from message with role={getattr(last, 'role', 'unknown')}.",
            )
        return await self._execute_turn([], continuation=True)

    async def compact(self, *, instructions: str | None = None) -> dict[str, Any] | None:
        self._check_ready()
        if self._compactor is None:
            return None
        if self._phase != AgentHarnessPhase.IDLE:
            raise AgentHarnessError("busy", "compact() requires idle phase")
        self.phase = AgentHarnessPhase.COMPACTION
        try:
            hook_result = await self.hooks.emit(SessionBeforeCompactHookEvent(
                messages=list(self.state.messages),
                instructions=instructions,
            ))
            if hook_result and isinstance(hook_result, dict) and hook_result.get("cancel"):
                return None
            compacted = await self._compactor.compact(
                list(self.state.messages),
                reason="manual",
                instructions=instructions,
                signal=None,
            )
            if compacted.summary and compacted.kept_count > 0:
                await self._apply_compaction_result(compacted, list(self.state.messages))
                return {"compacted": True, "result": True}
            return {"compacted": False, "result": False}
        except Exception as exc:
            raise AgentHarnessError("compaction", str(exc), cause=exc) from exc
        finally:
            self.phase = AgentHarnessPhase.IDLE

    def abort(self) -> None:
        if self._abort_event is not None:
            self._abort_event.set()
        self._human_input_gate.cancel_all()

    async def abort_and_wait(self) -> dict[str, Any]:
        cleared_steer = self._steering.drain()
        cleared_follow_up = self._follow_up.drain()
        self.abort()
        await self.wait_for_idle()
        await self._notify_listeners(AbortEvent(
            cleared_steer=list(cleared_steer),
            cleared_follow_up=list(cleared_follow_up),
        ))
        return {
            "cleared_steer": list(cleared_steer),
            "cleared_follow_up": list(cleared_follow_up),
            "next_turn_count": self._next_turn.item_count,
        }

    async def wait_for_idle(self) -> None:
        if self._active_run is not None:
            await self._active_run

    def provide_human_input(self, tool_call_id: str, values: dict[str, Any]) -> bool:
        return self._human_input_gate.provide_input(tool_call_id, values)

    def run_when_idle(self, callback: Callable[[], Awaitable[None] | None]) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()

        async def _deferred() -> None:
            try:
                active = self._active_run
                if active is not None and not active.done():
                    await active
                while self.phase != AgentHarnessPhase.IDLE:
                    await asyncio.sleep(0)
                result = callback()
                if inspect.isawaitable(result):
                    result = await result
                if not fut.done():
                    fut.set_result(result)
            except Exception as exc:
                if not fut.done():
                    fut.set_exception(exc)

        loop.create_task(_deferred())
        return fut

    # ── turn execution ──────────────────────────────────────────────

    async def _execute_turn(
        self,
        new_messages: list[Any],
        *,
        continuation: bool,
    ) -> AssistantMessage:
        self.phase = AgentHarnessPhase.TURN
        self._abort_event = asyncio.Event()
        self._pending_tool_calls.clear()
        self.clear_skill_activations()
        self.state.is_streaming = True
        self.state.error_message = None
        last_assistant: AssistantMessage | None = None

        async def _do_run() -> None:
            nonlocal last_assistant
            from agent_core.observability import generate_run_id, observe, _resolve_observe_user_id

            snapshot = self.create_turn_snapshot()
            context = AgentContext(
                system_prompt=snapshot.system_prompt,
                messages=list(snapshot.messages),
                tools=list(snapshot.tools),
            )
            run_id = generate_run_id()
            compact_cb = self._overflow_compact_callback
            config = build_loop_config(
                self,
                provider=self._provider,
                auth_source=self._auth_source,
                convert_to_llm=self._convert_to_llm,
                tool_registry=self._tool_registry,
                tool_execution=self._tool_execution,
                tool_timeout=self._tool_timeout,
                max_turns=self._max_turns,
                max_retries=self._max_retries,
                retry_base_delay=self._retry_base_delay,
                retry_max_delay=self._retry_max_delay,
                compact_callback=compact_cb,
                tool_result_max_chars=self._tool_result_max_chars,
                human_input_gate=self._human_input_gate,
                tool_catalog_threshold=self._tool_catalog_threshold,
                disable_tool_routing=self._disable_tool_routing,
                run_id=run_id,
            )

            before_agent_start = chain_before_agent_start_hooks(self.hooks)
            if before_agent_start is not None:
                prompt = new_messages[0].content[0].text if new_messages else ""
                result = await before_agent_start(prompt, context.system_prompt)
                if result:
                    if result.get("system_prompt"):
                        context.system_prompt = result["system_prompt"]
                    if result.get("message"):
                        context.messages.append(result["message"])

            # Extensions (e.g. plan step action space) may call set_active_tools
            # during before_agent_start — refresh tools for this turn's first LLM call.
            from agent_core.session.tool_utils import filter_active_tools

            context.tools = filter_active_tools(self.state.tools, self._active_tool_names)

            # Skill routing: filter skills section in system_prompt per user message
            if self._skill_routing and new_messages:
                all_skills = self._resources.get("skills", [])
                if all_skills:
                    from agent_core.routing.skill_router import route_skills
                    user_text = new_messages[0].content[0].text if new_messages[0].content else ""
                    active_skills = route_skills(user_text, all_skills)
                    active_names = {s.name for s in active_skills}
                    # Rebuild <available_skills> section with filtered skills
                    import re as _re
                    def _replace_skills(match: Any) -> str:
                        lines = ["<available_skills>"]
                        for s in active_skills:
                            if not s.disable_model_invocation:
                                lines.append(f'  <skill name="{s.name}">{s.description}</skill>')
                        lines.append("</available_skills>")
                        return "\n".join(lines)
                    context.system_prompt = _re.sub(
                        r"<available_skills>.*?</available_skills>",
                        _replace_skills,
                        context.system_prompt,
                        flags=_re.DOTALL,
                    )

            # Catalog mode: register tool_detail meta-tool and ensure it's always available
            threshold = self._tool_catalog_threshold
            if (
                threshold is not None
                and not self._disable_tool_routing
                and len(context.tools) > threshold
                and self._tool_registry is not None
            ):
                from agent_core.tools.tool_catalog import ToolCatalogTool
                from agent_core.session.tool_utils import resolve_tool_name

                catalog_tool = ToolCatalogTool(self._tool_registry)
                # Register in the tool registry so the executor can find it
                if self._tool_registry.get("tool_detail") is None:
                    self._tool_registry.register(catalog_tool)
                # Inject into context.tools if not already present
                tool_names_in_ctx = {
                    resolve_tool_name(t, i) for i, t in enumerate(context.tools)
                }
                if "tool_detail" not in tool_names_in_ctx:
                    context.tools.append(catalog_tool)

            async def _emit_sink(evt: AgentEvent) -> None:
                nonlocal last_assistant
                if isinstance(evt, AgentEnd) and evt.messages:
                    last_assistant = evt.messages[-1]
                await self._handle_event(evt, context)

            msgs = [] if continuation else new_messages
            model = snapshot.model
            provider_name = getattr(model, "provider", "") if model else ""
            model_id = getattr(model, "id", "") if model else ""

            with observe(
                self,
                session_id=self._session_id,
                run_id=run_id,
                provider_name=provider_name,
                model_id=model_id,
                system_prompt=context.system_prompt or "",
                user_id=_resolve_observe_user_id(self),
            ):
                try:
                    assistants = await run_agent_loop(
                        msgs, context, config, _emit_sink, self._abort_event,
                    )
                    if last_assistant is None and assistants:
                        last_assistant = assistants[-1]
                except Exception as exc:
                    logger.exception("AgentHarness run failed")
                    last_assistant = await self._emit_run_failure(
                        normalize_harness_error(exc), context, self._abort_event,
                    )

        task = asyncio.create_task(_do_run())
        self._active_run = task
        try:
            await task
        finally:
            self._finish_run()

        if last_assistant is None:
            raise AgentHarnessError("invalid_state", "Turn completed without assistant message")
        return last_assistant

    async def _emit_run_failure(
        self,
        exc: BaseException,
        context: AgentContext,
        abort_event: asyncio.Event | None = None,
    ) -> AssistantMessage:
        error_msg = str(exc)
        aborted = abort_event is not None and abort_event.is_set()
        model = self.state.model
        assistant = AssistantMessage(
            content=[TextContent(text="")],
            usage=Usage(),
            stop_reason="aborted" if aborted else "error",
            provider=model.provider if model else "",
            model=model.id if model else "",
            error_message=error_msg,
            retryable_error=getattr(exc, "retryable", False),
            timestamp=time.time(),
        )
        self.state.error_message = error_msg
        await self._handle_event(MessageStart(message=assistant), context)
        await self._handle_event(MessageEnd(message=assistant), context)
        await self._handle_event(TurnEnd(message=assistant, tool_results=[]), context)
        await self._handle_event(AgentEnd(messages=[assistant]), context)
        return assistant

    def _finish_run(self) -> None:
        self.phase = AgentHarnessPhase.IDLE
        self.state.is_streaming = False
        self.state.streaming_message = None
        self._pending_tool_calls.clear()
        self._active_run = None
        self._abort_event = None

    def create_turn_snapshot(self) -> Any:
        return create_turn_snapshot(self)

    async def prepare_next_turn(self) -> Any:
        return self.create_turn_snapshot()

    @staticmethod
    def _normalize_input(text_or_message: Any, images: list[ImageContent] | None) -> Any:
        if isinstance(text_or_message, str):
            content: list[Any] = [TextContent(text=text_or_message)]
            if images:
                content.extend(images)
            return UserMessage(content=content, timestamp=time.time())
        return text_or_message
