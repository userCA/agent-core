"""Optional OpenTelemetry observability for agent runs.

Usage::

    from agent_core.observability import observe
    from agent_core.session.harness import AgentHarness

    harness = AgentHarness(...)
    with observe(harness, session_id="s1"):
        await harness.prompt("Hello")

When OpenTelemetry is installed, spans are created for:
- ``agent.run`` — top-level span per user prompt (created by :func:`observe`)
- ``agent.turn`` — one span per turn (LLM call + tool execution)
- ``agent.llm_call`` — span for the LLM streaming call
- ``agent.tool_call.{name}`` — span per tool invocation

Without OpenTelemetry, all calls are no-ops.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import time
import uuid
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


def configure_otel_exporter(
    exporter: str | None = None,
    *,
    service_name: str = "agent-core",
) -> bool:
    """Configure the OTEL span exporter based on *exporter* or ``OTEL_EXPORTER``.

    Supported values:
    - ``"console"``: prints spans to stdout (useful for local debugging).
    - ``"otlp"``: sends spans to an OTLP-compatible endpoint (Jaeger, Grafana Tempo).
      Reads endpoint from ``OTEL_EXPORTER_OTLP_ENDPOINT`` (default ``http://localhost:4317``).
    - ``None`` / ``""``: no exporter configured (spans are still created but not exported).

    Returns ``True`` if an exporter was successfully configured.
    """
    if not _otel_available:
        logger.debug("OpenTelemetry not installed; skipping exporter configuration")
        return False

    exporter = exporter or os.environ.get("OTEL_EXPORTER", "")
    if not exporter:
        return False

    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        if exporter == "console":
            from opentelemetry.sdk.trace.export import (
                ConsoleSpanExporter,
                SimpleSpanProcessor,
            )
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(provider)
            logger.info("OTEL exporter configured: console")
            return True

        elif exporter == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            endpoint = os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
            )
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            trace.set_tracer_provider(provider)
            logger.info("OTEL exporter configured: otlp -> %s", endpoint)
            return True

        else:
            logger.warning("Unknown OTEL_EXPORTER value: %s", exporter)
            return False

    except ImportError as exc:
        logger.warning(
            "Failed to configure OTEL exporter %s: missing dependency (%s). "
            "Install with: pip install opentelemetry-sdk",
            exporter, exc,
        )
        return False


def generate_run_id() -> str:
    """Generate a unique run ID for an agent run."""
    return f"run-{uuid.uuid4().hex[:12]}"


def system_prompt_hash(prompt: str) -> str:
    """Return a short SHA-256 hash of the system prompt for version tracking."""
    if not prompt:
        return ""
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]


@contextlib.contextmanager
def observe(
    harness: Any,
    *,
    session_id: str = "",
    run_id: str = "",
    provider_name: str = "",
    model_id: str = "",
    system_prompt: str = "",
) -> Iterator[None]:
    """Instrument an AgentHarness with OpenTelemetry spans (no-op if OTEL unavailable).

    Creates a top-level ``agent.run`` span that parents all turn, LLM and
    tool spans.  Registers tracing hooks via
    ``harness.add_before_tool_call_hook`` /
    ``harness.add_after_tool_call_hook``.
    """
    if not _otel_available:
        yield
        return

    tracer = _get_tracer()
    if tracer is None:
        yield
        return

    # Register tracing hooks via public API, store references for cleanup
    tracing_before = _make_tracing_before_hook(tracer, session_id, run_id, provider_name, model_id)
    tracing_after = _make_tracing_after_hook(tracer)

    harness.add_before_tool_call_hook(tracing_before)
    harness.add_after_tool_call_hook(tracing_after)

    # Create run-level span
    run_span = tracer.start_span(
        "agent.run",
        kind=SpanKind.INTERNAL,
        attributes={
            "agent.session_id": session_id,
            "agent.run_id": run_id,
            "agent.provider": provider_name,
            "agent.model": model_id,
            "agent.system_prompt_hash": system_prompt_hash(system_prompt),
        },
    )

    try:
        with trace.use_span(run_span, end_on_exit=True):
            yield
    except Exception:
        run_span.set_status(Status(StatusCode.ERROR))
        raise
    finally:
        harness.remove_before_tool_call_hook(tracing_before)
        harness.remove_after_tool_call_hook(tracing_after)


def _make_tracing_before_hook(
    tracer: Any,
    session_id: str,
    run_id: str,
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
                "agent.run_id": run_id,
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
def trace_turn(
    *,
    turn_index: int = 0,
    session_id: str = "",
    run_id: str = "",
) -> Iterator[None]:
    """Context manager for a single agent turn (LLM call + tool execution).

    Creates an ``agent.turn`` span that parents any ``agent.llm_call`` and
    ``agent.tool_call`` spans started within its scope.
    """
    if not _otel_available:
        yield
        return
    tracer = _get_tracer()
    if tracer is None:
        yield
        return

    span = tracer.start_span(
        "agent.turn",
        kind=SpanKind.INTERNAL,
        attributes={
            "agent.turn_index": turn_index,
            "agent.session_id": session_id,
            "agent.run_id": run_id,
        },
    )
    try:
        with trace.use_span(span, end_on_exit=True):
            yield
    except Exception:
        span.set_status(Status(StatusCode.ERROR))
        raise


@contextlib.contextmanager
def trace_llm_call(
    *,
    provider: str = "",
    model: str = "",
    session_id: str = "",
    run_id: str = "",
    turn_index: int = 0,
) -> Iterator[dict[str, Any]]:
    """Context manager for LLM streaming calls.

    Yields a mutable *result* dict.  Callers should populate it with
    ``input_tokens``, ``output_tokens`` and ``stop_reason`` after the
    stream completes so the span attributes carry full usage data.
    """
    if not _otel_available:
        yield {}
        return
    tracer = _get_tracer()
    if tracer is None:
        yield {}
        return

    start = time.monotonic()
    result: dict[str, Any] = {}
    span = tracer.start_span(
        "agent.llm_call",
        kind=SpanKind.CLIENT,
        attributes={
            "llm.provider": provider,
            "llm.model": model,
            "agent.session_id": session_id,
            "agent.run_id": run_id,
            "agent.turn_index": turn_index,
        },
    )
    try:
        with trace.use_span(span, end_on_exit=False):
            yield result
    except Exception:
        span.set_status(Status(StatusCode.ERROR))
        raise
    finally:
        elapsed = time.monotonic() - start
        span.set_attribute("latency_ms", round(elapsed * 1000, 2))
        if result.get("input_tokens") is not None:
            span.set_attribute("llm.usage.input_tokens", result["input_tokens"])
        if result.get("output_tokens") is not None:
            span.set_attribute("llm.usage.output_tokens", result["output_tokens"])
        if result.get("stop_reason"):
            span.set_attribute("llm.stop_reason", result["stop_reason"])
        span.end()
