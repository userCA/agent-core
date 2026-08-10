"""Quota enforcement, abort semantics, and agent progress counter tests."""

from __future__ import annotations

import pytest

from agent_core.providers.types import StreamMessageEnd, StreamTextDelta


@pytest.mark.asyncio
async def test_runner_quota_exceeded_on_third_agent(workflow_env):
    """max_agent_invocations=2: third agent call fails with checkpoint.status=failed."""
    runner, _, _, provider, _, _ = await workflow_env(
        max_agent_invocations=2,
        enable_dynamic_exec=True,
    )
    for _ in range(2):
        provider.queue_script([
            StreamTextDelta(text="ok"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ])

    inline = '''
meta = {"name": "quota-demo", "description": "", "phases": ["work"]}

async def run(ctx):
    await ctx.phase("work")
    await ctx.agent("task 1", profile="worker")
    await ctx.agent("task 2", profile="worker")
    await ctx.agent("task 3", profile="worker")
    return {"done": True}
'''

    result = await runner.run(inline_source=inline)

    assert result.status == "failed"
    assert "max_agent_invocations" in (result.error_message or "")
    assert result.checkpoint is not None
    assert result.checkpoint.status == "failed"
    assert result.checkpoint.agent_invocation_count == 3


@pytest.mark.asyncio
async def test_pipeline_emits_agent_progress_counters(workflow_env):
    """Progress payloads include completed_agents/total_agents during pipeline runs."""
    events: list[dict] = []

    async def on_progress(payload: dict) -> None:
        events.append(payload)

    runner, _, _, provider, _, _ = await workflow_env()
    n = 3
    for i in range(n):
        provider.queue_script([
            StreamTextDelta(text=f"resp-{i}"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ])

    result = await runner.run(
        name="pipeline-demo",
        args={"n": n},
        on_progress=on_progress,
    )

    assert result.status == "completed"

    pipeline_events = [
        e for e in events if e.get("progress", {}).get("total_agents") == n
    ]
    assert pipeline_events, "expected progress events with total_agents set"

    completed_values = {
        e["progress"]["completed_agents"]
        for e in pipeline_events
        if e["status"] == "running"
    }
    assert completed_values == {0, 1, 2, 3}
