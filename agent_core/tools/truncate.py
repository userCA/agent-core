"""Output truncation utilities for large tool results."""

from __future__ import annotations


def truncate_tail(text: str, max_chars: int, *, hint: str = "...") -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(hint)] + hint


def truncate_head(text: str, max_chars: int, *, hint: str = "...") -> str:
    if len(text) <= max_chars:
        return text
    return hint + text[len(text) - max_chars + len(hint):]


def truncate_line(text: str, max_lines: int, *, hint: str = "...") -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n" + hint


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
