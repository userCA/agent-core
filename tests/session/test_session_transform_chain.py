from agent_core.core.agent import Agent
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.session import AgentSession
from tests.conftest import FakeProvider, fake_model


class _CaptureExt:
    name = "capture"

    def __init__(self, marker: str) -> None:
        self.marker = marker

    async def on_event(self, ctx, evt): ...
    async def on_before_tool_call(self, ctx, call): return None
    async def on_after_tool_call(self, ctx, call, result, is_error): return None

    async def transform_context(self, llm_messages, signal=None):
        return [{"role": "system", "content": f"[{self.marker}]"}, *llm_messages]


async def test_extension_transform_context_injects_before_provider():
    provider = FakeProvider()
    provider.queue_script([StreamTextDelta(text="ok"), StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1)])
    agent = Agent(provider=provider, auth_source=AuthSource.static(api_key="k"), initial_state=AgentState(system_prompt="sys", model=fake_model()))

    session = AgentSession(agent=agent, store=InMemoryStore(), session_id="s1", extensions=[_CaptureExt(marker="MEM")])
    await session.start()
    await session.prompt("hello")

    sent = provider.calls[0]["messages"]
    assert sent[0] == {"role": "system", "content": "[MEM]"}
    assert any(m.get("role") == "user" for m in sent)


async def test_multiple_extensions_compose_left_to_right():
    provider = FakeProvider()
    provider.queue_script([StreamTextDelta(text="ok"), StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1)])
    agent = Agent(provider=provider, auth_source=AuthSource.static(api_key="k"), initial_state=AgentState(system_prompt="sys", model=fake_model()))

    session = AgentSession(agent=agent, store=InMemoryStore(), session_id="s1", extensions=[_CaptureExt(marker="A"), _CaptureExt(marker="B")])
    await session.start()
    await session.prompt("hi")

    sent = provider.calls[0]["messages"]
    # Extensions are applied in registration order: A wraps first, then B wraps A's output,
    # so B's injection ends up closest to the top (sent[0]) — i.e. nearest to the model.
    assert sent[0]["content"] == "[B]"
    assert sent[1]["content"] == "[A]"
