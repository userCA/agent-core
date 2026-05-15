# agent-core Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP foundation of `agent-core`: a Python async agent framework with streaming LLM calls (OpenAI), tool execution (HTTP), and pluggable session storage (InMemory/JSONL). After this plan, a developer can instantiate `Agent` or `AgentSession`, stream from OpenAI, call HTTP tools, and persist conversation history.

**Architecture:** Layered package `agent_core/` with `core/` (pure runtime), `providers/` (LLM adapters), `tools/` (tool execution), `session/` (storage + composition). All Protocols injected; no IO leaks into `core/`. Async-first with `asyncio`; Pydantic v2 for state; httpx for HTTP/SSE.

**Tech Stack:** Python 3.11+, `pydantic>=2.5`, `httpx>=0.27`, `pytest>=8`, `pytest-asyncio>=0.23`, `respx>=0.20`, `hatchling` build backend.

---

## Phase 0: Project Setup

### Task 0.1: Bootstrap repository and pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `.gitignore`

- [ ] **Step 1: Initialize git repository**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core
git init
git branch -M main
```

Expected: `Initialized empty Git repository in /Users/yuanbaishu/pythonProject/agent-core/.git/`

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.coverage
htmlcov/
.venv/
venv/
dist/
build/
.mypy_cache/
.ruff_cache/
.DS_Store
sessions/
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-core"
version = "0.1.0"
description = "General-purpose Python agent framework with streaming, tools, and persistence."
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
    "pydantic>=2.5",
    "httpx>=0.27",
]

[project.optional-dependencies]
mongo     = ["motor>=3.4"]
mcp       = ["mcp>=1.0"]
openai    = ["openai>=1.40"]
anthropic = ["anthropic>=0.34"]
test      = ["pytest>=8", "pytest-asyncio>=0.23", "respx>=0.20"]
all       = ["motor>=3.4","mcp>=1.0","openai>=1.40","anthropic>=0.34"]

[tool.hatch.build.targets.wheel]
packages = ["agent_core"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 4: Create minimal `README.md`**

```markdown
# agent-core

General-purpose Python agent framework with streaming, tools, and persistence.

See `design.md` and `docs/superpowers/plans/` for the implementation roadmap.
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md .gitignore
git commit -m "chore: bootstrap pyproject.toml and gitignore"
```

---

### Task 0.2: Install dev dependencies and verify pytest

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Create venv and install editable + test deps**

Run:
```bash
cd /Users/yuanbaishu/pythonProject/agent-core
python3.11 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[test]"
```

Expected: ends with `Successfully installed agent-core-0.1.0 ...` (plus pydantic/httpx/pytest deps).

- [ ] **Step 2: Create `tests/__init__.py` (empty)**

```python
```

- [ ] **Step 3: Write smoke test `tests/test_smoke.py`**

```python
def test_smoke():
    assert True
```

- [ ] **Step 4: Run pytest to verify wiring**

Run: `.venv/bin/pytest -q`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/test_smoke.py
git commit -m "chore: add pytest configuration and smoke test"
```

---

### Task 0.3: Create package skeleton

**Files:**
- Create: `agent_core/__init__.py`
- Create: `agent_core/core/__init__.py`
- Create: `agent_core/providers/__init__.py`
- Create: `agent_core/tools/__init__.py`
- Create: `agent_core/session/__init__.py`

- [ ] **Step 1: Write package import smoke test `tests/test_package_imports.py`**

```python
def test_package_imports():
    import agent_core  # noqa: F401
    import agent_core.core  # noqa: F401
    import agent_core.providers  # noqa: F401
    import agent_core.tools  # noqa: F401
    import agent_core.session  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_package_imports.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_core'`.

- [ ] **Step 3: Create the four `__init__.py` files**

`agent_core/__init__.py`:
```python
"""agent-core: general-purpose Python agent framework."""

__version__ = "0.1.0"
```

`agent_core/core/__init__.py`:
```python
```

`agent_core/providers/__init__.py`:
```python
```

`agent_core/tools/__init__.py`:
```python
```

`agent_core/session/__init__.py`:
```python
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_package_imports.py -q`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add agent_core tests/test_package_imports.py
git commit -m "chore: create agent_core package skeleton"
```

---

## Phase 1: Core Types

### Task 1.1: Message content blocks

**Files:**
- Create: `agent_core/core/content.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_content.py`

- [ ] **Step 1: Write failing test `tests/core/test_content.py`**

```python
from agent_core.core.content import TextContent, ImageContent, ToolCallContent


def test_text_content_roundtrip():
    tc = TextContent(text="hello")
    assert tc.type == "text"
    assert tc.model_dump() == {"type": "text", "text": "hello"}


def test_image_content_roundtrip():
    ic = ImageContent(data="iVBORw0K", mime_type="image/png")
    assert ic.type == "image"
    assert ic.model_dump() == {"type": "image", "data": "iVBORw0K", "mime_type": "image/png"}


def test_tool_call_content_roundtrip():
    tc = ToolCallContent(id="call_1", name="search", arguments={"q": "x"})
    assert tc.type == "tool_call"
    assert tc.model_dump() == {
        "type": "tool_call",
        "id": "call_1",
        "name": "search",
        "arguments": {"q": "x"},
    }
```

Run: `.venv/bin/pytest tests/core/test_content.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_core.core.content'`.

- [ ] **Step 2: Create `tests/core/__init__.py` (empty)**

```python
```

- [ ] **Step 3: Implement `agent_core/core/content.py`**

```python
"""Content block models used across messages and tool results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    type: Literal["image"] = "image"
    data: str
    mime_type: str


class ToolCallContent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict[str, Any] = {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/core/test_content.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add agent_core/core/content.py tests/core
git commit -m "feat(core): add message content block types"
```

---

### Task 1.2: AgentMessage discriminated union

**Files:**
- Create: `agent_core/core/messages.py`
- Create: `tests/core/test_messages.py`

- [ ] **Step 1: Write failing test `tests/core/test_messages.py`**

```python
import time

from pydantic import TypeAdapter

from agent_core.core.content import TextContent, ToolCallContent
from agent_core.core.messages import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    ToolResultMessage,
    Usage,
    UserMessage,
)


def test_user_message():
    msg = UserMessage(content=[TextContent(text="hi")], timestamp=time.time())
    assert msg.role == "user"


def test_assistant_message_with_tool_call():
    msg = AssistantMessage(
        content=[
            TextContent(text="calling tool"),
            ToolCallContent(id="c1", name="echo", arguments={"x": 1}),
        ],
        usage=Usage(input_tokens=10, output_tokens=5),
        stop_reason="tool_use",
        provider="openai",
        model="gpt-4o",
        timestamp=time.time(),
    )
    assert msg.role == "assistant"
    assert msg.has_tool_calls()
    calls = msg.tool_calls()
    assert len(calls) == 1
    assert calls[0].name == "echo"


def test_tool_result_message():
    msg = ToolResultMessage(
        tool_call_id="c1",
        content=[TextContent(text="ok")],
        is_error=False,
        timestamp=time.time(),
    )
    assert msg.role == "tool_result"


def test_custom_message():
    msg = CustomMessage(
        custom_type="notification",
        content={"text": "hi"},
        timestamp=time.time(),
    )
    assert msg.role == "custom"


def test_discriminated_union_dispatch():
    adapter = TypeAdapter(AgentMessage)
    payload = {
        "role": "user",
        "content": [{"type": "text", "text": "hi"}],
        "timestamp": 1.0,
    }
    msg = adapter.validate_python(payload)
    assert isinstance(msg, UserMessage)
```

Run: `.venv/bin/pytest tests/core/test_messages.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_core.core.messages'`.

- [ ] **Step 2: Implement `agent_core/core/messages.py`**

