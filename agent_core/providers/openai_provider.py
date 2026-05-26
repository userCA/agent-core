"""OpenAI / OpenAI-compatible provider with httpx SSE streaming."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import (
    Model,
    StreamError,
    StreamEvent,
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)


def _is_context_overflow(status_code: int, body: str) -> bool:
    """Detect context window overflow from HTTP error responses."""
    lower = body.lower()
    keywords = (
        "context_length_exceeded",
        "maximum context length",
        "reduce the length of the messages",
        "too long",
        "token limit",
        "prompt is too long",
        "exceeds the maximum",
    )
    return any(kw in lower for kw in keywords)


class OpenAIProvider:
    name: str

    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        provider_name: str = "openai",
        models: list[Model] | None = None,
        timeout: float = 60.0,
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
                id="gpt-4o",
                context_window=128_000,
                max_output_tokens=4096,
            ),
            Model(
                provider=provider_name,
                id="gpt-4o-mini",
                context_window=128_000,
                max_output_tokens=16_384,
            ),
        ]

    def list_models(self) -> list[Model]:
        return list(self._models)

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
        payload = self._build_payload(
            model=model,
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            thinking_level=thinking_level,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        headers = {
            "Authorization": f"Bearer {auth.api_key}",
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
        tools: list[dict[str, Any]],
        system_prompt: str,
        thinking_level: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        msgs: list[dict[str, Any]] = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)
        payload: dict[str, Any] = {
            "model": model.id,
            "messages": msgs,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if thinking_level != "off" and model.supports_reasoning:
            payload["reasoning_effort"] = thinking_level
        return payload

    async def _stream_request(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        signal: asyncio.Event | None,
    ) -> AsyncIterator[StreamEvent]:
        url = f"{self._base_url}/chat/completions"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    body_text = body.decode("utf-8", errors="replace")
                    retryable = resp.status_code in (429, 500, 502, 503, 504)
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
        tool_calls: dict[int, dict[str, Any]] = {}
        started_tools: set[str] = set()

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

            choices = event.get("choices") or []
            if not choices:
                usage = event.get("usage")
                if usage:
                    yield StreamMessageEnd(
                        stop_reason="stop",
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                    )
                continue

            choice = choices[0]
            delta = choice.get("delta") or {}

            text = delta.get("content")
            if text:
                yield StreamTextDelta(text=text)

            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = tool_calls.setdefault(idx, {"id": None, "name": None, "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]
                if slot["id"] and slot["name"] and slot["id"] not in started_tools:
                    started_tools.add(slot["id"])
                    yield StreamToolCallStart(id=slot["id"], name=slot["name"])

            finish = choice.get("finish_reason")
            if finish:
                for slot in tool_calls.values():
                    if slot["id"] and slot["name"]:
                        try:
                            args = json.loads(slot["args"]) if slot["args"] else {}
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamToolCallEnd(id=slot["id"], arguments=args)
                usage = event.get("usage") or {}
                yield StreamMessageEnd(
                    stop_reason=finish,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                )
