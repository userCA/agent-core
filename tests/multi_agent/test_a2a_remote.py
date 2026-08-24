"""SubAgentRunner remote (A2A) dispatch tests."""

from __future__ import annotations

import asyncio
import json

import pytest
import respx
from httpx import Response

from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.sub_agent_factory import SubAgentFactory
from agent_core.multi_agent.sub_agent_runner import SubAgentRunner
from agent_core.multi_agent.types import AgentProfile
from agent_core.providers.auth import AuthSource
from agent_core.session.inmemory_store import InMemoryStore
from tests.conftest import FakeProvider, fake_model

BASE = "http://a2a.test"


def _task(state: str, text: str) -> dict:
    return {
        "id": "t-1",
        "status": {"state": state},
        "artifacts": [],
        "messages": [{"role": "agent", "parts": [{"type": "text", "text": text}]}],
    }


def _rpc_result(result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": "1", "result": result}


class _Handler:
    def __init__(self, *, final_state: str = "completed") -> None:
        self.calls: list[str] = []
        self.state = "working"
        self.final_state = final_state
        self.get_count = 0

    def __call__(self, request):
        body = json.loads(request.content)
        method = body["method"]
        self.calls.append(method)
        if method == "message/send":
            return Response(200, json=_rpc_result(_task(self.state, "working...")))
        if method == "tasks/get":
            self.get_count += 1
            if self.get_count >= 2:
                self.state = self.final_state
            text = "final answer" if self.state == "completed" else self.state
            return Response(200, json=_rpc_result(_task(self.state, text)))
        if method == "tasks/cancel":
            self.state = "canceled"
            return Response(200, json=_rpc_result(_task("canceled", "")))
        raise AssertionError(f"unexpected A2A method: {method}")


def _runner() -> SubAgentRunner:
    store = InMemoryStore()
    registry = AgentProfileRegistry()
    registry.register(
        AgentProfile(
            name="researcher",
            description="research agent",
            system_prompt="(unused for remote)",
            transport="a2a",
            endpoint=BASE,
            timeout_seconds=5,
        )
    )
    factory = SubAgentFactory(
        provider=FakeProvider(),
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        parent_session_id="parent",
        default_model=fake_model(),
        all_tools=[],
    )
    return SubAgentRunner(factory=factory, registry=registry, store=store, max_concurrent_agents=2)


@pytest.mark.asyncio
@respx.mock
async def test_run_single_remote_completed():
    server = _Handler()
    respx.post(BASE + "/").mock(side_effect=server)
    runner = _runner()
    profile = runner._registry.resolve("researcher")
    assert profile is not None
    result = await runner.run_single(profile, "research X", delegation_id="d1")
    assert result.status == "completed"
    assert "final answer" in result.response_text
    assert result.session_id == "t-1"
    assert result.error_message is None


@pytest.mark.asyncio
@respx.mock
async def test_run_single_remote_failed():
    server = _Handler(final_state="failed")
    respx.post(BASE + "/").mock(side_effect=server)
    runner = _runner()
    profile = runner._registry.resolve("researcher")
    assert profile is not None
    result = await runner.run_single(profile, "bad task", delegation_id="d1")
    assert result.status == "failed"
    assert result.error_message


@pytest.mark.asyncio
@respx.mock
async def test_run_single_remote_abort_on_signal():
    server = _Handler()
    respx.post(BASE + "/").mock(side_effect=server)
    runner = _runner()
    profile = runner._registry.resolve("researcher")
    assert profile is not None
    signal = asyncio.Event()

    async def _set():
        await asyncio.sleep(0.02)
        signal.set()

    asyncio.get_running_loop().create_task(_set())
    result = await runner.run_single(profile, "long task", delegation_id="d1", signal=signal)
    assert result.status == "aborted"
    assert "tasks/cancel" in server.calls


@pytest.mark.asyncio
async def test_run_single_remote_missing_endpoint():
    store = InMemoryStore()
    registry = AgentProfileRegistry()
    registry.register(
        AgentProfile(
            name="ghost",
            description="missing endpoint",
            system_prompt="(unused)",
            transport="a2a",
        )
    )
    factory = SubAgentFactory(
        provider=FakeProvider(),
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        parent_session_id="parent",
        default_model=fake_model(),
        all_tools=[],
    )
    runner = SubAgentRunner(factory=factory, registry=registry, store=store)
    profile = runner._registry.resolve("ghost")
    assert profile is not None
    result = await runner.run_single(profile, "task", delegation_id="d1")
    assert result.status == "failed"
    assert "endpoint" in (result.error_message or "")


@pytest.mark.asyncio
@respx.mock
async def test_run_parallel_remote_agents():
    server = _Handler()
    respx.post(BASE + "/").mock(side_effect=server)
    runner = _runner()
    profile = runner._registry.resolve("researcher")
    assert profile is not None
    results = await runner.run_parallel([(profile, "q1"), (profile, "q2")], delegation_id="d2")
    assert len(results) == 2
    assert all(r.status == "completed" for r in results)
