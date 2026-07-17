"""Stream options cloning and patch semantics (aligned with TS harness)."""

from __future__ import annotations

import copy
from typing import Any


def clone_stream_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """Return a shallow copy of stream options; nested maps are shallow-copied."""
    if not options:
        return {}
    result = dict(options)
    if "headers" in result and result["headers"] is not None:
        result["headers"] = dict(result["headers"])
    if "metadata" in result and result["metadata"] is not None:
        result["metadata"] = dict(result["metadata"])
    return result


def apply_stream_options_patch(
    base: dict[str, Any],
    patch: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply a patch to stream options.

    Top-level keys present in *patch* replace or delete (``None`` deletes).
    ``headers`` / ``metadata`` patches merge by key; ``None`` value deletes a key.
    """
    result = clone_stream_options(base)
    if not patch:
        return result

    scalar_keys = (
        "transport",
        "timeout_ms",
        "max_retries",
        "max_retry_delay_ms",
        "cache_retention",
        "temperature",
        "max_tokens",
    )
    for key in scalar_keys:
        if key in patch:
            if patch[key] is None:
                result.pop(key, None)
            else:
                result[key] = patch[key]

    if "headers" in patch:
        if patch["headers"] is None:
            result.pop("headers", None)
        else:
            headers = dict(result.get("headers") or {})
            for key, value in patch["headers"].items():
                if value is None:
                    headers.pop(key, None)
                else:
                    headers[key] = value
            result["headers"] = headers or None

    if "metadata" in patch:
        if patch["metadata"] is None:
            result.pop("metadata", None)
        else:
            metadata = dict(result.get("metadata") or {})
            for key, value in patch["metadata"].items():
                if value is None:
                    metadata.pop(key, None)
                else:
                    metadata[key] = value
            result["metadata"] = metadata or None

    return result
