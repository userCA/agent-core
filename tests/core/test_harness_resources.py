"""Harness resources snapshot / set_resources semantics."""

from __future__ import annotations

import pytest

from agent_core.core.events import ResourcesUpdate
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from tests.conftest import FakeProvider, fake_model


@pytest.mark.asyncio
async def test_set_resources_emits_update_and_snapshots():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=InMemoryStore(),
        session_id="res",
        initial_state=AgentState(model=fake_model()),
    )
    events: list[str] = []

    async def on_evt(evt):
        events.append(evt.type)

    harness.subscribe(on_evt)
    await harness.start()

    skill = {"name": "demo", "description": "d", "content": "c"}
    await harness.set_resources({"skills": [skill], "prompt_templates": []})
    assert "resources_update" in events
    got = harness.get_resources()
    assert len(got["skills"]) == 1
    assert got["skills"][0]["name"] == "demo"

    snap = harness.create_turn_snapshot()
    assert snap.resources["skills"][0]["name"] == "demo"
    assert snap.session_id == "res"

    got["skills"].clear()
    assert len(harness.get_resources()["skills"]) == 1

    await harness.prompt("hi")
    await harness.set_resources({"skills": [], "prompt_templates": [{"name": "t"}]})
    assert harness.get_resources()["prompt_templates"][0]["name"] == "t"


@pytest.mark.asyncio
async def test_resources_update_carries_previous():
    harness = AgentHarness(
        provider=FakeProvider(),
        auth_source=AuthSource.static(api_key="fake"),
        store=InMemoryStore(),
        session_id="res2",
        initial_state=AgentState(model=fake_model()),
    )
    seen: list[ResourcesUpdate] = []

    async def on_evt(evt):
        if isinstance(evt, ResourcesUpdate):
            seen.append(evt)

    harness.subscribe(on_evt)
    await harness.start()
    await harness.set_resources({"skills": [{"name": "a"}], "prompt_templates": []})
    await harness.set_resources({"skills": [{"name": "b"}], "prompt_templates": []})

    assert len(seen) == 2
    assert seen[1].previous_resources["skills"][0]["name"] == "a"
    assert seen[1].resources["skills"][0]["name"] == "b"
