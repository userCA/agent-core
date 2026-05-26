# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`agent-core` is a general-purpose Python agent framework. It provides a library-level runtime for streaming LLM interaction, tool execution, session persistence, context compaction, and extension hooks. It is **not** a service — consumers build their own runtimes (FastAPI, CLI, notebook, etc.) on top of it.

The codebase is a Python re-implementation of the TypeScript `pi-mono` architecture found in `demo/`. **`demo/` is read-only TypeScript reference material — never edit it and never import from it.**

`docs/design.md` is the authoritative design document for this codebase. `docs/development-log.md` and `docs/mistake-log.md` are living records of recent decisions and past pitfalls — check them before making non-trivial changes so you don't repeat resolved mistakes.

## Skill Routing

Modify code in these paths? Load the corresponding skill first to prevent known anti-patterns:

| Scope | Skill |
|---|---|
| `agent_core/core/`, `providers/`, `session/`, `tools/`, `compaction/`, `extensions/` | `/dev-process-backend` |
| `scene/http_sse/static/src/` | `/dev-process-frontend` |
| Cross-layer (touching both scopes above) | `/dev-process-optimizer` first, then the sub-skill |

## Commit Checklist

Before committing non-trivial changes, execute these three steps in order:

1. **Update dev log** — append a dated entry to `docs/development-log/YYYY-MM-DD.md` (create if new day), update `docs/development-log.md` index
2. **Check skills** — does any fix reveal a new anti-pattern? Apply the three-question gate from `dev-process-optimizer` maintenance rules before adding a rule
3. **Commit** — concise message describing WHY, referencing problem numbers from dev log

## Development Commands

```bash
# Install in editable mode with test dependencies
pip install -e ".[test]"

# Run all tests
pytest

# Run a single test file
pytest tests/core/test_agent.py

# Run a single test
pytest tests/core/test_agent.py::test_prompt_basic

# Run with verbose output
pytest -v

# Run tests for a specific module
pytest tests/tools/
```

- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` (configured in `pyproject.toml`).
- `tests/conftest.py` provides `FakeProvider`, a test double for `ModelProvider` that yields scripted `StreamEvent` sequences.

## Architecture

### Package Layout

```
agent_core/
├── core/           # Pure runtime — no IO dependencies
│   ├── agent.py    # Stateful wrapper around agent_loop
│   ├── loop.py     # Core async generator: stream LLM → execute tools → repeat
│   ├── events.py   # AgentEvent discriminated union
│   ├── state.py    # AgentState Pydantic model
│   ├── context.py  # AgentContext / AgentLoopConfig value objects
│   ├── messages.py # UserMessage, AssistantMessage, ToolResultMessage
│   ├── content.py  # TextContent, ImageContent, ToolCallContent
│   ├── tool_runner.py   # Tool execution (parallel / sequential)
│   ├── queue.py    # PendingMessageQueue for steering / follow-up
│   └── human_input.py   # HITL (Human In The Loop) gate
├── providers/      # LLM provider adapters
│   ├── base.py     # ModelProvider Protocol
│   ├── registry.py # ModelRegistry: provider → adapter + auth
│   ├── openai_provider.py   # OpenAI / OpenAI-compatible endpoints
│   ├── anthropic_provider.py
│   └── auth.py     # AuthSource (static / env / dynamic)
├── tools/          # Tool abstractions and built-in tools
│   ├── base.py     # Tool Protocol, ToolResult, ToolDefinition, ToolRegistry, ToolContext
│   ├── http_tool.py
│   ├── operations.py        # FileOperations / BashOperations Protocols (inject for sandboxing)
│   ├── operations_local.py  # Local implementations of the Protocols above
│   ├── mutation_queue.py    # FileMutationQueue: per-path asyncio.Lock for write/edit
│   ├── render.py            # ToolRenderer Protocol + RenderedOutput
│   ├── truncate.py          # Text truncation helpers (head/tail/lines/bytes)
│   ├── music.py             # TextToMusicTool — example long-running tool
│   └── local/               # Filesystem tools: read, write, edit, ls, find, grep, bash, confirm
├── session/        # Session persistence
│   ├── store.py    # SessionStore Protocol + SessionEntry types
│   ├── session.py  # AgentSession: composes Agent + Store + Extensions
│   ├── jsonl_store.py
│   └── inmemory_store.py
├── compaction/     # Context window compaction
│   ├── compactor.py
│   └── strategies.py
├── extensions/     # Extension / Hook system
│   └── base.py     # Extension Protocol + ExtensionRunner
├── resources/      # Resource loading (skills, prompts, themes, context files)
│   ├── loader.py        # ResourceLoader entry point
│   ├── skills.py        # Skill discovery (~/.pi/agent/skills/, ./.pi/skills/)
│   ├── prompts.py       # Prompt template loading
│   ├── context_files.py # AGENTS.md / CLAUDE.md / etc. resolution
│   ├── themes.py        # Terminal theme resources
│   ├── extensions.py    # Extension manifest loading
│   ├── diagnostics.py   # Resource validation / reporting
│   └── types.py
├── skills/         # Placeholder package — bundled built-in skills land here
├── prompts/        # System prompt construction
│   └── builder.py  # SystemPromptBuilder
└── logging_config.py    # Logging setup helpers for hosts
```

### Key Architectural Decisions

**Async-first.** All public APIs are coroutines or async generators. The core loop (`agent_core/core/loop.py`) is a pure async generator that yields `AgentEvent` objects. `Agent` (`agent_core/core/agent.py`) is a thin stateful wrapper around it.

**Layered, unidirectional dependencies.** `core` has no IO dependencies. `session` depends on `core`. `extensions` depends on `core` and is wired into `session`. Never introduce circular dependencies between layers.

**Event-driven streaming.** The agent loop emits a discriminated union of `AgentEvent` objects (`agent_core/core/events.py`). Consumers subscribe via `Agent.subscribe(listener)`. Listeners may be sync or async — the framework handles both.

**Message queuing.** `Agent` maintains two `PendingMessageQueue` instances:
- `steering` — messages injected during a run (e.g. user interrupts)
- `follow_up` — messages queued after a run completes
Each queue supports modes `"one-at-a-time"` (default) and `"all"`.

**Tool execution modes.** `AgentLoopConfig.tool_execution` controls whether multiple tool calls in one turn run `"parallel"` (default, via `asyncio.gather`) or `"sequential"` (one at a time with intermediate `ToolExecutionUpdate` events).

**Human-in-the-loop.** Tools can raise `RequiresHumanInput` (`agent_core/core/human_input.py`) to pause execution and emit a `HumanInputRequired` event. The tool resumes when `Agent.provide_human_input()` is called with the matching `tool_call_id`.

**Provider abstraction.** `ModelProvider` is a Protocol (`agent_core/providers/base.py`). All providers output a uniform `StreamEvent` stream. `ModelRegistry` maps provider names to adapter instances and resolves authentication via `AuthSource`.

**Session persistence.** `AgentSession` (`agent_core/session/session.py`) composes `Agent` + `SessionStore` + optional `Compactor` + `Extension`s. It persists every `MessageEnd` event as a `MessageEntry` and auto-triggers compaction at `AgentEnd` when context thresholds are met.

**System prompt building.** `SystemPromptBuilder` (`agent_core/prompts/builder.py`) dynamically assembles the system prompt from base prompt, active tools, guidelines, context files, and skills. Skills are discovered from `~/.pi/agent/skills/` and `./.pi/skills/`.

### Scene Layer

The `scene/` directory contains runnable applications built on `agent_core`:

- `scene/cli/` — Interactive terminal chat (`python -m scene.cli.cli`)
- `scene/http_sse/` — FastAPI server with SSE streaming (`python -m scene.http_sse.server`)
- `scene/voice_ws/` — WebSocket voice chat server

`scene/cli/chat_assistant.py` and `scene/http_sse/chat_assistant.py` are the high-level `ChatAssistant` wrappers that wire together providers, tools, skills, and session storage.

## Testing Patterns

- Use `FakeProvider` from `tests/conftest.py` to script provider behavior without network calls.
- `FakeProvider.queue_script([...])` enqueues a sequence of `StreamEvent` objects; each call to `stream` consumes one script in order.
- Tests for the agent loop typically subscribe to events, call `agent.prompt()`, and assert on captured events.

## Optional Dependencies

The framework uses extras for optional integrations:

- `[mongo]` — `motor` for MongoDB session store
- `[mcp]` — `mcp` SDK for MCP tool servers
- `[openai]` — `openai` SDK
- `[anthropic]` — `anthropic` SDK
- `[test]` — `pytest`, `pytest-asyncio`, `respx`
- `[all]` — all of the above

## Coding Guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
