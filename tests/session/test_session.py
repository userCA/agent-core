import pytest

from agent_core.core.agent import Agent
from agent_core.core.errors import AgentHarnessError
from agent_core.core.events import MessageEnd, TextDelta, MessageUpdate, AgentEnd
from agent_core.core.messages import UserMessage
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamTextDelta, StreamMessageEnd
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.session import AgentSession
from tests.conftest import FakeProvider, fake_model


@pytest.mark.asyncio
async def test_session_start_creates_store_entry():
    provider = FakeProvider()
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        initial_state=AgentState(model=fake_model()),
    )
    store = InMemoryStore()
    session = AgentSession(agent=agent, store=store, session_id="s1")

    await session.start()

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
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        initial_state=AgentState(model=fake_model()),
    )
    store = InMemoryStore()
    session = AgentSession(agent=agent, store=store, session_id="s2")
    await session.start()

    await session.prompt("hi")

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
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        initial_state=AgentState(model=fake_model()),
    )
    store = InMemoryStore()
    session = AgentSession(agent=agent, store=store, session_id="s3")
    await session.start()

    events = []
    session.subscribe(lambda e: events.append(e.type))

    await session.prompt("hello")

    assert "agent_start" in events
    assert "agent_end" in events


@pytest.mark.asyncio
async def test_session_dispose_prevents_prompt():
    provider = FakeProvider()
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        initial_state=AgentState(model=fake_model()),
    )
    store = InMemoryStore()
    session = AgentSession(agent=agent, store=store, session_id="s4")
    await session.start()
    await session.dispose()

    with pytest.raises(AgentHarnessError, match="disposed"):
        await session.prompt("x")


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
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        initial_state=AgentState(model=fake_model()),
    )
    store = InMemoryStore()
    session = AgentSession(agent=agent, store=store, session_id="s5")
    await session.start()

    await session.prompt("test")

    assert len(session.messages) == 2
    assert session.messages[0].role == "user"
    assert session.messages[1].role == "assistant"