```python
"""Message types: user, assistant, tool_result, custom — discriminated union."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

from agent_core.core.content import ImageContent, TextContent, ToolCallContent

StopReason = Literal[
    "stop", "tool_use", "length", "content_filter", "error", "aborted"
]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: list[TextContent | ImageContent]
    timestamp: float


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: list[TextContent | ToolCallContent]
    usage: Usage = Usage()
    stop_reason: StopReason = "stop"
    error_message: str | None = None
    provider: str | None = None
    model: str | None = None
    timestamp: float

    def tool_calls(self) -> list[ToolCallContent]:
        return [c for c in self.content if isinstance(c, ToolCallContent)]

    def has_tool_calls(self) -> bool:
        return any(isinstance(c, ToolCallContent) for c in self.content)


class ToolResultMessage(BaseModel):
    role: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    content: list[TextContent | ImageContent]
    is_error: bool = False
    timestamp: float


class CustomMessage(BaseModel):
    role: Literal["custom"] = "custom"
    custom_type: str
    content: Any
    display: Any | None = None
    details: Any | None = None
    timestamp: float


AgentMessage = Annotated[
    Union[UserMessage, AssistantMessage, ToolResultMessage, CustomMessage],
    Field(discriminator="role"),
]
```

- [ ] **Step 3: Run test to verify it passes**

Run: `.venv/bin/pytest tests/core/test_messages.py -q`
Expected: `5 passed`.

- [ ] **Step 4: Commit**

```bash
git add agent_core/core/messages.py tests/core/test_messages.py
git commit -m "feat(core): add AgentMessage discriminated union"
```

---

### Task 1.3: AgentState and AgentEvent types

**Files:**
- Create: `agent_core/core/state.py`
- Create: `agent_core/core/events.py`
- Create: `tests/core/test_state.py`
- Create: `tests/core/test_events.py`

- [ ] **Step 1: Write failing test `tests/core/test_state.py`**

```python
from agent_core.core.state import AgentState


def test_default_state():
    s = AgentState()
    assert s.system_prompt == ""
    assert s.model is None
    assert s.thinking_level == "off"
    assert s.tools == []
    assert s.messages == []
    assert s.is_streaming is False
    assert s.pending_tool_calls == set()


def test_assignment_copies_lists():
    s = AgentState()
    tools_in = [{"name": "x"}]
    s.tools = tools_in
    tools_in.append({"name": "y"})
    assert len(s.tools) == 1  # outer list copy isolates external mutation
```

Run: `.venv/bin/pytest tests/core/test_state.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_core.core.state'`.

- [ ] **Step 2: Implement `agent_core/core/state.py`**

```python
"""Mutable runtime state shared across an Agent run."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh"]


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    system_prompt: str = ""
    model: Any | None = None
    thinking_level: ThinkingLevel = "off"
    tools: list[Any] = Field(default_factory=list)
    messages: list[Any] = Field(default_factory=list)

    is_streaming: bool = False
    streaming_message: Any | None = None
    pending_tool_calls: set[str] = Field(default_factory=set)
    error_message: str | None = None

    @field_validator("tools", "messages", mode="before")
    @classmethod
    def _copy_list(cls, v: Any) -> Any:
        if isinstance(v, list):
            return list(v)
        return v
```

- [ ] **Step 3: Run state test to verify pass**

Run: `.venv/bin/pytest tests/core/test_state.py -q`
Expected: `2 passed`.

- [ ] **Step 4: Write failing test `tests/core/test_events.py`**

```python
from pydantic import TypeAdapter

from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    TextDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)


def test_event_types_have_type_discriminator():
    assert AgentStart().type == "agent_start"
    assert AgentEnd(messages=[]).type == "agent_end"
    assert TurnStart().type == "turn_start"
    assert TurnEnd(message=None, tool_results=[]).type == "turn_end"
    assert MessageStart(message=None).type == "message_start"
    assert MessageEnd(message=None).type == "message_end"
    assert MessageUpdate(message=None, delta=TextDelta(text="hi")).type == "message_update"
    assert ToolExecutionStart(tool_call_id="x", tool_name="t", args={}).type == "tool_execution_start"
    assert ToolExecutionEnd(
        tool_call_id="x", tool_name="t", result=None, is_error=False
    ).type == "tool_execution_end"


def test_event_union_dispatch():
    adapter = TypeAdapter(AgentEvent)
    evt = adapter.validate_python({"type": "agent_start"})
    assert isinstance(evt, AgentStart)
```

Run: `.venv/bin/pytest tests/core/test_events.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_core.core.events'`.

- [ ] **Step 5: Implement `agent_core/core/events.py`**

```python
"""AgentEvent discriminated union emitted by the agent loop."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ThinkingDelta(BaseModel):
    type: Literal["thinking_delta"] = "thinking_delta"
    text: str


class ToolCallDelta(BaseModel):
    type: Literal["tool_call_delta"] = "tool_call_delta"
    id: str
    name: str | None = None
    arguments_delta: str | None = None


MessageDelta = Annotated[
    Union[TextDelta, ThinkingDelta, ToolCallDelta],
    Field(discriminator="type"),
]


class _EventBase(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)


class AgentStart(_EventBase):
    type: Literal["agent_start"] = "agent_start"


class AgentEnd(_EventBase):
    type: Literal["agent_end"] = "agent_end"
    messages: list[Any]


class TurnStart(_EventBase):
    type: Literal["turn_start"] = "turn_start"


class TurnEnd(_EventBase):
    type: Literal["turn_end"] = "turn_end"
    message: Any
    tool_results: list[Any]


class MessageStart(_EventBase):
    type: Literal["message_start"] = "message_start"
    message: Any


class MessageUpdate(_EventBase):
    type: Literal["message_update"] = "message_update"
    message: Any
    delta: MessageDelta


class MessageEnd(_EventBase):
    type: Literal["message_end"] = "message_end"
    message: Any


class ToolExecutionStart(_EventBase):
    type: Literal["tool_execution_start"] = "tool_execution_start"
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]


class ToolExecutionUpdate(_EventBase):
    type: Literal["tool_execution_update"] = "tool_execution_update"
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    partial_result: Any


class ToolExecutionEnd(_EventBase):
    type: Literal["tool_execution_end"] = "tool_execution_end"
    tool_call_id: str
    tool_name: str
    result: Any
    is_error: bool


AgentEvent = Annotated[
    Union[
        AgentStart,
        AgentEnd,
        TurnStart,
        TurnEnd,
        MessageStart,
        MessageUpdate,
        MessageEnd,
        ToolExecutionStart,
        ToolExecutionUpdate,
        ToolExecutionEnd,
    ],
    Field(discriminator="type"),
]
```

- [ ] **Step 6: Run event test to verify pass**

Run: `.venv/bin/pytest tests/core/test_events.py -q`
Expected: `2 passed`.

- [ ] **Step 7: Commit**

```bash
git add agent_core/core/state.py agent_core/core/events.py tests/core/test_state.py tests/core/test_events.py
git commit -m "feat(core): add AgentState and AgentEvent types"
```

---

## Phase 2: Provider Abstraction + OpenAI Adapter

### Task 2.1: Model and StreamEvent types

**Files:**
- Create: `agent_core/providers/types.py`
- Create: `tests/providers/__init__.py`
- Create: `tests/providers/test_types.py`

- [ ] **Step 1: Write failing test `tests/providers/test_types.py`**

```python
from pydantic import TypeAdapter

from agent_core.providers.types import (
    Model,
    ModelCost,
    StreamEvent,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
    StreamMessageEnd,
)


def test_model_defaults():
    m = Model(
        provider="openai",
        id="gpt-4o",
        context_window=128_000,
        max_output_tokens=4096,
    )
    assert m.supports_reasoning is False
    assert m.cost.input == 0.0


def test_model_cost():
    m = Model(
        provider="openai",
        id="gpt-4o",
        context_window=1,
        max_output_tokens=1,
        cost=ModelCost(input=2.5, output=10.0),
    )
    assert m.cost.input == 2.5
    assert m.cost.output == 10.0


def test_stream_event_union():
    adapter = TypeAdapter(StreamEvent)
    evt = adapter.validate_python({"type": "text_delta", "text": "hi"})
    assert isinstance(evt, StreamTextDelta)
    evt2 = adapter.validate_python(
        {"type": "tool_call_start", "id": "c1", "name": "echo"}
    )
    assert isinstance(evt2, StreamToolCallStart)
    evt3 = adapter.validate_python(
        {"type": "tool_call_end", "id": "c1", "arguments": {"x": 1}}
    )
    assert isinstance(evt3, StreamToolCallEnd)
    evt4 = adapter.validate_python(
        {"type": "message_end", "stop_reason": "stop"}
    )
    assert isinstance(evt4, StreamMessageEnd)
```

