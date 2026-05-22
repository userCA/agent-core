# Memory 与 Retrieval 基础 — 实施计划

> **面向智能体工作流：** 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐个任务实施。

**目标：** 新增 `agent_core/memory/` 和 `agent_core/retrieval/` 两个子系统，Protocol 优先，内存适配器验证，通过 Extension/Tool 桥接入运行时。**`agent_core/core/` 零改动。**

**架构：** 定义 `MemoryStore`、`Retriever` 两个 Protocol。通过 Extension Protocol 实现自动召回/持久化和预 LLM 注入，通过 Tool Protocol 实现智能体 RAG 模式。复用 `AgentLoopConfig.transform_context` hook（`loop.py:60-61`）。`AgentSession.start()` 用与现有 `before_tool_call` 相同的 monkey-patch 模式链式组合 `transform_context`，保持对称一致。

**技术栈：** Python 3.11+、pydantic 2.5+、asyncio、pytest + pytest-asyncio（asyncio_mode="auto"）、`FakeProvider`。

---

## 文件结构

```
agent_core/
├── memory/
│   ├── __init__.py
│   ├── base.py                # MemoryStore Protocol + MemoryRecord
│   ├── extension.py           # MemoryExtension
│   └── adapters/
│       ├── __init__.py
│       └── inmemory.py        # InMemoryMemoryStore
│
├── retrieval/
│   ├── __init__.py
│   ├── base.py                # Retriever Protocol + RetrievedChunk + Query
│   ├── tool.py                # RetrieverTool
│   ├── extension.py           # AutoRetrievalExtension
│   └── adapters/
│       ├── __init__.py
│       └── inmemory.py        # InMemoryRetriever

tests/
├── memory/
│   ├── __init__.py
│   ├── test_inmemory_store.py
│   └── test_memory_extension.py
└── retrieval/
    ├── __init__.py
    ├── test_inmemory_retriever.py
    ├── test_retriever_tool.py
    └── test_auto_retrieval_extension.py
```

**修改的文件：** `docs/design.md`（追加 §10）、`agent_core/session/session.py`（链式组合 transform_context）。

---

## 前置须知

1. **`transform_context` hook 已存在**（`loop.py:60-61`）。不新增核心 hook。
2. **Extension Protocol 表面窄**（`extensions/base.py:21-38`）：只有 `on_event`、`on_before_tool_call`、`on_after_tool_call`。不扩展。
3. **Tool Protocol**（`tools/base.py`）：`definition: ToolDefinition` + `async execute(...) -> ToolResult`。`ToolResult` 只有 `content / details / display`，**没有** `is_error`。
4. **`FakeProvider`**（`tests/conftest.py`）：`queue_script([...])` 入队脚本响应。`pytest-asyncio` 自动模式。
5. **`AgentSession.start()`** 已用 monkey-patch 模式链式组合 `before_tool_call`（session.py:71-91）。`transform_context` 用相同模式。
6. **`AuthSource.static(api_key="k")`** —— keyword-only，不能传位置参数。
7. **`agent_core/__init__.py`** 只暴露 `__version__`。子包各自导出公开 API。

---

## 任务 1：Retrieval Protocol + 数据类型

**文件：** `agent_core/retrieval/__init__.py`、`agent_core/retrieval/base.py`、`tests/retrieval/__init__.py`、`tests/retrieval/test_base.py`

- [ ] **编写失败测试** → 创建 `tests/retrieval/test_base.py`：

```python
from agent_core.retrieval.base import Query, RetrievedChunk, Retriever


def test_query_defaults():
    q = Query(text="hello")
    assert q.text == "hello"
    assert q.top_k == 5
    assert q.filters == {}


def test_retrieved_chunk_fields():
    c = RetrievedChunk(text="doc body", score=0.83, source="doc-1", metadata={"page": 2})
    assert c.text == "doc body"
    assert c.score == 0.83
    assert c.source == "doc-1"
    assert c.metadata == {"page": 2}


def test_retriever_is_protocol():
    class Dummy:
        async def retrieve(self, query):
            return []
    r: Retriever = Dummy()
    assert hasattr(r, "retrieve")
```

