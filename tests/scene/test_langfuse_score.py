"""Tests for optional Langfuse Score HTTP helper."""

import pytest
import respx
import httpx

from scene.http_sse.langfuse_score import submit_user_score


@pytest.mark.asyncio
async def test_submit_user_score_noop_without_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    assert await submit_user_score(run_id="run-1", value=1.0) is False


@pytest.mark.asyncio
@respx.mock
async def test_submit_user_score_posts(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.invalid")

    route = respx.post("https://example.invalid/api/public/scores").mock(
        return_value=httpx.Response(200, json={"id": "score-1"})
    )

    ok = await submit_user_score(
        run_id="run-abc",
        session_id="sess-1",
        value=1.0,
        comment="helpful",
    )
    assert ok is True
    assert route.called
    body = route.calls.last.request.content.decode()
    assert "run-abc" in body
    assert "sess-1" in body
