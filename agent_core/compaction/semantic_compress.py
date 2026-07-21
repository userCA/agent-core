"""L2 SemanticCompress — distill oversized tool results to a bounded summary.

Full body remains in L1 ArtifactStore. This module only produces the
LLM-visible summary. On LLM failure (or when no ``compress_fn`` is wired),
uses structured fallback truncation — never bare substring alone for the
L2 path.

Pitfall (agent engineering): preview / prefix matching must use the raw
original ``substring``, never an LLM-rewritten preview.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

logger = logging.getLogger(__name__)

DEFAULT_COMPRESS_MIN_CHARS = 10_000
DEFAULT_TARGET_CHARS = 2_000
DEFAULT_FALLBACK_HEAD_CHARS = 3_000
DEFAULT_PREVIEW_CHARS = 200

CompressFn = Callable[..., Awaitable[str]]


class SupportsCompress(Protocol):
    async def __call__(
        self,
        text: str,
        *,
        target_chars: int,
        tool_name: str,
    ) -> str: ...


@dataclass(frozen=True)
class CompressResult:
    """Outcome of L2 compression for one tool result body."""

    summary: str
    method: str  # "llm" | "fallback" | "substring"
    preview: str  # raw original prefix — never LLM-rewritten
    fallback_truncated: bool


def raw_preview(text: str, *, preview_chars: int = DEFAULT_PREVIEW_CHARS) -> str:
    """Deterministic prefix for matching / audit (not for LLM rewrite)."""
    if preview_chars <= 0:
        return ""
    return text[:preview_chars]


def structured_fallback_compress(
    text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    head_chars: int = DEFAULT_FALLBACK_HEAD_CHARS,
) -> str:
    """JSON-wrapped head truncation with ``__fallbackTruncated``.

    Always returns valid JSON whose length is ≤ ``target_chars`` (raises the
    effective floor to a minimal valid envelope when ``target_chars`` is tiny).
    """
    minimal = json.dumps(
        {
            "__fallbackTruncated": True,
            "chars": len(text),
            "head": "",
            "note": "truncated",
        },
        ensure_ascii=False,
    )
    effective_target = max(target_chars, len(minimal))

    head_budget = min(head_chars, len(text), max(0, effective_target - len(minimal)))
    while True:
        head = text[:head_budget]
        payload: dict[str, Any] = {
            "__fallbackTruncated": True,
            "chars": len(text),
            "head": head,
            "note": "Structured truncation; full body available via artifact refId.",
        }
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded) <= effective_target:
            return encoded
        if head_budget <= 0:
            # Shorten note until minimal envelope fits.
            payload["note"] = "truncated"
            encoded = json.dumps(payload, ensure_ascii=False)
            if len(encoded) <= effective_target:
                return encoded
            return minimal
        overflow = len(encoded) - effective_target
        head_budget = max(0, head_budget - max(overflow, head_budget // 4 or 1))


async def semantic_compress(
    text: str,
    *,
    compress_fn: CompressFn | None = None,
    tool_name: str = "",
    target_chars: int = DEFAULT_TARGET_CHARS,
    compress_min_chars: int = DEFAULT_COMPRESS_MIN_CHARS,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    fallback_head_chars: int = DEFAULT_FALLBACK_HEAD_CHARS,
) -> CompressResult:
    """Compress *text* when at/above ``compress_min_chars``.

    Below the threshold, returns a raw substring summary (L1-style).
    At/above: try ``compress_fn``, else structured fallback.
    """
    preview = raw_preview(text, preview_chars=preview_chars)

    if len(text) < compress_min_chars:
        summary = text[:target_chars]
        return CompressResult(
            summary=summary,
            method="substring",
            preview=preview,
            fallback_truncated=False,
        )

    if compress_fn is not None:
        try:
            summary = await compress_fn(
                text,
                target_chars=target_chars,
                tool_name=tool_name,
            )
            if not isinstance(summary, str):
                raise TypeError("compress_fn must return str")
            summary = summary.strip()
            if len(summary) > target_chars:
                summary = summary[:target_chars]
            if summary:
                return CompressResult(
                    summary=summary,
                    method="llm",
                    preview=preview,
                    fallback_truncated=False,
                )
        except Exception as exc:
            logger.warning("L2 compress_fn failed; using structured fallback: %s", exc)

    summary = structured_fallback_compress(
        text,
        target_chars=target_chars,
        head_chars=fallback_head_chars,
    )
    return CompressResult(
        summary=summary,
        method="fallback",
        preview=preview,
        fallback_truncated=True,
    )
