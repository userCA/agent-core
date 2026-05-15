"""End-to-end validation of ChatAssistant with Minimax API."""

from __future__ import annotations

import asyncio
import os
import tempfile

from dotenv import load_dotenv

from agent_core.core.events import (
    AgentEvent,
    MessageEnd,
    MessageUpdate,
    TextDelta,
    ThinkingDelta,
    ToolCallDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from agent_core.session.jsonl_store import JsonlStore
from scene.cli.chat_assistant import ChatAssistant


load_dotenv()


# Re-use the same formatting rules as the CLI so tests mirror real usage.
class _TestFormatter:
    """Minimal formatter for test output (no ANSI colours)."""

    def __init__(self) -> None:
        self._in_think = False

    def _dim(self, text: str) -> str:
        return text

    def print_text_delta(self, text: str) -> None:
        while text:
            if self._in_think:
                end_idx = text.find("</think>")
                if end_idx != -1:
                    print(self._dim(text[:end_idx]), end="", flush=True)
                    print(self._dim("</think>"), end="", flush=True)
                    text = text[end_idx + len("</think>"):]
                    self._in_think = False
                else:
                    print(self._dim(text), end="", flush=True)
                    break
            else:
                start_idx = text.find("<think>")
                if start_idx != -1:
                    print(text[:start_idx], end="", flush=True)
                    print(self._dim("<think>"), end="", flush=True)
                    text = text[start_idx + len("<think>"):]
                    self._in_think = True
                else:
                    print(text, end="", flush=True)
                    break

    def print_thinking_delta(self, text: str) -> None:
        print(self._dim(text), end="", flush=True)

    def print_tool_call(self, name: str, args: dict) -> None:
        print(f"\n[Tool: {name}]")
        for k, v in args.items():
            print(f"  {k}: {v}")
        print("")

    def print_tool_result(self, result: str, is_error: bool) -> None:
        prefix = "[Error]" if is_error else "[Result]"
        print(f"{prefix}")
        if len(result) > 500:
            print(result[:500])
            print(f"  … ({len(result) - 500} more chars)")
        else:
            print(result)
        print("")

    def print_usage(self, usage: Any) -> None:
        total = (
            usage.input_tokens
            + usage.output_tokens
            + usage.cache_read_tokens
            + usage.cache_write_tokens
        )
        if total > 0:
            parts = [f"{usage.input_tokens} in", f"{usage.output_tokens} out"]
            if usage.cache_read_tokens:
                parts.append(f"{usage.cache_read_tokens} cache-read")
            if usage.cache_write_tokens:
                parts.append(f"{usage.cache_write_tokens} cache-write")
            print(f"  [Tokens: {' / '.join(parts)} | total {total}]")


def _make_handler() -> tuple[list[AgentEvent], callable]:
    events: list[AgentEvent] = []
    fmt = _TestFormatter()

    def handler(evt: AgentEvent) -> None:
        events.append(evt)
        if isinstance(evt, MessageUpdate):
            delta = evt.delta
            if isinstance(delta, TextDelta):
                fmt.print_text_delta(delta.text)
            elif isinstance(delta, ThinkingDelta):
                fmt.print_thinking_delta(delta.text)
            elif isinstance(delta, ToolCallDelta):
                pass
        elif isinstance(evt, ToolExecutionStart):
            fmt.print_tool_call(evt.tool_name, evt.args)
        elif isinstance(evt, ToolExecutionEnd):
            text = ""
            if evt.result.content and len(evt.result.content) > 0:
                text = evt.result.content[0].text
            fmt.print_tool_result(text, evt.is_error)
        elif isinstance(evt, MessageEnd):
            msg = evt.message
            if hasattr(msg, "usage") and msg.usage:
                fmt.print_usage(msg.usage)

    return events, handler


async def test_minimax_simple_message() -> None:
    """Test basic streaming conversation with Minimax."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY not set in environment")

    with tempfile.TemporaryDirectory() as tmpdir:
        assistant = await ChatAssistant.create(
            provider_name="minimax",
            model_id="minimax-m2.7",
            api_key=api_key,
            session_store=JsonlStore(tmpdir),
            system_prompt="You are a helpful assistant. Keep answers brief.",
        )

        events, handler = _make_handler()
        assistant.on_event(handler)

        print("User: 你好，请介绍一下你自己")
        print("Assistant: ", end="", flush=True)
        await assistant.send_message("你好，请介绍一下你自己")
        print("\n")

        text_parts = [
            e.delta.text
            for e in events
            if isinstance(e, MessageUpdate) and isinstance(e.delta, TextDelta)
        ]
        full_text = "".join(text_parts)
        assert len(full_text) > 0, "Expected non-empty response from Minimax"

        # Verify token usage was reported
        usage_ends = [
            e for e in events
            if isinstance(e, MessageEnd) and hasattr(e.message, "usage")
        ]
        assert len(usage_ends) > 0, "Expected MessageEnd with usage"
        total_tokens = usage_ends[0].message.usage.total_tokens
        assert total_tokens > 0, f"Expected positive token usage, got {total_tokens}"

        print(f"[PASS] Simple message — {len(full_text)} chars, {total_tokens} tokens")
        await assistant.dispose()


async def test_minimax_tool_call() -> None:
    """Test tool calling with Minimax (listing current directory)."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY not set in environment")

    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "test_file.txt"), "w") as f:
            f.write("hello")

        assistant = await ChatAssistant.create(
            provider_name="minimax",
            model_id="minimax-m2.7",
            api_key=api_key,
            session_store=JsonlStore(tmpdir),
            cwd=tmpdir,
            system_prompt=(
                "You are a helpful assistant with access to file tools. "
                "When asked about files or directories, use the available tools."
            ),
        )

        events, handler = _make_handler()
        assistant.on_event(handler)

        prompt = f"请列出 {tmpdir} 目录下的所有文件"
        print(f"User: {prompt}")
        print("Assistant: ", end="", flush=True)
        await assistant.send_message(prompt)
        print("\n")

        tool_starts = [e for e in events if isinstance(e, ToolExecutionStart)]
        tool_ends = [e for e in events if isinstance(e, ToolExecutionEnd)]

        assert len(tool_starts) > 0, "Expected at least one tool call"
        assert len(tool_ends) > 0, "Expected at least one tool result"
        assert any(e.tool_name == "ls" for e in tool_starts), "Expected ls tool call"

        # Verify token usage was reported for the tool-turn as well
        usage_ends = [
            e for e in events
            if isinstance(e, MessageEnd) and hasattr(e.message, "usage")
        ]
        total_tokens = sum(e.message.usage.total_tokens for e in usage_ends)
        assert total_tokens > 0, "Expected positive token usage across turns"

        print(f"[PASS] Tool call — {len(tool_starts)} tool(s), {total_tokens} tokens")
        await assistant.dispose()


async def main() -> int:
    print("=" * 50)
    print("Minimax E2E Validation")
    print("=" * 50)

    await test_minimax_simple_message()
    print()
    await test_minimax_tool_call()

    print()
    print("=" * 50)
    print("All tests passed!")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    asyncio.run(main())