Run: `.venv/bin/pytest tests/providers/test_types.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2: Create `tests/providers/__init__.py` (empty)**

```python
```

- [ ] **Step 3: Implement `agent_core/providers/types.py`**

```python
"""Provider-neutral Model and StreamEvent types."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class ModelCost(BaseModel):
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


class Model(BaseModel):
    provider: str
    id: str
    context_window: int
    max_output_tokens: int
    supports_reasoning: bool = False
    supports_xhigh_thinking: bool = False
    cost: ModelCost = ModelCost()


class StreamTextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class StreamThinkingDelta(BaseModel):
    type: Literal["thinking_delta"] = "thinking_delta"
    text: str


class StreamToolCallStart(BaseModel):
    type: Literal["tool_call_start"] = "tool_call_start"
    id: str
    name: str


class StreamToolCallDelta(BaseModel):
    type: Literal["tool_call_delta"] = "tool_call_delta"
    id: str
    arguments_delta: str


class StreamToolCallEnd(BaseModel):
    type: Literal["tool_call_end"] = "tool_call_end"
    id: str
    arguments: dict[str, Any]


class StreamMessageEnd(BaseModel):
    type: Literal["message_end"] = "message_end"
    stop_reason: str
    input_tokens: int = 0
    output_tokens: int = 0


class StreamError(BaseModel):
    type: Literal["error"] = "error"
    message: str
    retryable: bool = False


StreamEvent = Annotated[
    Union[
        StreamTextDelta,
        StreamThinkingDelta,
        StreamToolCallStart,
        StreamToolCallDelta,
        StreamToolCallEnd,
        StreamMessageEnd,
        StreamError,
    ],
    Field(discriminator="type"),
]
```

- [ ] **Step 4: Run test to verify pass**

Run: `.venv/bin/pytest tests/providers/test_types.py -q`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add agent_core/providers/types.py tests/providers
git commit -m "feat(providers): add Model and StreamEvent types"
```

---

### Task 2.2: ModelProvider Protocol and AuthSource

**Files:**
- Create: `agent_core/providers/base.py`
- Create: `agent_core/providers/auth.py`
- Create: `tests/providers/test_auth.py`

- [ ] **Step 1: Write failing test `tests/providers/test_auth.py`**

```python
import asyncio
import os

import pytest

from agent_core.providers.auth import AuthSource, MissingCredentialsError, ProviderAuth


def test_static_auth():
    source = AuthSource.static(api_key="sk-test")
    auth = asyncio.run(source.resolve("openai"))
    assert auth.api_key == "sk-test"


def test_env_auth(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    source = AuthSource.env("OPENAI_API_KEY")
    auth = asyncio.run(source.resolve("openai"))
    assert auth.api_key == "sk-env"


def test_env_auth_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source = AuthSource.env("OPENAI_API_KEY")
    with pytest.raises(MissingCredentialsError):
        asyncio.run(source.resolve("openai"))


def test_dynamic_auth():
    async def cb(provider: str) -> ProviderAuth:
        return ProviderAuth(api_key=f"sk-{provider}")

    source = AuthSource.dynamic(cb)
    auth = asyncio.run(source.resolve("openai"))
    assert auth.api_key == "sk-openai"
```

Run: `.venv/bin/pytest tests/providers/test_auth.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_core.providers.auth'`.

- [ ] **Step 2: Implement `agent_core/providers/auth.py`**

```python
"""Provider credential resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Awaitable, Callable


class MissingCredentialsError(RuntimeError):
    """Raised when no credentials can be resolved for a provider."""


@dataclass
class ProviderAuth:
    api_key: str
    extra_headers: dict[str, str] | None = None


AuthCallback = Callable[[str], Awaitable[ProviderAuth]]


@dataclass
class AuthSource:
    _resolver: AuthCallback

    async def resolve(self, provider: str) -> ProviderAuth:
        return await self._resolver(provider)

    @classmethod
    def static(cls, *, api_key: str, extra_headers: dict[str, str] | None = None) -> "AuthSource":
        async def _cb(_: str) -> ProviderAuth:
            return ProviderAuth(api_key=api_key, extra_headers=extra_headers)

        return cls(_resolver=_cb)

    @classmethod
    def env(cls, var: str) -> "AuthSource":
        async def _cb(provider: str) -> ProviderAuth:
            value = os.environ.get(var)
            if not value:
                raise MissingCredentialsError(
                    f"Environment variable {var} not set for provider {provider}"
                )
            return ProviderAuth(api_key=value)

        return cls(_resolver=_cb)

    @classmethod
    def dynamic(cls, callback: AuthCallback) -> "AuthSource":
        return cls(_resolver=callback)
```

- [ ] **Step 3: Run auth test to verify pass**

Run: `.venv/bin/pytest tests/providers/test_auth.py -q`
Expected: `4 passed`.

- [ ] **Step 4: Implement `agent_core/providers/base.py`**

```python
"""ModelProvider Protocol — all LLM adapters implement this."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import Model, StreamEvent


@runtime_checkable
class ModelProvider(Protocol):
    name: str

    def list_models(self) -> list[Model]: ...

    async def stream(
        self,
        *,
        model: Model,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
        thinking_level: str = "off",
        temperature: float | None = None,
        max_tokens: int | None = None,
        signal: asyncio.Event | None = None,
        auth: ProviderAuth,
    ) -> AsyncIterator[StreamEvent]: ...
```

- [ ] **Step 5: Commit**

```bash
git add agent_core/providers/auth.py agent_core/providers/base.py tests/providers/test_auth.py
git commit -m "feat(providers): add ModelProvider Protocol and AuthSource"
```

---

### Task 2.3: ModelRegistry

**Files:**
- Create: `agent_core/providers/registry.py`
- Create: `tests/providers/test_registry.py`

- [ ] **Step 1: Write failing test `tests/providers/test_registry.py`**

```python
import asyncio
from typing import Any, AsyncIterator

import pytest

from agent_core.providers.auth import AuthSource, ProviderAuth
from agent_core.providers.registry import (
    MissingCredentialsError,
    ModelRegistry,
    UnknownProviderError,
)
from agent_core.providers.types import Model, StreamEvent


class FakeProvider:
    name = "fake"

    def list_models(self) -> list[Model]:
        return [
            Model(provider="fake", id="fast", context_window=1024, max_output_tokens=256),
            Model(provider="fake", id="slow", context_window=2048, max_output_tokens=512),
        ]

    async def stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        if False:
            yield  # pragma: no cover


def test_register_and_find():
    reg = ModelRegistry()
    reg.register_provider(FakeProvider(), auth_source=AuthSource.static(api_key="k"))
    found = reg.find("fake", "fast")
    assert found is not None
    assert found.id == "fast"

    assert reg.find("fake", "missing") is None
    assert reg.find("unknown", "fast") is None


def test_list_available():
    reg = ModelRegistry()
    reg.register_provider(FakeProvider(), auth_source=AuthSource.static(api_key="k"))
    models = reg.list_available()
    assert {m.id for m in models} == {"fast", "slow"}


def test_get_auth():
    reg = ModelRegistry()
    reg.register_provider(FakeProvider(), auth_source=AuthSource.static(api_key="k"))
    model = reg.find("fake", "fast")
    auth = asyncio.run(reg.get_auth(model))
    assert auth.api_key == "k"


def test_get_auth_unknown_provider_raises():
    reg = ModelRegistry()
    model = Model(provider="ghost", id="x", context_window=1, max_output_tokens=1)
    with pytest.raises(UnknownProviderError):
        asyncio.run(reg.get_auth(model))


def test_get_provider():
    reg = ModelRegistry()
    p = FakeProvider()
    reg.register_provider(p, auth_source=AuthSource.static(api_key="k"))
    assert reg.get_provider("fake") is p
    with pytest.raises(UnknownProviderError):
        reg.get_provider("ghost")
```

Run: `.venv/bin/pytest tests/providers/test_registry.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2: Implement `agent_core/providers/registry.py`**

```python
"""ModelRegistry — maps provider name → ModelProvider + credentials."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_core.providers.auth import (
    AuthSource,
    MissingCredentialsError,
    ProviderAuth,
)
from agent_core.providers.base import ModelProvider
from agent_core.providers.types import Model