- [ ] **验证失败** → `pytest tests/retrieval/test_base.py -v` → `ModuleNotFoundError`

- [ ] **实现** → `agent_core/retrieval/base.py`：

```python
"""Retriever Protocol and data types for RAG."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Query(BaseModel):
    text: str
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    text: str
    score: float
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Retriever(Protocol):
    async def retrieve(self, query: Query) -> list[RetrievedChunk]: ...
```

`agent_core/retrieval/__init__.py`：

```python
from agent_core.retrieval.base import Query, RetrievedChunk, Retriever

__all__ = ["Query", "RetrievedChunk", "Retriever"]
```

- [ ] **验证通过** → `pytest tests/retrieval/test_base.py -v` → 3 PASS

- [ ] **提交** → `feat(retrieval): add Retriever Protocol and data types`

---

## 任务 2：InMemory Retriever 适配器

**文件：** `agent_core/retrieval/adapters/__init__.py`、`agent_core/retrieval/adapters/inmemory.py`、`tests/retrieval/test_inmemory_retriever.py`

- [ ] **编写失败测试** → `tests/retrieval/test_inmemory_retriever.py`：

```python
from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.base import Query, RetrievedChunk


async def test_returns_top_k_by_keyword_overlap():
    r = InMemoryRetriever()
    r.add("Python is a programming language", source="d1")
    r.add("Cats are mammals", source="d2")
    r.add("Python snakes live in Asia", source="d3")

    chunks = await r.retrieve(Query(text="python language", top_k=2))

    assert len(chunks) == 2
    assert chunks[0].source == "d1"
    assert all(isinstance(c, RetrievedChunk) for c in chunks)
    assert chunks[0].score >= chunks[1].score


async def test_returns_empty_when_no_overlap():
    r = InMemoryRetriever()
    r.add("Cats are mammals", source="d1")
    chunks = await r.retrieve(Query(text="quantum physics", top_k=5))
    assert chunks == []


async def test_filter_by_metadata():
    r = InMemoryRetriever()
    r.add("Python guide", source="d1", metadata={"lang": "en"})
    r.add("Python 教程", source="d2", metadata={"lang": "zh"})
    chunks = await r.retrieve(Query(text="python", top_k=5, filters={"lang": "zh"}))
    assert len(chunks) == 1
    assert chunks[0].source == "d2"
```

- [ ] **验证失败** → `ModuleNotFoundError`

- [ ] **实现** → `agent_core/retrieval/adapters/inmemory.py`：

```python
"""In-memory keyword-overlap retriever for tests and small demos."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent_core.retrieval.base import Query, RetrievedChunk

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}


@dataclass
class _Doc:
    text: str
    source: str | None
    metadata: dict[str, Any]
    tokens: set[str]


class InMemoryRetriever:
    def __init__(self) -> None:
        self._docs: list[_Doc] = []

    def add(self, text: str, *, source: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._docs.append(_Doc(text=text, source=source, metadata=metadata or {}, tokens=_tokenize(text)))

    async def retrieve(self, query: Query) -> list[RetrievedChunk]:
        q_tokens = _tokenize(query.text)
        if not q_tokens:
            return []
        scored: list[tuple[float, _Doc]] = []
        for doc in self._docs:
            if query.filters and not all(doc.metadata.get(k) == v for k, v in query.filters.items()):
                continue
            overlap = len(q_tokens & doc.tokens)
            if overlap == 0:
                continue
            scored.append((overlap / len(q_tokens), doc))
        scored.sort(key=lambda p: p[0], reverse=True)
        return [
            RetrievedChunk(text=doc.text, score=score, source=doc.source, metadata=dict(doc.metadata))
            for score, doc in scored[: query.top_k]
        ]
```

`agent_core/retrieval/adapters/__init__.py`：

```python
from agent_core.retrieval.adapters.inmemory import InMemoryRetriever

__all__ = ["InMemoryRetriever"]
```

- [ ] **验证通过** → 3 PASS

- [ ] **提交** → `feat(retrieval): add InMemoryRetriever adapter`

