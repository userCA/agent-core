"""Optional OpenTelemetry observability for agent runs.

Usage::

    from agent_core.observability import observe

    agent = Agent(...)
    with observe(agent, session_id="s1"):
        await agent.prompt("Hello")

When OpenTelemetry is installed, spans are created for:
- ``agent.prompt`` — top-level span per user message
- ``agent.turn`` — one span per turn (LLM call + tool execution)
- ``agent.llm_call`` — span for the LLM streaming call
- ``agent.tool_call.{name}`` — span per tool invocation

Without OpenTelemetry, all calls are no-ops.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Iterator

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode

    _otel_available = True
except ImportError:
    _otel_available = False


def _get_tracer() -> Any:
    if _otel_available:
        return trace.get_tracer("agent_core")
    return None


@contextlib.contextmanager
def observe(
    agent: Any,
    *,
    session_id: str = "",
    provider_name: str = "",
    model_id: str = "",
) -> Iterator[None]:
    """Instrument an Agent with OpenTelemetry spans (no-op if OTEL unavailable).

    Patches ``agent._before_hooks`` and ``agent._after_hooks`` with tracing wrappers.
    """
    if not _otel_available:
        yield
        return

    tracer = _get_tracer()
    if tracer is None:
        yield
        return

    # Register tracing hooks via public API, store references for cleanup
    tracing_before = _make_tracing_before_hook(tracer, session_id, provider_name, model_id)
    tracing_after = _make_tracing_after_hook(tracer)

    agent.add_before_tool_call_hook(tracing_before)
    agent.add_after_tool_call_hook(tracing_after)

    try:
        yield
    finally:
        agent.remove_before_tool_call_hook(tracing_before)
        agent.remove_after_tool_call_hook(tracing_after)


def _make_tracing_before_hook(
    tracer: Any,
    session_id: str,
    provider_name: str,
    model_id: str,
) -> Any:
    """Create a before-tool-call hook that starts a span for each tool."""

    async def _hook(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
        tool_call = call_ctx.get("tool_call")
        if tool_call is None:
            return None

        name = getattr(tool_call, "name", "unknown")
        tc_id = getattr(tool_call, "id", "")

        span = tracer.start_span(
            f"agent.tool_call.{name}",
            kind=SpanKind.INTERNAL,
            attributes={
                "tool.name": name,
                "tool.call_id": tc_id,
                "agent.session_id": session_id,
                "agent.provider": provider_name,
                "agent.model": model_id,
            },
        )
        # Store span in metadata so the after-hook can end it
        metadata = call_ctx.setdefault("__tracing", {})
        metadata["span"] = span
        metadata.setdefault("spans", []).append(span)
        return {"inject_metadata": {"__tracing_span": span}}

    return _hook


def _make_tracing_after_hook(tracer: Any) -> Any:
    """Create an after-tool-call hook that ends tool spans."""

    async def _hook(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
        tracing_meta = call_ctx.get("__tracing", {})
        span = tracing_meta.get("span")
        if span is not None:
            is_error = call_ctx.get("is_error", False)
            if is_error:
                span.set_status(Status(StatusCode.ERROR))
            span.end()
        return None

    return _hook


@contextlib.contextmanager
def trace_llm_call(
    *,
    provider: str = "",
    model: str = "",
    session_id: str = "",
) -> Iterator[None]:
    """Context manager for LLM streaming calls."""
    if not _otel_available:
        yield
        return
    tracer = _get_tracer()
    if tracer is None:
        yield
        return

    span = tracer.start_span(
        "agent.llm_call",
        kind=SpanKind.CLIENT,
        attributes={
            "llm.provider": provider,
            "llm.model": model,
            "agent.session_id": session_id,
        },
    )
    try:
        yield
    except Exception:
        span.set_status(Status(StatusCode.ERROR))
        raise
    finally:
        span.end()
