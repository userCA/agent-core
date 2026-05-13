"""ModelProvider Protocol — all LLM adapters implement this."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import Model, StreamEvent


@runtime_checkable
class ModelProvider(Protocol):
    name: str

    def list_models(self) -> list[Model]: ...

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
    ) -> AsyncIterator[StreamEvent]: ...
