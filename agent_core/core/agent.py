"""Agent — loop runner that wraps run_agent_loop with state/subscribe/abort.

When used with AgentSession/AgentHarness (the preferred mode), the Agent
delegates hooks, phase, queues, listeners, config setters, and event handling
to the harness via ``_harness`` injection.  With harness attached,
``_handle_event`` and ``_notify_listeners`` are pure delegates.
Standalone use retains all fields on the Agent itself for backward compatibility.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Awaitable, Callable

from agent_core.core.content import ImageContent, TextContent
from agent_core.core.errors import AgentHarnessError, normalize_harness_error
from agent_core.core.pending_writes import PendingSessionWrite
from agent_core.core.context import (
    AgentContext,
    AgentLoopConfig,
    AuthResolver,
    ConvertToLlm,
    TransformContext,
    TurnSnapshot,
)
from agent_core.core.events import (
    AbortEvent,
    AgentEnd,
    AgentEvent,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ModelUpdate,
    QueueUpdate,
    ResourcesUpdate,
    Settled,
    ThinkingLevelUpdate,
    ToolsUpdate,
    TurnEnd,
)
from agent_core.core.hooks import (
    AgentHooks,
    BeforeAgentStartHookEvent,
    BeforeProviderPayloadHookEvent,
    BeforeProviderRequestHookEvent,
    AfterProviderResponseHookEvent,
    ContextHookEvent,
    ToolCallHookEvent,
    ToolResultHookEvent,
)
from agent_core.core.stream_options import clone_stream_options
from agent_core.core.human_input import HumanInputGate
from agent_core.core.loop import run_agent_loop
from agent_core.core.messages import AssistantMessage, ToolResultMessage, Usage, UserMessage
from agent_core.core.queue import PendingMessageQueue, QueueMode
from agent_core.core.state import AgentHarnessPhase, AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.base import ModelProvider
from agent_core.providers.message_converter import create_default_converter
from agent_core.tools.mutation_queue import FileMutationQueue

_log = logging.getLogger(__name__)

Listener = Callable[[AgentEvent], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


async def _maybe_await(fn: Any, *args: Any) -> Any:
    result = fn(*args)
    if inspect.isawaitable(result):
        return await result
    return result


def _resolve_tool_name(tool: Any, index: int = 0) -> str:
    name = getattr(tool, "name", None)
    if name:
        return str(name)
    definition = getattr(tool, "definition", None)
    if definition is not None:
        def_name = getattr(definition, "name", None)
        if def_name:
            return str(def_name)
    return str(index)


def _filter_active_tools(tools: list[Any], active_tool_names: list[str] | None) -> list[Any]:
    if active_tool_names is None:
        return list(tools)
    active = set(active_tool_names)
    return [
        t for i, t in enumerate(tools)
        if _resolve_tool_name(t, i) in active
    ]


class Agent:
    def __init__(
        self,
        *,
        provider: ModelProvider,
        auth_source: AuthSource,
        initial_state: AgentState | None = None,
        convert_to_llm: ConvertToLlm | None = None,
        transform_context: TransformContext | None = None,
        tool_registry: Any | None = None,
        before_tool_call: Any | None = None,
        after_tool_call: Any | None = None,
        tool_execution: str = "parallel",
        tool_timeout: float | None = 120.0,
        max_turns: int | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 60.0,
        compact_callback: Any | None = None,
        tool_result_max_chars: int = 4000,
        steering_mode: QueueMode = "one-at-a-time",
        followup_mode: QueueMode = "one-at-a-time",
    ) -> None:
        self.state: AgentState = initial_state or AgentState()
        self._provider = provider
        self._auth_source = auth_source
        if convert_to_llm is not None:
            self._convert_to_llm = convert_to_llm
        elif hasattr(provider, "create_message_converter"):
            self._convert_to_llm = provider.create_message_converter(tool_result_max_chars)
        else:
            self._convert_to_llm = create_default_converter(tool_result_max_chars)
        self._tool_registry = tool_registry
        self._tool_execution = tool_execution
        self._tool_timeout = tool_timeout
        self._max_turns = max_turns
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay
        self._compact_callback = compact_callback
        self._tool_result_max_chars = tool_result_max_chars
        self._steering = PendingMessageQueue(steering_mode)
        self._follow_up = PendingMessageQueue(followup_mode)
        self._human_input_gate = HumanInputGate()
        self._listeners: list[Listener] = []
        self._active_run: asyncio.Task | None = None
        self._abort_event: asyncio.Event | None = None
        self._pending_tool_calls: set[str] = set()
        self._pending_writes: list[PendingSessionWrite] = []
        self._phase: AgentHarnessPhase = AgentHarnessPhase.IDLE
        self._harness: Any | None = None  # Set by AgentSession/AgentHarness
        self._active_tool_names: list[str] | None = None
        self._stream_options: dict[str, Any] = {}

        # Unified hook system (standalone default; delegated when harness is set)
        self._hooks = AgentHooks()

        # Register constructor-provided hooks via the unified system
        if before_tool_call is not None:
            self._register_legacy_tool_call(before_tool_call)
        if after_tool_call is not None:
            self._register_legacy_tool_result(after_tool_call)
        if transform_context is not None:
            self._register_legacy_context(transform_context)

    @property
    def hooks(self) -> AgentHooks:
        """Hook registry.  Delegates to harness when set, else uses own."""
        if self._harness is not None:
            return self._harness.hooks
        return self._hooks

    # ── MCP tools ───────────────────────────────────────────────────

    async def setup_mcp_tools(self, mcp_manager: Any | None = None) -> int:
        if mcp_manager is None:
            from agent_core.tools.mcp_tool import MCPManager
            mcp_manager = MCPManager.from_env()
            await mcp_manager.start()
        self._mcp_manager = mcp_manager
        if self._tool_registry is not None:
            return mcp_manager.register_tools(self._tool_registry)
        return 0

    # ── phase ─────────────────────────────────────────────────────

    @property
    def phase(self) -> AgentHarnessPhase:
        """Current lifecycle phase of the agent."""
        if self._harness is not None:
            return self._harness.phase
        return self._phase

    @phase.setter
    def phase(self, value: AgentHarnessPhase) -> None:
        self._phase = value
        self.state.phase = value
        if self._harness is not None:
            self._harness.phase = value

    # ── public API ──────────────────────────────────────────────────

    @property
    def signal(self) -> asyncio.Event | None:
        """The abort signal for the current run, or None if idle."""
        return self._abort_event

    @property
    def pending_tool_calls(self) -> set[str]:
        """Tool call IDs currently executing."""
        return self._pending_tool_calls

    def has_queued_messages(self) -> bool:
        if self._harness is not None:
            return self._harness.has_queued_messages()
        return self._steering.has_items() or self._follow_up.has_items()

    def subscribe(self, listener: Listener) -> Unsubscribe:
        if self._harness is not None:
            return self._harness.subscribe(listener)
        self._listeners.append(listener)

        def _unsub() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _unsub

    def steer(self, message: Any) -> None:
        if self._harness is not None:
            self._harness.steer(message)
            return
        self._steering.enqueue(message)
        self._schedule_queue_update()

    def follow_up(self, message: Any) -> None:
        if self._harness is not None:
            self._harness.follow_up(message)
            return
        self._follow_up.enqueue(message)
        self._schedule_queue_update()

    def provide_human_input(self, tool_call_id: str, values: dict[str, Any]) -> bool:
        return self._human_input_gate.provide_input(tool_call_id, values)

    def clear_all_queues(self) -> None:
        if self._harness is not None:
            self._harness.clear_all_queues()
            return
        self._steering.clear()
        self._follow_up.clear()

    @property
    def steering_mode(self) -> QueueMode:
        if self._harness is not None:
            return self._harness.steering_mode
        return self._steering.mode

    @steering_mode.setter
    def steering_mode(self, mode: QueueMode) -> None:
        if self._harness is not None:
            self._harness.steering_mode = mode
            return
        self._steering.mode = mode

    @property
    def followup_mode(self) -> QueueMode:
        if self._harness is not None:
            return self._harness.followup_mode
        return self._follow_up.mode

    @followup_mode.setter
    def followup_mode(self, mode: QueueMode) -> None:
        if self._harness is not None:
            self._harness.followup_mode = mode
            return
        self._follow_up.mode = mode

    # ── hooks ───────────────────────────────────────────────────────

    def add_before_agent_start_hook(self, hook: Any) -> None:
        self.hooks.on("before_agent_start", hook)

    def add_before_tool_call_hook(self, hook: Any) -> None:
        self._register_legacy_tool_call(hook)

    def remove_before_tool_call_hook(self, hook: Any) -> None:
        # Legacy compat — best-effort removal not supported with unified hooks
        pass

    def add_after_tool_call_hook(self, hook: Any) -> None:
        self._register_legacy_tool_result(hook)

    def remove_after_tool_call_hook(self, hook: Any) -> None:
        pass

    def add_transform_context_hook(self, hook: Any) -> None:
        self._register_legacy_context(hook)

    # -- legacy hook adapters --

    def _register_legacy_tool_call(self, handler: Any) -> None:
        """Adapt old-style before_tool_call handler to typed ToolCallHookEvent."""
        async def _adapter(event: ToolCallHookEvent) -> Any:
            return await _maybe_await(handler, event.call_ctx)
        self.hooks.on("tool_call", _adapter)

    def _register_legacy_tool_result(self, handler: Any) -> None:
        """Adapt old-style after_tool_call handler to typed ToolResultHookEvent."""
        async def _adapter(event: ToolResultHookEvent) -> Any:
            return await _maybe_await(handler, event.call_ctx)
        self.hooks.on("tool_result", _adapter)

    def _register_legacy_context(self, handler: Any) -> None:
        """Adapt old-style transform_context handler to typed ContextHookEvent."""
        async def _adapter(event: ContextHookEvent) -> Any:
            result = handler(event.messages, None)  # signal=None for compat
            if inspect.isawaitable(result):
                result = await result
            if result is not None and result is not event.messages:
                return {"messages": result}
            return None
        self.hooks.on("context", _adapter)

    # ── runtime config setters ────────────────────────────────────

    def get_model(self) -> Any:
        """Current model configuration."""
        if self._harness is not None:
            return self._harness.get_model()
        return self.state.model

    async def set_model(self, model: Any) -> None:
        """Update the model.  Delegates to harness when set."""
        if self._harness is not None:
            await self._harness.set_model(model)
            return
        previous_model = self.state.model
        self._pending_writes.append(PendingSessionWrite(
            type="model_change",
            data={"provider": getattr(model, "provider", ""), "model_id": getattr(model, "id", "")},
        ))
        self.state.model = model
        await self._notify_listeners(ModelUpdate(
            model=model, previous_model=previous_model, source="set",
        ))

    def get_thinking_level(self) -> str:
        """Current thinking level."""
        if self._harness is not None:
            return self._harness.get_thinking_level()
        return self.state.thinking_level

    async def set_thinking_level(self, level: str) -> None:
        """Update thinking level.  Delegates to harness when set."""
        if self._harness is not None:
            await self._harness.set_thinking_level(level)
            return
        previous_level = self.state.thinking_level
        self._pending_writes.append(PendingSessionWrite(
            type="thinking_level_change",
            data={"thinking_level": level},
        ))
        self.state.thinking_level = level
        await self._notify_listeners(ThinkingLevelUpdate(
            level=level, previous_level=previous_level,
        ))

    def get_tools(self) -> list[Any]:
        """Current tool list."""
        if self._harness is not None:
            return self._harness.get_tools()
        return list(self.state.tools)

    async def set_tools(self, tools: list[Any], active_tool_names: list[str] | None = None) -> None:
        """Replace tool set.  Delegates to harness when set."""
        if self._harness is not None:
            await self._harness.set_tools(tools, active_tool_names)
            return
        names = [_resolve_tool_name(t, i) for i, t in enumerate(tools)]
        if len(names) != len(set(names)):
            raise AgentHarnessError("invalid_argument", "Duplicate tool name(s)")
        previous_tool_names = [_resolve_tool_name(t, i) for i, t in enumerate(self.state.tools)]
        if active_tool_names is None:
            active_tool_names = list(names)
        self._pending_writes.append(PendingSessionWrite(
            type="active_tools_change",
            data={"active_tool_names": list(active_tool_names)},
        ))
        self.state.tools = list(tools)
        self._active_tool_names = list(active_tool_names)
        await self._notify_listeners(ToolsUpdate(
            tool_names=names,
            previous_tool_names=previous_tool_names,
            active_tool_names=list(active_tool_names),
            previous_active_tool_names=previous_tool_names,
            source="set",
        ))

    async def set_active_tools(self, tool_names: list[str]) -> None:
        """Change which tools are active (by name).  Delegates to harness when set."""
        if self._harness is not None:
            await self._harness.set_active_tools(tool_names)
            return
        all_names = {_resolve_tool_name(t, i) for i, t in enumerate(self.state.tools)}
        unknown = [n for n in tool_names if n not in all_names]
        if unknown:
            raise AgentHarnessError("invalid_argument", f"Unknown tool(s): {', '.join(unknown)}")
        previous_tool_names = [_resolve_tool_name(t, i) for i, t in enumerate(self.state.tools)]
        previous_active = previous_tool_names
        self._pending_writes.append(PendingSessionWrite(
            type="active_tools_change",
            data={"active_tool_names": list(tool_names)},
        ))
        self._active_tool_names = list(tool_names)
        await self._notify_listeners(ToolsUpdate(
            tool_names=previous_tool_names,
            previous_tool_names=previous_tool_names,
            active_tool_names=list(tool_names),
            previous_active_tool_names=previous_active,
            source="set",
        ))

    def get_stream_options(self) -> dict[str, Any]:
        """Current stream options (harness config, not in-flight snapshot)."""
        if self._harness is not None:
            return self._harness.get_stream_options()
        return clone_stream_options(self._stream_options)

    def set_stream_options(self, options: dict[str, Any]) -> None:
        """Update stream options immediately; affects future turn snapshots only."""
        if self._harness is not None:
            self._harness.set_stream_options(options)
            return
        self._stream_options = clone_stream_options(options)

    async def _notify_listeners(self, evt: AgentEvent) -> None:
        """Emit a harness own event to all listeners."""
        if self._harness is not None:
            await self._harness._notify_listeners(evt)
            return
        for listener in list(self._listeners):
            result = listener(evt)
            if inspect.isawaitable(result):
                await result

    def _schedule_queue_update(self) -> None:
        """Schedule a QueueUpdate emit (fire-and-forget task)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no running loop, skip emit
        asyncio.create_task(self._emit_queue_update())

    async def _emit_queue_update(self) -> None:
        """Emit a QueueUpdate event to listeners."""
        await self._notify_listeners(QueueUpdate(
            steer_count=self._steering.item_count,
            follow_up_count=self._follow_up.item_count,
        ))

    # ── control ─────────────────────────────────────────────────────

    def abort(self) -> None:
        if self._abort_event is not None:
            self._abort_event.set()
        self._human_input_gate.cancel_all()

    async def abort_and_wait(self) -> dict[str, Any]:
        """Abort the current run and wait for idle.  Delegates to harness when set."""
        if self._harness is not None:
            return await self._harness.abort_and_wait()
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
        }

    async def wait_for_idle(self) -> None:
        if self._active_run is not None:
            await self._active_run

    def reset(self) -> None:
        self.state = AgentState(
            system_prompt=self.state.system_prompt,
            model=self.state.model,
            thinking_level=self.state.thinking_level,
            tools=list(self.state.tools),
        )
        self._steering.clear()
        self._follow_up.clear()
        self._pending_tool_calls.clear()

    # ── compact ───────────────────────────────────────────────────

    async def compact(self, *, instructions: str | None = None) -> dict[str, Any] | None:
        """Manually trigger compaction.  Requires IDLE phase.

        Emits ``session_before_compact`` hook (handler may cancel),
        then calls the configured ``compact_callback``.
        Returns the compaction result dict or None if cancelled.
        """
        if self._phase != AgentHarnessPhase.IDLE:
            raise AgentHarnessError("busy", "compact() requires idle phase")
        self.phase = AgentHarnessPhase.COMPACTION
        try:
            # Emit before_compact hook
            from agent_core.core.hooks import SessionBeforeCompactHookEvent
            hook_result = await self.hooks.emit(SessionBeforeCompactHookEvent(
                messages=list(self.state.messages),
                instructions=instructions,
            ))
            if hook_result and isinstance(hook_result, dict) and hook_result.get("cancel"):
                return None

            if self._compact_callback is None:
                return None

            result = await self._compact_callback(list(self.state.messages))
            return {"compacted": True, "result": result}
        except Exception as exc:
            raise AgentHarnessError("compaction", str(exc), cause=exc)
        finally:
            self.phase = AgentHarnessPhase.IDLE

    # ── run ─────────────────────────────────────────────────────────

    async def prompt(
        self,
        text_or_message: Any,
        *,
        images: list[ImageContent] | None = None,
        compact_callback: Any | None = None,
    ) -> None:
        if self._phase != AgentHarnessPhase.IDLE:
            raise AgentHarnessError("busy", "Agent is busy (phase=%s); use steer/follow_up or wait_for_idle." % self._phase.value)
        message = self._normalize_input(text_or_message, images)
        await self._run([message], continuation=False, compact_callback=compact_callback)

    async def continue_(self, *, compact_callback: Any | None = None) -> None:
        if self._phase != AgentHarnessPhase.IDLE:
            raise AgentHarnessError("busy", "Agent is busy (phase=%s)." % self._phase.value)
        if not self.state.messages:
            raise AgentHarnessError("invalid_state", "No messages in state to continue from.")
        last = self.state.messages[-1]
        if not isinstance(last, (UserMessage, ToolResultMessage)):
            raise AgentHarnessError("invalid_state", f"Cannot continue from message with role={getattr(last, 'role', 'unknown')}.")
        await self._run([], continuation=True, compact_callback=compact_callback)

    # ── internal ────────────────────────────────────────────────────

    def _normalize_input(
        self, text_or_message: Any, images: list[ImageContent] | None
    ) -> Any:
        if isinstance(text_or_message, str):
            content: list[Any] = [TextContent(text=text_or_message)]
            if images:
                content.extend(images)
            return UserMessage(content=content, timestamp=time.time())
        return text_or_message

    def _stream_fn(self):
        """Return the provider's stream method — loop calls it directly."""
        return self._provider.stream

    def _make_stream_fn(self, config: AgentLoopConfig) -> Any:
        """Wrap provider stream with stream options and provider hooks."""
        base_stream = self._provider.stream
        agent = self

        async def stream_fn(**kwargs: Any) -> Any:
            from agent_core.core.stream_options import clone_stream_options

            options = clone_stream_options(config.stream_options)
            session_id = ""
            if agent._harness is not None:
                session_id = getattr(agent._harness, "_session_id", "")

            req_evt = BeforeProviderRequestHookEvent(
                model=kwargs.get("model"),
                session_id=session_id,
                stream_options=options,
            )
            req_result = await agent.hooks.emit(req_evt)
            if req_result and isinstance(req_result, dict) and "stream_options" in req_result:
                options = req_result["stream_options"]

            payload = {
                "messages": list(kwargs.get("messages") or []),
                "tools": list(kwargs.get("tools") or []),
                "system_prompt": kwargs.get("system_prompt", ""),
            }
            payload_evt = BeforeProviderPayloadHookEvent(
                model=kwargs.get("model"),
                payload=payload,
            )
            payload_result = await agent.hooks.emit(payload_evt)
            if payload_result and isinstance(payload_result, dict) and "payload" in payload_result:
                payload = payload_result["payload"]

            call_kwargs = dict(kwargs)
            call_kwargs["messages"] = payload.get("messages", call_kwargs.get("messages"))
            call_kwargs["tools"] = payload.get("tools", call_kwargs.get("tools"))
            call_kwargs["system_prompt"] = payload.get(
                "system_prompt", call_kwargs.get("system_prompt", ""),
            )
            call_kwargs["stream_options"] = options
            if options.get("headers"):
                call_kwargs["request_headers"] = dict(options["headers"])
            if options.get("metadata"):
                call_kwargs["request_metadata"] = dict(options["metadata"])
            if "temperature" in options:
                call_kwargs["temperature"] = options["temperature"]
            if "max_tokens" in options:
                call_kwargs["max_tokens"] = options["max_tokens"]

            async for evt in base_stream(**call_kwargs):
                yield evt

            resp_evt = AfterProviderResponseHookEvent(
                model=kwargs.get("model"),
                status=200,
                headers={},
            )
            await agent.hooks.emit(resp_evt)

        return stream_fn

    def _create_loop_config(
        self, *, compact_callback: Any | None = None
    ) -> AgentLoopConfig:
        async def auth_resolver(provider_name: str):
            return await self._auth_source.resolve(provider_name)

        snapshot = self.create_turn_snapshot()
        config = AgentLoopConfig(
            model=self.state.model,
            stream_fn=self._stream_fn(),
            convert_to_llm=self._convert_to_llm,
            auth_resolver=auth_resolver,
            transform_context=self._chain_transform_hooks(),
            thinking_level=self.state.thinking_level,
            tool_execution=self._tool_execution,
            tool_registry=self._tool_registry,
            before_tool_call=self._chain_before_hooks(),
            after_tool_call=self._chain_after_hooks(),
            tool_timeout=self._tool_timeout,
            max_turns=self._max_turns,
            max_retries=self._max_retries,
            retry_base_delay=self._retry_base_delay,
            retry_max_delay=self._retry_max_delay,
            compact_callback=compact_callback or self._compact_callback,
            mutation_queue=FileMutationQueue(),
            tool_result_max_chars=self._tool_result_max_chars,
            get_steering_messages=self._drain_steering,
            get_follow_up_messages=self._drain_follow_up,
            human_input_gate=self._human_input_gate,
            prepare_next_turn=self._prepare_next_turn,
            flush_pending_writes=self._flush_pending_writes,
            stream_options=clone_stream_options(snapshot.stream_options),
        )
        config.stream_fn = self._make_stream_fn(config)
        return config

    async def _run(
        self, new_messages: list[Any], *, continuation: bool, compact_callback: Any | None = None
    ) -> None:
        # Phase guard: structural operations require IDLE
        self.phase = AgentHarnessPhase.TURN
        self._abort_event = asyncio.Event()
        self._pending_tool_calls.clear()
        self.state.is_streaming = True  # deprecated compat
        self.state.error_message = None

        async def _do_run() -> None:
            context = AgentContext(
                system_prompt=self.state.system_prompt,
                messages=list(self.state.messages),
                tools=list(self.state.tools),
            )
            config = self._create_loop_config(compact_callback=compact_callback)

            # Let extensions inspect/modify the run before the loop starts.
            before_agent_start = self._chain_before_agent_start_hooks()
            if before_agent_start is not None:
                prompt = new_messages[0].content[0].text if new_messages else ""
                result = await before_agent_start(prompt, context.system_prompt)
                if result:
                    if result.get("system_prompt"):
                        context.system_prompt = result["system_prompt"]
                    if result.get("message"):
                        context.messages.append(result["message"])

            # Emit-sink: routes to harness._handle_event or agent._handle_event
            if self._harness is not None:
                async def _emit_sink(evt: AgentEvent) -> None:
                    await self._harness._handle_event(evt, context)
            else:
                async def _emit_sink(evt: AgentEvent) -> None:
                    await self._handle_event(evt, context)

            msgs = [] if continuation else new_messages
            try:
                await run_agent_loop(msgs, context, config, _emit_sink, self._abort_event)
            except Exception as exc:
                _log.exception("Agent run failed")
                await self._emit_run_failure(
                    normalize_harness_error(exc), context, self._abort_event,
                )

        task = asyncio.create_task(_do_run())
        self._active_run = task
        try:
            await task
        finally:
            self._finish_run()

    async def _emit_run_failure(
        self, exc: BaseException, context: AgentContext, abort_event: asyncio.Event | None = None,
    ) -> None:
        """Emit a full failure event flow: message_start → message_end → turn_end → agent_end.

        This ensures state updates, persistence, and listener notifications
        all go through the normal event handling path.
        """
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
            retryable_error=getattr(exc, 'retryable', False),
            timestamp=time.time(),
        )
        self.state.error_message = error_msg

        async def _emit_sink(evt: AgentEvent) -> None:
            if self._harness is not None:
                await self._harness._handle_event(evt, context)
            else:
                await self._handle_event(evt, context)

        await _emit_sink(MessageStart(message=assistant))
        await _emit_sink(MessageEnd(message=assistant))
        await _emit_sink(TurnEnd(message=assistant, tool_results=[]))
        await _emit_sink(AgentEnd(messages=[assistant]))

    def _finish_run(self) -> None:
        self.phase = AgentHarnessPhase.IDLE
        self.state.is_streaming = False  # deprecated compat
        self.state.streaming_message = None
        self._pending_tool_calls.clear()
        self._active_run = None
        self._abort_event = None

    # ── hook chaining (delegated to unified AgentHooks) ────────────

    def _chain_before_agent_start_hooks(self) -> Any | None:
        """Return an async callable for before-agent-start, or None."""
        if not self.hooks._handlers.get("before_agent_start"):
            return None

        async def _chained(prompt: str, system_prompt: str) -> dict[str, Any] | None:
            evt = BeforeAgentStartHookEvent(prompt=prompt, system_prompt=system_prompt)
            return await self.hooks.emit(evt)

        return _chained

    def _chain_before_hooks(self) -> Any | None:
        """Return an async callable for before-tool-call, or None."""
        if not self.hooks._handlers.get("tool_call"):
            return None

        async def _chained(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
            evt = ToolCallHookEvent(
                tool_call_id=call_ctx.get("tool_call_id", ""),
                tool_name=call_ctx.get("tool_name", ""),
                input=call_ctx.get("input", {}),
                call_ctx=call_ctx,
            )
            return await self.hooks.emit(evt)

        return _chained

    def _chain_after_hooks(self) -> Any | None:
        """Return an async callable for after-tool-call, or None."""
        if not self.hooks._handlers.get("tool_result"):
            return None

        async def _chained(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
            evt = ToolResultHookEvent(
                tool_call_id=call_ctx.get("tool_call_id", ""),
                tool_name=call_ctx.get("tool_name", ""),
                input=call_ctx.get("input", {}),
                result=call_ctx.get("result"),
                is_error=call_ctx.get("is_error", False),
                call_ctx=call_ctx,
            )
            return await self.hooks.emit(evt)

        return _chained

    def _chain_transform_hooks(self) -> Any | None:
        """Return an async callable for context transform, or None."""
        if not self.hooks._handlers.get("context"):
            return None

        async def _chained(llm_messages: list[Any], signal: Any) -> list[Any]:
            evt = ContextHookEvent(messages=list(llm_messages))
            result = await self.hooks.emit(evt)
            if result and isinstance(result, dict) and "messages" in result:
                return result["messages"]
            return llm_messages

        return _chained

    # ── queue drains ────────────────────────────────────────────────

    async def _drain_steering(self) -> list[Any]:
        if self._harness is not None:
            return await self._harness._drain_steering()
        return self._steering.drain()

    async def _drain_follow_up(self) -> list[Any]:
        if self._harness is not None:
            return await self._harness._drain_follow_up()
        return self._follow_up.drain()

    # ── turn snapshot ───────────────────────────────────────────────

    def create_turn_snapshot(self) -> TurnSnapshot:
        """Create an immutable snapshot of the current harness config.

        Called at the start of each turn and at save points.  Runtime config
        setters update the harness but do NOT mutate an in-flight snapshot.
        """
        all_tools = list(self.state.tools)
        active_tools = _filter_active_tools(all_tools, self._active_tool_names)
        return TurnSnapshot(
            messages=list(self.state.messages),
            system_prompt=self.state.system_prompt,
            tools=active_tools,
            model=self.state.model,
            thinking_level=self.state.thinking_level,
            stream_options=clone_stream_options(self._stream_options),
        )

    async def _prepare_next_turn(self) -> TurnSnapshot | None:
        """Save-point callback: create a fresh snapshot for the next turn.

        Called by the loop after turn_end and before the next provider
        request.  Returns a new snapshot so the loop can pick up runtime
        config changes (model, thinking level, tools, system prompt)
        made during the current turn.
        """
        return self.create_turn_snapshot()

    # ── pending writes ─────────────────────────────────────────────

    async def _flush_pending_writes(self) -> None:
        """Flush all queued session writes (FIFO).  Delegates to harness when set."""
        if self._harness is not None:
            await self._harness._flush_pending_writes()
            return
        while self._pending_writes:
            write = self._pending_writes.pop(0)
            _log.debug("Flushing pending write: %s", write.type)

    # ── event handling ──────────────────────────────────────────────

    async def _handle_event(self, evt: AgentEvent, context: AgentContext) -> None:
        """Handle events on the standalone path; delegates to harness when attached."""
        if self._harness is not None:
            await self._harness._handle_event(evt, context)
            return
        if isinstance(evt, MessageStart):
            if isinstance(evt.message, AssistantMessage):
                self.state.streaming_message = evt.message
        elif isinstance(evt, MessageUpdate):
            self.state.streaming_message = evt.message
        elif isinstance(evt, MessageEnd):
            self.state.streaming_message = None
            self.state.messages.append(evt.message)
        elif isinstance(evt, TurnEnd):
            msg = evt.message
            if isinstance(msg, AssistantMessage) and msg.error_message:
                self.state.error_message = msg.error_message
            for tool_result in evt.tool_results:
                self.state.messages.append(tool_result)
            await self._flush_pending_writes()
        elif isinstance(evt, AgentEnd):
            self.state.streaming_message = None
            await self._flush_pending_writes()
            await self._notify_listeners(Settled())

        # Track executing tool calls
        from agent_core.core.events import ToolExecutionStart, ToolExecutionEnd
        if isinstance(evt, ToolExecutionStart):
            self._pending_tool_calls.add(evt.tool_call_id)
        elif isinstance(evt, ToolExecutionEnd):
            self._pending_tool_calls.discard(evt.tool_call_id)

        for listener in list(self._listeners):
            result = listener(evt)
            if inspect.isawaitable(result):
                await result
