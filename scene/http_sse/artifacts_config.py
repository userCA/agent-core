"""L1 artifact externalization flags for http_sse scene."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_SHARED_STORE: Any | None = None

# Align with converter tool_result_max_chars (4000): externalize at that
# boundary so there is no 4k–8k dead zone; keep summary under converter max.
_SCENE_CHAR_THRESHOLD = 4000
_SCENE_SUMMARY_CHARS = 3500


def artifacts_enabled() -> bool:
    return os.environ.get("ENABLE_ARTIFACTS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def shared_artifact_store() -> Any:
    """Process-wide InMemoryArtifactStore (MVP; lost on restart)."""
    global _SHARED_STORE
    if _SHARED_STORE is None:
        from agent_core.artifacts import InMemoryArtifactStore

        _SHARED_STORE = InMemoryArtifactStore()
    return _SHARED_STORE


def _parse_non_negative_int(raw: str, default: int, *, name: str) -> int:
    raw = raw.strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default
    if value < 0:
        logger.warning("Negative %s=%r; using default %s", name, raw, default)
        return default
    return value


def build_artifact_extension(
    *,
    char_threshold: int | None = None,
    summary_chars: int | None = None,
) -> tuple[Any, Any] | tuple[None, None]:
    """Return ``(store, extension)`` when enabled, else ``(None, None)``.

    Thresholds may be overridden via ``ARTIFACT_CHAR_THRESHOLD`` /
    ``ARTIFACT_SUMMARY_CHARS`` env vars.
    """
    if not artifacts_enabled():
        return None, None

    from agent_core.artifacts import create_artifact_extension

    thr = char_threshold
    if thr is None:
        thr = _parse_non_negative_int(
            os.environ.get("ARTIFACT_CHAR_THRESHOLD", ""),
            _SCENE_CHAR_THRESHOLD,
            name="ARTIFACT_CHAR_THRESHOLD",
        )
    summ = summary_chars
    if summ is None:
        summ = _parse_non_negative_int(
            os.environ.get("ARTIFACT_SUMMARY_CHARS", ""),
            _SCENE_SUMMARY_CHARS,
            name="ARTIFACT_SUMMARY_CHARS",
        )

    store = shared_artifact_store()
    _, ext = create_artifact_extension(
        store,
        char_threshold=thr,
        summary_chars=summ,
    )
    return store, ext
