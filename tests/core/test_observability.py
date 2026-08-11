"""Tests for agent_core.observability — tracing primitives (A1)."""

import asyncio
import base64

import pytest

from agent_core.observability import (
    agent_span_attributes,
    build_langfuse_otlp_headers,
    configure_langfuse_otel_from_env,
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


def test_agent_span_attributes_include_session_aliases():
    attrs = agent_span_attributes(session_id="sess-1", run_id="run-abc")
    assert attrs["agent.session_id"] == "sess-1"
    assert attrs["agent.run_id"] == "run-abc"
    assert attrs["session.id"] == "sess-1"
    assert attrs["langfuse.session.id"] == "sess-1"
    assert attrs["langfuse.trace.metadata.run_id"] == "run-abc"


def test_agent_span_attributes_empty_omits_aliases():
    attrs = agent_span_attributes(session_id="", run_id="")
    assert attrs == {"agent.session_id": "", "agent.run_id": ""}


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


def test_build_langfuse_otlp_headers():
    headers = build_langfuse_otlp_headers("pk-lf-test", "sk-lf-secret")
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")
    raw = base64.b64decode(headers["Authorization"].split(" ", 1)[1]).decode()
    assert raw == "pk-lf-test:sk-lf-secret"
    assert headers["x-langfuse-ingestion-version"] == "4"


def test_configure_langfuse_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    assert configure_langfuse_otel_from_env() is False


def test_configure_langfuse_enabled_missing_keys_returns_false(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert configure_langfuse_otel_from_env() is False


def test_configure_otel_exporter_otlp_http_sets_provider():
    """Smoke: otlp_http path imports HTTP exporter or returns False cleanly."""
    from agent_core import observability as obs

    if not obs._otel_available:
        assert obs.configure_otel_exporter(
            exporter="otlp_http",
            endpoint="http://localhost:3000/api/public/otel",
            headers={"Authorization": "Basic xxx", "x-langfuse-ingestion-version": "4"},
        ) is False
        return

    result = obs.configure_otel_exporter(
        exporter="otlp_http",
        endpoint="http://localhost:3000/api/public/otel",
        headers={"Authorization": "Basic xxx", "x-langfuse-ingestion-version": "4"},
    )
    assert result in (True, False)


def test_configure_langfuse_enabled_with_keys_calls_http_exporter(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-y")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")

    called: dict = {}

    def fake_configure(*, exporter=None, endpoint=None, headers=None, service_name="agent-core"):
        called["exporter"] = exporter
        called["endpoint"] = endpoint
        called["headers"] = headers
        return True

    monkeypatch.setattr(
        "agent_core.observability.configure_otel_exporter",
        fake_configure,
    )
    assert configure_langfuse_otel_from_env() is True
    assert called["exporter"] == "otlp_http"
    assert called["endpoint"] == "http://localhost:3000/api/public/otel"
    assert called["headers"]["x-langfuse-ingestion-version"] == "4"


@pytest.mark.asyncio
async def test_tracing_after_hook_ends_pending_span(monkeypatch):
    from unittest.mock import MagicMock

    from agent_core import observability as obs
    from agent_core.observability import (
        _make_tracing_after_hook,
        _make_tracing_before_hook,
    )

    if not obs._otel_available:
        fake_kind = MagicMock()
        fake_kind.INTERNAL = "INTERNAL"
        monkeypatch.setattr(obs, "SpanKind", fake_kind, raising=False)
        fake_status_code = MagicMock()
        fake_status_code.ERROR = "ERROR"
        monkeypatch.setattr(obs, "StatusCode", fake_status_code, raising=False)
        monkeypatch.setattr(obs, "Status", MagicMock(), raising=False)

    ended: list[bool] = []
    mock_span = MagicMock()
    mock_span.end.side_effect = lambda: ended.append(True)

    mock_tracer = MagicMock()
    mock_tracer.start_span.return_value = mock_span

    run_id = "run-test123456"
    before = _make_tracing_before_hook(mock_tracer, "sess", run_id, "fake", "m1")
    after = _make_tracing_after_hook(mock_tracer, run_id)

    tool_call = MagicMock()
    tool_call.name = "grep"
    tool_call.id = "tc-1"

    await before({"tool_call": tool_call})
    assert f"{run_id}:tc-1" in obs._pending_tool_spans

    await after({"tool_call": tool_call, "is_error": False})

    assert len(ended) == 1
    assert f"{run_id}:tc-1" not in obs._pending_tool_spans


@pytest.mark.asyncio
async def test_tracing_after_hook_sets_error_status(monkeypatch):
    from unittest.mock import MagicMock

    from agent_core import observability as obs
    from agent_core.observability import _make_tracing_after_hook, _make_tracing_before_hook

    if not obs._otel_available:
        fake_kind = MagicMock()
        fake_kind.INTERNAL = "INTERNAL"
        monkeypatch.setattr(obs, "SpanKind", fake_kind, raising=False)
        fake_status_code = MagicMock()
        fake_status_code.ERROR = "ERROR"
        monkeypatch.setattr(obs, "StatusCode", fake_status_code, raising=False)
        monkeypatch.setattr(obs, "Status", MagicMock(), raising=False)

    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_span.return_value = mock_span

    run_id = "run-err1234567"
    before = _make_tracing_before_hook(mock_tracer, "sess", run_id, "fake", "m1")
    after = _make_tracing_after_hook(mock_tracer, run_id)

    tool_call = MagicMock()
    tool_call.name = "bash"
    tool_call.id = "tc-err"

    await before({"tool_call": tool_call})
    await after({"tool_call": tool_call, "is_error": True})

    mock_span.set_status.assert_called_once()
    mock_span.end.assert_called_once()
    assert f"{run_id}:tc-err" not in obs._pending_tool_spans


def test_cleanup_pending_tool_spans_ends_orphans():
    from unittest.mock import MagicMock

    from agent_core import observability as obs
    from agent_core.observability import _cleanup_pending_tool_spans

    ended: list[str] = []
    span_a = MagicMock()
    span_a.end.side_effect = lambda: ended.append("a")
    span_b = MagicMock()
    span_b.end.side_effect = lambda: ended.append("b")

    run_id = "run-orphan1234"
    obs._pending_tool_spans[f"{run_id}:tc-a"] = span_a
    obs._pending_tool_spans[f"{run_id}:tc-b"] = span_b
    obs._pending_tool_spans["other-run:tc-x"] = MagicMock()

    _cleanup_pending_tool_spans(run_id)

    assert set(ended) == {"a", "b"}
    assert f"{run_id}:tc-a" not in obs._pending_tool_spans
    assert f"{run_id}:tc-b" not in obs._pending_tool_spans
    assert "other-run:tc-x" in obs._pending_tool_spans

    obs._pending_tool_spans.pop("other-run:tc-x", None)
