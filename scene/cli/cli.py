"""CLI entry point for the scene chat assistant."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

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
from agent_core.logging_config import configure_logging
from agent_core.session.jsonl_store import JsonlStore

from scene.cli.chat_assistant import ChatAssistant


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

class _OutputFormatter:
    """Terminal output formatter with colour support and think-block isolation."""

    def __init__(self, *, no_color: bool = False, show_think: bool = False) -> None:
        self._no_color = no_color or os.environ.get("NO_COLOR") is not None
        self._show_think = show_think
        self._in_think = False

    def _c(self, text: str, code: str) -> str:
        if self._no_color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def _dim(self, text: str) -> str:
        return self._c(text, "2")

    def _yellow(self, text: str) -> str:
        return self._c(text, "33")

    def _green(self, text: str) -> str:
        return self._c(text, "32")

    def _red(self, text: str) -> str:
        return self._c(text, "31")

    # ---- text / think -----------------------------------------------------

    def print_text_delta(self, text: str) -> None:
        """Handle a TextDelta, isolating <think>…</think> blocks."""
        while text:
            if self._in_think:
                end_idx = text.find("</think>")
                if end_idx != -1:
                    if self._show_think:
                        print(self._dim(text[:end_idx]), end="", flush=True)
                        print(self._dim("</think>"), end="", flush=True)
                    text = text[end_idx + len("</think>"):]
                    self._in_think = False
                else:
                    if self._show_think:
                        print(self._dim(text), end="", flush=True)
                    # else: silently drop think content
                    break
            else:
                start_idx = text.find("<think>")
                if start_idx != -1:
                    print(text[:start_idx], end="", flush=True)
                    text = text[start_idx + len("<think>"):]
                    self._in_think = True
                    if not self._show_think:
                        # Collapse: emit placeholder once when think starts
                        print(self._dim("<think> ... </think>"), end="", flush=True)
                else:
                    print(text, end="", flush=True)
                    break

    def print_thinking_delta(self, text: str) -> None:
        """Handle an explicit ThinkingDelta (e.g. Anthropic reasoning)."""
        if self._show_think:
            print(self._dim(text), end="", flush=True)
        # else: silently drop

    # ---- tool calls / results ---------------------------------------------

    def print_tool_call(self, name: str, args: dict) -> None:
        print(f"\n{self._yellow(f'[Tool: {name}]')}")
        for k, v in args.items():
            print(f"  {self._dim(f'{k}:')} {v}")
        print("")

    def print_tool_result(self, result: str, is_error: bool) -> None:
        prefix = self._red("[Error]") if is_error else self._green("[Result]")
        print(f"{prefix}")
        if len(result) > 500:
            print(result[:500])
            print(self._dim(f"  … ({len(result) - 500} more chars)"))
        else:
            print(result)
        print("")

    # ---- usage ------------------------------------------------------------

    def print_usage(self, usage: Any) -> None:
        total = (
            usage.input_tokens
            + usage.output_tokens
            + usage.cache_read_tokens
            + usage.cache_write_tokens
        )
        if total > 0:
            parts = [
                f"{usage.input_tokens} in",
                f"{usage.output_tokens} out",
            ]
            if usage.cache_read_tokens:
                parts.append(f"{usage.cache_read_tokens} cache-read")
            if usage.cache_write_tokens:
                parts.append(f"{usage.cache_write_tokens} cache-write")
            line = f"[Tokens: {' / '.join(parts)} | total {total}]"
            print(f"\n{self._dim(line)}", flush=True)


# ---------------------------------------------------------------------------
# Event handler factory
# ---------------------------------------------------------------------------

def _make_event_handler(fmt: _OutputFormatter) -> Callable[[AgentEvent], None]:
    from typing import Callable

    def _handler(evt: AgentEvent) -> None:
        if isinstance(evt, MessageUpdate):
            delta = evt.delta
            if isinstance(delta, TextDelta):
                fmt.print_text_delta(delta.text)
            elif isinstance(delta, ThinkingDelta):
                fmt.print_thinking_delta(delta.text)
            elif isinstance(delta, ToolCallDelta):
                # Tool call meta-data is surfaced via ToolExecutionStart/End
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
            if hasattr(msg, "error_message") and msg.error_message:
                print(f"\n{fmt._red('[Error]')} {msg.error_message}")
            if hasattr(msg, "usage") and msg.usage:
                fmt.print_usage(msg.usage)

    return _handler


# ---------------------------------------------------------------------------
# Argument parsing & main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scene Chat Assistant")
    parser.add_argument("--provider", default="openai", help="LLM provider (openai, anthropic, minimax)")
    parser.add_argument("--model", default="gpt-4o", help="Model ID")
    parser.add_argument("--api-key", default=None, help="API key (or set env var)")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Environment variable for API key")
    parser.add_argument("--session-dir", default="./sessions", help="Directory for JSONL session storage")
    parser.add_argument("--session-id", default=None, help="Session ID")
    parser.add_argument("--skills-dir", default=None, help="Additional skills directory")
    parser.add_argument("--system-prompt", default=None, help="Custom system prompt")
    parser.add_argument("--cwd", default=os.getcwd(), help="Working directory")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument("--one-shot", default=None, help="Single prompt mode (non-interactive)")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colours")
    parser.add_argument("--show-think", action="store_true", help="Show model reasoning / <think> blocks")
    return parser.parse_args()


async def run_interactive(assistant: ChatAssistant, fmt: _OutputFormatter) -> None:
    print("Scene Chat Assistant")
    print("Type 'exit' or 'quit' to leave.\n")

    assistant.on_event(_make_event_handler(fmt))

    while True:
        try:
            user_input = await asyncio.to_thread(input, "> ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        text = user_input.strip()
        if text.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        if not text:
            continue

        print("Assistant: ", end="", flush=True)
        await assistant.send_message(text)
        print("\n")


async def run_one_shot(assistant: ChatAssistant, prompt: str, fmt: _OutputFormatter) -> None:
    assistant.on_event(_make_event_handler(fmt))
    print("Assistant: ", end="", flush=True)
    await assistant.send_message(prompt)
    print("\n")


async def main() -> int:
    load_dotenv()
    args = parse_args()
    configure_logging(level=args.log_level)

    session_store = JsonlStore(args.session_dir)
    fmt = _OutputFormatter(no_color=args.no_color, show_think=args.show_think)

    assistant = await ChatAssistant.create(
        provider_name=args.provider,
        model_id=args.model,
        api_key=args.api_key,
        api_key_env=args.api_key_env,
        skills_dir=args.skills_dir,
        session_store=session_store,
        session_id=args.session_id,
        system_prompt=args.system_prompt,
        cwd=args.cwd,
    )

    # Print configuration summary
    model = assistant._agent.state.model
    print(f"Provider : {model.provider}")
    print(f"Model    : {model.id}")
    print(f"Tools    : {len(assistant.tool_names)} ({', '.join(assistant.tool_names[:5])}{'...' if len(assistant.tool_names) > 5 else ''})")
    print(f"Session  : {args.session_dir}")
    print(f"CWD      : {args.cwd}")
    print("")

    try:
        if args.one_shot:
            await run_one_shot(assistant, args.one_shot, fmt)
        else:
            await run_interactive(assistant, fmt)
    finally:
        await assistant.dispose()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
