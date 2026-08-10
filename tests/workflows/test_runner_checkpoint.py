"""WorkflowRunner execution and checkpoint resume tests."""

from __future__ import annotations

import pytest

from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.workflows.errors import QuotaExceeded
from agent_core.workflows.runner import WorkflowRunner
from agent_core.workflows.types import WorkflowOptions


@pytest.mark.asyncio
async def test_runner_executes_sample_ok(workflow_env):
    runner, _, _, _, _, _ = await workflow_env()

    result = await runner.run(name="sample-ok")

    assert result.status == "completed"
    assert result.result == {"ok": True}
    assert result.run_id
    assert result.checkpoint is not None
    assert result.checkpoint.status == "completed"


@pytest.mark.asyncio
async def test_runner_executes_with_pipeline(workflow_env):
    runner, _, _, provider, _, _ = await workflow_env()
    n = 3
    for i in range(n):
        provider.queue_script([
            StreamTextDelta(text=f"resp-{i}"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ])

    result = await runner.run(name="pipeline-demo", args={"n": n})

    assert result.status == "completed"
    assert result.result == {"count": n}
    assert result.checkpoint is not None
    assert result.checkpoint.phase_outputs["work"] == ["resp-0", "resp-1", "resp-2"]


@pytest.mark.asyncio
async def test_resume_skips_completed_phase(workflow_env):
    runner, _, _, provider, store, _ = await workflow_env(max_agent_invocations=0)

    first = await runner.run(name="two-phase")
    assert first.status == "failed"
    assert first.checkpoint is not None
    assert "A" in first.checkpoint.completed_phases
    assert "B" not in first.checkpoint.completed_phases

    run_id = first.run_id

    resume_runner, _, _, provider2, _, _ = await workflow_env(
        max_agent_invocations=2,
        store=store,
    )
    provider2.queue_script([
        StreamTextDelta(text="phase-b-done"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    second = await resume_runner.run(resume_run_id=run_id)

    assert second.status == "completed"
    assert second.result == {"A": "doneA", "B": "doneB"}
    assert len(provider2.calls) == 1


@pytest.mark.asyncio
async def test_abort_sets_aborted(workflow_env):
    import asyncio

    from tests.conftest import FakeProvider

    class SlowFakeProvider(FakeProvider):
        async def stream(self, **kwargs):
            self.calls.append(kwargs)
            await asyncio.sleep(0.2)
            events = self._scripts.pop(0) if self._scripts else []
            for event in events:
                await asyncio.sleep(0)
                yield event

    provider = SlowFakeProvider()
    provider.queue_script([
        StreamTextDelta(text="slow"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    runner, _, _, _, _, _ = await workflow_env(
        enable_dynamic_exec=True,
        provider=provider,
    )

    inline = '''
meta = {"name": "abort-demo", "description": "", "phases": ["work"]}

async def run(ctx):
    await ctx.phase("work")
    await ctx.agent("blocking task", profile="worker")
    return {"done": True}
'''

    run_task = asyncio.create_task(runner.run(inline_source=inline))
    await asyncio.sleep(0.05)
    await runner.abort()
    result = await run_task

    assert result.status == "aborted"


@pytest.mark.asyncio
async def test_inline_source_requires_enable_dynamic_exec(workflow_env):
    runner, _, _, _, _, _ = await workflow_env()

    result = await runner.run(
        inline_source='meta = {"name": "x"}\nasync def run(ctx):\n    return {}',
    )

    assert result.status == "failed"
    assert "enable_dynamic_exec" in (result.error_message or "")
