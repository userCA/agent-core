"""Tests for truncation utilities."""

from __future__ import annotations

from agent_core.tools.truncate import format_size, truncate_head, truncate_line, truncate_tail


def test_truncate_tail():
    text = "a" * 100
    result = truncate_tail(text, 10)
    assert result.endswith("...")
    assert len(result) == 10


def test_truncate_head():
    text = "a" * 100
    result = truncate_head(text, 10)
    assert result.startswith("...")


def test_truncate_line():
    text = "\n".join([f"line{i}" for i in range(10)])
    result = truncate_line(text, 3)
    assert result.count("\n") == 3  # 3 lines + "..." on its own line
    assert result.endswith("...")


def test_format_size():
    assert format_size(512) == "512 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
    assert format_size(1024 * 1024 * 1024) == "1.0 GB"