class UnknownProviderError(KeyError):
    """Raised when a provider name is not registered."""


@dataclass
class _Entry:
    provider: ModelProvider
    auth_source: AuthSource
    models: dict[str, Model] = field(default_factory=dict)


class ModelRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def register_provider(
        self, provider: ModelProvider, *, auth_source: AuthSource
    ) -> None:
        models = {m.id: m for m in provider.list_models()}
        self._entries[provider.name] = _Entry(
            provider=provider, auth_source=auth_source, models=models
        )

    def get_provider(self, name: str) -> ModelProvider:
        entry = self._entries.get(name)
        if entry is None:
            raise UnknownProviderError(name)
        return entry.provider

    def find(self, provider: str, model_id: str) -> Model | None:
        entry = self._entries.get(provider)
        if entry is None:
            return None
        return entry.models.get(model_id)

    def list_available(self) -> list[Model]:
        return [m for entry in self._entries.values() for m in entry.models.values()]

    async def get_auth(self, model: Model) -> ProviderAuth:
        entry = self._entries.get(model.provider)
        if entry is None:
            raise UnknownProviderError(model.provider)
        return await entry.auth_source.resolve(model.provider)

    def has_configured_auth(self, model: Model) -> bool:
        return model.provider in self._entries


__all__ = [
    "ModelRegistry",
    "UnknownProviderError",
    "MissingCredentialsError",
]
```

- [ ] **Step 3: Run registry test to verify pass**

Run: `.venv/bin/pytest tests/providers/test_registry.py -q`
Expected: `5 passed`.

- [ ] **Step 4: Commit**

```bash
git add agent_core/providers/registry.py tests/providers/test_registry.py
git commit -m "feat(providers): add ModelRegistry"
```

---

### Task 2.4: OpenAIProvider with httpx SSE streaming

**Files:**
- Create: `agent_core/providers/openai_provider.py`
- Create: `tests/providers/test_openai_provider.py`

- [ ] **Step 1: Write failing test `tests/providers/test_openai_provider.py`**

```python
import asyncio

import httpx
import pytest
import respx

from agent_core.providers.auth import ProviderAuth
from agent_core.providers.openai_provider import OpenAIProvider
from agent_core.providers.types import (
    Model,
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)


def _sse(*chunks: str) -> str:
    body = ""
    for c in chunks:
        body += f"data: {c}\n\n"
    body += "data: [DONE]\n\n"
    return body


@respx.mock
def test_openai_provider_streams_text():
    provider = OpenAIProvider(base_url="https://api.openai.com/v1")
    model = Model(
        provider="openai", id="gpt-4o", context_window=128_000, max_output_tokens=4096
    )
    body = _sse(
        '{"choices":[{"delta":{"content":"Hello"}}]}',
        '{"choices":[{"delta":{"content":" world"}}]}',
        '{"choices":[{"delta":{},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":5,"completion_tokens":2}}',
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    )

    async def run() -> list:
        events = []
        async for evt in provider.stream(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            system_prompt="be brief",
            auth=ProviderAuth(api_key="sk-test"),
        ):
            events.append(evt)
        return events

    events = asyncio.run(run())
    text_deltas = [e for e in events if isinstance(e, StreamTextDelta)]
    assert "".join(e.text for e in text_deltas) == "Hello world"
    ends = [e for e in events if isinstance(e, StreamMessageEnd)]
    assert len(ends) == 1
    assert ends[0].stop_reason == "stop"
    assert ends[0].input_tokens == 5


@respx.mock
def test_openai_provider_streams_tool_call():
    provider = OpenAIProvider(base_url="https://api.openai.com/v1")
    model = Model(
        provider="openai", id="gpt-4o", context_window=128_000, max_output_tokens=4096
    )
    body = _sse(
        '{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"echo","arguments":""}}]}}]}',
        '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"x\\":"}}]}}]}',
        '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"1}"}}]}}]}',
        '{"choices":[{"delta":{},"finish_reason":"tool_calls"}],'
        '"usage":{"prompt_tokens":3,"completion_tokens":4}}',
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    )

    async def run():
        events = []
        async for evt in provider.stream(
            model=model,
            messages=[{"role": "user", "content": "do it"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "description": "echo",
                        "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
                    },
                }
            ],
            system_prompt="",
            auth=ProviderAuth(api_key="sk-test"),
        ):
            events.append(evt)
        return events

    events = asyncio.run(run())
    starts = [e for e in events if isinstance(e, StreamToolCallStart)]
    ends = [e for e in events if isinstance(e, StreamToolCallEnd)]
    assert len(starts) == 1
    assert starts[0].name == "echo"
    assert len(ends) == 1
    assert ends[0].arguments == {"x": 1}
```

Run: `.venv/bin/pytest tests/providers/test_openai_provider.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2: Implement `agent_core/providers/openai_provider.py`**

```python
"""OpenAI / OpenAI-compatible provider with httpx SSE streaming."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import (
    Model,
    StreamError,
    StreamEvent,
    StreamMessageEnd,
    StreamTextDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)


class OpenAIProvider:
    name: str

    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        provider_name: str = "openai",
        models: list[Model] | None = None,
        timeout: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = provider_name
        self._base_url = base_url.rstrip("/")
        self._models = models or self._default_models(provider_name)
        self._timeout = timeout
        self._client = http_client

    @staticmethod
    def _default_models(provider_name: str) -> list[Model]:
        return [
            Model(
                provider=provider_name,
                id="gpt-4o",
                context_window=128_000,
                max_output_tokens=4096,
            ),
            Model(
                provider=provider_name,
                id="gpt-4o-mini",
                context_window=128_000,
                max_output_tokens=16_384,
            ),
        ]

    def list_models(self) -> list[Model]:
        return list(self._models)

    async def stream(
        self,
        *,
        model: Model,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
        thinking_level: str = "off",
        temperature: float | None = None,
        max_tokens: int | None = None,
        signal: asyncio.Event | None = None,
        auth: ProviderAuth,
    ) -> AsyncIterator[StreamEvent]:
        payload = self._build_payload(
            model=model,
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            thinking_level=thinking_level,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        headers = {
            "Authorization": f"Bearer {auth.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if auth.extra_headers:
            headers.update(auth.extra_headers)

        async for evt in self._stream_request(payload, headers, signal):
            yield evt

    def _build_payload(
        self,
        *,
        model: Model,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
        thinking_level: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        msgs: list[dict[str, Any]] = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)
        payload: dict[str, Any] = {
            "model": model.id,
            "messages": msgs,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if thinking_level != "off" and model.supports_reasoning:
            payload["reasoning_effort"] = thinking_level
        return payload

    async def _stream_request(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        signal: asyncio.Event | None,
    ) -> AsyncIterator[StreamEvent]:
        url = f"{self._base_url}/chat/completions"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    yield StreamError(
                        message=f"HTTP {resp.status_code}: {body.decode('utf-8', errors='replace')}",
                        retryable=resp.status_code in (429, 500, 502, 503, 504),
                    )
                    return
                async for evt in self._parse_sse(resp, signal):
                    yield evt
        finally:
            if owns_client:
                await client.aclose()

    async def _parse_sse(
        self, resp: httpx.Response, signal: asyncio.Event | None
    ) -> AsyncIterator[StreamEvent]:
        tool_calls: dict[int, dict[str, Any]] = {}
        started_tools: set[str] = set()

        async for raw_line in resp.aiter_lines():
            if signal is not None and signal.is_set():
                break
            line = raw_line.strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue

            choices = event.get("choices") or []
            if not choices:
                usage = event.get("usage")
                if usage:
                    yield StreamMessageEnd(
                        stop_reason="stop",
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                    )
                continue

            choice = choices[0]
            delta = choice.get("delta") or {}

            text = delta.get("content")
            if text:
                yield StreamTextDelta(text=text)

            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = tool_calls.setdefault(idx, {"id": None, "name": None, "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]
                if slot["id"] and slot["name"] and slot["id"] not in started_tools:
                    started_tools.add(slot["id"])
                    yield StreamToolCallStart(id=slot["id"], name=slot["name"])

            finish = choice.get("finish_reason")
            if finish:
                for slot in tool_calls.values():
                    if slot["id"] and slot["name"]:
                        try:
                            args = json.loads(slot["args"]) if slot["args"] else {}
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamToolCallEnd(id=slot["id"], arguments=args)
                usage = event.get("usage") or {}
                yield StreamMessageEnd(
                    stop_reason=finish,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                )
```

