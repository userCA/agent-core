"""ModelProvider Protocol — all LLM adapters implement this."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import Model, StreamEvent


def tools_to_provider_format(tools: list[Any]) -> list[dict[str, Any]]:
    """Convert tool definitions (dict or Pydantic model) to OpenAI function-calling format."""
    out: list[dict[str, Any]] = []
    for t in tools:
        if isinstance(t, dict):
            out.append(_definition_to_openai(t))
        elif hasattr(t, "model_dump"):
            out.append(_definition_to_openai(t.model_dump()))
        elif hasattr(t, "definition"):
            definition = t.definition
            if hasattr(definition, "model_dump"):
                out.append(_definition_to_openai(definition.model_dump()))
            elif isinstance(definition, dict):
                out.append(_definition_to_openai(definition))
    return out


def _definition_to_openai(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": d["name"],
            "description": d.get("description", ""),
            "parameters": d.get("parameters", {"type": "object", "properties": {}}),
        },
    }


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
