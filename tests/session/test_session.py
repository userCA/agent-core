import pytest

from agent_core.core.errors import AgentHarnessError
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamTextDelta, StreamMessageEnd
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from tests.conftest import FakeProvider, fake_model


@pytest.mark.asyncio
async def test_session_start_creates_store_entry():
    provider = FakeProvider()
    store = InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id="s1",
        initial_state=AgentState(model=fake_model()),
    )

    await harness.start()

    sessions = await store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].session_id == "s1"


@pytest.mark.asyncio
async def test_session_prompt_persists_messages():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="hello"),
        StreamMessageEnd(
            usage={"input_tokens": 1, "output_tokens": 1},
            stop_reason="stop",
            provider="fake",
            model="fake-1",
        ),
    ])
    store = InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id="s2",
        initial_state=AgentState(model=fake_model()),
    )
    await harness.start()

    await harness.prompt("hi")

    snap = await store.load_session("s2")
    assert len(snap.entries) == 2  # user message + assistant message


@pytest.mark.asyncio
async def test_session_subscribe_receives_events():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="hi"),
        StreamMessageEnd(
            usage={"input_tokens": 1, "output_tokens": 1},
            stop_reason="stop",
            provider="fake",
            model="fake-1",
        ),
    ])
    store = InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id="s3",
        initial_state=AgentState(model=fake_model()),
    )
    await harness.start()

    events = []
    harness.subscribe(lambda e: events.append(e.type))

    await harness.prompt("hello")

    assert "agent_start" in events
    assert "agent_end" in events


@pytest.mark.asyncio
async def test_session_dispose_prevents_prompt():
    provider = FakeProvider()
    store = InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id="s4",
        initial_state=AgentState(model=fake_model()),
    )
    await harness.start()
    await harness.dispose()

    with pytest.raises(AgentHarnessError, match="disposed"):
        await harness.prompt("x")


@pytest.mark.asyncio
async def test_session_messages_property():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(
            usage={"input_tokens": 1, "output_tokens": 1},
            stop_reason="stop",
            provider="fake",
            model="fake-1",
        ),
    ])
    store = InMemoryStore()
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        session_id="s5",
        initial_state=AgentState(model=fake_model()),
    )
    await harness.start()

    await harness.prompt("test")

    assert len(harness.messages) == 2
    assert harness.messages[0].role == "user"
    assert harness.messages[1].role == "assistant"
