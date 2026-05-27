import asyncio

from agent_core.core.agent import Agent
from agent_core.core.messages import UserMessage
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta

from tests.conftest import FakeProvider, fake_model


def test_follow_up_message_runs_after_first_turn():
    provider = FakeProvider()
    provider.queue_script(
        [
            StreamTextDelta(text="first"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ]
    )
    provider.queue_script(
        [
            StreamTextDelta(text="second"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )

    async def run():
        agent.follow_up(UserMessage(content=[{"type": "text", "text": "next"}], timestamp=0.0))
        await agent.prompt("first")

    asyncio.run(run())
    user_msgs = [m for m in agent.state.messages if getattr(m, "role", None) == "user"]
    assistant_msgs = [m for m in agent.state.messages if getattr(m, "role", None) == "assistant"]
    assert len(user_msgs) == 2
    assert len(assistant_msgs) == 2


def test_clear_all_queues():
    provider = FakeProvider()
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )
    agent.steer(UserMessage(content=[{"type": "text", "text": "a"}], timestamp=0.0))
    agent.follow_up(UserMessage(content=[{"type": "text", "text": "b"}], timestamp=0.0))
    agent.clear_all_queues()
    assert asyncio.run(agent._drain_steering()) == []
    assert asyncio.run(agent._drain_follow_up()) == []
