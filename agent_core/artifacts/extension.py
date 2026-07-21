"""Extension that externalizes oversized tool results into an ArtifactStore."""

from __future__ import annotations

from typing import Any

from agent_core.artifacts.store import ArtifactStore
from agent_core.core.content import TextContent
from agent_core.extensions.base import ExtensionContext

DEFAULT_CHAR_THRESHOLD = 8000
DEFAULT_SUMMARY_CHARS = 2000
_HINT = "Full content is stored externally under refId; do not invent missing data."


def _extract_text(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def format_artifact_ref_message(
    *,
    ref_id: str,
    chars: int,
    summary: str,
    hint: str = _HINT,
) -> str:
    return (
        "[artifact_ref]\n"
        f"refId: {ref_id}\n"
        f"chars: {chars}\n"
        f"summary: {summary}\n"
        f"hint: {hint}"
    )


class ArtifactExternalizeExtension:
    """Replace oversized tool results with artifact_ref + bounded summary (L1).

    Full body lives in *store*; transcript / LLM context keep a single ref representation.
    Skips error results and results already marked ``__stored``.

    ``summary_chars`` should stay well below ``tool_result_max_chars`` (default 4000)
    so the converter does not re-truncate the artifact_ref envelope.
    """

    name = "artifact_externalize"

    def __init__(
        self,
        store: ArtifactStore,
        *,
        char_threshold: int = DEFAULT_CHAR_THRESHOLD,
        summary_chars: int = DEFAULT_SUMMARY_CHARS,
    ) -> None:
        self._store = store
        self._char_threshold = char_threshold
        self._summary_chars = summary_chars

    async def on_after_tool_call(
        self,
        ctx: ExtensionContext,
        tool_call: Any,
        result: Any,
        is_error: bool,
    ) -> dict[str, Any] | None:
        if is_error:
            return None

        details = getattr(result, "details", None)
        if isinstance(details, dict) and details.get("__stored"):
            return None

        text = _extract_text(result)
        if len(text) <= self._char_threshold:
            return None

        tool_name = getattr(tool_call, "name", None) or ""
        tool_call_id = getattr(tool_call, "id", None) or ""
        ref_id = await self._store.put(
            text,
            meta={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "chars": len(text),
                "session_id": ctx.session_id,
            },
        )
        summary = text[: self._summary_chars]
        ref_text = format_artifact_ref_message(
            ref_id=ref_id,
            chars=len(text),
            summary=summary,
        )
        meta = {
            "__stored": True,
            "__refId": ref_id,
            "__summary": summary,
            "__chars": len(text),
            "__hint": _HINT,
        }
        # Preserve existing top-level keys (exit_code, plan, urls, …).
        if isinstance(details, dict):
            new_details = {**details, **meta}
        else:
            new_details = dict(meta)
            if details is not None:
                new_details["original_details"] = details

        return {
            "result": {
                "content": [TextContent(text=ref_text)],
                "details": new_details,
                "display": getattr(result, "display", None),
            }
        }


def create_artifact_extension(
    store: ArtifactStore | None = None,
    *,
    char_threshold: int = DEFAULT_CHAR_THRESHOLD,
    summary_chars: int = DEFAULT_SUMMARY_CHARS,
) -> tuple[ArtifactStore, ArtifactExternalizeExtension]:
    """Return (store, extension) ready to append to Harness ``extensions``."""
    from agent_core.artifacts.store import InMemoryArtifactStore

    resolved: ArtifactStore = store if store is not None else InMemoryArtifactStore()
    ext = ArtifactExternalizeExtension(
        resolved,
        char_threshold=char_threshold,
        summary_chars=summary_chars,
    )
    return resolved, ext