---

## 任务 3：RetrieverTool

**文件：** `agent_core/retrieval/tool.py`、`tests/retrieval/test_retriever_tool.py`

- [ ] **编写失败测试**：

```python
import asyncio

from agent_core.core.content import TextContent
from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.tool import RetrieverTool
from agent_core.tools.base import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(signal=asyncio.Event(), on_update=None, metadata={}, mutation_queue=None)


async def test_tool_definition_shape():
    r = InMemoryRetriever()
    tool = RetrieverTool(retriever=r, name="search_kb", description="Search KB")
    assert tool.definition.name == "search_kb"
    assert "query" in tool.definition.parameters["properties"]
    assert tool.definition.parameters["required"] == ["query"]


async def test_tool_returns_chunks_as_text():
    r = InMemoryRetriever()
    r.add("Python is great", source="d1")
    tool = RetrieverTool(retriever=r)

    result = await tool.execute(tool_call_id="t1", params={"query": "python", "top_k": 1}, ctx=_ctx())

    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert "Python is great" in result.content[0].text
    assert "d1" in result.content[0].text


async def test_tool_empty_result_message():
    r = InMemoryRetriever()
    tool = RetrieverTool(retriever=r)
    result = await tool.execute(tool_call_id="t1", params={"query": "nothing"}, ctx=_ctx())
    assert "No matching" in result.content[0].text
```

- [ ] **验证失败** → `ImportError`

- [ ] **实现** → `agent_core/retrieval/tool.py`：

```python
"""Wrap a Retriever as an LLM-callable Tool."""

from __future__ import annotations

from typing import Any

from agent_core.core.content import TextContent
from agent_core.retrieval.base import Query, Retriever
from agent_core.tools.base import ToolContext, ToolDefinition, ToolResult


class RetrieverTool:
    def __init__(self, *, retriever: Retriever, name: str = "retrieve", description: str = "Retrieve relevant context for a query.") -> None:
        self._retriever = retriever
        self.definition = ToolDefinition(
            name=name,
            description=description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language query."},
                    "top_k": {"type": "integer", "description": "Maximum number of chunks to return.", "default": 5},
                    "filters": {"type": "object", "description": "Optional metadata equality filters.", "default": {}},
                },
                "required": ["query"],
            },
        )

    async def execute(self, tool_call_id: str, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = Query(text=params["query"], top_k=params.get("top_k", 5), filters=params.get("filters", {}))
        chunks = await self._retriever.retrieve(query)
        if not chunks:
            return ToolResult(content=[TextContent(text="No matching results.")])
        lines: list[str] = []
        for i, c in enumerate(chunks, 1):
            tag = f" [{c.source}]" if c.source else ""
            lines.append(f"[{i}] (score={c.score:.3f}){tag}\n{c.text}")
        return ToolResult(content=[TextContent(text="\n\n".join(lines))])
```

更新 `agent_core/retrieval/__init__.py` 追加 `RetrieverTool` 导出。

- [ ] **验证通过** → 3 PASS

- [ ] **提交** → `feat(retrieval): add RetrieverTool bridge`

---

## 任务 4：AutoRetrievalExtension

**文件：** `agent_core/retrieval/extension.py`、`tests/retrieval/test_auto_retrieval_extension.py`

- [ ] **编写失败测试**：

```python
from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.extension import AutoRetrievalExtension


async def test_injects_chunks_before_user_message():
    r = InMemoryRetriever()
    r.add("Python uses GIL for threading", source="d1")
    ext = AutoRetrievalExtension(retriever=r, top_k=2)

    out = await ext.transform_context([{"role": "user", "content": "Tell me about Python threading"}], signal=None)

    assert len(out) == 2
    assert out[0]["role"] == "system"
    assert "Python uses GIL" in out[0]["content"]


async def test_noop_when_no_user_message():
    r = InMemoryRetriever()
    r.add("doc", source="d1")
    ext = AutoRetrievalExtension(retriever=r)
    out = await ext.transform_context([{"role": "assistant", "content": "hi"}], signal=None)
    assert out == [{"role": "assistant", "content": "hi"}]


async def test_noop_when_no_chunks_match():
    ext = AutoRetrievalExtension(retriever=InMemoryRetriever())
    msgs = [{"role": "user", "content": "anything"}]
    out = await ext.transform_context(msgs, signal=None)
    assert out == msgs
```

