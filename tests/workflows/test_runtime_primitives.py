"""WorkflowContext primitive behavior tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_core.multi_agent.profile_registry import AgentProfileRegistry
from agent_core.multi_agent.sub_agent_factory import SubAgentFactory
from agent_core.multi_agent.sub_agent_runner import SubAgentRunner
from agent_core.multi_agent.types import AgentProfile
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.store import SessionHeader
from agent_core.workflows.errors import QuotaExceeded
from agent_core.workflows.runtime import WorkflowContext
from agent_core.workflows.types import WorkflowCheckpoint
from tests.conftest import FakeProvider, fake_model


async def _make_context(
    *,
    provider: FakeProvider | None = None,
    max_agent_invocations: int = 100,
    resume: WorkflowCheckpoint | None = None,
    on_progress=None,
) -> tuple[WorkflowContext, FakeProvider, SubAgentRunner]:
    provider = provider or FakeProvider()
    store = InMemoryStore()
    await store.create_session(
        "parent",
        SessionHeader(
            id="parent",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            owner="alice",
        ),
    )
    registry = AgentProfileRegistry()
    registry.register(
        AgentProfile(
            name="worker",
            description="worker",
            system_prompt="You are a worker.",
        )
    )
    factory = SubAgentFactory(
        provider=provider,
        auth_source=AuthSource.static(api_key="fake"),
        store=store,
        parent_session_id="parent",
        default_model=fake_model(),
        all_tools=[],
        owner="alice",
    )
    runner = SubAgentRunner(factory=factory, registry=registry, store=store)
    ctx = WorkflowContext(
        run_id="run-1",
        workflow_name="test-wf",
        phases=["a", "b"],
        args={"key": "val"},
        runner=runner,
        registry=registry,
        max_agent_invocations=max_agent_invocations,
        on_progress=on_progress,
        resume=resume,
    )
    return ctx, provider, runner


@pytest.mark.asyncio
async def test_phase_updates_current_phase_and_emits_progress():
    events: list[dict] = []

    async def on_progress(payload: dict) -> None:
        events.append(payload)

    ctx, _, _ = await _make_context(on_progress=on_progress)
    await ctx.phase("a")

    assert ctx.current_phase == "a"
    assert len(events) == 1
    assert events[0]["type"] == "workflow"
    assert events[0]["run_id"] == "run-1"
    assert events[0]["name"] == "test-wf"
    assert events[0]["phase"] == "a"
    assert events[0]["phases"] == ["a", "b"]


@pytest.mark.asyncio
async def test_log_caps_at_200():
    ctx, _, _ = await _make_context()
    for i in range(250):
        ctx.log(f"msg-{i}")

    assert len(ctx.logs) == 200
    assert ctx.logs[0] == "msg-50"
    assert ctx.logs[-1] == "msg-249"


@pytest.mark.asyncio
async def test_agent_increments_count_and_returns_text():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="hello worker"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=2),
    ])
    ctx, _, _ = await _make_context(provider=provider)

    result = await ctx.agent("do task", profile="worker")

    assert result == "hello worker"
    assert ctx.agent_invocation_count == 1


@pytest.mark.asyncio
async def test_agent_quota_exceeded():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="ok"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    ctx, _, _ = await _make_context(provider=provider, max_agent_invocations=1)

    await ctx.agent("first", profile="worker")
    with pytest.raises(QuotaExceeded):
        await ctx.agent("second", profile="worker")


@pytest.mark.asyncio
async def test_pipeline_preserves_order():
    ctx, _, _ = await _make_context()

    async def fn(item, index):
        return item * 10

    out = await ctx.pipeline([1, 2, 3], fn)
    assert out == [10, 20, 30]


@pytest.mark.asyncio
async def test_pipeline_emits_agent_progress_counters():
    events: list[dict] = []

    async def on_progress(payload: dict) -> None:
        events.append(payload)

    provider = FakeProvider()
    for i in range(3):
        provider.queue_script([
            StreamTextDelta(text=f"r{i}"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ])
    ctx, _, _ = await _make_context(provider=provider, on_progress=on_progress)

    async def fn(item, index):
        return await ctx.agent(f"task {item}", profile="worker")

    await ctx.pipeline([0, 1, 2], fn)

    totals = {e["progress"]["total_agents"] for e in events}
    assert 3 in totals
    completed = [
        e["progress"]["completed_agents"]
        for e in events
        if e["progress"].get("total_agents") == 3
    ]
    assert 0 in completed
    assert 3 in completed


@pytest.mark.asyncio
async def test_resume_is_phase_done_and_get_phase_output():
    resume = WorkflowCheckpoint(
        run_id="run-1",
        workflow_name="test-wf",
        status="running",
        completed_phases=["fanout"],
        phase_outputs={"fanout": [10, 20, 30]},
        updated_at=1.0,
    )
    ctx, _, _ = await _make_context(resume=resume)

    assert ctx.is_phase_done("fanout") is True
    assert ctx.is_phase_done("other") is False
    assert ctx.get_phase_output("fanout") == [10, 20, 30]

    ctx.set_phase_output("merge", {"ok": True})
    assert ctx.is_phase_done("merge") is True
    assert ctx.get_phase_output("merge") == {"ok": True}
