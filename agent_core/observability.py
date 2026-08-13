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

import base64
import contextlib
import datetime
import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_pending_tool_spans: dict[str, Any] = {}
# run_id -> span context token for the active agent.turn span
_pending_turn_spans: dict[str, Any] = {}

try:
    from opentelemetry import context as _otel_context
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode

    _otel_available = True
except ImportError:
    _otel_available = False


def _get_tracer() -> Any:
    if _otel_available:
        return trace.get_tracer("agent_core")
    return None


def build_langfuse_otlp_headers(public_key: str, secret_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "x-langfuse-ingestion-version": "4",
    }


def _env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def configure_otel_exporter(
    exporter: str | None = None,
    *,
    service_name: str = "agent-core",
    endpoint: str | None = None,
    headers: dict[str, str] | None = None,
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

            endpoint = endpoint or os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
            )
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            trace.set_tracer_provider(provider)
            logger.info("OTEL exporter configured: otlp -> %s", endpoint)
            return True

        elif exporter == "otlp_http":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            ep = endpoint or os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                "http://localhost:4318",
            )
            exporter_kwargs: dict[str, Any] = {"endpoint": ep}
            if headers:
                exporter_kwargs["headers"] = headers
            otlp_exporter = OTLPSpanExporter(**exporter_kwargs)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            trace.set_tracer_provider(provider)
            logger.info("OTEL exporter configured: otlp_http -> %s", ep)
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


def configure_langfuse_otel_from_env(*, service_name: str = "agent-core") -> bool:
    """If LANGFUSE_ENABLED and keys set, configure OTLP/HTTP to Langfuse. Else False."""
    if not _env_flag("LANGFUSE_ENABLED"):
        return False
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    if not pk or not sk:
        logger.warning(
            "LANGFUSE_ENABLED but LANGFUSE_PUBLIC_KEY/SECRET_KEY missing; skip"
        )
        return False
    base = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")
    # Python OTLPSpanExporter expects the traces path (Langfuse SDK uses the same).
    endpoint = f"{base}/api/public/otel/v1/traces"
    headers = build_langfuse_otlp_headers(pk, sk)
    ok = configure_otel_exporter(
        exporter="otlp_http",
        endpoint=endpoint,
        headers=headers,
        service_name=service_name,
    )
    if ok:
        logger.info("Langfuse OTEL exporter configured: %s", endpoint)
    return ok


def _cleanup_pending_tool_spans(run_id: str) -> None:
    """End and remove any tool spans still pending for *run_id*."""
    prefix = f"{run_id}:"
    for key in [k for k in _pending_tool_spans if k.startswith(prefix)]:
        span = _pending_tool_spans.pop(key, None)
        if span is not None:
            span.end()


def generate_run_id() -> str:
    """Generate a unique run ID for an agent run."""
    return f"run-{uuid.uuid4().hex[:12]}"


def system_prompt_hash(prompt: str) -> str:
    """Return a short SHA-256 hash of the system prompt for version tracking."""
    if not prompt:
        return ""
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]