- [ ] **验证失败** → `ImportError`

- [ ] **实现** → `agent_core/retrieval/extension.py`：

```python
"""Extension that auto-injects retrieved context before each LLM call."""

from __future__ import annotations

import asyncio
from typing import Any

from agent_core._llm_message_utils import latest_user_index, latest_user_text
from agent_core.retrieval.base import Query, Retriever


class AutoRetrievalExtension:
    name = "auto_retrieval"

    def __init__(self, *, retriever: Retriever, top_k: int = 5) -> None:
        self._retriever = retriever
        self._top_k = top_k

    async def on_event(self, ctx: Any, evt: Any) -> None: ...
    async def on_before_tool_call(self, ctx: Any, tool_call: Any) -> dict[str, Any] | None: return None
    async def on_after_tool_call(self, ctx: Any, tool_call: Any, result: Any, is_error: bool) -> dict[str, Any] | None: return None

    async def transform_context(self, llm_messages: list[dict[str, Any]], signal: asyncio.Event | None) -> list[dict[str, Any]]:
        query_text = latest_user_text(llm_messages)
        if not query_text:
            return llm_messages

        chunks = await self._retriever.retrieve(Query(text=query_text, top_k=self._top_k))
        if not chunks:
            return llm_messages

        body_lines = ["Relevant context retrieved for the latest user query:"]
        for i, c in enumerate(chunks, 1):
            tag = f" [{c.source}]" if c.source else ""
            body_lines.append(f"[{i}]{tag} {c.text}")
        system_msg = {"role": "system", "content": "\n".join(body_lines)}

        insert_at = latest_user_index(llm_messages)
        return [*llm_messages[:insert_at], system_msg, *llm_messages[insert_at:]]
```

> **共享 helper：** `agent_core/_llm_message_utils.py` 提供 `latest_user_index` / `latest_user_text`，被 `AutoRetrievalExtension` 和 `MemoryExtension` 共用。在任务 4 实现里**先**创建该文件：
>
> ```python
> """Internal helpers for inspecting LLM-format messages (provider-neutral dict shape)."""
>
> from __future__ import annotations
>
> from typing import Any
>
>
> def latest_user_index(messages: list[dict[str, Any]]) -> int:
>     for i in range(len(messages) - 1, -1, -1):
>         if messages[i].get("role") == "user":
>             return i
>     return len(messages)
>
>
> def latest_user_text(messages: list[dict[str, Any]]) -> str | None:
>     idx = latest_user_index(messages)
>     if idx == len(messages):
>         return None
>     content = messages[idx].get("content")
>     if isinstance(content, str):
>         return content
>     if isinstance(content, list):
>         parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
>         return "\n".join(p for p in parts if p) or None
>     return None
> ```

- [ ] **验证通过** → 3 PASS

- [ ] **提交** → `feat(retrieval): add AutoRetrievalExtension`

---

## 任务 5：Memory Protocol + InMemory 适配器

**文件：** `agent_core/memory/__init__.py`、`agent_core/memory/base.py`、`agent_core/memory/adapters/__init__.py`、`agent_core/memory/adapters/inmemory.py`、`tests/memory/__init__.py`、`tests/memory/test_inmemory_store.py`

- [ ] **编写失败测试**：

