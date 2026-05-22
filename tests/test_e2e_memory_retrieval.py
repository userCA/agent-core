from agent_core.core.agent import Agent
from agent_core.core.state import AgentState
from agent_core.memory.adapters.inmemory import InMemoryMemoryStore
from agent_core.memory.extension import MemoryExtension
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.extension import AutoRetrievalExtension
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.session import AgentSession
from tests.conftest import FakeProvider, fake_model


async def test_scene_assembled_rag_and_memory():
    retriever = InMemoryRetriever()
    retriever.add("Mars has two moons: Phobos and Deimos.", source="astronomy")

    memory_store = InMemoryMemoryStore()
    await memory_store.remember(session_id="sess-x", text="User is a planetary science researcher who studies Mars.")

    provider = FakeProvider()
    provider.queue_script([StreamTextDelta(text="Phobos and Deimos."), StreamMessageEnd(stop_reason="stop", input_tokens=10, output_tokens=4)])
    agent = Agent(provider=provider, auth_source=AuthSource.static(api_key="k"), initial_state=AgentState(system_prompt="You answer concisely.", model=fake_model()))

    session = AgentSession(
        agent=agent, store=InMemoryStore(), session_id="sess-x",
        extensions=[
            AutoRetrievalExtension(retriever=retriever, top_k=3),
            MemoryExtension(store=memory_store, session_id="sess-x", top_k=3),
        ],
    )
    await session.start()
    await session.prompt("How many moons does Mars have?")

    sent = provider.calls[0]["messages"]
    system_contents = [m["content"] for m in sent if m["role"] == "system"]
    assert any("Phobos and Deimos" in s for s in system_contents)
    assert any("planetary science researcher" in s for s in system_contents)

    recs = await memory_store.recall(session_id="sess-x", query="any", limit=10)
    assert any("How many moons does Mars have?" in r.text for r in recs)
