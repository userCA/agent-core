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
import hashlib
import logging
import os
import uuid
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_pending_tool_spans: dict[str, Any] = {}

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
    attrs: dict[str, Any] = {
        "agent.session_id": session_id,
        "agent.run_id": run_id,
    }
    if session_id:
        attrs["session.id"] = session_id
        attrs["langfuse.session.id"] = session_id
    if run_id:
        attrs["langfuse.trace.metadata.run_id"] = run_id
    if user_id:
        attrs["user.id"] = user_id
    attrs.update({k: v for k, v in extra.items() if v is not None and v != ""})
    return attrs


def resolve_observe_user_id(harness: Any, user_id: str = "") -> str:
    """Resolve user.id for observability spans.

    Priority: 1) explicit ``user_id`` 2) ``harness.observability_user_id`` 3) ``harness.owner``.
    """
    # 为什么改:该函数被 session 层(harness/turn_runtime)跨模块复用,下划线私有命名违反约定,
    # 且 turn_runtime 内联重复实现了同一解析链,存在漂移风险
    # 会影响什么:对外改名 resolve_observe_user_id(原私有名不再存在);解析优先级与行为完全不变
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
    ``harness.add_after_tool_call_hook``.
    """
    if not _otel_available:
        yield
        return

    tracer = _get_tracer()
    if tracer is None:
        yield
        return

    resolved_user_id = resolve_observe_user_id(harness, user_id)

    # Register tracing hooks via public API, store references for cleanup
    tracing_before = _make_tracing_before_hook(
        tracer, session_id, run_id, provider_name, model_id, resolved_user_id,
    )
    tracing_after = _make_tracing_after_hook(tracer, run_id)

    harness.add_before_tool_call_hook(tracing_before)
    harness.add_after_tool_call_hook(tracing_after)

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
        _cleanup_pending_tool_spans(run_id)


def _apply_skill_activation_attributes(run_span: Any, harness: Any) -> None:
    activations = getattr(harness, "skill_activations", None)
    if not activations:
        return
    names = sorted({name for name, _ in activations})
    run_span.set_attribute("agent.skills.activated", ",".join(names))
    sources = ",".join(f"{name}:{source}" for name, source in activations)
    run_span.set_attribute("agent.skills.sources", sources)


def _make_tracing_before_hook(
    tracer: Any,
    session_id: str,
    run_id: str,
    provider_name: str,
    model_id: str,
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
                    "agent.provider": provider_name,
                    "agent.model": model_id,
                },
            ),
        )
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
        attributes=agent_span_attributes(
            session_id=session_id,
            run_id=run_id,
            **{"agent.turn_index": turn_index},
        ),
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
    user_id: str = "",
) -> Iterator[dict[str, Any]]:
    """Context manager for LLM streaming calls.

    Yields a mutable *result* dict.  Callers should populate it with
    ``input_tokens``, ``output_tokens`` and ``stop_reason`` after the
    stream completes so the span attributes carry full usage data.

    Span attributes follow OpenTelemetry GenAI semantic conventions
    (``gen_ai.*``, ``user.id``, ``session.id``).
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
            },
        ),
    )
    try:
        with trace.use_span(span, end_on_exit=False):
            yield result
    except Exception:
        span.set_status(Status(StatusCode.ERROR))
        raise
    finally:
        if result.get("input_tokens") is not None:
            span.set_attribute("gen_ai.usage.input_tokens", result["input_tokens"])
        if result.get("output_tokens") is not None:
            span.set_attribute("gen_ai.usage.output_tokens", result["output_tokens"])
        if result.get("stop_reason"):
            # 为什么改:OTel GenAI 语义约定定义 gen_ai.response.finish_reasons 为 string[](数组),原实现写入单个字符串,违反本提交宣称对齐的规范
            # 会影响什么:仅 LLM span 该属性值变为 ["stop"] 数组形式,供 Langfuse 等按约定解析,不影响 agent 循环逻辑
            span.set_attribute("gen_ai.response.finish_reasons", [result["stop_reason"]])
        span.end()