```python
from agent_core.memory.adapters.inmemory import InMemoryMemoryStore
from agent_core.memory.base import MemoryRecord


async def test_remember_then_recall_same_session():
    store = InMemoryMemoryStore()
    await store.remember(session_id="s1", text="User loves Go")
    await store.remember(session_id="s1", text="Prefers terse answers")
    recs = await store.recall(session_id="s1", query="language preference", limit=10)
    assert len(recs) == 2
    assert {r.text for r in recs} == {"User loves Go", "Prefers terse answers"}


async def test_recall_is_session_scoped():
    store = InMemoryMemoryStore()
    await store.remember(session_id="s1", text="secret-1")
    await store.remember(session_id="s2", text="secret-2")
    recs = await store.recall(session_id="s1", query="any", limit=10)
    assert [r.text for r in recs] == ["secret-1"]


async def test_recall_respects_limit():
    store = InMemoryMemoryStore()
    for i in range(5):
        await store.remember(session_id="s1", text=f"fact {i}")
    recs = await store.recall(session_id="s1", query="any", limit=2)
    assert len(recs) == 2


async def test_forget_session_removes_records():
    store = InMemoryMemoryStore()
    await store.remember(session_id="s1", text="t")
    await store.forget(session_id="s1")
    assert await store.recall(session_id="s1", query="any", limit=10) == []


async def test_recall_ranks_by_query_overlap():
    store = InMemoryMemoryStore()
    await store.remember(session_id="s1", text="Cats are mammals")
    await store.remember(session_id="s1", text="Python is a programming language")
    recs = await store.recall(session_id="s1", query="python language", limit=1)
    assert recs[0].text == "Python is a programming language"
```

- [ ] **验证失败** → `ModuleNotFoundError`

- [ ] **实现** → `agent_core/memory/base.py`：

```python
"""MemoryStore Protocol and MemoryRecord type."""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    text: str
    session_id: str
    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class MemoryStore(Protocol):
    async def remember(self, *, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> None: ...
    async def recall(self, *, session_id: str, query: str, limit: int = 10) -> list[MemoryRecord]: ...
    async def forget(self, *, session_id: str) -> None: ...
```

`agent_core/memory/adapters/inmemory.py`：

```python
"""In-memory MemoryStore — token-overlap ranking, recency fallback."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from agent_core.memory.base import MemoryRecord

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._records: dict[str, list[MemoryRecord]] = defaultdict(list)

    async def remember(self, *, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._records[session_id].append(MemoryRecord(text=text, session_id=session_id, metadata=metadata or {}))

    async def recall(self, *, session_id: str, query: str, limit: int = 10) -> list[MemoryRecord]:
        records = self._records.get(session_id, [])
        if not records:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return list(reversed(records))[:limit]
        scored = [(len(q_tokens & _tokenize(r.text)), i, r) for i, r in enumerate(records)]
        scored.sort(key=lambda t: (-t[0], -t[1]))
        return [r for _, _, r in scored[:limit]]

    async def forget(self, *, session_id: str) -> None:
        self._records.pop(session_id, None)
```

`agent_core/memory/__init__.py`：

```python
from agent_core.memory.base import MemoryRecord, MemoryStore

__all__ = ["MemoryRecord", "MemoryStore"]
```

`agent_core/memory/adapters/__init__.py`：

```python
from agent_core.memory.adapters.inmemory import InMemoryMemoryStore

__all__ = ["InMemoryMemoryStore"]
```

- [ ] **验证通过** → 5 PASS

- [ ] **提交** → `feat(memory): add MemoryStore Protocol and InMemoryMemoryStore`

---

## 任务 6：MemoryExtension

**文件：** `agent_core/memory/extension.py`、`tests/memory/test_memory_extension.py`

两阶段持久化：`MessageEnd(user)` 入队 → `TurnEnd` 刷盘。防止同 turn 消息被 `transform_context` 回声召回。

- [ ] **编写失败测试**：

