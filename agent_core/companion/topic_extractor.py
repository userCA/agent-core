"""Lightweight topic hint extraction — no LLM calls."""

from __future__ import annotations

_SKIP_WORDS = {"杀", "死", "炸", "黑", "破解", "攻击", "自杀", "赌博"}


def extract_topic_hint(prompt: str) -> str | None:
    """Extract a 4-12 char intent summary. Returns None if quality check fails."""
    cleaned = prompt.strip().replace("\n", " ")[:18]

    for w in _SKIP_WORDS:
        if w in cleaned:
            return None

    if len(cleaned) < 4:
        return None

    return cleaned[:12]