- [ ] **Step 3: Run OpenAI test to verify pass**

Run: `.venv/bin/pytest tests/providers/test_openai_provider.py -q`
Expected: `2 passed`.

- [ ] **Step 4: Wire up `agent_core/providers/__init__.py`**

```python
"""Provider abstractions and built-in adapters."""

from agent_core.providers.auth import (
    AuthSource,
    MissingCredentialsError,
    ProviderAuth,
)
from agent_core.providers.base import ModelProvider
from agent_core.providers.openai_provider import OpenAIProvider
from agent_core.providers.registry import ModelRegistry, UnknownProviderError
from agent_core.providers.types import (
    Model,
    ModelCost,
    StreamEvent,
    StreamMessageEnd,
    StreamTextDelta,
    StreamThinkingDelta,
    StreamToolCallDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)

__all__ = [
    "AuthSource",
    "MissingCredentialsError",
    "ProviderAuth",
    "ModelProvider",
    "Model",
    "ModelCost",
    "ModelRegistry",
    "OpenAIProvider",
    "StreamEvent",
    "StreamMessageEnd",
    "StreamTextDelta",
    "StreamThinkingDelta",
    "StreamToolCallDelta",
    "StreamToolCallEnd",
    "StreamToolCallStart",
    "UnknownProviderError",
]
```

- [ ] **Step 5: Run full provider test suite**

Run: `.venv/bin/pytest tests/providers -q`
Expected: `14 passed`.

- [ ] **Step 6: Commit**

```bash
git add agent_core/providers/openai_provider.py agent_core/providers/__init__.py tests/providers/test_openai_provider.py
git commit -m "feat(providers): add OpenAIProvider with httpx SSE streaming"
```

---

## Phase 3: Agent Loop + Agent Class

### Task 3.1: Pending message queues

**Files:**
- Create: `agent_core/core/queue.py`
- Create: `tests/core/test_queue.py`

- [ ] **Step 1: Write failing test `tests/core/test_queue.py`**

```python
from agent_core.core.queue import PendingMessageQueue


def test_queue_one_at_a_time():
    q = PendingMessageQueue(mode="one-at-a-time")
    q.enqueue("a")
    q.enqueue("b")
    assert q.has_items()
    assert q.drain() == ["a"]
    assert q.drain() == ["b"]
    assert q.drain() == []


def test_queue_drain_all():
    q = PendingMessageQueue(mode="all")
    q.enqueue("a")
    q.enqueue("b")
    assert q.drain() == ["a", "b"]
    assert q.has_items() is False


def test_queue_clear():
    q = PendingMessageQueue(mode="all")
    q.enqueue("a")
    q.clear()
    assert q.has_items() is False


def test_queue_mode_can_be_set():
    q = PendingMessageQueue(mode="all")
    q.mode = "one-at-a-time"
    q.enqueue("a")
    q.enqueue("b")
    assert q.drain() == ["a"]
```

Run: `.venv/bin/pytest tests/core/test_queue.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2: Implement `agent_core/core/queue.py`**

```python
"""SteeringQueue / FollowUpQueue — internal pending-message buffers."""

from __future__ import annotations

from typing import Any, Literal

QueueMode = Literal["all", "one-at-a-time"]


class PendingMessageQueue:
    def __init__(self, mode: QueueMode = "one-at-a-time") -> None:
        self.mode: QueueMode = mode
        self._items: list[Any] = []

    def enqueue(self, message: Any) -> None:
        self._items.append(message)

    def has_items(self) -> bool:
        return bool(self._items)

    def drain(self) -> list[Any]:
        if not self._items:
            return []
        if self.mode == "all":
            drained = list(self._items)
            self._items.clear()
            return drained
        return [self._items.pop(0)]

    def clear(self) -> None:
        self._items.clear()
```

- [ ] **Step 3: Run queue test to verify pass**

Run: `.venv/bin/pytest tests/core/test_queue.py -q`
Expected: `4 passed`.

- [ ] **Step 4: Commit**

```bash
git add agent_core/core/queue.py tests/core/test_queue.py
git commit -m "feat(core): add PendingMessageQueue"
```

---

### Task 3.2: agent_loop (text-only, no tools yet)

**Files:**
- Create: `agent_core/core/context.py`
- Create: `agent_core/core/loop.py`
- Create: `tests/conftest.py`
- Create: `tests/core/test_loop_text.py`

- [ ] **Step 1: Create `tests/conftest.py` with FakeProvider helper**

```python
"""Shared test helpers."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Callable

from agent_core.providers.types import Model, StreamEvent


class FakeProvider:
    """Test double for ModelProvider.

    Each call to `stream` consumes one scripted event sequence in order.
    """

    name = "fake"

    def __init__(self, scripts: list[list[StreamEvent]] | None = None) -> None:
        self._scripts: list[list[StreamEvent]] = scripts or []
        self.calls: list[dict[str, Any]] = []

    def list_models(self) -> list[Model]:
        return [Model(provider="fake", id="fake-1", context_window=4096, max_output_tokens=1024)]

    def queue_script(self, events: list[StreamEvent]) -> None:
        self._scripts.append(events)

    async def stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        self.calls.append(kwargs)
        events = self._scripts.pop(0) if self._scripts else []
        for e in events:
            await asyncio.sleep(0)
            yield e


def fake_model() -> Model:
    return Model(provider="fake", id="fake-1", context_window=4096, max_output_tokens=1024)
```

- [ ] **Step 2: Write failing test `tests/core/test_loop_text.py`**

```python
import asyncio

import pytest

from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.events import (
    AgentEnd,
    AgentStart,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    TurnEnd,
    TurnStart,
)
from agent_core.core.loop import agent_loop
from agent_core.core.messages import UserMessage
from agent_core.providers.auth import ProviderAuth
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta

from tests.conftest import FakeProvider, fake_model


async def _collect(gen):
    return [e async for e in gen]


def test_agent_loop_text_only():
    provider = FakeProvider()
    provider.queue_script(
        [
            StreamTextDelta(text="Hello"),
            StreamTextDelta(text=" world"),
            StreamMessageEnd(stop_reason="stop", input_tokens=3, output_tokens=2),
        ]
    )

    user_msg = UserMessage(content=[{"type": "text", "text": "hi"}], timestamp=0.0)

    async def llm_convert(msgs):
        return [{"role": "user", "content": "hi"}]

    async def auth_resolver(_: str) -> ProviderAuth:
        return ProviderAuth(api_key="k")

    context = AgentContext(
        system_prompt="be brief",
        messages=[user_msg],
        tools=[],
    )
    config = AgentLoopConfig(
        provider=provider,
        model=fake_model(),
        convert_to_llm=llm_convert,
        auth_resolver=auth_resolver,
    )

    async def run():
        return await _collect(agent_loop([user_msg], context, config))

    events = asyncio.run(run())
    types = [type(e).__name__ for e in events]
    assert types[0] == "AgentStart"
    assert types[-1] == "AgentEnd"
    assert "TurnStart" in types
    assert "TurnEnd" in types
    text_updates = [
        e for e in events if isinstance(e, MessageUpdate) and e.delta.type == "text_delta"
    ]
    assert "".join(u.delta.text for u in text_updates) == "Hello world"
    end_msgs = [e for e in events if isinstance(e, MessageEnd) and getattr(e.message, "role", None) == "assistant"]
    assert len(end_msgs) == 1
    assert end_msgs[0].message.usage.input_tokens == 3
```

Run: `.venv/bin/pytest tests/core/test_loop_text.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_core.core.loop'`.

- [ ] **Step 3: Implement `agent_core/core/context.py`**

```python
"""AgentContext / AgentLoopConfig — value snapshots passed into agent_loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from agent_core.providers.auth import ProviderAuth
from agent_core.providers.base import ModelProvider
from agent_core.providers.types import Model