```python
import time
from types import SimpleNamespace

from agent_core.core.content import TextContent
from agent_core.core.events import MessageEnd, TurnEnd
from agent_core.core.messages import UserMessage
from agent_core.memory.adapters.inmemory import InMemoryMemoryStore
from agent_core.memory.extension import MemoryExtension


def _ctx(session_id: str = "sess-1"):
    return SimpleNamespace(session_id=session_id, agent=None, store=None)


async def test_persists_user_message_after_turn_end():
    store = InMemoryMemoryStore()
    ext = MemoryExtension(store=store, session_id="sess-1")
    user = UserMessage(content=[TextContent(text="I prefer Go")], timestamp=time.time())

    await ext.on_event(_ctx(), MessageEnd(message=user))
    assert await store.recall(session_id="sess-1", query="x", limit=10) == []

    await ext.on_event(_ctx(), TurnEnd(message=SimpleNamespace(), tool_results=[]))
    recs = await store.recall(session_id="sess-1", query="x", limit=10)
    assert len(recs) == 1
    assert recs[0].text == "I prefer Go"


async def test_does_not_persist_non_user_messages():
    store = InMemoryMemoryStore()
    ext = MemoryExtension(store=store, session_id="sess-1")
    await ext.on_event(_ctx(), MessageEnd(message=SimpleNamespace(role="assistant", content=[])))
    await ext.on_event(_ctx(), TurnEnd(message=SimpleNamespace(), tool_results=[]))
    assert await store.recall(session_id="sess-1", query="x", limit=10) == []


async def test_transform_context_injects_recall():
    store = InMemoryMemoryStore()
    await store.remember(session_id="sess-1", text="User prefers Go")
    ext = MemoryExtension(store=store, session_id="sess-1", top_k=5)

    out = await ext.transform_context([{"role": "user", "content": "what language do I like"}], signal=None)

    assert len(out) == 2
    assert out[0]["role"] == "system"
    assert "User prefers Go" in out[0]["content"]


async def test_transform_context_noop_when_no_records():
    store = InMemoryMemoryStore()
    ext = MemoryExtension(store=store, session_id="sess-1")
    msgs = [{"role": "user", "content": "hi"}]
    out = await ext.transform_context(msgs, signal=None)
    assert out == msgs
```

- [ ] **验证失败** → `ImportError`

- [ ] **实现** → `agent_core/memory/extension.py`：

```python
"""Extension that persists user messages and recalls relevant memory."""

from __future__ import annotations

import asyncio
from typing import Any

from agent_core._llm_message_utils import latest_user_index, latest_user_text
from agent_core.core.content import TextContent
from agent_core.core.events import MessageEnd, TurnEnd
from agent_core.memory.base import MemoryStore


class MemoryExtension:
    name = "memory"

    def __init__(self, *, store: MemoryStore, session_id: str | None = None, top_k: int = 5) -> None:
        self._store = store
        self._session_id = session_id
        self._top_k = top_k
        self._pending: list[str] = []

    async def on_event(self, ctx: Any, evt: Any) -> None:
        if isinstance(evt, MessageEnd):
            msg = evt.message
            if getattr(msg, "role", None) != "user":
                return
            text_parts = [c.text for c in getattr(msg, "content", []) if isinstance(c, TextContent)]
            if not text_parts:
                return
            self._pending.append("\n".join(text_parts))
        elif isinstance(evt, TurnEnd):
            session_id = self._session_id
            if not session_id:
                return
            for text in self._pending:
                await self._store.remember(session_id=session_id, text=text)
            self._pending.clear()

    async def on_before_tool_call(self, ctx: Any, tool_call: Any) -> dict[str, Any] | None: return None
    async def on_after_tool_call(self, ctx: Any, tool_call: Any, result: Any, is_error: bool) -> dict[str, Any] | None: return None

    async def transform_context(self, llm_messages: list[dict[str, Any]], signal: asyncio.Event | None) -> list[dict[str, Any]]:
        session_id = self._session_id
        if not session_id:
            return llm_messages
        query_text = latest_user_text(llm_messages) or ""
        records = await self._store.recall(session_id=session_id, query=query_text, limit=self._top_k)
        if not records:
            return llm_messages

        body_lines = ["Recalled memory for this session:"]
        for i, r in enumerate(records, 1):
            body_lines.append(f"[{i}] {r.text}")
        system_msg = {"role": "system", "content": "\n".join(body_lines)}
        insert_at = latest_user_index(llm_messages)
        return [*llm_messages[:insert_at], system_msg, *llm_messages[insert_at:]]
```

更新 `agent_core/memory/__init__.py` 追加 `MemoryExtension` 导出。

- [ ] **验证通过** → 4 PASS

