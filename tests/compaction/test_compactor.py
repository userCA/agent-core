import pytest

from agent_core.compaction.compactor import LLMSummaryCompactor
from agent_core.compaction.strategies import estimate_tokens, total_tokens
from agent_core.core.messages import UserMessage
from agent_core.core.content import TextContent


def test_estimate_tokens():
    msg = UserMessage(content=[TextContent(text="hello world")], timestamp=0)
    tokens = estimate_tokens(msg)
    assert tokens > 0


def test_total_tokens():
    msgs = [
        UserMessage(content=[TextContent(text="a" * 400)], timestamp=0),
        UserMessage(content=[TextContent(text="b" * 400)], timestamp=0),
    ]
    assert total_tokens(msgs) == sum(estimate_tokens(m) for m in msgs)


@pytest.mark.asyncio
async def test_llm_summary_compactor_should_compact():
    async def _summarize(msgs):
        return "summary"

    compactor = LLMSummaryCompactor(
        summarize_fn=_summarize, threshold=0.5, keep_recent=2
    )
    # empty -> no
    assert not compactor.should_compact([], context_window=1000)

    # short -> no
    msgs = [UserMessage(content=[TextContent(text="hi")], timestamp=0)]
    assert not compactor.should_compact(msgs, context_window=10000)

    # long -> yes
    msgs = [UserMessage(content=[TextContent(text="x" * 4000)], timestamp=0)]
    assert compactor.should_compact(msgs, context_window=1000)


@pytest.mark.asyncio
async def test_llm_summary_compactor_compact():
    async def _summarize(msgs):
        return f"summarized {len(msgs)} messages"

    compactor = LLMSummaryCompactor(
        summarize_fn=_summarize, threshold=0.8, keep_recent=2
    )
    msgs = [
        UserMessage(content=[TextContent(text="a")], timestamp=0),
        UserMessage(content=[TextContent(text="b")], timestamp=0),
        UserMessage(content=[TextContent(text="c")], timestamp=0),
        UserMessage(content=[TextContent(text="d")], timestamp=0),
    ]
    result = await compactor.compact(msgs, reason="threshold")

    assert result.summary == "summarized 2 messages"
    assert result.first_kept_entry_id == ""
    assert result.tokens_before > 0
    assert result.tokens_after >= 0


@pytest.mark.asyncio
async def test_llm_summary_compactor_no_summarize_fn():
    compactor = LLMSummaryCompactor(summarize_fn=None, keep_recent=2)
    msgs = [
        UserMessage(content=[TextContent(text="a")], timestamp=0),
        UserMessage(content=[TextContent(text="b")], timestamp=0),
        UserMessage(content=[TextContent(text="c")], timestamp=0),
    ]
    result = await compactor.compact(msgs, reason="threshold")
    assert result.summary == ""