ConvertToLlm = Callable[[list[Any]], Awaitable[list[dict[str, Any]]]]
TransformContext = Callable[
    [list[Any], asyncio.Event | None], Awaitable[list[Any]]
]
AuthResolver = Callable[[str], Awaitable[ProviderAuth]]


@dataclass
class AgentContext:
    system_prompt: str = ""
    messages: list[Any] = field(default_factory=list)
    tools: list[Any] = field(default_factory=list)


@dataclass
class AgentLoopConfig:
    provider: ModelProvider
    model: Model
    convert_to_llm: ConvertToLlm
    auth_resolver: AuthResolver
    transform_context: TransformContext | None = None
    thinking_level: Literal["off", "minimal", "low", "medium", "high", "xhigh"] = "off"
    tool_execution: Literal["parallel", "sequential"] = "parallel"
    temperature: float | None = None
    max_tokens: int | None = None
    tool_registry: Any | None = None
    before_tool_call: Any | None = None
    after_tool_call: Any | None = None
    get_steering_messages: Any | None = None
    get_follow_up_messages: Any | None = None
```

- [ ] **Step 4: Implement `agent_core/core/loop.py`**

```python
"""Pure async-generator agent loop."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.content import TextContent, ToolCallContent
from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    TextDelta,
    ToolCallDelta,
    ThinkingDelta,
    TurnEnd,
    TurnStart,
)
from agent_core.core.messages import AssistantMessage, Usage
from agent_core.providers.types import (
    StreamError,
    StreamMessageEnd,
    StreamTextDelta,
    StreamThinkingDelta,
    StreamToolCallDelta,
    StreamToolCallEnd,
    StreamToolCallStart,
)


async def agent_loop(
    new_messages: list[Any],
    context: AgentContext,
    config: AgentLoopConfig,
    signal: asyncio.Event | None = None,
) -> AsyncIterator[AgentEvent]:
    """Drive an agent run: yield user messages → stream LLM → execute tools → repeat."""

    yield AgentStart()

    context.messages.extend(new_messages)
    for msg in new_messages:
        yield MessageStart(message=msg)
        yield MessageEnd(message=msg)

    new_assistant_messages: list[Any] = []

    while True:
        if signal is not None and signal.is_set():
            break

        yield TurnStart()

        llm_messages = await config.convert_to_llm(context.messages)
        if config.transform_context is not None:
            llm_messages = await config.transform_context(llm_messages, signal)

        auth = await config.auth_resolver(config.model.provider)

        tool_defs = _tools_to_provider_format(context.tools)

        assistant, updates = await _stream_assistant(
            config=config,
            llm_messages=llm_messages,
            tool_defs=tool_defs,
            auth=auth,
            signal=signal,
        )

        yield MessageStart(message=assistant)
        for upd in updates:
            yield upd
        yield MessageEnd(message=assistant)
        context.messages.append(assistant)
        new_assistant_messages.append(assistant)

        tool_result_messages: list[Any] = []
        if assistant.has_tool_calls() and config.tool_registry is not None:
            async for evt in _execute_tools(
                assistant=assistant,
                config=config,
                context=context,
                signal=signal,
                tool_results_out=tool_result_messages,
            ):
                yield evt

        yield TurnEnd(message=assistant, tool_results=tool_result_messages)

        if assistant.stop_reason in ("error", "aborted"):
            break
        if tool_result_messages:
            continue

        steering: list[Any] = []
        if config.get_steering_messages is not None:
            steering = await config.get_steering_messages()
        if steering:
            for msg in steering:
                context.messages.append(msg)
                yield MessageStart(message=msg)
                yield MessageEnd(message=msg)
            continue

        follow_ups: list[Any] = []
        if config.get_follow_up_messages is not None:
            follow_ups = await config.get_follow_up_messages()
        if follow_ups:
            for msg in follow_ups:
                context.messages.append(msg)
                yield MessageStart(message=msg)
                yield MessageEnd(message=msg)
            continue

        break

    yield AgentEnd(messages=new_assistant_messages)


async def agent_loop_continue(
    context: AgentContext,
    config: AgentLoopConfig,
    signal: asyncio.Event | None = None,
) -> AsyncIterator[AgentEvent]:
    """Continue an agent run from the existing transcript (no new user message)."""

    async for evt in agent_loop([], context, config, signal):
        yield evt


def _tools_to_provider_format(tools: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in tools:
        if isinstance(t, dict):
            out.append(_definition_to_openai(t))
        elif hasattr(t, "model_dump"):
            out.append(_definition_to_openai(t.model_dump()))
    return out


def _definition_to_openai(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": d["name"],
            "description": d.get("description", ""),
            "parameters": d.get("parameters", {"type": "object", "properties": {}}),
        },
    }


async def _stream_assistant(
    *,
    config: AgentLoopConfig,
    llm_messages: list[dict[str, Any]],
    tool_defs: list[dict[str, Any]],
    auth: Any,
    signal: asyncio.Event | None,
) -> tuple[AssistantMessage, list[MessageUpdate]]:
    assistant = AssistantMessage(
        content=[],
        usage=Usage(),
        stop_reason="stop",
        provider=config.model.provider,
        model=config.model.id,
        timestamp=time.time(),
    )

    updates: list[MessageUpdate] = []
    text_buf = ""
    tool_buffers: dict[str, dict[str, Any]] = {}
    error_message: str | None = None

    stream = config.provider.stream(
        model=config.model,
        messages=llm_messages,
        tools=tool_defs,
        system_prompt=config.model.provider and config.model.provider or "",
        thinking_level=config.thinking_level,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        signal=signal,
        auth=auth,
    )
    # provider.stream may be coroutine returning AsyncIterator or AsyncIterator itself
    if hasattr(stream, "__aiter__"):
        iterator = stream
    else:
        iterator = await stream  # type: ignore[assignment]

    async for evt in iterator:
        if isinstance(evt, StreamTextDelta):
            text_buf += evt.text
            updates.append(MessageUpdate(message=assistant, delta=TextDelta(text=evt.text)))
        elif isinstance(evt, StreamThinkingDelta):
            updates.append(MessageUpdate(message=assistant, delta=ThinkingDelta(text=evt.text)))
        elif isinstance(evt, StreamToolCallStart):
            tool_buffers[evt.id] = {"id": evt.id, "name": evt.name, "args": {}}
            updates.append(
                MessageUpdate(
                    message=assistant,
                    delta=ToolCallDelta(id=evt.id, name=evt.name),
                )
            )
        elif isinstance(evt, StreamToolCallDelta):
            updates.append(
                MessageUpdate(
                    message=assistant,
                    delta=ToolCallDelta(id=evt.id, arguments_delta=evt.arguments_delta),
                )
            )
        elif isinstance(evt, StreamToolCallEnd):
            slot = tool_buffers.setdefault(evt.id, {"id": evt.id, "name": "", "args": {}})
            slot["args"] = evt.arguments
        elif isinstance(evt, StreamMessageEnd):
            assistant.usage = Usage(
                input_tokens=evt.input_tokens,
                output_tokens=evt.output_tokens,
            )
            stop = evt.stop_reason
            if stop in ("tool_calls", "tool_use"):
                assistant.stop_reason = "tool_use"
            elif stop in ("stop", "end_turn"):
                assistant.stop_reason = "stop"
            elif stop == "length":
                assistant.stop_reason = "length"
            else:
                assistant.stop_reason = "stop"
        elif isinstance(evt, StreamError):
            error_message = evt.message
            assistant.stop_reason = "error"

    if text_buf:
        assistant.content.append(TextContent(text=text_buf))
    for slot in tool_buffers.values():
        assistant.content.append(
            ToolCallContent(id=slot["id"], name=slot["name"] or "", arguments=slot["args"])
        )
    if error_message:
        assistant.error_message = error_message

    return assistant, updates


async def _execute_tools(
    *,
    assistant: AssistantMessage,
    config: AgentLoopConfig,
    context: AgentContext,
    signal: asyncio.Event | None,
    tool_results_out: list[Any],
) -> AsyncIterator[AgentEvent]:
    # Stub: filled in during Phase 4 (tools). For Phase 3, no tool registry is wired.
    if False:
        yield AgentStart()  # pragma: no cover
    return
```

- [ ] **Step 5: Run loop test to verify pass**

Run: `.venv/bin/pytest tests/core/test_loop_text.py -q`
Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add agent_core/core/context.py agent_core/core/loop.py tests/conftest.py tests/core/test_loop_text.py
git commit -m "feat(core): add agent_loop with text streaming"
```

---

### Task 3.3: Agent class with subscribe/abort/prompt

**Files:**
- Create: `agent_core/core/agent.py`
- Create: `tests/core/test_agent.py`

- [ ] **Step 1: Write failing test `tests/core/test_agent.py`**

```python
import asyncio

import pytest

from agent_core.core.agent import Agent
from agent_core.core.events import MessageUpdate
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta

from tests.conftest import FakeProvider, fake_model


def test_agent_prompt_collects_streaming_text():
    provider = FakeProvider()
    provider.queue_script(
        [
            StreamTextDelta(text="Hi"),
            StreamTextDelta(text="!"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=2),
        ]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model(), system_prompt="hello"),
    )
    deltas: list[str] = []

    async def on_event(evt):
        if isinstance(evt, MessageUpdate) and evt.delta.type == "text_delta":
            deltas.append(evt.delta.text)

    agent.subscribe(on_event)
    asyncio.run(agent.prompt("hi"))

    assert "".join(deltas) == "Hi!"
    assert any(getattr(m, "role", None) == "user" for m in agent.state.messages)
    assistant = [m for m in agent.state.messages if getattr(m, "role", None) == "assistant"]
    assert len(assistant) == 1
    assert agent.state.is_streaming is False
    assert agent.state.error_message is None


def test_agent_prompt_double_call_raises_when_active():
    provider = FakeProvider()
    provider.queue_script([])
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )

    async def run():
        first = agent.prompt("a")
        with pytest.raises(RuntimeError):
            await agent.prompt("b")
        await first

    asyncio.run(run())


def test_agent_unsubscribe_removes_listener():
    provider = FakeProvider()
    provider.queue_script(
        [StreamMessageEnd(stop_reason="stop", input_tokens=0, output_tokens=0)]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )
    count = {"n": 0}

    async def listener(_):
        count["n"] += 1

    unsub = agent.subscribe(listener)
    unsub()
    asyncio.run(agent.prompt("x"))
    assert count["n"] == 0
```

Run: `.venv/bin/pytest tests/core/test_agent.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_core.core.agent'`.

- [ ] **Step 2: Implement `agent_core/core/agent.py`**

```python
"""Stateful Agent — wraps agent_loop with subscribe/abort/state."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Awaitable, Callable

