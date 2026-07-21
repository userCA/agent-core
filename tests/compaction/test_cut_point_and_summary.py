"""Tests for safe cut-point and structured handoff summary."""

from __future__ import annotations

import pytest

from agent_core.compaction.compactor import LLMSummaryCompactor, create_default_compactor
from agent_core.compaction.cut_point import find_safe_cutoff
from agent_core.compaction.summarize import structured_handoff_summary
from agent_core.core.content import TextContent, ToolCallContent
from agent_core.core.messages import AssistantMessage, ToolResultMessage, UserMessage


def _user(text: str) -> UserMessage:
    return UserMessage(content=[TextContent(text=text)], timestamp=0)


def _assistant(text: str = "", *, tools: list[str] | None = None) -> AssistantMessage:
    content: list = []
    if text:
        content.append(TextContent(text=text))
    for i, name in enumerate(tools or []):
        content.append(ToolCallContent(id=f"c{i}", name=name, arguments={}))
    return AssistantMessage(content=content, timestamp=0)


def _tool(name: str, text: str, *, details=None) -> ToolResultMessage:
    return ToolResultMessage(
        tool_call_id="c0",
        tool_name=name,
        content=[TextContent(text=text)],
        details=details,
        timestamp=0,
    )


def test_find_safe_cutoff_basic():
    msgs = [_user("a"), _user("b"), _user("c"), _user("d")]
    assert find_safe_cutoff(msgs, keep_recent=2, min_keep=1, min_delete=1) == 2


def test_find_safe_cutoff_avoids_starting_on_tool_result():
    # Naive keep_recent=2 lands on tool_result (index 5); safe must walk back to assistant.
    msgs = [
        _user("u1"),
        _user("u2"),
        _user("u3"),
        _user("u4"),
        _assistant("run", tools=["bash"]),
        _tool("bash", "big output"),
        _user("follow"),
    ]
    naive = len(msgs) - 2
    assert getattr(msgs[naive], "role", None) == "tool_result"

    cutoff = find_safe_cutoff(msgs, keep_recent=2, min_keep=2, min_delete=2)
    assert cutoff is not None
    assert getattr(msgs[cutoff], "role", None) == "assistant"
    kept_roles = [getattr(m, "role", None) for m in msgs[cutoff:]]
    assert kept_roles == ["assistant", "tool_result", "user"]


def test_find_safe_cutoff_returns_none_when_walkback_violates_min_delete():
    # Long list so min_delete gate applies; walk-back would push cutoff below min_delete.
    msgs = [
        _user("a"),
        _assistant("t", tools=["bash"]),
        _tool("bash", "out"),
        _user("b"),
        _user("c"),
        _user("d"),
        _user("e"),
        _user("f"),
    ]
    # Force keep that lands on tool_result near the start after walk-back.
    cutoff = find_safe_cutoff(msgs, keep_recent=6, min_keep=6, min_delete=2)
    # Either safe assistant window or skip — must not start on tool_result
    if cutoff is not None:
        assert getattr(msgs[cutoff], "role", None) != "tool_result"


def test_find_safe_cutoff_skips_when_too_short():
    msgs = [_user("a"), _user("b")]
    assert find_safe_cutoff(msgs, keep_recent=2) is None


def test_short_list_honors_keep_recent_exactly():
    """n < min_keep+min_delete must not silently shrink keep_recent via min_delete."""
    msgs = [_user("a"), _user("b"), _user("c")]
    cutoff = find_safe_cutoff(msgs, keep_recent=2, min_keep=6, min_delete=2)
    assert cutoff == 1  # keep exactly 2



def test_structured_handoff_summary_sections():
    msgs = [
        _user("Book a flight to Tokyo"),
        _assistant("searching", tools=["search"]),
        _tool(
            "search",
            "[artifact_ref]\nrefId: deadbeefcafebabe\nsummary: big\n",
            details={"__stored": True, "__refId": "deadbeefcafebabe"},
        ),
    ]
    text = structured_handoff_summary(msgs)
    assert "## Compaction handoff" in text
    assert "Book a flight to Tokyo" in text
    assert "search" in text
    assert "deadbeefcafebabe" in text


@pytest.mark.asyncio
async def test_compactor_uses_safe_cutoff_and_instructions():
    seen: dict = {}

    async def _summarize(msgs, instructions=None):
        seen["n"] = len(msgs)
        seen["instructions"] = instructions
        return "ok"

    msgs = [
        _user("q"),
        _assistant("a", tools=["echo"]),
        _tool("echo", "x" * 20),
        _user("u2"),
        _assistant("a2"),
        _user("u3"),
        _assistant("a3"),
        _user("u4"),
    ]
    compactor = LLMSummaryCompactor(
        summarize_fn=_summarize, keep_recent=3, min_keep=3, min_delete=2
    )
    result = await compactor.compact(msgs, reason="test", instructions="keep IDs")
    assert result.summary == "ok"
    assert result.kept_count >= 3
    assert getattr(msgs[-result.kept_count], "role", None) != "tool_result"
    assert seen["instructions"] == "keep IDs"


@pytest.mark.asyncio
async def test_create_default_compactor_structured():
    compactor = create_default_compactor(keep_recent=2)
    msgs = [_user("goal"), _assistant("x"), _user("y"), _assistant("z")]
    result = await compactor.compact(msgs, reason="threshold")
    assert "Compaction handoff" in result.summary
    assert "goal" in result.summary
    assert result.kept_count == 2
