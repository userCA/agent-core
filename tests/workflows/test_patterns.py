"""Tests for workflow orchestration pattern helpers."""

from __future__ import annotations

import pytest

from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.workflows import patterns
from agent_core.workflows.runtime import WorkflowContext
from tests.conftest import FakeProvider
from tests.workflows.test_runtime_primitives import _make_context


@pytest.mark.asyncio
async def test_fanout_synthesize_maps_then_synthesizes():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="mapped-a"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="mapped-b"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="synthesized"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    ctx, _, _ = await _make_context(provider=provider)

    result = await patterns.fanout_synthesize(
        ctx,
        ["a", "b"],
        map_prompt=lambda item, i: f"map:{item}:{i}",
        synthesize_prompt=lambda rows: f"synth:{rows}",
    )

    assert result == "synthesized"
    assert ctx.agent_invocation_count == 3


@pytest.mark.asyncio
async def test_adversarial_verify_converges_on_approval():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="APPROVED"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    ctx, _, _ = await _make_context(provider=provider)

    out = await patterns.adversarial_verify(ctx, "draft v1", "be concise")

    assert out["converged"] is True
    assert out["final"] == "draft v1"
    assert len(out["rounds"]) == 1
    assert out["rounds"][0]["critique"] == "APPROVED"


@pytest.mark.asyncio
async def test_adversarial_verify_revises_when_not_approved():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="Too verbose"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="draft v2"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    ctx, _, _ = await _make_context(provider=provider)

    out = await patterns.adversarial_verify(
        ctx, "draft v1", "be concise", max_rounds=1
    )

    assert out["converged"] is False
    assert out["final"] == "draft v2"
    assert out["rounds"][0]["revised"] == "draft v2"


@pytest.mark.asyncio
async def test_generate_and_filter_returns_top_scored():
    provider = FakeProvider()
    for label in ("low", "high", "mid"):
        provider.queue_script([
            StreamTextDelta(text=f"candidate-{label}"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ])
    provider.queue_script([
        StreamTextDelta(text="1"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="9"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    provider.queue_script([
        StreamTextDelta(text="5"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    ctx, _, _ = await _make_context(provider=provider)

    top = await patterns.generate_and_filter(
        ctx,
        3,
        gen_prompt=lambda i: f"gen:{i}",
        score_prompt=lambda c: f"score:{c}",
        top_k=1,
    )

    assert top == ["candidate-high"]


@pytest.mark.asyncio
async def test_tournament_picks_winner():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="beta is better"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    ctx, _, _ = await _make_context(provider=provider)

    winner = await patterns.tournament(
        ctx,
        ["alpha", "beta"],
        compare_prompt=lambda a, b: f"compare {a} vs {b}",
    )

    assert winner == "beta"


@pytest.mark.asyncio
async def test_classify_and_execute_routes_to_handler():
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="billing"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])
    ctx, _, _ = await _make_context(provider=provider)

    async def billing_handler(c: WorkflowContext, t: str) -> str:
        return f"billing:{t}"

    async def support_handler(c: WorkflowContext, t: str) -> str:
        return f"support:{t}"

    result = await patterns.classify_and_execute(
        ctx,
        "invoice question",
        {"billing": billing_handler, "support": support_handler},
    )

    assert result == "billing:invoice question"


@pytest.mark.asyncio
async def test_loop_until_stops_when_done():
    ctx, _, _ = await _make_context()

    async def step(c: WorkflowContext, i: int) -> int:
        return i + 1

    result = await patterns.loop_until(ctx, step, done=lambda v: v >= 3, max_iters=10)

    assert result == 3
