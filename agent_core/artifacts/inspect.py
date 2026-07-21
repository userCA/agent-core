"""L4 Inspect tool — fetch slices from L1 ArtifactStore by refId."""

from __future__ import annotations

import json
import re
from typing import Any

from agent_core.artifacts.ref_index import ArtifactRefIndex
from agent_core.artifacts.store import ArtifactStore
from agent_core.core.content import TextContent
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult

FULL_INJECT_MAX = 4096
ENHANCED_SUMMARY_MAX = 1000
SEARCH_MAX_HITS = 20
SEARCH_SNIPPET = 200


def build_outline(text: str, *, max_lines: int = 40) -> str:
    """Deterministic structure sketch (lines / JSON keys / head markers)."""
    lines = text.splitlines()
    parts: list[str] = [
        f"chars={len(text)}",
        f"lines={len(lines)}",
    ]
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                keys = list(data.keys())[:30]
                parts.append(f"json_object_keys={keys}")
            elif isinstance(data, list):
                parts.append(f"json_array_len={len(data)}")
                if data and isinstance(data[0], dict):
                    parts.append(f"json_item0_keys={list(data[0].keys())[:20]}")
        except (TypeError, ValueError, json.JSONDecodeError):
            parts.append("json_parse=failed")
    # Heading-like / key=value lines
    markers: list[str] = []
    for i, line in enumerate(lines[: max_lines * 3]):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") or re.match(r"^[A-Za-z_][\w]*\s*[:=]", s) or s.endswith(":"):
            markers.append(f"L{i + 1}: {s[:120]}")
        if len(markers) >= max_lines:
            break
    if markers:
        parts.append("markers:")
        parts.extend(f"  {m}" for m in markers)
    else:
        head = "\n".join(lines[:12])
        parts.append("head:")
        parts.append(head[:600])
    return "\n".join(parts)


def enhanced_summary(text: str, *, limit: int = ENHANCED_SUMMARY_MAX) -> str:
    """Structure-preserving summary for bodies larger than FULL_INJECT_MAX."""
    outline = build_outline(text, max_lines=20)
    head = text[: min(300, len(text))]
    tail = text[-min(200, len(text)) :] if len(text) > 300 else ""
    body = (
        f"[enhanced_summary]\n"
        f"{outline}\n"
        f"--- head ---\n{head}\n"
        f"--- tail ---\n{tail}"
    )
    if len(body) <= limit:
        return body
    return body[: limit - 1] + "…"


def apply_fetch_budget(
    text: str,
    *,
    budget_chars: int | None = None,
    prefer_full: bool = True,
) -> tuple[str, str]:
    """Return (payload, degradation_level).

    Levels: ``full`` | ``summary`` | ``truncated``.
    Degradation order (MVP): full → enhanced summary → hard truncate.
    """
    limit = budget_chars if budget_chars is not None else FULL_INJECT_MAX
    if prefer_full and len(text) <= min(limit, FULL_INJECT_MAX):
        return text, "full"
    if len(text) <= limit:
        return text, "full"

    summary = enhanced_summary(text, limit=min(ENHANCED_SUMMARY_MAX, limit))
    if len(summary) <= limit:
        return summary, "summary"
    return summary[: max(0, limit - 1)] + "…", "truncated"


def search_text(text: str, query: str, *, max_hits: int = SEARCH_MAX_HITS) -> list[dict[str, Any]]:
    if not query:
        return []
    hits: list[dict[str, Any]] = []
    # Case-insensitive line search
    q = query.lower()
    for i, line in enumerate(text.splitlines()):
        if q in line.lower():
            snippet = line.strip()
            if len(snippet) > SEARCH_SNIPPET:
                pos = snippet.lower().find(q)
                start = max(0, pos - 40)
                snippet = ("…" if start else "") + snippet[start : start + SEARCH_SNIPPET] + "…"
            hits.append({"line": i + 1, "snippet": snippet})
            if len(hits) >= max_hits:
                break
    return hits