def agent_span_attributes(
    *,
    session_id: str = "",
    run_id: str = "",
    user_id: str = "",
    **extra: Any,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if session_id:
        attrs["session.id"] = session_id
        attrs["langfuse.session.id"] = session_id
    if run_id:
        attrs["langfuse.trace.metadata.run_id"] = run_id
    if user_id:
        attrs["user.id"] = user_id
    attrs.update({k: v for k, v in extra.items() if v is not None and v != ""})
    return attrs


def _resolve_observe_user_id(harness: Any, user_id: str = "") -> str:
    """Resolve user.id for observability spans.

    Priority: 1) explicit ``user_id`` 2) ``harness.observability_user_id`` 3) ``harness.owner``.
    """
    if user_id:
        return user_id
    uid = getattr(harness, "observability_user_id", "") or ""
    if uid:
        return uid
    return getattr(harness, "owner", "") or ""


@contextlib.contextmanager
def observe(
    harness: Any,
    *,
    session_id: str = "",
    run_id: str = "",
    provider_name: str = "",
    model_id: str = "",
    system_prompt: str = "",
    user_id: str = "",
) -> Iterator[None]:
    """Instrument an AgentHarness with OpenTelemetry spans (no-op if OTEL unavailable).

    Creates a top-level ``agent.run`` span that parents all turn, LLM and
    tool spans.  Registers tracing hooks via
    ``harness.add_before_tool_call_hook`` /
    ``harness.add_after_tool_call_hook`` and subscribes to harness events
    so each ``TurnStart``/``TurnEnd`` pair becomes an ``agent.turn`` span.
    """
    if not _otel_available:
        yield
        return

    tracer = _get_tracer()
    if tracer is None:
        yield
        return

    resolved_user_id = _resolve_observe_user_id(harness, user_id)

    # Register tracing hooks via public API, store references for cleanup
    tracing_before = _make_tracing_before_hook(
        tracer, session_id, run_id, resolved_user_id,
    )
    tracing_after = _make_tracing_after_hook(tracer, run_id)

    harness.add_before_tool_call_hook(tracing_before)
    harness.add_after_tool_call_hook(tracing_after)

    # Turn spans are driven by harness events, so any code path that emits
    # TurnStart/TurnEnd (including the max_turns forced-summary turn) is
    # covered without touching the loop.
    unsubscribe = _subscribe_turn_spans(
        harness, tracer, session_id, run_id, resolved_user_id,
    )

    # Create run-level span
    run_span = tracer.start_span(
        "agent.run",
        kind=SpanKind.INTERNAL,
        attributes=agent_span_attributes(
            session_id=session_id,
            run_id=run_id,
            user_id=resolved_user_id,
            **{
                "agent.provider": provider_name,
                "agent.model": model_id,
                "agent.system_prompt_hash": system_prompt_hash(system_prompt),
            },
        ),
    )

    try:
        with trace.use_span(run_span, end_on_exit=True):
            yield
    except Exception:
        run_span.set_status(Status(StatusCode.ERROR))
        raise
    finally:
        _apply_skill_activation_attributes(run_span, harness)
        harness.remove_before_tool_call_hook(tracing_before)
        harness.remove_after_tool_call_hook(tracing_after)
        unsubscribe()
        _cleanup_pending_tool_spans(run_id)
        _cleanup_pending_turn_spans(run_id)


def _subscribe_turn_spans(
    harness: Any,
    tracer: Any,
    session_id: str,
    run_id: str,
    user_id: str,
) -> Any:
    """Subscribe to harness events to create ``agent.turn`` spans.

    Returns an unsubscribe callable.  A ``TurnStart`` event starts an
    ``agent.turn`` span and attaches it as the active span so the
    ``agent.llm_call`` and ``agent.tool_call`` spans created within the
    turn inherit it as parent; ``TurnEnd`` detaches and ends it.
    """
    turn_index = 0

    def _on_event(evt: Any) -> None:
        nonlocal turn_index
        etype = getattr(evt, "type", "")
        if etype == "turn_start":
            turn_index += 1
            # Defensive: a previous turn may have been cut short (exception)
            # without a TurnEnd event — close it before starting a new one.
            stale = _pending_turn_spans.pop(run_id, None)
            if stale is not None:
                stale_span, stale_token = stale
                _otel_context.detach(stale_token)
                stale_span.end()
            span = tracer.start_span(
                "agent.turn",
                kind=SpanKind.INTERNAL,
                attributes=agent_span_attributes(
                    session_id=session_id,
                    run_id=run_id,
                    user_id=user_id,
                    **{"agent.turn_index": turn_index},
                ),
            )
            ctx = trace.set_span_in_context(span)
            token = _otel_context.attach(ctx)
            _pending_turn_spans[run_id] = (span, token)
        elif etype == "turn_end":
            entry = _pending_turn_spans.pop(run_id, None)
            if entry is not None:
                span, token = entry
                _otel_context.detach(token)
                span.end()

    unsubscribe = harness.subscribe(_on_event)
    return unsubscribe


def _cleanup_pending_turn_spans(run_id: str) -> None:
    """End and detach any turn span still pending for *run_id*."""
    entry = _pending_turn_spans.pop(run_id, None)
    if entry is not None:
        span, token = entry
        _otel_context.detach(token)
        span.end()


def _apply_skill_activation_attributes(run_span: Any, harness: Any) -> None:
    activations = getattr(harness, "skill_activations", None)
    if not activations:
        return
    names = sorted({name for name, _ in activations})
    run_span.set_attribute("agent.skills.activated", ",".join(names))
    sources = ",".join(f"{name}:{source}" for name, source in activations)
    run_span.set_attribute("agent.skills.sources", sources)


def _tool_result_text(result: Any) -> str:
    """Extract a plain-text summary from a ToolResult for span attributes."""
    if result is None:
        return ""
    content = getattr(result, "content", None)
    if not content:
        return ""
    parts = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _make_tracing_before_hook(
    tracer: Any,
    session_id: str,
    run_id: str,
    user_id: str = "",
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
            attributes=agent_span_attributes(
                session_id=session_id,
                run_id=run_id,
                user_id=user_id,
                **{
                    "tool.name": name,
                    "tool.call_id": tc_id,
                },
            ),
        )
        args = call_ctx.get("args")
        if _env_flag("LANGFUSE_CAPTURE_CONTENT"):
            span.set_attribute("tool.input", json.dumps(args, ensure_ascii=False))
        _pending_tool_spans[f"{run_id}:{tc_id}"] = span
        return None

    return _hook


def _make_tracing_after_hook(tracer: Any, run_id: str) -> Any:
    """Create an after-tool-call hook that ends tool spans."""

    async def _hook(call_ctx: dict[str, Any]) -> dict[str, Any] | None:
        tool_call = call_ctx.get("tool_call")
        if tool_call is None:
            return None

        tc_id = getattr(tool_call, "id", "")
        span = _pending_tool_spans.pop(f"{run_id}:{tc_id}", None)
        if span is not None:
            if call_ctx.get("is_error", False):
                span.set_status(Status(StatusCode.ERROR))
            if _env_flag("LANGFUSE_CAPTURE_CONTENT"):
                result = call_ctx.get("result")
                text = _tool_result_text(result)
                if text:
                    attr = "tool.error" if call_ctx.get("is_error", False) else "tool.output"
                    span.set_attribute(attr, text[:2000])
            span.end()
        return None

    return _hook


@contextlib.contextmanager
def trace_llm_call(
    *,
    provider: str = "",
    model: str = "",
    session_id: str = "",
    run_id: str = "",
    turn_index: int = 0,
    user_id: str = "",
    prompt: str = "",
) -> Iterator[dict[str, Any]]:
    """Context manager for LLM streaming calls.

    Yields a mutable *result* dict.  Callers should populate it with
    ``input_tokens``, ``output_tokens``, ``stop_reason`` and optionally
    ``completion`` after the stream completes so the span attributes carry
    full usage data.

    Span attributes follow OpenTelemetry GenAI semantic conventions
    (``gen_ai.*``, ``user.id``, ``session.id``).

    When ``LANGFUSE_CAPTURE_CONTENT=1`` is set, the prompt text passed as
    ``prompt`` and the ``completion`` key returned in the result dict are
    written to the span (truncated); otherwise they are not captured.
    """
    if not _otel_available:
        yield {}
        return
    tracer = _get_tracer()
    if tracer is None:
        yield {}
        return

    result: dict[str, Any] = {}
    span = tracer.start_span(
        "agent.llm_call",
        kind=SpanKind.CLIENT,
        attributes=agent_span_attributes(
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
            **{
                "gen_ai.operation.name": "chat",
                "gen_ai.system": provider,
                "gen_ai.request.model": model,
                "agent.turn_index": turn_index,
                # Langfuse OTLP ingestion requires this attribute to map the
                # span to the Langfuse data model as a generation.  gen_ai.*
                # alone is not mapped by all self-hosted versions.
                "langfuse.observation.type": "generation",
            },
        ),
    )
    if _env_flag("LANGFUSE_CAPTURE_CONTENT"):
        if prompt:
            span.set_attribute("gen_ai.prompt", prompt[:2000])
    try:
        with trace.use_span(span, end_on_exit=False):
            yield result
    except Exception:
        span.set_status(Status(StatusCode.ERROR))
        raise
    finally:
        if _env_flag("LANGFUSE_CAPTURE_CONTENT") and result.get("completion"):
            span.set_attribute("gen_ai.completion", result["completion"][:2000])
        if result.get("input_tokens") is not None:
            span.set_attribute("gen_ai.usage.input_tokens", result["input_tokens"])
        if result.get("output_tokens") is not None:
            span.set_attribute("gen_ai.usage.output_tokens", result["output_tokens"])
        if result.get("stop_reason"):
            span.set_attribute("gen_ai.response.finish_reasons", result["stop_reason"])
        # TTFT: completion_start_time for time-to-first-token calculation
        first_token_ts = result.get("first_token_time")
        if first_token_ts is not None:
            span.set_attribute(
                "gen_ai.response.first_token_time",
                datetime.datetime.fromtimestamp(
                    first_token_ts, tz=datetime.timezone.utc
                ).isoformat(),
            )
            span.set_attribute(
                "langfuse.observation.completion_start_time",
                datetime.datetime.fromtimestamp(
                    first_token_ts, tz=datetime.timezone.utc
                ).isoformat(),
            )
        # Langfuse-native usage_details (JSON) — needed for self-hosted v4.x
        # that does not auto-map gen_ai.usage.* to usageDetails.
        usage = {}
        if result.get("input_tokens") is not None:
            usage["input"] = result["input_tokens"]
        if result.get("output_tokens") is not None:
            usage["output"] = result["output_tokens"]
        if usage:
            span.set_attribute("langfuse.observation.usage_details", json.dumps(usage))
        span.end()