from agent_core.core.content import ImageContent, TextContent
from agent_core.core.context import (
    AgentContext,
    AgentLoopConfig,
    AuthResolver,
    ConvertToLlm,
    TransformContext,
)
from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
)
from agent_core.core.loop import agent_loop, agent_loop_continue
from agent_core.core.messages import AssistantMessage, UserMessage
from agent_core.core.queue import PendingMessageQueue, QueueMode
from agent_core.core.state import AgentState, ThinkingLevel
from agent_core.providers.auth import AuthSource
from agent_core.providers.base import ModelProvider

Listener = Callable[[AgentEvent], Awaitable[None] | None]
Unsubscribe = Callable[[], None]


def _default_convert_to_llm() -> ConvertToLlm:
    async def convert(messages: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            role = getattr(m, "role", None)
            if role == "user":
                content = _user_content_to_openai(m.content)
                out.append({"role": "user", "content": content})
            elif role == "assistant":
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": "".join(c.text for c in m.content if getattr(c, "type", None) == "text"),
                }
                tool_calls = [c for c in m.content if getattr(c, "type", None) == "tool_call"]
                if tool_calls:
                    import json as _json

                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": _json.dumps(tc.arguments)},
                        }
                        for tc in tool_calls
                    ]
                out.append(msg)
            elif role == "tool_result":
                text_parts = "".join(
                    c.text for c in m.content if getattr(c, "type", None) == "text"
                )
                out.append(
                    {"role": "tool", "tool_call_id": m.tool_call_id, "content": text_parts}
                )
        return out

    return convert


def _user_content_to_openai(content: list[Any]) -> Any:
    parts: list[dict[str, Any]] = []
    only_text = True
    for c in content:
        t = getattr(c, "type", None) or (c.get("type") if isinstance(c, dict) else None)
        if t == "text":
            text = getattr(c, "text", None) or c.get("text", "")
            parts.append({"type": "text", "text": text})
        elif t == "image":
            data = getattr(c, "data", None) or c.get("data")
            mime = getattr(c, "mime_type", None) or c.get("mime_type", "image/png")
            parts.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}
            )
            only_text = False
    if only_text:
        return "".join(p["text"] for p in parts)
    return parts