- [ ] **提交** → `feat(memory): add MemoryExtension`

---

## 任务 7：AgentSession 链式组合 transform_context

**文件：** `agent_core/session/session.py`、`tests/session/test_session_transform_chain.py`

用与现有 `before_tool_call` 相同的 monkey-patch 模式，链式组合 Extension 的 `transform_context` 方法。

- [ ] **编写失败测试**：

```python
from agent_core.core.agent import Agent
from agent_core.core.state import AgentState
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.session import AgentSession
from tests.conftest import FakeProvider, fake_model


class _CaptureExt:
    name = "capture"
    def __init__(self, marker: str) -> None:
        self.marker = marker
    async def on_event(self, ctx, evt): ...
    async def on_before_tool_call(self, ctx, call): return None
    async def on_after_tool_call(self, ctx, call, result, is_error): return None
    async def transform_context(self, llm_messages, signal=None):
        return [{"role": "system", "content": f"[{self.marker}]"}, *llm_messages]


async def test_extension_transform_context_injects_before_provider():
    provider = FakeProvider()
    provider.queue_script([StreamTextDelta(text="ok"), StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1)])
    agent = Agent(provider=provider, auth_source=AuthSource.static(api_key="k"), initial_state=AgentState(system_prompt="sys", model=fake_model()))

    session = AgentSession(agent=agent, store=InMemoryStore(), session_id="s1", extensions=[_CaptureExt(marker="MEM")])
    await session.start()
    await session.prompt("hello")

    sent = provider.calls[0]["messages"]
    assert sent[0] == {"role": "system", "content": "[MEM]"}
    assert any(m.get("role") == "user" for m in sent)


async def test_multiple_extensions_compose_left_to_right():
    provider = FakeProvider()
    provider.queue_script([StreamTextDelta(text="ok"), StreamMessageEnd(stop_reason="stop", input_tokens=1, output_tokens=1)])
    agent = Agent(provider=provider, auth_source=AuthSource.static(api_key="k"), initial_state=AgentState(system_prompt="sys", model=fake_model()))

    session = AgentSession(agent=agent, store=InMemoryStore(), session_id="s1", extensions=[_CaptureExt(marker="A"), _CaptureExt(marker="B")])
    await session.start()
    await session.prompt("hi")

    sent = provider.calls[0]["messages"]
    # Extensions are applied in registration order: A wraps first, then B wraps A's output,
    # so B's injection ends up closest to the top (sent[0]) — i.e. nearest to the model.
    assert sent[0]["content"] == "[B]"
    assert sent[1]["content"] == "[A]"
```

- [ ] **验证失败** → 扩展的 transform 未被调用

- [ ] **实现** → 在 `agent_core/session/session.py` 的 `start()` 方法中，在现有 `before_tool_call` monkey-patch 块之后，追加：

```python
        # Chain Extension.transform_context
        ext_transforms = [getattr(e, "transform_context", None) for e in self._extensions]
        ext_transforms = [t for t in ext_transforms if callable(t)]
        if ext_transforms:
            existing_transform = getattr(self._agent, "_transform_context", None)

            async def _chained_transform(llm_messages, signal):
                current = llm_messages
                if existing_transform is not None:
                    current = await existing_transform(current, signal)
                for t in ext_transforms:
                    current = await t(current, signal)
                return current

            self._agent._transform_context = _chained_transform
```

- [ ] **验证通过** → 2 PASS + 全套件无回归

- [ ] **提交** → `feat(session): chain Extension.transform_context into agent loop`

---

## 任务 8：端到端冒烟测试 + 文档

**文件：** `tests/test_e2e_memory_retrieval.py`、`docs/design.md`

- [ ] **编写 e2e 测试**：

