"""Scene-layer smoke tests: ChatAssistant + AgentHarness without live LLM."""

from __future__ import annotations

import tempfile
from typing import Any

import pytest

from agent_core.core.events import AgentEnd, MessageUpdate, TextDelta
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.core.state import AgentState
from scene.http_sse.chat_assistant import ChatAssistant
from tests.conftest import FakeProvider, fake_model


@pytest.mark.asyncio
async def test_chat_assistant_wires_agent_harness():
    """ChatAssistant.create builds and starts an AgentHarness-backed runtime."""
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="pong"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    with tempfile.TemporaryDirectory() as tmp:
        harness = AgentHarness(
            provider=provider,
            auth_source=AuthSource.static(api_key="fake"),
            store=InMemoryStore(),
            session_id="scene-smoke",
            initial_state=AgentState(model=fake_model(), system_prompt="test"),
        )
        assistant = ChatAssistant(harness=harness, cwd=tmp)
        await assistant.start()

        assert isinstance(assistant.harness, AgentHarness)
        events: list[Any] = []

        async def capture(evt: Any) -> None:
            events.append(evt)

        assistant.on_event(capture)
        await assistant.send_message("ping")

        assert any(isinstance(e, MessageUpdate) for e in events)
        assert any(isinstance(e, AgentEnd) for e in events)
        assert assistant.harness.state.messages[-1].role == "assistant"
        await assistant.dispose()
