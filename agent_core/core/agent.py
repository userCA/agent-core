"""Stateful Agent — wraps agent_loop with subscribe/abort/state."""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Awaitable, Callable

from agent_core.core.content import ImageContent, TextContent
from agent_core.core.context import (
    AgentContext,
    AgentLoopConfig,
    AuthResolver,
    ConvertToLlm,
    TransformContext,
)
from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    TurnEnd,
)
from agent_core.core.human_input import HumanInputGate
from agent_core.core.loop import agent_loop
from agent_core.core.messages import AssistantMessage, ToolResultMessage, UserMessage
from agent_core.core.queue import PendingMessageQueue, QueueMode
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.base import ModelProvider
from agent_core.providers.message_converter import create_default_converter
from agent_core.tools.mutation_queue import FileMutationQueue

_log = logging.getLogger(__name__)

Listener = Callable[[AgentEvent], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


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

        # Hook chains — primary (constructor) + additional (registered)
        self._before_hooks: list[Any] = []
        if before_tool_call is not None:
            self._before_hooks.append(before_tool_call)
        self._after_hooks: list[Any] = []
        if after_tool_call is not None:
            self._after_hooks.append(after_tool_call)
        self._transform_hooks: list[Any] = []
        if transform_context is not None:
            self._transform_hooks.append(transform_context)

    # ---------- subscriptions ----------
    def subscribe(self, listener: Listener) -> Unsubscribe:
        self._listeners.append(listener)

        def _unsub() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _unsub

    # ---------- queues ----------
    def steer(self, message: Any) -> None:
        self._steering.enqueue(message)

    def follow_up(self, message: Any) -> None:
        self._follow_up.enqueue(message)

    def provide_human_input(self, tool_call_id: str, values: dict[str, Any]) -> bool:
        """Resume a tool that is waiting for human input.

        Returns True if the input was accepted (a pending future existed).
        """
        return self._human_input_gate.provide_input(tool_call_id, values)

    def clear_all_queues(self) -> None:
        self._steering.clear()
        self._follow_up.clear()

    @property
    def steering_mode(self) -> QueueMode:
        return self._steering.mode

    @steering_mode.setter
    def steering_mode(self, mode: QueueMode) -> None:
        self._steering.mode = mode

    @property
    def followup_mode(self) -> QueueMode:
        return self._follow_up.mode

    @followup_mode.setter
    def followup_mode(self, mode: QueueMode) -> None:
        self._follow_up.mode = mode

    # ---------- hook registration ----------
    def add_before_tool_call_hook(self, hook: Any) -> None:
        """Register a hook that runs before each tool call.

        Hooks run in registration order. A hook may return:
        - ``{"block": True, "reason": "..."}`` to prevent the tool call
        - ``{"inject_metadata": {...}}`` to inject metadata into the ToolContext
        - ``None`` to allow the call unchanged
        """
        self._before_hooks.append(hook)

    def add_after_tool_call_hook(self, hook: Any) -> None:
        """Register a hook that runs after each tool call.

        Hooks run in registration order. A hook may return
        ``{"result": {"content": [...], "details": {...}}}`` to mutate the result.
        """
        self._after_hooks.append(hook)

    def add_transform_context_hook(self, hook: Any) -> None:
        """Register a hook that transforms the LLM message list before each turn.

        Hooks run in registration order, each receiving the output of the previous.
        """
        self._transform_hooks.append(hook)

    # ---------- control ----------
    def abort(self) -> None:
        if self._abort_event is not None:
            self._abort_event.set()
        self._human_input_gate.cancel_all()

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

    # ---------- run ----------
    async def prompt(
        self,
        text_or_message: Any,
        *,
        images: list[ImageContent] | None = None,
        compact_callback: Any | None = None,
    ) -> None:
        if self._active_run is not None and not self._active_run.done():
            raise RuntimeError("Agent is already running a prompt; use steer/follow_up or wait_for_idle.")
        message = self._normalize_input(text_or_message, images)
        await self._run([message], continuation=False, compact_callback=compact_callback)

    async def continue_(self, *, compact_callback: Any | None = None) -> None:
        if self._active_run is not None and not self._active_run.done():
            raise RuntimeError("Agent is already running.")
        if not self.state.messages:
            raise RuntimeError("No messages in state to continue from.")
        last = self.state.messages[-1]
        if not isinstance(last, (UserMessage, ToolResultMessage)):
            raise RuntimeError(f"Cannot continue from message with role={getattr(last, 'role', 'unknown')}.")
        await self._run([], continuation=True, compact_callback=compact_callback)

    def _normalize_input(
        self, text_or_message: Any, images: list[ImageContent] | None
    ) -> Any:
        if isinstance(text_or_message, str):
            content: list[Any] = [TextContent(text=text_or_message)]
            if images:
                content.extend(images)
            return UserMessage(content=content, timestamp=time.time())
        return text_or_message

    async def _run(self, new_messages: list[Any], *, continuation: bool, compact_callback: Any | None = None) -> None:
        self._abort_event = asyncio.Event()
        self.state.is_streaming = True
        self.state.error_message = None

        async def _do_run() -> None:
            context = AgentContext(
                system_prompt=self.state.system_prompt,
                messages=list(self.state.messages),
                tools=list(self.state.tools),
            )

            async def auth_resolver(provider_name: str):
                return await self._auth_source.resolve(provider_name)

            config = AgentLoopConfig(
                provider=self._provider,
                model=self.state.model,
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
            )

            if continuation:
                gen = agent_loop([], context, config, self._abort_event)
            else:
                gen = agent_loop(new_messages, context, config, self._abort_event)

            try:
                async for evt in gen:
                    await self._handle_event(evt, context)
            except Exception as exc:  # pragma: no cover — last-resort
                _log.exception("Agent run failed")
                self.state.error_message = str(exc)

        task = asyncio.create_task(_do_run())
        self._active_run = task
        try:
            await task
        finally:
            self.state.is_streaming = False
            self.state.streaming_message = None
            self._active_run = None
            self._abort_event = None

    def _chain_before_hooks(self) -> Any | None:
        if not self._before_hooks:
            return None
        hooks = list(self._before_hooks)

        async def _chained(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
            merged: dict[str, Any] = {}
            for hook in hooks:
                result = hook(call_ctx)
                if inspect.isawaitable(result):
                    result = await result
                if result and result.get("block"):
                    return result
                if result and result.get("inject_metadata"):
                    merged.update(result["inject_metadata"])
            return {"inject_metadata": merged} if merged else None

        return _chained

    def _chain_after_hooks(self) -> Any | None:
        if not self._after_hooks:
            return None
        hooks = list(self._after_hooks)

        async def _chained(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
            last_result = None
            for hook in hooks:
                hook_result = hook(call_ctx)
                if inspect.isawaitable(hook_result):
                    hook_result = await hook_result
                if hook_result and hook_result.get("result"):
                    last_result = hook_result
                    hr = hook_result["result"]
                    orig = call_ctx.get("result")
                    call_ctx["result"] = type(orig)(
                        content=hr.get("content", orig.content),
                        details=hr.get("details", orig.details),
                        display=hr.get("display", orig.display),
                    )
            return last_result

        return _chained

    def _chain_transform_hooks(self) -> Any | None:
        if not self._transform_hooks:
            return None
        hooks = list(self._transform_hooks)

        async def _chained(llm_messages: list[Any], signal: Any) -> list[Any]:
            current = llm_messages
            for hook in hooks:
                result = hook(current, signal)
                if inspect.isawaitable(result):
                    current = await result
                else:
                    current = result
            return current

        return _chained

    async def _drain_steering(self) -> list[Any]:
        return self._steering.drain()

    async def _drain_follow_up(self) -> list[Any]:
        return self._follow_up.drain()

    async def _handle_event(self, evt: AgentEvent, context: AgentContext) -> None:
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
        elif isinstance(evt, AgentEnd):
            self.state.streaming_message = None

        for listener in list(self._listeners):
            result = listener(evt)
            if inspect.isawaitable(result):
                await result