```python
from agent_core.core.agent import Agent
from agent_core.core.state import AgentState
from agent_core.memory.adapters.inmemory import InMemoryMemoryStore
from agent_core.memory.extension import MemoryExtension
from agent_core.providers.auth import AuthSource
from agent_core.providers.types import StreamMessageEnd, StreamTextDelta
from agent_core.retrieval.adapters.inmemory import InMemoryRetriever
from agent_core.retrieval.extension import AutoRetrievalExtension
from agent_core.session.inmemory_store import InMemoryStore
from agent_core.session.session import AgentSession
from tests.conftest import FakeProvider, fake_model


async def test_scene_assembled_rag_and_memory():
    retriever = InMemoryRetriever()
    retriever.add("Mars has two moons: Phobos and Deimos.", source="astronomy")

    memory_store = InMemoryMemoryStore()
    await memory_store.remember(session_id="sess-x", text="User is a planetary science researcher who studies Mars.")

    provider = FakeProvider()
    provider.queue_script([StreamTextDelta(text="Phobos and Deimos."), StreamMessageEnd(stop_reason="stop", input_tokens=10, output_tokens=4)])
    agent = Agent(provider=provider, auth_source=AuthSource.static(api_key="k"), initial_state=AgentState(system_prompt="You answer concisely.", model=fake_model()))

    session = AgentSession(
        agent=agent, store=InMemoryStore(), session_id="sess-x",
        extensions=[
            AutoRetrievalExtension(retriever=retriever, top_k=3),
            MemoryExtension(store=memory_store, session_id="sess-x", top_k=3),
        ],
    )
    await session.start()
    await session.prompt("How many moons does Mars have?")

    sent = provider.calls[0]["messages"]
    system_contents = [m["content"] for m in sent if m["role"] == "system"]
    assert any("Phobos and Deimos" in s for s in system_contents)
    assert any("planetary science researcher" in s for s in system_contents)

    recs = await memory_store.recall(session_id="sess-x", query="any", limit=10)
    assert any("How many moons does Mars have?" in r.text for r in recs)
```

- [ ] **验证通过** → `pytest tests/test_e2e_memory_retrieval.py -v` + 全套件无回归

- [ ] **追加 §10 到 `docs/design.md`**：

```markdown
## 10. Memory & Retrieval

两个可选子系统，基于现有 Extension 和 Tool Protocol。`agent_core/core/` 零改动。

### 10.1 Protocols

- `Retriever`（`retrieval/base.py`）：无状态 query→chunks 接口
- `MemoryStore`（`memory/base.py`）：session 范围的读写接口（remember / recall / forget）

两者有意分开 —— 合并会迫使 mem0（事实提取）和 Pinecone（向量搜索）等后端采用别扭的 API 形状。

### 10.2 运行时桥接

| 桥接 | 模块 | 机制 |
|---|---|---|
| `RetrieverTool` | `retrieval/tool.py` | Tool Protocol — 智能体 RAG，模型按需调用 |
| `AutoRetrievalExtension` | `retrieval/extension.py` | Extension + `transform_context` — 经典 RAG，每 turn 自动注入 |
| `MemoryExtension` | `memory/extension.py` | Extension + `transform_context` — 持久化用户消息，召回为系统注释 |

`AgentSession.start()` 链式组合 Extension 的 `transform_context` 方法到 `AgentLoopConfig.transform_context` 槽，与 `before_tool_call` 使用相同的 monkey-patch 模式。

### 10.3 内置适配器

- `InMemoryRetriever`（关键词重叠评分）—— 测试、演示
- `InMemoryMemoryStore`（token 重叠 + 时间回退排序）—— 测试、单进程状态

真实后端（mem0、Pinecone、PGVector、Chroma）在后续工作中加入，由 `pyproject.toml` extras 控制。

### 10.4 设计提示

- `MemoryExtension` 当前**原样持久化用户消息**。生产环境建议外接带事实抽取的后端（如 mem0），否则连续追问会把上一轮提问本身当作"记忆"召回。
- Extension 注册顺序决定 `transform_context` 包裹顺序：**后注册的更靠近模型**。
```

- [ ] **提交** → `test: e2e smoke + docs: §10 memory & retrieval`

---

## 验证清单

```bash
pytest -v
pytest tests/memory/ tests/retrieval/ tests/session/test_session_transform_chain.py tests/test_e2e_memory_retrieval.py -v
```

所有测试通过。无计划文件结构之外的新文件。
