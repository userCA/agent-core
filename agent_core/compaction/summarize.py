"""Deterministic structured handoff summary for L3 compaction."""

from __future__ import annotations

import re
from typing import Any

_REF_ID_RE = re.compile(r"refId:\s*([0-9a-fA-F]{8,})")


def _msg_text(message: Any) -> str:
    role = getattr(message, "role", None)
    if role == "custom":
        return str(getattr(message, "content", "") or "")
    parts: list[str] = []
    for c in getattr(message, "content", []) or []:
        text = getattr(c, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
        name = getattr(c, "name", None)
        if name:
            parts.append(f"[tool_call:{name}]")
    return "\n".join(parts)


def _clip(text: str, limit: int = 240) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def structured_handoff_summary(
    messages: list[Any],
    *,
    instructions: str | None = None,
) -> str:
    """Build a structured compaction handoff (no LLM).

    Sections:
    1. User request
    2. Execution history (roles + clipped text / tool names)
    3. Artifact ref index
    4. Optional extra instructions
    """
    user_request = ""
    history_lines: list[str] = []
    ref_ids: list[str] = []
    seen_refs: set[str] = set()

    for m in messages:
        role = getattr(m, "role", None) or "unknown"
        text = _msg_text(m)
        if role == "user" and not user_request and text:
            user_request = _clip(text, 400)

        if role == "assistant":
            tool_names = [
                getattr(c, "name", "")
                for c in getattr(m, "content", []) or []
                if getattr(c, "type", None) == "tool_call" or getattr(c, "name", None)
            ]
            tool_names = [n for n in tool_names if n]
            label = f"assistant tools={','.join(tool_names)}" if tool_names else "assistant"
            history_lines.append(f"- {label}: {_clip(text) if text else '(no text)'}")
        elif role == "tool_result":
            name = getattr(m, "tool_name", None) or "tool"
            history_lines.append(f"- tool_result[{name}]: {_clip(text)}")
            details = getattr(m, "details", None)
            if isinstance(details, dict):
                rid = details.get("__refId")
                if isinstance(rid, str) and rid and rid not in seen_refs:
                    seen_refs.add(rid)
                    ref_ids.append(rid)
            for match in _REF_ID_RE.findall(text):
                if match not in seen_refs:
                    seen_refs.add(match)
                    ref_ids.append(match)
        elif role == "user":
            history_lines.append(f"- user: {_clip(text)}")
        elif role == "custom":
            history_lines.append(f"- custom: {_clip(text)}")

    sections = [
        "## Compaction handoff",
        "### 1. User request",
        user_request or "(unknown)",
        "### 2. Execution history",
        "\n".join(history_lines) if history_lines else "(none)",
        "### 3. Abandoned paths",
        "(none recorded)",
        "### 4. Artifact ref index",
        ", ".join(ref_ids) if ref_ids else "(none)",
    ]
    if instructions:
        sections.extend(["### 5. Extra instructions", instructions.strip()])
    return "\n".join(sections)
