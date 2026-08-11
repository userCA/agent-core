import pytest

from agent_core.core.events import AgentStart
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.session.harness import AgentHarness
from agent_core.session.inmemory_store import InMemoryStore
from tests.conftest import FakeProvider, fake_model


def _make_harness(session_id: str = "s-run") -> tuple[AgentHarness, FakeProvider]:
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
    return harness, provider


@pytest.mark.asyncio
async def test_harness_prompt_emits_agent_start_with_run_id():
    harness, _ = _make_harness("s-run-1")
    await harness.start()

    events: list = []
    harness.subscribe(lambda e: events.append(e))

    await harness.prompt("hi")

    agent_starts = [e for e in events if isinstance(e, AgentStart)]
    assert len(agent_starts) == 1
    run_id = agent_starts[0].run_id
    assert run_id.startswith("run-")
    assert len(run_id) == len("run-") + 12


@pytest.mark.asyncio
async def test_harness_prompt_run_ids_differ_across_turns():
    harness, provider = _make_harness("s-run-2")
    provider.queue_script([
        StreamTextDelta(text="one"),
        StreamMessageEnd(
            usage={"input_tokens": 1, "output_tokens": 1},
            stop_reason="stop",
            provider="fake",
            model="fake-1",
        ),
    ])
    provider.queue_script([
        StreamTextDelta(text="two"),
        StreamMessageEnd(
            usage={"input_tokens": 1, "output_tokens": 1},
            stop_reason="stop",
            provider="fake",
            model="fake-1",
        ),
    ])
    await harness.start()

    run_ids: list[str] = []

    def _capture(evt) -> None:
        if isinstance(evt, AgentStart):
            run_ids.append(evt.run_id)

    harness.subscribe(_capture)

    await harness.prompt("first")
    await harness.prompt("second")

    assert len(run_ids) == 2
    assert run_ids[0] != run_ids[1]


@pytest.mark.asyncio
async def test_harness_uses_pregenerated_run_id(monkeypatch):
    fixed_run_id = "run-fixed123456"
    monkeypatch.setattr(
        "agent_core.observability.generate_run_id",
        lambda: fixed_run_id,
    )

    harness, _ = _make_harness("s-run-3")
    await harness.start()

    events: list = []
    harness.subscribe(lambda e: events.append(e))

    await harness.prompt("hi")

    agent_starts = [e for e in events if isinstance(e, AgentStart)]
    assert len(agent_starts) == 1
    assert agent_starts[0].run_id == fixed_run_id


@pytest.mark.asyncio
async def test_remove_before_tool_call_hook_unsubscribes_one_handler():
    harness, _ = _make_harness("s-hook-1")

    async def hook(_call_ctx):
        return None

    harness.add_before_tool_call_hook(hook)
    harness.add_before_tool_call_hook(hook)

    handlers = harness.hooks._handlers.get("tool_call", [])
    assert len(handlers) == 2

    harness.remove_before_tool_call_hook(hook)

    handlers = harness.hooks._handlers.get("tool_call", [])
    assert len(handlers) == 1


@pytest.mark.asyncio
async def test_remove_after_tool_call_hook_unsubscribes_one_handler():
    harness, _ = _make_harness("s-hook-2")

    async def hook(_call_ctx):
        return None

    harness.add_after_tool_call_hook(hook)
    harness.add_after_tool_call_hook(hook)

    handlers = harness.hooks._handlers.get("tool_result", [])
    assert len(handlers) == 2

    harness.remove_after_tool_call_hook(hook)

    handlers = harness.hooks._handlers.get("tool_result", [])
    assert len(handlers) == 1