class InspectArtifactTool:
    """L4 DataBus inspect chain over L1 ArtifactStore."""

    def __init__(
        self,
        *,
        store: ArtifactStore,
        ref_index: ArtifactRefIndex,
        session_id: str,
        name: str = "inspect_artifact",
    ) -> None:
        self._store = store
        self._index = ref_index
        self._session_id = session_id
        self.definition = ToolDefinition(
            name=name,
            description=(
                "Inspect externally stored tool results (artifact_ref). "
                "action=list_refs: catalog known refIds for this session. "
                "action=outline: structure sketch for a refId. "
                "action=search: find lines matching query inside a ref. "
                "action=get_context: fetch full text (≤4096) or enhanced summary; "
                "optional budget_chars for further truncation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list_refs", "outline", "search", "get_context"],
                    },
                    "ref_id": {"type": "string"},
                    "query": {"type": "string"},
                    "budget_chars": {
                        "type": "integer",
                        "description": "Max chars to return for get_context (degrades full→summary→truncate)",
                    },
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["action"],
            },
            prompt_snippet=(
                "When you see [artifact_ref], use inspect_artifact to outline/search/"
                "get_context by refId instead of inventing missing content."
            ),
        )

    async def execute(
        self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        action = str(params.get("action") or "").strip()
        if action == "list_refs":
            return self._list_refs()
        ref_id = str(params.get("ref_id") or "").strip()
        if not ref_id:
            return self._error("ref_id is required for this action")
        # Session isolation: only allow refs registered for this session.
        if self._index.get(self._session_id, ref_id) is None:
            return self._error(f"refId not found: {ref_id}")
        art = await self._store.get(ref_id)
        if art is None:
            return self._error(f"refId not found: {ref_id}")

        if action == "outline":
            text = build_outline(art.content)
            return ToolResult(
                content=[TextContent(text=text)],
                details={"inspect": {"action": action, "ref_id": ref_id}},
            )
        if action == "search":
            query = str(params.get("query") or "")
            hits = search_text(art.content, query)
            payload = json.dumps(
                {"ref_id": ref_id, "query": query, "hits": hits, "hit_count": len(hits)},
                ensure_ascii=False,
            )
            return ToolResult(
                content=[TextContent(text=payload)],
                details={"inspect": {"action": action, "ref_id": ref_id, "hit_count": len(hits)}},
            )
        if action == "get_context":
            return self._get_context(art.content, ref_id, params)
        return self._error(f"unknown action: {action}")

    def _list_refs(self) -> ToolResult:
        entries = self._index.list_for_session(self._session_id)
        rows = [
            {
                "ref_id": e.ref_id,
                "chars": e.chars,
                "tool_name": e.tool_name,
                "summary": e.summary,
            }
            for e in entries
        ]
        payload = json.dumps({"refs": rows, "count": len(rows)}, ensure_ascii=False)
        return ToolResult(
            content=[TextContent(text=payload)],
            details={"inspect": {"action": "list_refs", "count": len(rows)}},
        )

    def _get_context(
        self, content: str, ref_id: str, params: dict[str, Any]
    ) -> ToolResult:
        start = params.get("start_line")
        end = params.get("end_line")
        slice_text = content
        if start is not None or end is not None:
            lines = content.splitlines()
            if start is not None:
                s = max(0, int(start) - 1)
            else:
                s = 0
            e = int(end) if end is not None else len(lines)
            e = max(s, min(e, len(lines)))
            slice_text = "\n".join(lines[s:e])

        budget = params.get("budget_chars")
        budget_i = int(budget) if budget is not None else None
        payload, level = apply_fetch_budget(slice_text, budget_chars=budget_i)
        return ToolResult(
            content=[TextContent(text=payload)],
            details={
                "inspect": {
                    "action": "get_context",
                    "ref_id": ref_id,
                    "degradation": level,
                    "source_chars": len(slice_text),
                    "returned_chars": len(payload),
                }
            },
        )

    def _error(self, message: str) -> ToolResult:
        return ToolResult(content=[TextContent(text=message)])
