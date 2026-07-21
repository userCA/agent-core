"""C4 single-representation check — one form per refId in LLM-bound context.

Detects forbidden co-presence for the same artifact refId, e.g.:
- ``artifact_ref`` envelope + residual ``inline_full`` body
- ``summary`` + ``preview`` lines inside the same envelope

DataBus system index (``## Artifact Ref Index``) is **not** treated as a
second body form — it is metadata pointing at inspectable refs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

SINGLE_REPRESENTATION_VIOLATION = "SINGLE_REPRESENTATION_VIOLATION"

RefForm = Literal["artifact_ref", "inline_full", "preview"]

_REF_ID_RE = re.compile(r"refId:\s*([0-9a-fA-F]{8,})", re.IGNORECASE)
_SUMMARY_LINE_RE = re.compile(r"(?m)^summary:\s")
_PREVIEW_LINE_RE = re.compile(r"(?m)^preview:\s")
_ENVELOPE_META_RE = re.compile(r"^(refId|chars|summary|preview|hint):\s?")


def _artifact_ref_block(text: str) -> str:
    """Return only the artifact_ref metadata block (not trailing content)."""
    start = text.find("[artifact_ref]")
    if start < 0:
        return ""
    lines: list[str] = []
    seen_hint = False
    for line in text[start:].splitlines():
        if not lines:
            lines.append(line)
            continue
        if seen_hint:
            break
        if _ENVELOPE_META_RE.match(line):
            lines.append(line)
            if line.startswith("hint:"):
                seen_hint = True
            continue
        break
    return "\n".join(lines)


# Forms that conflict when co-present for the same refId.
_CONFLICTING = frozenset({"artifact_ref", "inline_full", "preview"})


@dataclass(frozen=True)
class RepresentationViolation:
    ref_id: str
    forms: frozenset[str]
    detail: str


def _content_text(message: Any) -> str:
    role = getattr(message, "role", None)
    if role == "custom":
        return str(getattr(message, "content", "") or "")
    parts: list[str] = []
    for block in getattr(message, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts)


def _collect_forms_from_message(message: Any) -> dict[str, set[str]]:
    """Map ref_id → forms found in one message (LLM-bound content + details)."""
    found: dict[str, set[str]] = {}
    text = _content_text(message)
    details = getattr(message, "details", None)
    details_dict = details if isinstance(details, dict) else {}

    is_envelope = "[artifact_ref]" in text
    envelope_ids = set(_REF_ID_RE.findall(text)) if is_envelope else set()

    for rid in envelope_ids:
        found.setdefault(rid, set()).add("artifact_ref")
        block = _artifact_ref_block(text)
        if _SUMMARY_LINE_RE.search(block) and _PREVIEW_LINE_RE.search(block):
            found[rid].add("preview")

    ref_id = details_dict.get("__refId")
    if isinstance(ref_id, str) and ref_id:
        stored = bool(details_dict.get("__stored"))
        chars = details_dict.get("__chars")
        if stored and not is_envelope:
            # Marked externalized but content is still raw body.
            found.setdefault(ref_id, set()).add("inline_full")
        elif stored and is_envelope and isinstance(chars, int) and chars > 2000:
            # Envelope should be bounded; near-original size ⇒ body leaked back.
            if len(text) >= max(int(chars * 0.5), chars - 500):
                found.setdefault(ref_id, set()).add("inline_full")

    return found


def validate_single_representation(
    messages: list[Any],
    *,
    system_prompt: str = "",
) -> list[RepresentationViolation]:
    """Scan *messages* for same-refId multi-form violations.

    ``system_prompt`` is accepted for API symmetry (DataBus index is ignored
    as a conflicting form).
    """
    del system_prompt  # intentional: index is not a body form
    by_ref: dict[str, set[str]] = {}
    for msg in messages:
        for rid, forms in _collect_forms_from_message(msg).items():
            by_ref.setdefault(rid, set()).update(forms)

    violations: list[RepresentationViolation] = []
    for rid, forms in by_ref.items():
        conflicting = forms & _CONFLICTING
        # Stored raw body without envelope is itself illegal (expected: artifact_ref only).
        if forms == {"inline_full"}:
            detail = (
                f"{SINGLE_REPRESENTATION_VIOLATION}: refId={rid} "
                f"is marked __stored but content is not an artifact_ref envelope"
            )
            violations.append(
                RepresentationViolation(
                    ref_id=rid,
                    forms=frozenset(forms),
                    detail=detail,
                )
            )
            continue
        if len(conflicting) > 1:
            detail = (
                f"{SINGLE_REPRESENTATION_VIOLATION}: refId={rid} "
                f"has multiple forms {sorted(conflicting)}"
            )
            violations.append(
                RepresentationViolation(
                    ref_id=rid,
                    forms=frozenset(conflicting),
                    detail=detail,
                )
            )
    return violations


def check_single_representation(
    messages: list[Any],
    *,
    system_prompt: str = "",
    mode: Literal["off", "warn", "raise"] = "warn",
) -> tuple[bool, str]:
    """Apply *mode* to validation results.

    Returns ``(True, "")`` when the provider call may proceed, or
    ``(False, detail)`` when *mode* is ``raise`` and violations exist.
    """
    if mode == "off":
        return True, ""
    violations = validate_single_representation(
        messages, system_prompt=system_prompt
    )
    if not violations:
        return True, ""
    detail = "; ".join(v.detail for v in violations)
    if mode == "warn":
        logger.warning("Single-representation check: %s", detail)
        return True, ""
    return False, detail
