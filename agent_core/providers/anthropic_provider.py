"""Anthropic provider with thinking budgets and content-block streaming."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from agent_core.core.content import ImageContent, TextContent, ToolCallContent
from agent_core.core.messages import AssistantMessage, CustomMessage, ToolResultMessage, UserMessage
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import (
    Model,
    StreamError,
    StreamEvent,
    StreamMessageEnd,
    StreamTextDelta,
    StreamThinkingDelta,
    StreamToolCallDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)

THINKING_BUDGETS = {
    "minimal": 128,
    "low": 512,
    "medium": 1024,
    "high": 2048,
    "xhigh": 4096,
}


def _create_anthropic_converter(tool_result_max_chars: int = 4000) -> Any:
    """Build a ConvertToLlm callable that outputs Anthropic-native messages."""

    async def convert(messages: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, UserMessage):
                blocks: list[dict[str, Any]] = []
                for c in m.content:
                    if isinstance(c, TextContent):
                        blocks.append({"type": "text", "text": c.text})
                    elif isinstance(c, ImageContent):
                        blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": c.mime_type,
                                "data": c.data,
                            },
                        })
                out.append({"role": "user", "content": blocks if blocks else [{"type": "text", "text": ""}]})
            elif isinstance(m, AssistantMessage):
                blocks: list[dict[str, Any]] = []
                text = "".join(c.text for c in m.content if isinstance(c, TextContent))
                if text:
                    blocks.append({"type": "text", "text": text})
                for tc in m.content:
                    if isinstance(tc, ToolCallContent):
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                out.append({"role": "assistant", "content": blocks if blocks else [{"type": "text", "text": ""}]})
            elif isinstance(m, ToolResultMessage):
                text_parts = "".join(c.text for c in m.content if isinstance(c, TextContent))
                if len(text_parts) > tool_result_max_chars:
                    text_parts = (
                        text_parts[:tool_result_max_chars]
                        + f"\n...[truncated, {len(text_parts)} chars total]"
                    )
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id,
                    "content": text_parts,
                }
                if out and out[-1]["role"] == "user":
                    out[-1]["content"].append(result_block)
                else:
                    out.append({"role": "user", "content": [result_block]})
            elif isinstance(m, CustomMessage) and m.custom_type == "compaction_summary":
                text = m.content if isinstance(m.content, str) else str(m.content)
                out.append({
                    "role": "user",
                    "content": [{"type": "text", "text": f"[Earlier conversation summary]\n{text}"}],
                })
        return out

    return convert


def _is_anthropic_format(messages: list[dict[str, Any]]) -> bool:
    """Check if messages are already in Anthropic-native content-block format."""
    for m in messages:
        role = m.get("role")
        if role in ("user", "assistant"):
            content = m.get("content")
            if isinstance(content, list) and len(content) > 0:
                first = content[0]
                if isinstance(first, dict) and first.get("type") in (
                    "text", "image", "tool_use", "tool_result"
                ):
                    return True
            return False
    return False


class AnthropicProvider:
    name: str

    def __init__(
        self,
        *,
        base_url: str = "https://api.anthropic.com/v1",
        provider_name: str = "anthropic",
        models: list[Model] | None = None,
        timeout: float = 120.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = provider_name
        self._base_url = base_url.rstrip("/")
        self._models = models or self._default_models(provider_name)
        self._timeout = timeout
        self._client = http_client

    @staticmethod
    def _default_models(provider_name: str) -> list[Model]:
        return [
            Model(
                provider=provider_name,
                id="claude-sonnet-4-6",
                context_window=200_000,
                max_output_tokens=8192,
                supports_reasoning=True,
                supports_xhigh_thinking=True,
            ),
            Model(
                provider=provider_name,
                id="claude-opus-4-7",
                context_window=200_000,
                max_output_tokens=16384,
                supports_reasoning=True,
                supports_xhigh_thinking=True,
            ),
        ]

    def list_models(self) -> list[Model]:
        return list(self._models)

    def create_message_converter(self, tool_result_max_chars: int = 4000) -> Any:
        """Return a ConvertToLlm callable that produces Anthropic-native messages."""
        return _create_anthropic_converter(tool_result_max_chars)

    async def stream(
        self,
        *,
        model: Model,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
        thinking_level: str = "off",
        temperature: float | None = None,
        max_tokens: int | None = None,
        signal: asyncio.Event | None = None,
        auth: ProviderAuth,
    ) -> AsyncIterator[StreamEvent]:
        if _is_anthropic_format(messages):
            anthropic_msgs, system = _merge_anthropic_messages(messages, system_prompt)
        else:
            anthropic_msgs, system = _convert_messages(messages, system_prompt)
        payload = self._build_payload(
            model=model,
            messages=anthropic_msgs,
            system=system,
            tools=tools,
            thinking_level=thinking_level,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        headers = {
            "x-api-key": auth.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if auth.extra_headers:
            headers.update(auth.extra_headers)

        async for evt in self._stream_request(payload, headers, signal):
            yield evt

    def _build_payload(
        self,
        *,
        model: Model,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]],
        thinking_level: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model.id,
            "messages": messages,
            "max_tokens": max_tokens or model.max_output_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [_convert_tool_def(t) for t in tools]
        if temperature is not None:
            payload["temperature"] = temperature
        if thinking_level != "off" and model.supports_reasoning:
            budget = THINKING_BUDGETS.get(thinking_level, 1024)
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": budget,
            }
        return payload

    async def _stream_request(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        signal: asyncio.Event | None,
    ) -> AsyncIterator[StreamEvent]:
        url = f"{self._base_url}/messages"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    body_text = body.decode("utf-8", errors="replace")
                    retryable = resp.status_code in (429, 500, 502, 503, 504)
                    from agent_core.providers.openai_provider import _is_context_overflow
                    overflow = _is_context_overflow(resp.status_code, body_text)
                    yield StreamError(
                        message=f"HTTP {resp.status_code}: {body_text}",
                        retryable=retryable,
                        overflow=overflow,
                    )
                    return
                async for evt in self._parse_sse(resp, signal):
                    yield evt
        finally:
            if owns_client:
                await client.aclose()

    async def _parse_sse(
        self, resp: httpx.Response, signal: asyncio.Event | None
    ) -> AsyncIterator[StreamEvent]:
        tool_buffers: dict[str, dict[str, Any]] = {}
        started_tools: set[str] = set()
        index_to_tool: dict[int, str] = {}

        async for raw_line in resp.aiter_lines():
            if signal is not None and signal.is_set():
                break
            line = raw_line.strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue

            evt_type = event.get("type")
            if evt_type == "message_start":
                usage = event.get("message", {}).get("usage", {})
                if usage:
                    pass  # input_tokens available; we emit at message_end
            elif evt_type == "content_block_start":
                block = event.get("content_block", {})
                idx = event.get("index", 0)
                if block.get("type") == "tool_use":
                    tid = block.get("id", "")
                    name = block.get("name", "")
                    tool_buffers[tid] = {"id": tid, "name": name, "args": ""}
                    index_to_tool[idx] = tid
                    if tid not in started_tools:
                        started_tools.add(tid)
                        yield StreamToolCallStart(id=tid, name=name)
            elif evt_type == "content_block_delta":
                delta = event.get("delta", {})
                d_type = delta.get("type")
                if d_type == "text_delta":
                    yield StreamTextDelta(text=delta.get("text", ""))
                elif d_type == "thinking_delta":
                    yield StreamThinkingDelta(text=delta.get("thinking", ""))
                elif d_type == "input_json_delta":
                    tid = index_to_tool.get(event.get("index", 0))
                    if tid and tid in tool_buffers:
                        tool_buffers[tid]["args"] += delta.get("partial_json", "")
            elif evt_type == "message_delta":
                delta = event.get("delta", {})
                usage = event.get("usage", {})
                stop_reason = delta.get("stop_reason", "stop")
                if stop_reason == "tool_use":
                    stop_reason = "tool_use"
                yield StreamMessageEnd(
                    stop_reason=stop_reason,
                    input_tokens=0,
                    output_tokens=usage.get("output_tokens", 0),
                )
            elif evt_type == "message_stop":
                for buf in tool_buffers.values():
                    if buf["id"] and buf["name"] and buf["id"] not in started_tools:
                        continue
                    try:
                        args = json.loads(buf["args"]) if buf["args"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    yield StreamToolCallEnd(id=buf["id"], arguments=args)


def _convert_tool_def(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool.get("function", {}).get("name", tool.get("name", "")),
        "description": tool.get("function", {}).get("description", tool.get("description", "")),
        "input_schema": tool.get("function", {}).get("parameters", tool.get("parameters", {})),
    }


def _convert_messages(
    messages: list[dict[str, Any]], system_prompt: str
) -> tuple[list[dict[str, Any]], str]:
    """Convert OpenAI-format messages to Anthropic format.

    Returns (anthropic_messages, system_text).
    """
    system = system_prompt
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            text = _extract_text(msg.get("content"))
            if text:
                system = text
            continue
        if role == "user":
            content = _to_anthropic_content(msg.get("content"))
            out.append({"role": "user", "content": content})
        elif role == "assistant":
            content = _assistant_to_anthropic(msg)
            out.append({"role": "assistant", "content": content})
        elif role == "tool":
            # Attach tool_result to previous user message if possible
            result = {
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id", ""),
                "content": _extract_text(msg.get("content")),
            }
            if out and out[-1]["role"] == "user":
                out[-1]["content"].append(result)
            else:
                out.append({"role": "user", "content": [result]})

    # Merge consecutive same-role messages
    merged: list[dict[str, Any]] = []
    for m in out:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"].extend(m["content"])
        else:
            merged.append(m)
    return merged, system


def _merge_anthropic_messages(
    messages: list[dict[str, Any]], system_prompt: str
) -> tuple[list[dict[str, Any]], str]:
    """Merge consecutive same-role messages when already in Anthropic format."""
    system = system_prompt
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            text = _extract_text(msg.get("content"))
            if text:
                system = text
            continue
        if role in ("user", "assistant"):
            out.append({"role": role, "content": list(msg.get("content", []))})

    # Merge consecutive same-role messages
    merged: list[dict[str, Any]] = []
    for m in out:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"].extend(m["content"])
        else:
            merged.append(m)
    return merged, system


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
            elif isinstance(c, str):
                parts.append(c)
        return "".join(parts)
    return ""


def _to_anthropic_content(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        out: list[dict[str, Any]] = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    out.append({"type": "text", "text": c.get("text", "")})
                elif c.get("type") == "image_url":
                    url = c.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        media_type, b64 = _split_data_url(url)
                        out.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64,
                                },
                            }
                        )
                else:
                    out.append(c)
            elif isinstance(c, str):
                out.append({"type": "text", "text": c})
        return out if out else [{"type": "text", "text": ""}]
    return [{"type": "text", "text": str(content)}]


def _assistant_to_anthropic(msg: dict[str, Any]) -> list[dict[str, Any]]:
    content = msg.get("content")
    out: list[dict[str, Any]] = []
    text = _extract_text(content)
    if text:
        out.append({"type": "text", "text": text})
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except json.JSONDecodeError:
            args = {}
        out.append(
            {
                "type": "tool_use",
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "input": args,
            }
        )
    return out if out else [{"type": "text", "text": ""}]


def _split_data_url(url: str) -> tuple[str, str]:
    # data:image/png;base64,ABC...
    after_prefix = url[5:]  # strip "data:"
    media_type, rest = after_prefix.split(";", 1)
    _, b64 = rest.split(",", 1)
    return media_type, b64
