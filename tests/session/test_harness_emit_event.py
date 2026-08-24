"""Tests for AgentHarness.emit_event — external events reach extensions + subscribers."""

import pytest

from agent_core.core.events import SkillStart
from agent_core.core.state import AgentState
from agent_core.extensions.base import Extension
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore


class _CapExtension(Extension):
    name = "cap"

    def __init__(self) -> None:
        self.types: list[str] = []

    async def on_event(self, ctx, evt) -> None:
        self.types.append(getattr(evt, "type", None))


@pytest.mark.asyncio
async def test_emit_event_reaches_extension_and_subscriber():
    cap = _CapExtension()
    harness = AgentHarness(
        provider=object(),
        auth_source=object(),
        store=InMemoryStore(),
        session_id="s1",
        initial_state=AgentState(system_prompt="", model=None, tools=[]),
        extensions=[cap],
    )
    await harness.start()
    seen: list[str] = []
    harness.subscribe(lambda e: seen.append(e.type))
    await harness.emit_event(SkillStart(skill_name="demo", skill_description="d"))
    assert "skill_start" in cap.types
    assert "skill_start" in seen
