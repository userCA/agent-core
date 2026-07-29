"""Tests for agent_core.observability — tracing primitives (A1)."""

import asyncio

import pytest

from agent_core.observability import (
    generate_run_id,
    system_prompt_hash,
    trace_llm_call,
    trace_turn,
)


def test_generate_run_id_format():
    rid = generate_run_id()
    assert rid.startswith("run-")
    assert len(rid) == len("run-") + 12  # 12 hex chars


def test_generate_run_id_unique():
    ids = {generate_run_id() for _ in range(50)}
    assert len(ids) == 50  # all unique


def test_system_prompt_hash_deterministic():
    h1 = system_prompt_hash("You are a helpful assistant.")
    h2 = system_prompt_hash("You are a helpful assistant.")
    assert h1 == h2
    assert len(h1) == 12


def test_system_prompt_hash_empty():
    assert system_prompt_hash("") == ""


def test_trace_turn_no_op_without_otel():
    """trace_turn is a no-op when OTEL is not installed."""
    entered = False
    with trace_turn(turn_index=1, session_id="s1", run_id="r1"):
        entered = True
    assert entered


def test_trace_llm_call_no_op_yields_dict():
    """trace_llm_call yields a dict even when OTEL is unavailable."""
    result = None
    with trace_llm_call(
        provider="openai",
        model="gpt-4o",
        session_id="s1",
        run_id="r1",
        turn_index=1,
    ) as r:
        result = r
        result["input_tokens"] = 10
        result["output_tokens"] = 5
        result["stop_reason"] = "stop"

    assert isinstance(result, dict)
    assert result["input_tokens"] == 10
