"""Stateful Agent — wraps agent_loop with subscribe/abort/state."""

from __future__ import annotations

import asyncio
import inspect
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
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
)
from agent_core.core.loop import agent_loop, agent_loop_continue
from agent_core.core.messages import AssistantMessage, UserMessage
from agent_core.core.queue import PendingMessageQueue, QueueMode
from agent_core.core.state import AgentState, ThinkingLevel
from agent_core.providers.auth import AuthSource
from agent_core.providers.base import ModelProvider

Listener = Callable[[AgentEvent], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


def _default_convert_to_llm() -> ConvertToLlm:
    async def convert(messages: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            role = getattr(m, "role", None)
            if role == "user":
                content = _user_content_to_openai(m.content)
                out.append({"role": "user", "content": content})
            elif role == "assistant":
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": "".join(c.text for c in m.content if getattr(c, "type", None) == "text"),
                }
                tool_calls = [c for c in m.content if getattr(c, "type", None) == "tool_call"]
                if tool_calls:
                    import json as _json

                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": _json.dumps(tc.arguments)},
                        }
                        for tc in tool_calls
                    ]
                out.append(msg)
            elif role == "tool_result":
                text_parts = "".join(
                    c.text for c in m.content if getattr(c, "type", None) == "text"
                )
                out.append(
                    {"role": "tool", "tool_call_id": m.tool_call_id, "content": text_parts}
                )
        return out

    return convert


def _user_content_to_openai(content: list[Any]) -> Any:
    parts: list[dict[str, Any]] = []
    only_text = True
    for c in content:
        t = getattr(c, "type", None) or (c.get("type") if isinstance(c, dict) else None)
        if t == "text":
            text = getattr(c, "text", None) or c.get("text", "")
            parts.append({"type": "text", "text": text})
        elif t == "image":
            data = getattr(c, "data", None) or c.get("data")
            mime = getattr(c, "mime_type", None) or c.get("mime_type", "image/png")
            parts.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
            )
            only_text = False
    if only_text:
        return "".join(p["text"] for p in parts)
    return parts


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
        steering_mode: QueueMode = "one-at-a-time",
        followup_mode: QueueMode = "one-at-a-time",
    ) -> None:
        self.state: AgentState = initial_state or AgentState()
        self._provider = provider
        self._auth_source = auth_source
        self._convert_to_llm = convert_to_llm or _default_convert_to_llm()
        self._transform_context = transform_context
        self._tool_registry = tool_registry
        self._before_tool_call = before_tool_call
        self._after_tool_call = after_tool_call
        self._tool_execution = tool_execution
        self._steering = PendingMessageQueue(steering_mode)
        self._follow_up = PendingMessageQueue(followup_mode)
        self._listeners: list[Listener] = []
        self._active_run: asyncio.Task | None = None
        self._abort_event: asyncio.Event | None = None

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

    # ---------- control ----------
    def abort(self) -> None:
        if self._abort_event is not None:
            self._abort_event.set()

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
    ) -> None:
        if self._active_run is not None and not self._active_run.done():
            raise RuntimeError("Agent is already running a prompt; use steer/follow_up or wait_for_idle.")
        message = self._normalize_input(text_or_message, images)
        await self._run([message], continuation=False)

    async def continue_(self) -> None:
        if self._active_run is not None and not self._active_run.done():
            raise RuntimeError("Agent is already running.")
        if not self.state.messages:
            raise RuntimeError("No messages in state to continue from.")
        last = self.state.messages[-1]
        role = getattr(last, "role", None)
        if role not in ("user", "tool_result"):
            raise RuntimeError(f"Cannot continue from message with role={role}.")
        await self._run([], continuation=True)

    def _normalize_input(
        self, text_or_message: Any, images: list[ImageContent] | None
    ) -> Any:
        if isinstance(text_or_message, str):
            content: list[Any] = [TextContent(text=text_or_message)]
            if images:
                content.extend(images)
            return UserMessage(content=content, timestamp=time.time())
        return text_or_message

    async def _run(self, new_messages: list[Any], *, continuation: bool) -> None:
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
                transform_context=self._transform_context,
                thinking_level=self.state.thinking_level,
                tool_execution=self._tool_execution,
                tool_registry=self._tool_registry,
                before_tool_call=self._before_tool_call,
                after_tool_call=self._after_tool_call,
                get_steering_messages=self._drain_steering,
                get_follow_up_messages=self._drain_follow_up,
            )

            if continuation:
                gen = agent_loop_continue(context, config, self._abort_event)
            else:
                gen = agent_loop(new_messages, context, config, self._abort_event)

            try:
                async for evt in gen:
                    await self._handle_event(evt, context)
            except Exception as exc:  # pragma: no cover — last-resort
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

    async def _drain_steering(self) -> list[Any]:
        return self._steering.drain()

    async def _drain_follow_up(self) -> list[Any]:
        return self._follow_up.drain()

    async def _handle_event(self, evt: AgentEvent, context: AgentContext) -> None:
        if isinstance(evt, MessageStart):
            if getattr(evt.message, "role", None) == "assistant":
                self.state.streaming_message = evt.message
        elif isinstance(evt, MessageUpdate):
            self.state.streaming_message = evt.message
        elif isinstance(evt, MessageEnd):
            self.state.streaming_message = None
            self.state.messages.append(evt.message)
        elif isinstance(evt, ToolExecutionStart):
            self.state.pending_tool_calls.add(evt.tool_call_id)
        elif isinstance(evt, ToolExecutionEnd):
            self.state.pending_tool_calls.discard(evt.tool_call_id)
        elif isinstance(evt, TurnEnd):
            msg = evt.message
            if getattr(msg, "role", None) == "assistant" and getattr(msg, "error_message", None):
                self.state.error_message = msg.error_message
        elif isinstance(evt, AgentEnd):
            self.state.streaming_message = None

        for listener in list(self._listeners):
            result = listener(evt)
            if inspect.isawaitable(result):
                await result
