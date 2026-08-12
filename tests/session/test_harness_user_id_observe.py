import pytest

from agent_core.core.events import AgentStart
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from tests.conftest import FakeProvider, fake_model


def _make_harness(session_id: str = "s-user", user_id: str = "") -> tuple[AgentHarness, FakeProvider]:
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
    harness = AgentHarness(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=InMemoryStore(),
        session_id=session_id,
        initial_state=AgentState(model=fake_model()),
    )
    if user_id:
        harness.observability_user_id = user_id
    return harness, provider


@pytest.mark.asyncio
async def test_harness_prompt_propagates_user_id_to_loop_config(monkeypatch):
    captured: dict[str, str] = {}

    import agent_core.session.harness as harness_module

    original = harness_module.build_loop_config

    def _capture_build_loop_config(host, **kwargs):
        config = original(host, **kwargs)
        captured["user_id"] = config.user_id
        return config

    monkeypatch.setattr(harness_module, "build_loop_config", _capture_build_loop_config)

    harness, _ = _make_harness(user_id="u-harness")
    await harness.start()
    await harness.prompt("hi")

    assert captured["user_id"] == "u-harness"


@pytest.mark.asyncio
async def test_harness_prompt_still_emits_run_id():
    harness, _ = _make_harness("s-run-user")
    await harness.start()

    events: list = []
    harness.subscribe(lambda e: events.append(e))

    await harness.prompt("hi")

    agent_starts = [e for e in events if isinstance(e, AgentStart)]
    assert len(agent_starts) == 1
    assert agent_starts[0].run_id.startswith("run-")
