"""Shared test helpers."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Callable

from agent_core.providers.types import Model, StreamEvent


class FakeProvider:
    """Test double for ModelProvider.

    Each call to `stream` consumes one scripted event sequence in order.
    """

    name = "fake"

    def __init__(self, scripts: list[list[StreamEvent]] | None = None) -> None:
        self._scripts: list[list[StreamEvent]] = scripts or []
        self.calls: list[dict[str, Any]] = []

    def list_models(self) -> list[Model]:
        return [Model(provider="fake", id="fake-1", context_window=4096, max_output_tokens=1024)]

    def queue_script(self, events: list[StreamEvent]) -> None:
        self._scripts.append(events)

    async def stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        self.calls.append(kwargs)
        events = self._scripts.pop(0) if self._scripts else []
        for e in events:
            await asyncio.sleep(0)
            yield e


def fake_model() -> Model:
    return Model(provider="fake", id="fake-1", context_window=4096, max_output_tokens=1024)
