"""Shared test helpers."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Callable

from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import Model, StreamEvent
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore


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


async def make_harness(
    *,
    provider: FakeProvider | None = None,
    session_id: str = "test",
    initial_state: AgentState | None = None,
    store: InMemoryStore | None = None,
    **kwargs: Any,
) -> AgentHarness:
    """Create a started AgentHarness for tests."""
    provider = provider or FakeProvider()
    store = store or InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id=session_id,
        initial_state=initial_state or AgentState(model=fake_model()),
        **kwargs,
    )
    await harness.start()
    return harness


def run_harness(coro: Callable[..., Any]) -> Any:
    return asyncio.run(coro())
