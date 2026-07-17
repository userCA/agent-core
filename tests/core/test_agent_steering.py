import asyncio

import pytest

from agent_core.core.errors import AgentHarnessError
from agent_core.core.messages import UserMessage
from agent_core.core.state import AgentState
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta

from tests.conftest import FakeProvider, fake_model, make_harness


def test_next_turn_message_runs_before_prompt():
    """next_turn inserts before the user message on the next prompt."""
    provider = FakeProvider()
    provider.queue_script(
        [
            StreamTextDelta(text="ok"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ]
    )

    async def run():
        harness = await make_harness(
            provider=provider,
            initial_state=AgentState(model=fake_model()),
        )
        await harness.next_turn(UserMessage(content=[{"type": "text", "text": "next"}], timestamp=0.0))
        await harness.prompt("first")
        user_msgs = [m for m in harness.state.messages if getattr(m, "role", None) == "user"]
        assert len(user_msgs) >= 2
        assert user_msgs[0].content[0].text == "next"
        assert user_msgs[1].content[0].text == "first"

    asyncio.run(run())


def test_idle_steer_rejected():
    async def run():
        harness = await make_harness(initial_state=AgentState(model=fake_model()))
        with pytest.raises(AgentHarnessError) as ei:
            await harness.steer(UserMessage(content=[{"type": "text", "text": "a"}], timestamp=0.0))
        assert ei.value.code == "invalid_state"

    asyncio.run(run())


def test_clear_all_queues_keeps_next_turn():
    async def run():
        harness = await make_harness(initial_state=AgentState(model=fake_model()))
        await harness.next_turn(UserMessage(content=[{"type": "text", "text": "b"}], timestamp=0.0))
        harness.clear_all_queues()
        assert harness._next_turn.item_count == 1
        assert harness._steering.item_count == 0
        assert harness._follow_up.item_count == 0

    asyncio.run(run())
