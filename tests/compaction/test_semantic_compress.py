"""Tests for L2 semantic_compress."""

from __future__ import annotations

import json

import pytest

from agent_core.compaction.semantic_compress import (
    semantic_compress,
    structured_fallback_compress,
)


def test_structured_fallback_tiny_target_still_valid_json():
    text = "Z" * 5000
    out = structured_fallback_compress(text, target_chars=50, head_chars=3000)
    payload = json.loads(out)  # must not raise
    assert payload["__fallbackTruncated"] is True


def test_structured_fallback_fits_target_and_flags():
    text = "A" * 20_000
    out = structured_fallback_compress(text, target_chars=2000, head_chars=3000)
    assert len(out) <= 2000
    payload = json.loads(out)
    assert payload["__fallbackTruncated"] is True
    assert payload["chars"] == 20_000
    assert payload["head"].startswith("A")
    # head is raw substring — never rewritten field names
    assert set(payload["head"]) <= {"A"}


@pytest.mark.asyncio
async def test_semantic_compress_below_min_uses_substring():
    text = "hello world " * 100
    result = await semantic_compress(text, compress_min_chars=10_000, target_chars=50)
    assert result.method == "substring"
    assert result.fallback_truncated is False
    assert result.summary == text[:50]
    assert result.preview == text[: min(200, len(text))]


@pytest.mark.asyncio
async def test_semantic_compress_uses_llm_fn():
    text = "B" * 12_000

    async def compress_fn(t, *, target_chars, tool_name):
        assert len(t) == 12_000
        assert tool_name == "bash"
        return "distilled summary"

    result = await semantic_compress(
        text,
        compress_fn=compress_fn,
        tool_name="bash",
        compress_min_chars=10_000,
        target_chars=2000,
        preview_chars=10,
    )
    assert result.method == "llm"
    assert result.summary == "distilled summary"
    assert result.preview == "B" * 10
    assert result.fallback_truncated is False


@pytest.mark.asyncio
async def test_semantic_compress_llm_failure_falls_back():
    text = "C" * 12_000

    async def boom(t, *, target_chars, tool_name):
        raise RuntimeError("llm down")

    result = await semantic_compress(
        text,
        compress_fn=boom,
        compress_min_chars=10_000,
        target_chars=1800,
    )
    assert result.method == "fallback"
    assert result.fallback_truncated is True
    assert len(result.summary) <= 1800
    assert json.loads(result.summary)["__fallbackTruncated"] is True
    assert result.preview == text[:200]


@pytest.mark.asyncio
async def test_semantic_compress_no_fn_uses_fallback():
    text = "D" * 11_000
    result = await semantic_compress(text, compress_fn=None, compress_min_chars=10_000)
    assert result.method == "fallback"
    assert "__fallbackTruncated" in result.summary
