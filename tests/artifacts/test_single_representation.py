"""C4 single-representation validation tests."""

from __future__ import annotations

import pytest

from agent_core.compaction.single_representation import (
    SINGLE_REPRESENTATION_VIOLATION,
    check_single_representation,
    validate_single_representation,
)
from agent_core.core.content import TextContent
from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.loop import run_agent_loop
from agent_core.core.messages import ToolResultMessage, UserMessage
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from tests.conftest import FakeProvider, fake_model


def _envelope(ref_id: str, *, with_preview: bool = False) -> str:
    lines = [
        "[artifact_ref]",
        f"refId: {ref_id}",
        "chars: 9000",
        "summary: hello summary",
    ]
    if with_preview:
        lines.append("preview: hello raw prefix")
    lines.append("hint: Full content is stored externally under refId")
    return "\n".join(lines)


def test_clean_artifact_ref_passes():
    rid = "a" * 32
    msg = ToolResultMessage(
        tool_call_id="c1",
        tool_name="bash",
        content=[TextContent(text=_envelope(rid))],
        details={"__stored": True, "__refId": rid, "__chars": 9000},
        timestamp=0,
    )
    assert validate_single_representation([msg]) == []


def test_summary_plus_preview_in_envelope_violates():
    rid = "b" * 32
    msg = ToolResultMessage(
        tool_call_id="c1",
        tool_name="bash",
        content=[TextContent(text=_envelope(rid, with_preview=True))],
        details={"__stored": True, "__refId": rid, "__chars": 9000},
        timestamp=0,
    )
    viol = validate_single_representation([msg])
    assert len(viol) == 1
    assert viol[0].ref_id == rid
    assert "preview" in viol[0].forms
    assert "artifact_ref" in viol[0].forms


def test_stored_but_raw_body_violates():
    rid = "c" * 32
    body = "FULL BODY " * 500
    msg = ToolResultMessage(
        tool_call_id="c1",
        tool_name="bash",
        content=[TextContent(text=body)],
        details={"__stored": True, "__refId": rid, "__chars": len(body)},
        timestamp=0,
    )
    viol = validate_single_representation([msg])
    assert len(viol) == 1
    assert "inline_full" in viol[0].forms


def test_preview_outside_envelope_block_does_not_false_positive():
    rid = "f" * 32
    # Second content block has a "preview:" line that is not part of the envelope.
    msg = ToolResultMessage(
        tool_call_id="c1",
        tool_name="bash",
        content=[
            TextContent(text=_envelope(rid)),
            TextContent(text="preview: this is user-facing text, not metadata"),
        ],
        details={"__stored": True, "__refId": rid, "__chars": 9000},
        timestamp=0,
    )
    assert validate_single_representation([msg]) == []


def test_oversized_envelope_violates():
    rid = "g" * 32
    chars = 3000
    body_leaked = "X" * 2600
    envelope_text = (
        f"[artifact_ref]\nrefId: {rid}\nchars: {chars}\n"
        f"summary: s\nhint: h\n{body_leaked}"
    )
    msg = ToolResultMessage(
        tool_call_id="c1",
        tool_name="bash",
        content=[TextContent(text=envelope_text)],
        details={"__stored": True, "__refId": rid, "__chars": chars},
        timestamp=0,
    )
    viol = validate_single_representation([msg])
    assert len(viol) == 1
    assert "inline_full" in viol[0].forms


def test_off_mode_skips_check():
    rid = "h" * 32
    msg = ToolResultMessage(
        tool_call_id="c1",
        tool_name="bash",
        content=[TextContent(text=_envelope(rid, with_preview=True))],
        details={"__stored": True, "__refId": rid, "__chars": 9000},
        timestamp=0,
    )
    ok, detail = check_single_representation([msg], mode="off")
    assert ok is True
    assert detail == ""


def test_warn_mode_allows_provider_raise_blocks():
    rid = "d" * 32
    msg = ToolResultMessage(
        tool_call_id="c1",
        tool_name="bash",
        content=[TextContent(text=_envelope(rid, with_preview=True))],
        details={"__stored": True, "__refId": rid, "__chars": 9000},
        timestamp=0,
    )
    ok, _ = check_single_representation([msg], mode="warn")
    assert ok is True
    ok, detail = check_single_representation([msg], mode="raise")
    assert ok is False
    assert SINGLE_REPRESENTATION_VIOLATION in detail


@pytest.mark.asyncio
async def test_loop_raise_mode_skips_provider():
    rid = "e" * 32
    provider = FakeProvider()
    provider.queue_script([
        StreamTextDelta(text="should not run"),
        StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
    ])

    async def convert(msgs):
        return [{"role": "user", "content": "x"}]

    async def auth(_n):
        return ProviderAuth(api_key="k")

    events: list = []

    async def emit(evt):
        events.append(evt)

    bad = ToolResultMessage(
        tool_call_id="c1",
        tool_name="bash",
        content=[TextContent(text=_envelope(rid, with_preview=True))],
        details={"__stored": True, "__refId": rid, "__chars": 9000},
        timestamp=0,
    )
    context = AgentContext(system_prompt="", messages=[bad], tools=[])
    config = AgentLoopConfig(
        model=fake_model(),
        stream_fn=provider.stream,
        convert_to_llm=convert,
        auth_resolver=auth,
        prompt_budget_ratio=None,
        single_representation_mode="raise",
        duplicate_tool_max_repeats=None,
    )
    await run_agent_loop(
        [UserMessage(content=[TextContent(text="go")], timestamp=0)],
        context,
        config,
        emit,
    )
    assert provider.calls == []
    assistants = [
        e for e in events
        if getattr(e, "type", None) == "message_end"
        and getattr(getattr(e, "message", None), "role", None) == "assistant"
    ]
    assert assistants
    assert SINGLE_REPRESENTATION_VIOLATION in (
        getattr(assistants[-1].message, "error_message", "") or ""
    )