class Agent:
    def __init__(
        self,
        *,
        provider: ModelProvider,
        auth_source: AuthSource,
        initial_state: AgentState | None = None,
        convert_to_llm: ConvertToLlm | None = None,
        transform_context: TransformContext | None = None,
        tool_registry: Any | None = None,
        before_tool_call: Any | None = None,
        after_tool_call: Any | None = None,
        tool_execution: str = "parallel",
        steering_mode: QueueMode = "one-at-a-time",
        followup_mode: QueueMode = "one-at-a-time",
    ) -> None:
        self.state: AgentState = initial_state or AgentState()
        self._provider = provider
        self._auth_source = auth_source
        self._convert_to_llm = convert_to_llm or _default_convert_to_llm()
        self._transform_context = transform_context
        self._tool_registry = tool_registry
        self._before_tool_call = before_tool_call
        self._after_tool_call = after_tool_call
        self._tool_execution = tool_execution
        self._steering = PendingMessageQueue(steering_mode)
        self._follow_up = PendingMessageQueue(followup_mode)
        self._listeners: list[Listener] = []
        self._active_run: asyncio.Task | None = None
        self._abort_event: asyncio.Event | None = None

    # ---------- subscriptions ----------
    def subscribe(self, listener: Listener) -> Unsubscribe:
        self._listeners.append(listener)

        def _unsub() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _unsub

    # ---------- queues ----------
    def steer(self, message: Any) -> None:
        self._steering.enqueue(message)

    def follow_up(self, message: Any) -> None:
        self._follow_up.enqueue(message)

    def clear_all_queues(self) -> None:
        self._steering.clear()
        self._follow_up.clear()

    @property
    def steering_mode(self) -> QueueMode:
        return self._steering.mode

    @steering_mode.setter
    def steering_mode(self, mode: QueueMode) -> None:
        self._steering.mode = mode

    @property
    def followup_mode(self) -> QueueMode:
        return self._follow_up.mode

    @followup_mode.setter
    def followup_mode(self, mode: QueueMode) -> None:
        self._follow_up.mode = mode

    # ---------- control ----------
    def abort(self) -> None:
        if self._abort_event is not None:
            self._abort_event.set()

    async def wait_for_idle(self) -> None:
        if self._active_run is not None:
            await self._active_run

    def reset(self) -> None:
        self.state = AgentState(
            system_prompt=self.state.system_prompt,
            model=self.state.model,
            thinking_level=self.state.thinking_level,
            tools=list(self.state.tools),
        )
        self._steering.clear()
        self._follow_up.clear()

    # ---------- run ----------
    async def prompt(
        self,
        text_or_message: Any,
        *,
        images: list[ImageContent] | None = None,
    ) -> None:
        if self._active_run is not None and not self._active_run.done():
            raise RuntimeError("Agent is already running a prompt; use steer/follow_up or wait_for_idle.")
        message = self._normalize_input(text_or_message, images)
        await self._run([message], continuation=False)

    async def continue_(self) -> None:
        if self._active_run is not None and not self._active_run.done():
            raise RuntimeError("Agent is already running.")
        if not self.state.messages:
            raise RuntimeError("No messages in state to continue from.")
        last = self.state.messages[-1]
        role = getattr(last, "role", None)
        if role not in ("user", "tool_result"):
            raise RuntimeError(f"Cannot continue from message with role={role}.")
        await self._run([], continuation=True)

    def _normalize_input(
        self, text_or_message: Any, images: list[ImageContent] | None
    ) -> Any:
        if isinstance(text_or_message, str):
            content: list[Any] = [TextContent(text=text_or_message)]
            if images:
                content.extend(images)
            return UserMessage(content=content, timestamp=time.time())
        return text_or_message

    async def _run(self, new_messages: list[Any], *, continuation: bool) -> None:
        self._abort_event = asyncio.Event()
        self.state.is_streaming = True
        self.state.error_message = None

        async def _do_run() -> None:
            context = AgentContext(
                system_prompt=self.state.system_prompt,
                messages=list(self.state.messages),
                tools=list(self.state.tools),
            )

            async def auth_resolver(provider_name: str):
                return await self._auth_source.resolve(provider_name)

            config = AgentLoopConfig(
                provider=self._provider,
                model=self.state.model,
                convert_to_llm=self._convert_to_llm,
                auth_resolver=auth_resolver,
                transform_context=self._transform_context,
                thinking_level=self.state.thinking_level,
                tool_execution=self._tool_execution,
                tool_registry=self._tool_registry,
                before_tool_call=self._before_tool_call,
                after_tool_call=self._after_tool_call,
                get_steering_messages=self._drain_steering,
                get_follow_up_messages=self._drain_follow_up,
            )

            if continuation:
                gen = agent_loop_continue(context, config, self._abort_event)
            else:
                gen = agent_loop(new_messages, context, config, self._abort_event)

            try:
                async for evt in gen:
                    await self._handle_event(evt, context)
            except Exception as exc:  # pragma: no cover — last-resort
                self.state.error_message = str(exc)

        task = asyncio.create_task(_do_run())
        self._active_run = task
        try:
            await task
        finally:
            self.state.is_streaming = False
            self.state.streaming_message = None
            self._active_run = None
            self._abort_event = None

    async def _drain_steering(self) -> list[Any]:
        return self._steering.drain()

    async def _drain_follow_up(self) -> list[Any]:
        return self._follow_up.drain()

    async def _handle_event(self, evt: AgentEvent, context: AgentContext) -> None:
        if isinstance(evt, MessageStart):
            if getattr(evt.message, "role", None) == "assistant":
                self.state.streaming_message = evt.message
        elif isinstance(evt, MessageUpdate):
            self.state.streaming_message = evt.message
        elif isinstance(evt, MessageEnd):
            self.state.streaming_message = None
            self.state.messages.append(evt.message)
        elif isinstance(evt, ToolExecutionStart):
            self.state.pending_tool_calls.add(evt.tool_call_id)
        elif isinstance(evt, ToolExecutionEnd):
            self.state.pending_tool_calls.discard(evt.tool_call_id)
        elif isinstance(evt, TurnEnd):
            msg = evt.message
            if getattr(msg, "role", None) == "assistant" and getattr(msg, "error_message", None):
                self.state.error_message = msg.error_message
        elif isinstance(evt, AgentEnd):
            self.state.streaming_message = None

        for listener in list(self._listeners):
            result = listener(evt)
            if inspect.isawaitable(result):
                await result
```

- [ ] **Step 3: Run agent test to verify pass**

Run: `.venv/bin/pytest tests/core/test_agent.py -q`
Expected: `3 passed`.

- [ ] **Step 4: Wire up `agent_core/core/__init__.py`**

```python
"""Core runtime types and Agent class."""

from agent_core.core.agent import Agent
from agent_core.core.content import ImageContent, TextContent, ToolCallContent
from agent_core.core.context import AgentContext, AgentLoopConfig
from agent_core.core.events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageDelta,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    TextDelta,
    ThinkingDelta,
    ToolCallDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
    TurnEnd,
    TurnStart,
)
from agent_core.core.loop import agent_loop, agent_loop_continue
from agent_core.core.messages import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    StopReason,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from agent_core.core.state import AgentState, ThinkingLevel

__all__ = [
    "Agent",
    "AgentContext",
    "AgentEnd",
    "AgentEvent",
    "AgentLoopConfig",
    "AgentMessage",
    "AgentStart",
    "AgentState",
    "AssistantMessage",
    "CustomMessage",
    "ImageContent",
    "MessageDelta",
    "MessageEnd",
    "MessageStart",
    "MessageUpdate",
    "StopReason",
    "TextContent",
    "TextDelta",
    "ThinkingDelta",
    "ThinkingLevel",
    "ToolCallContent",
    "ToolCallDelta",
    "ToolExecutionEnd",
    "ToolExecutionStart",
    "ToolExecutionUpdate",
    "ToolResultMessage",
    "TurnEnd",
    "TurnStart",
    "Usage",
    "UserMessage",
    "agent_loop",
    "agent_loop_continue",
]
```

- [ ] **Step 5: Commit**

```bash
git add agent_core/core/agent.py agent_core/core/__init__.py tests/core/test_agent.py
git commit -m "feat(core): add stateful Agent class"
```

---

### Task 3.4: Steering and follow-up integration test

**Files:**
- Create: `tests/core/test_agent_steering.py`

- [ ] **Step 1: Write integration test `tests/core/test_agent_steering.py`**

```python
import asyncio

from agent_core.core.agent import Agent
from agent_core.core.messages import UserMessage
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta

from tests.conftest import FakeProvider, fake_model


def test_follow_up_message_runs_after_first_turn():
    provider = FakeProvider()
    provider.queue_script(
        [
            StreamTextDelta(text="first"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ]
    )
    provider.queue_script(
        [
            StreamTextDelta(text="second"),
            StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1),
        ]
    )
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )

    async def run():
        agent.follow_up(UserMessage(content=[{"type": "text", "text": "next"}], timestamp=0.0))
        await agent.prompt("first")

    asyncio.run(run())
    user_msgs = [m for m in agent.state.messages if getattr(m, "role", None) == "user"]
    assistant_msgs = [m for m in agent.state.messages if getattr(m, "role", None) == "assistant"]
    assert len(user_msgs) == 2
    assert len(assistant_msgs) == 2


def test_clear_all_queues():
    provider = FakeProvider()
    agent = Agent(
        provider=provider,
        auth_source=AuthSource.static(api_key="k"),
        initial_state=AgentState(model=fake_model()),
    )
    agent.steer(UserMessage(content=[{"type": "text", "text": "a"}], timestamp=0.0))
    agent.follow_up(UserMessage(content=[{"type": "text", "text": "b"}], timestamp=0.0))
    agent.clear_all_queues()
    assert agent._steering.has_items() is False
    assert agent._follow_up.has_items() is False
```

- [ ] **Step 2: Run integration test**

Run: `.venv/bin/pytest tests/core/test_agent_steering.py -q`
Expected: `2 passed`.

- [ ] **Step 3: Run full core suite to ensure nothing regressed**

Run: `.venv/bin/pytest tests/core -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/core/test_agent_steering.py
git commit -m "test(core): cover follow-up queue draining"
```

---
